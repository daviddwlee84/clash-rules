# AI 服务端点维护笔记（rules/ai.list）

为什么单独一个类别：主流 AI 服务按**出口 IP 区域**封锁（HK 等
"unsupported region" 节点会 403 甚至封号），所以它们不能混在通用 PROXY
组里，要钉到专门的 `AI` 策略组（美/日/新节点）。

## 各厂商域名备忘

| 厂商 | 域名 | 备注 |
|---|---|---|
| OpenAI | `openai.com`, `chatgpt.com`, `sora.com` | `chatgpt.com` 是 2024 起的 App 主域 |
| | `oaistatic.com`, `oaiusercontent.com` | 静态资源 / 用户上传 CDN，漏了会白屏 |
| Anthropic | `anthropic.com`, `claude.com`, `claude.ai` | `claude.ai` 为旧 App 域，仍在用 |
| Cursor | `cursor.com`, `cursor.sh` | `.sh` 是旧域 + `api2`/`repo42` 等 API 端点 |
| | `cursorapi.com`, `cursor-cdn.com` | API CDN；漏了会出现"能登录但补全失败" |
| GitHub Copilot | `githubcopilot.com` | 补全流量走它，**不是** `github.com` |
| | `copilot.microsoft.com` | 微软侧 Copilot 入口 |
| Google | `gemini.google.com`, `aistudio.google.com`, `notebooklm.google.com` | 精确 DOMAIN，不能 suffix 整个 google.com |
| | `generativelanguage.googleapis.com`, `aiplatform.googleapis.com` | Gemini API / Vertex AI |
| | `ai.google.dev`, `deepmind.com`, `deepmind.google` | 文档与 DeepMind |
| xAI | `x.ai`, `grok.com` | |
| Perplexity | `perplexity.ai`, `pplx.ai` | `pplx.ai` 是 API 短域 |
| Mistral | `mistral.ai` | |
| Meta | `meta.ai` | |
| Poe | `poe.com` | Quora 的多模型前端 |

**不收录**：DeepSeek、Qwen（通义）、Kimi（Moonshot）等大陆服务——它们
应直连，属于 `direct.list` 的范畴（或者根本不用写，GEOIP,CN 兜底）。

## 如何发现新域名 / 排查漏网域名

某 AI 产品"网页打得开但功能异常"基本都是漏了辅助域名（CDN、API、遥测）。
排查手段：

1. **mihomo 连接面板**：Dashboard（metacubexd/yacd）的 Connections 页按
   时间排序，操作一下出问题的功能，看哪些新连接走错了策略组。
2. **浏览器 DevTools → Network**：看失败请求的域名。
3. **社区规则对照**：[blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script/tree/master/rule/Clash)
   有 `OpenAI`、`Claude`、`Gemini`、`Copilot` 等现成分类，可对照查漏
   （不直接整包引用是为了保持本仓库"只收个人确实在用的"原则）。
4. **客户端日志**：mihomo `log-level: info` 下能看到每条连接命中的规则。

加新厂商时：在 `rules/ai.list` 里开一个新的 `# --- Vendor ---` 分节，
按字母序插入，冷门域名补一行来源注释。提交后跑 `just build` 校验。
