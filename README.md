# clash-rules

個人分流政策、鎖定的上游資料與診斷知識庫。公開規則由 Git 管理；節點、訂閱、API
credential、裝置設定與瀏覽紀錄留在 ignored private/。目前以
[RPi-ImmortalWrt](https://github.com/daviddwlee84/RPi-ImmortalWrt) 的 Nikki/Mihomo 作為第一個 dogfood 用戶端。

本 repo 保留自訂政策與 review 流程；通用域名／IP 分類鏡像自
[MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)，不另造大型分類資料庫。
鏡像與個人政策分開更新，建置不需連線。

| 路徑 | 責任 |
|---|---|
| rules/*.list | 個人分類；TYPE,payload，不含出口政策 |
| vendor/metacubex/、upstreams.lock.json | 指定 commit 的資料／授權／來源說明與逐檔 SHA-256 |
| scripts/build.py、dist/ | 離線驗證、去重、重疊報告、跨用戶端 artifact 與內容版本 |
| scripts/compose_profile.py | 已驗證私密基底加上 AI 固定 leaf node；保留一般群組與順序 |
| scripts/propose_rule.py | 診斷報告轉精確 domain 候選；人工 review 後才改政策 |
| scripts/native_check.py、tests/ | 鎖定 Mihomo 1.19.27 的語法與 localhost 路由 fixture |
| docs/ | 術語、FAQ、官方設定參考與版本／私密資料流程 |

```sh
just check                       # 完全離線；不寫 dist/
just test
just build
just native-check --download     # 首次明確下載並驗 hash；之後省略 --download
just publish-preview            # 不建立 commit、不 push
```

Python 3.11+ 為基礎工具；私密 YAML 組合另需 Mike Farah yq v4。完整流程見
[架構與操作](docs/architecture.md)、[診斷知識](docs/diagnosis.md) 與
[版本發布](docs/release-pipeline.md)。CI 只有 main 通過驗證後才更新 release 分支，保留歷史，
並建立不可覆寫的 rules-<完整內容 SHA-256> tag；此次工作本身不會觸發遠端發布。

## 分類

ai、apple、reject、direct、proxy、media-global、media-hkmt 為自訂分類。
政策由用戶端 RULE-SET 的第三欄決定；跨分類重複可能是有意義的，不會自動刪除。
自訂清單最初來自 DockerCompose-V2Ray 的 legacy CFW example（歷史來源可查 Git），
不能把舊域名的存在當成今日服務擁有權或封鎖證據。

既有訂閱範例 [Clash](examples/clash.yaml)／[Shadowrocket](examples/shadowrocket.conf)
仍示範浮動 release URL。受管理 Pi 使用離線內嵌 profile 與既有 transaction；其他 clients
若要可回滾版本，將 URL 的 @release 換成具體 rules-<SHA-256> tag。CDN 可達性與快取均需實測。

<!-- project-knowledge-harness:readme-roadmap -->
後續工作統一列在 [TODO.md](TODO.md)，分析留在 [backlog/](backlog/)，排錯經驗留在
[pitfalls/](pitfalls/)。相關服務端專案為
[DockerCompose-V2Ray](https://github.com/daviddwlee84/DockerCompose-V2Ray)。
<!-- project-knowledge-harness:readme-roadmap (end) -->

本 repo 自有內容沿用 [MIT](LICENSE)；第三方鏡像保留上游授權與來源，見
[THIRD_PARTY.md](THIRD_PARTY.md)。不要將 vendor/ 一概視為 MIT。
