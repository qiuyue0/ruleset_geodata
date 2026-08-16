# Mihomo ruleset → Loon ruleset

本分支把 [DustinWin/ruleset_geodata](https://github.com/DustinWin/ruleset_geodata) 的
[`mihomo-ruleset` Release](https://github.com/DustinWin/ruleset_geodata/releases/tag/mihomo-ruleset)
中所有 `.list` 资产转换成 Loon 可直接订阅的远程规则；不下载、不保存 `.mrs`。

> 上游的 `mihomo-ruleset` 实际是持续更新的 Release tag，不是普通 Git 分支；规则文件位于 Release Assets。

## 转换规则

| Mihomo | Loon 输出 |
| --- | --- |
| `+.example.com` / `*.example.com` | `DOMAIN-SUFFIX,example.com` |
| `example.com` | `DOMAIN,example.com` |
| IPv4 CIDR | `IP-CIDR,192.0.2.0/24` |
| IPv6 CIDR | `IP-CIDR6,2001:db8::/32` |
| 已带类型的 classical 规则 | 保留 Loon 支持的类型并移除策略、`no-resolve` 等 Mihomo 参数 |
| `PROCESS-NAME`、中间域名通配符等 Loon 无安全等价能力的规则 | 省略，并在对应文件头部写明数量 |

输出文件不写死策略。请在 Loon 的订阅规则中指定策略，例如：

```ini
https://raw.githubusercontent.com/<你的用户名>/ruleset_geodata/loon-ruleset/ads.list,REJECT
https://raw.githubusercontent.com/<你的用户名>/ruleset_geodata/loon-ruleset/proxy.list,PROXY
```

## 本地同步

只需要 Python 3.10+，没有第三方依赖：

```bash
python scripts/sync_rules.py --output .
python -m unittest discover -s tests -t . -v
```

脚本通过 GitHub Release API 发现全部 `.list`，并发下载、严格转换、去重和清理上游已删除的旧 `.list`。
若上游新增未知规则类型，转换会直接失败，避免静默产出错误规则。

## 云端自动同步

`.github/workflows/sync-upstream.yml` 每天北京时间 03:45 运行，也支持手动触发。它会：

1. 读取上游 `mihomo-ruleset` Release；
2. 只下载 `.list`；
3. 转换并运行测试；
4. 仅在规则发生变化时提交到 `loon-ruleset`。

GitHub 的定时工作流只从默认分支触发。完成 fork 和推送后，请把 fork 的默认分支设为
`loon-ruleset`；本项目在远端初始化阶段会尝试自动完成这一步。

## 来源与许可

转换后的规则数据来源和许可遵循上游项目。适配器代码用于格式转换与同步；使用前请同时阅读
[上游 LICENSE](https://github.com/DustinWin/ruleset_geodata/blob/master/LICENSE)。
