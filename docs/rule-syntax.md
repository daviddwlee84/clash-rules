# 规则语法与客户端兼容性

## 为什么源文件是 "classical 减策略" 格式

`rules/*.list` 每行是 `TYPE,value[,modifier]`，**不带策略**（policy）。
策略来自客户端 base config 里引用它的那一行：

```yaml
# 客户端侧决定 ai 这组规则走哪个策略组
- RULE-SET,ai,AI
```

这样同一份 `.list` 可以被不同客户端、不同策略名复用（Clash 的
`behavior: classical, format: text` 与 Shadowrocket 的 `RULE-SET` 吃的是
完全相同的行），构建只是"校验 + 扇出"，不需要翻译。

## rule-provider 的 behavior / format 组合（mihomo）

| behavior | 行内容 | 适用 |
|---|---|---|
| `domain` | 纯域名（`+.google.com`） | 只有域名时最快，可转 `.mrs` |
| `ipcidr` | 纯 CIDR | 只有 IP 段时 |
| `classical` | 完整 `TYPE,value` 行 | 混合类型（本项目，因为有 IP-CIDR/DOMAIN-KEYWORD 等混在一起） |

format 有 `text` / `yaml` / `mrs`（mihomo 二进制格式，仅 domain/ipcidr）。
本项目两种都产出：`dist/clash/<cat>.list`（text）和 `<cat>.yaml`。

## 规则集内允许 / 禁止的类型

`scripts/build.py` 的校验白名单（`ALLOWED_TYPES`）：

- 域名类：`DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`DOMAIN-WILDCARD`、`DOMAIN-REGEX`
- IP 类：`IP-CIDR`、`IP-CIDR6`、`IP-SUFFIX`、`IP-ASN`、`GEOIP`
- 其他：`DST-PORT`、`SRC-PORT`、`SRC-IP-CIDR`、`PROCESS-NAME`、`PROCESS-PATH`、
  `USER-AGENT`、`URL-REGEX`、逻辑组合 `AND`/`OR`/`NOT`

**禁止**进规则集（属于 base config 的顶层路由构造）：`MATCH`、`RULE-SET`、
`SUB-RULE`、`FINAL`。所以 `GEOIP,CN,DIRECT` 和 `MATCH,PROXY` 这类兜底永远
写在客户端配置里，不在本仓库的 `.list` 里。

## 常用类型速查

| 写法 | 匹配 |
|---|---|
| `DOMAIN,gemini.google.com` | 仅该精确域名 |
| `DOMAIN-SUFFIX,openai.com` | `openai.com` 及全部子域 |
| `DOMAIN-KEYWORD,openai` | 域名任意位置含 `openai`（宽，慎用） |
| `IP-CIDR,91.108.4.0/22,no-resolve` | 目标 IP 段；`no-resolve` 防止为纯域名流量触发 DNS 解析 |
| `USER-AGENT,MicroMessenger*` | UA 通配（仅 HTTP，Shadowrocket 常用） |

经验法则：

- 能用 `DOMAIN-SUFFIX` 就不用 `DOMAIN-KEYWORD`；keyword 容易误伤
  （`DOMAIN-KEYWORD,openai` 也会命中 `notopenai.example.com`）。
- 大厂共用主域时用精确 `DOMAIN`，避免把整个主域拖进策略组——例如 Gemini
  用 `DOMAIN,gemini.google.com`，绝不能 `DOMAIN-SUFFIX,google.com`。
- IP 规则一律加 `no-resolve`，除非确实想让它对域名流量也做解析匹配。

## 客户端差异备忘

- **mihomo（Clash Meta 内核）**：上表全支持；老版原版 Clash 不认
  `DOMAIN-REGEX`/`DOMAIN-WILDCARD`/`IP-ASN`，加这些类型前想想还有没有
  设备跑老内核。
- **Shadowrocket**：`RULE-SET,<url>,<policy>` 直接吃 classical text；
  `USER-AGENT`/`URL-REGEX` 仅它和部分 iOS 客户端支持。
- 匹配顺序 = 配置中行序，**first match wins**。示例配置的顺序约定：
  `reject → ai → apple → media → direct → proxy → GEOIP,CN → MATCH`，
  特异性高的在前。
