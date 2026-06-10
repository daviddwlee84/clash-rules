# docs/ — 项目知识库

本项目相关的背景知识与维护笔记，按主题分类。改动规则本身不需要读这些；
排查"为什么客户端没更新 / URL 404 / 规则不生效"时再来翻。

| 文档 | 内容 |
|---|---|
| [jsdelivr.md](jsdelivr.md) | jsDelivr CDN：URL 结构、缓存策略、purge API 的真实限制、大陆可达性与备用镜像 |
| [release-pipeline.md](release-pipeline.md) | 从 `git push` 到客户端生效的完整链路：CI、release 分支模式、各级缓存与强制刷新 |
| [rule-syntax.md](rule-syntax.md) | classical 规则语法、rule-provider 的 behavior/format 组合、各客户端兼容性 |
| [ai-endpoints.md](ai-endpoints.md) | `rules/ai.list` 的维护笔记：各 AI 厂商的域名/端点、如何发现新域名 |
| [tooling.md](tooling.md) | uv（PEP 723 单文件脚本）与 just 的用法约定 |
