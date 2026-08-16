#!/usr/bin/env python3
"""Download Mihomo .list release assets and convert them to Loon rules."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_REPOSITORY = "DustinWin/ruleset_geodata"
DEFAULT_TAG = "mihomo-ruleset"
USER_AGENT = "mihomo-to-loon-ruleset-sync/1.0"

LOON_TYPES = {
    "DOMAIN",
    "DOMAIN-SUFFIX",
    "DOMAIN-KEYWORD",
    "USER-AGENT",
    "URL-REGEX",
    "IP-CIDR",
    "IP-CIDR6",
    "GEOIP",
    "IP-ASN",
    "SRC-PORT",
    "DEST-PORT",
    "PROTOCOL",
}
TYPE_ALIASES = {
    "DST-PORT": "DEST-PORT",
    "NETWORK": "PROTOCOL",
}
UNSUPPORTED_TYPES = {
    "PROCESS-NAME",
    "PROCESS-PATH",
    "RULE-SET",
    "SCRIPT",
    "SUB-RULE",
}
DOMAIN_RE = re.compile(r"^(?=.{1,253}\.?$)[A-Za-z0-9_\-\u0080-\uffff.*]+(?:\.[A-Za-z0-9_\-\u0080-\uffff.*]+)*\.?$")
CLASSICAL_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")


class ConversionError(ValueError):
    """Raised when an upstream line cannot be converted safely."""


@dataclass(frozen=True)
class ConvertedFile:
    name: str
    rules: list[str]
    skipped: Counter[str]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _normalize_network(value: str) -> tuple[str, str]:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ConversionError(f"invalid CIDR {value!r}") from exc
    rule_type = "IP-CIDR6" if network.version == 6 else "IP-CIDR"
    return rule_type, str(network)


def convert_line(raw_line: str) -> tuple[str | None, str | None]:
    """Convert one Mihomo rule. Returns (rule, skipped_reason)."""
    line = raw_line.lstrip("\ufeff").strip()
    if not line or line.startswith(("#", "//")):
        return None, None

    if line == "payload:":
        return None, None
    if line.startswith("- "):
        line = _unquote(line[2:])

    if line in {"*", "+.*", ".*"}:
        return None, "MATCH-ALL"

    if "," in line:
        fields = [field.strip() for field in line.split(",")]
        rule_type = fields[0].upper()
        if rule_type in UNSUPPORTED_TYPES:
            return None, rule_type
        rule_type = TYPE_ALIASES.get(rule_type, rule_type)
        if rule_type in LOON_TYPES:
            if len(fields) < 2 or not fields[1]:
                raise ConversionError(f"missing value in {line!r}")
            value = _unquote(fields[1])
            if rule_type in {"IP-CIDR", "IP-CIDR6"}:
                return ",".join(_normalize_network(value)), None
            if rule_type == "PROTOCOL":
                value = value.upper()
            return f"{rule_type},{value}", None
        if CLASSICAL_TYPE_RE.fullmatch(rule_type):
            raise ConversionError(f"unsupported rule type {rule_type!r}")

    candidate = _unquote(line)
    try:
        return ",".join(_normalize_network(candidate)), None
    except ConversionError:
        pass

    prefix = "DOMAIN"
    if candidate.startswith(("+.", "*.")):
        prefix = "DOMAIN-SUFFIX"
        candidate = candidate[2:]
    elif candidate.startswith("."):
        prefix = "DOMAIN-SUFFIX"
        candidate = candidate[1:]

    if "*" in candidate:
        return None, "DOMAIN-WILDCARD"
    if any(character.isspace() for character in candidate):
        return None, "INVALID-DOMAIN"
    if not candidate or not DOMAIN_RE.fullmatch(candidate):
        raise ConversionError(f"unrecognized rule {line!r}")
    return f"{prefix},{candidate.rstrip('.')}", None


def convert_text(name: str, text: str) -> ConvertedFile:
    rules: list[str] = []
    skipped: Counter[str] = Counter()
    seen: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        try:
            rule, reason = convert_line(raw_line)
        except ConversionError as exc:
            raise ConversionError(f"{name}:{line_number}: {exc}") from exc
        if reason:
            skipped[reason] += 1
        if rule and rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return ConvertedFile(name=name, rules=rules, skipped=skipped)


def render_file(converted: ConvertedFile, source_url: str) -> str:
    lines = [
        "# Loon rule set converted from Mihomo format.",
        f"# Source: {source_url}",
    ]
    if converted.skipped:
        summary = ", ".join(
            f"{rule_type}={count}" for rule_type, count in sorted(converted.skipped.items())
        )
        lines.append(f"# Omitted because Loon has no safe equivalent: {summary}")
    lines.extend(converted.rules)
    return "\n".join(lines) + "\n"


def _request_json(url: str, token: str | None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(f"GitHub API request failed: {url}: {exc}") from exc


def _download_text(url: str, token: str | None) -> str:
    headers = {"Accept": "application/octet-stream", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode("utf-8-sig")
    except (UnicodeDecodeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(f"asset download failed: {url}: {exc}") from exc


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _convert_assets(
    assets: Iterable[tuple[str, str, str | None]], output: Path, jobs: int
) -> list[ConvertedFile]:
    token = os.environ.get("GITHUB_TOKEN")

    def convert_asset(asset: tuple[str, str, str | None]) -> tuple[ConvertedFile, str]:
        name, source_url, local_path = asset
        text = Path(local_path).read_text(encoding="utf-8-sig") if local_path else _download_text(source_url, token)
        return convert_text(name, text), source_url

    asset_list = sorted(assets, key=lambda item: item[0])
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        converted_assets = list(executor.map(convert_asset, asset_list))

    results: list[ConvertedFile] = []
    expected_names: set[str] = set()
    for converted, source_url in converted_assets:
        expected_names.add(converted.name)
        _atomic_write(output / converted.name, render_file(converted, source_url))
        results.append(converted)

    for stale_path in output.glob("*.list"):
        if stale_path.name not in expected_names:
            stale_path.unlink()
    return results


def sync_release(repository: str, tag: str, output: Path, jobs: int) -> list[ConvertedFile]:
    token = os.environ.get("GITHUB_TOKEN")
    api_url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
    release = _request_json(api_url, token)
    assets = [
        (asset["name"], asset["browser_download_url"], None)
        for asset in release.get("assets", [])
        if asset.get("name", "").endswith(".list")
    ]
    if not assets:
        raise RuntimeError(f"release {repository}@{tag} contains no .list assets")
    return _convert_assets(assets, output, jobs)


def sync_directory(source: Path, output: Path, jobs: int) -> list[ConvertedFile]:
    assets = [
        (path.name, path.as_uri(), str(path))
        for path in source.glob("*.list")
        if path.is_file()
    ]
    if not assets:
        raise RuntimeError(f"source directory contains no .list files: {source}")
    return _convert_assets(assets, output, jobs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--output", type=Path, default=Path.cwd())
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=6)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.source_dir:
        converted = sync_directory(args.source_dir.resolve(), output, args.jobs)
    else:
        converted = sync_release(args.repository, args.tag, output, args.jobs)

    total_rules = sum(len(item.rules) for item in converted)
    skipped = sum((item.skipped for item in converted), Counter())
    skipped_summary = ", ".join(f"{key}={value}" for key, value in sorted(skipped.items())) or "none"
    print(f"Converted {len(converted)} files with {total_rules} unique rules; skipped: {skipped_summary}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConversionError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
