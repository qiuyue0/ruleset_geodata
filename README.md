# Loon Ruleset

将 [DustinWin/ruleset_geodata](https://github.com/DustinWin/ruleset_geodata) 的
`mihomo-ruleset` 规则集转换为 Loon 可直接订阅的远程规则，并每日自动同步上游更新。

## 使用方法

将本仓库 `loon-ruleset` 分支中的 `.list` 文件作为远程订阅添加到 Loon，并在订阅中指定策略：

```ini
https://raw.githubusercontent.com/qiuyue0/ruleset_geodata/loon-ruleset/ads.list,REJECT
https://raw.githubusercontent.com/qiuyue0/ruleset_geodata/loon-ruleset/proxy.list,PROXY
```

规则文件不写死策略，请按需组合。常用文件说明：

| 文件                                                    | 用途                   |
| ------------------------------------------------------- | ---------------------- |
| `proxy.list`                                          | 代理规则（GFW 列表等） |
| `ads.list`                                            | 广告拦截               |
| `cn.list` / `cnip.list`                             | 国内直连域名 / IP      |
| `media.list` 及 `netflix.list`、`youtube.list` 等 | 流媒体分流             |
| `private.list` / `privateip.list`                   | 私有地址直连           |

完整文件列表见 `loon-ruleset` 分支。

## 转换规则

| Mihomo                                                       | Loon 输出                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------- |
| `+.example.com` / `*.example.com`                        | `DOMAIN-SUFFIX,example.com`                                 |
| `example.com`                                              | `DOMAIN,example.com`                                        |
| IPv4 CIDR                                                    | `IP-CIDR,192.0.2.0/24`                                      |
| IPv6 CIDR                                                    | `IP-CIDR6,2001:db8::/32`                                    |
| 已带类型的 classical 规则                                    | 保留 Loon 支持的类型并移除策略、`no-resolve` 等 Mihomo 参数 |
| `PROCESS-NAME`、中间域名通配符等 Loon 无安全等价能力的规则 | 省略，并在对应文件头部注明数量                                |

## 本地同步

```bash
python scripts/sync_rules.py --output .
python -m unittest discover -s tests -t . -v
```

脚本通过 GitHub Release API 发现全部 `.list`，并发下载并转换到指定目录。

## 自动化

`.github/workflows/sync-upstream.yml` 每天 03:45（北京时间）运行，也支持在 Actions 页面手动触发。
流程：读取上游 Release → 只下载 `.list` → 转换并测试 → 仅在规则变化时提交到 `loon-ruleset` 分支。

> 定时工作流仅从默认分支触发，请确保 fork 的默认分支为 `loon-ruleset`。

## 许可

转换后的规则数据来源与许可遵循上游项目；适配器代码用于格式转换与同步。
使用前请同时阅读 [上游 LICENSE](https://github.com/DustinWin/ruleset_geodata/blob/master/LICENSE) 与本仓库 [LICENSE](LICENSE)。
