import tempfile
import unittest
from pathlib import Path

from scripts.sync_rules import ConversionError, convert_line, convert_text, sync_directory


class ConvertLineTests(unittest.TestCase):
    def test_domain_behavior_rules(self):
        self.assertEqual(convert_line("+.example.com"), ("DOMAIN-SUFFIX,example.com", None))
        self.assertEqual(convert_line("example.com"), ("DOMAIN,example.com", None))
        self.assertEqual(convert_line("*.example.com"), ("DOMAIN-SUFFIX,example.com", None))

    def test_ip_rules(self):
        self.assertEqual(convert_line("192.0.2.1/24"), ("IP-CIDR,192.0.2.0/24", None))
        self.assertEqual(convert_line("2001:db8::1/32"), ("IP-CIDR6,2001:db8::/32", None))

    def test_classical_rule_drops_policy_and_options(self):
        self.assertEqual(
            convert_line("IP-CIDR,192.0.2.0/24,DIRECT,no-resolve"),
            ("IP-CIDR,192.0.2.0/24", None),
        )
        self.assertEqual(convert_line("DST-PORT,443"), ("DEST-PORT,443", None))

    def test_unsupported_rules_are_explicit(self):
        self.assertEqual(convert_line("PROCESS-NAME,aria2"), (None, "PROCESS-NAME"))
        self.assertEqual(convert_line("*"), (None, "MATCH-ALL"))
        self.assertEqual(convert_line("ntp.*.com"), (None, "DOMAIN-WILDCARD"))
        self.assertEqual(convert_line("Mijia Cloud"), (None, "INVALID-DOMAIN"))

    def test_yaml_wrapper(self):
        self.assertEqual(convert_line("payload:"), (None, None))
        self.assertEqual(convert_line("  - '+.example.com'"), ("DOMAIN-SUFFIX,example.com", None))

    def test_unknown_classical_type_fails(self):
        with self.assertRaises(ConversionError):
            convert_line("NEW-RULE,example")


class ConvertFileTests(unittest.TestCase):
    def test_deduplicates_and_counts_skips(self):
        result = convert_text(
            "sample.list",
            "+.example.com\n+.example.com\nPROCESS-NAME,aria2\n",
        )
        self.assertEqual(result.rules, ["DOMAIN-SUFFIX,example.com"])
        self.assertEqual(result.skipped["PROCESS-NAME"], 1)

    def test_directory_sync_prunes_stale_lists(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            source = Path(source_dir)
            output = Path(output_dir)
            (source / "current.list").write_text("+.example.com\n", encoding="utf-8")
            (output / "stale.list").write_text("stale\n", encoding="utf-8")

            results = sync_directory(source, output, jobs=1)

            self.assertEqual([item.name for item in results], ["current.list"])
            self.assertFalse((output / "stale.list").exists())
            self.assertIn("DOMAIN-SUFFIX,example.com", (output / "current.list").read_text())


if __name__ == "__main__":
    unittest.main()
