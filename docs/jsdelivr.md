# jsDelivr CDN

[jsDelivr](https://www.jsdelivr.com/) 是免费的开源公共 CDN，可直接加速 npm、
GitHub、WordPress 上的静态文件。本项目用它的 **GitHub 端点**把 `release`
分支上的规则文件分发给所有客户端。

## URL 结构（gh 端点）

```text
https://cdn.jsdelivr.net/gh/<user>/<repo>@<ref>/<path>
```

`<ref>` 可以是：

| ref 类型 | 示例 | CDN 缓存时长 |
|---|---|---|
| 分支名 | `@release`、`@main` | **12 小时**，到期自动回源 GitHub 拉新 |
| semver tag | `@1.2.3` | 永久（CDN 1 年 + jsDelivr 自家 S3 永久存档，**无法更新**） |
| commit hash | `@82f5daa` | 永久，同上 |
| 版本别名 | `@1`、`@latest` | 7 天，可用 purge API 提前刷新 |

本项目所有消费 URL 都钉在 `@release` 分支：

```text
https://cdn.jsdelivr.net/gh/daviddwlee84/clash-rules@release/clash/<category>.list
https://cdn.jsdelivr.net/gh/daviddwlee84/clash-rules@release/shadowrocket/<category>.list
```

### 本仓库踩过的坑：`@main/dist/...` 404

`dist/` 在 `main` 上被 `.gitignore` 排除，CI 是把 `dist/` 的**内容**作为
`release` 分支的根目录强推发布的（见 [release-pipeline.md](release-pipeline.md)）。
所以 `@main/dist/clash/x.list` 这个路径在 git 上根本不存在，jsDelivr 返回
`Couldn't find the requested file`。正确路径没有 `dist/` 前缀且 ref 是
`@release`。

## 缓存与更新时序

对分支 ref（本项目的情况）：

1. push 到 `main` → CI 重建 `release` 分支（约 1 分钟）。
2. jsDelivr 边缘节点对每个文件各自维护 12 小时缓存——**最坏情况下推送后
   12 小时**全球节点才都拿到新内容（命中率低的文件可能更快）。
3. 客户端（mihomo/Shadowrocket）还有自己的 provider `interval`（本项目示例
   为 86400 秒），叠加在 CDN 缓存之上。

即：一条规则从提交到所有设备生效，理论上限 ≈ 12h（CDN）+ 24h（客户端
interval）。日常维护无所谓；急用时见下面的强制刷新。

## purge.jsdelivr.net（及其真实限制）

jsDelivr 提供 purge API：对着要刷的文件把域名换成 `purge.jsdelivr.net`
发请求即可：

```bash
curl "https://purge.jsdelivr.net/gh/daviddwlee84/clash-rules@release/clash/ai.list"
```

但注意官方文档明确的限制（容易被各种博客教程误导）：

- **purge 设计上只保证对 semver release / 版本别名 URL 生效**；对 `@branch`
  URL 不保证——purge 只清边缘 CDN 节点，jsDelivr 内部 origin 服务器可能仍
  短时间缓存旧版（官方 issue #18376 原话："purge works only for releases,
  not branches"，分支的兜底就是等 12 小时）。
- 有速率限制；批量对所有文件无脑 purge 不被鼓励。
- 大规模/自动化 purge 权限需要邮件向 jsDelivr 申请（d@jsdelivr.com）。
- 对 tag / commit hash URL 完全无效（S3 永久存档）。

实践结论：**急更新时优先在客户端侧强刷 provider**（绕过本地 interval，见
release-pipeline.md），CDN 的 12 小时窗口基本只能等；purge 可以试但别依赖。

## 大陆可达性（为什么选它、以及备用方案）

选 jsDelivr 而非 `raw.githubusercontent.com` 的原因：raw 域名长期被 GFW
彻底阻断，jsDelivr 的多 CDN 域名总有可用的。但 jsDelivr 自身也不是稳的：

- 2021-12 jsDelivr 大陆 CDN 节点被关、ICP 备案被注销；2022-04 起
  `cdn.jsdelivr.net` 主域遭 DNS 污染，大陆直连时通时断。
- 官方明确表示不会为大陆单独搞域名/ICP，此状态长期化。

未被污染的官方子域（同样的路径直接换域名即可）：

| 域名 | 提供方 | 备注 |
|---|---|---|
| `fastly.jsdelivr.net` | Fastly | 大陆可达性最好的一个 |
| `gcore.jsdelivr.net` | Gcore | 间歇性被干扰 |
| `testingcf.jsdelivr.net` | Cloudflare | 测试域，不保证长期 |

本项目场景的特殊性：**规则文件本来就是给代理客户端用的**——只要客户端把
`cdn.jsdelivr.net` 自身走代理（它匹配不到 direct 规则时走 MATCH,PROXY），
主域被污染也不影响订阅更新。只有"裸连第一次拉规则"的冷启动场景才需要
fastly 等备用域。如遇长期不可达，把 examples 里的 `cdn.` 批量换成
`fastly.` 即可，路径不变。
