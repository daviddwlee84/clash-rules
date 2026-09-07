# 版本發布與回滾

build 對自有規則、mirror、lock 與授權計算逐檔 SHA-256，再由 canonical hash map
得到 manifest.json 的 version。沒有 timestamp，所以重建不會產生假更新。

CI 對 PR 與 main 執行 unit tests、離線 build、publication preview 與 Mihomo 1.19.27
localhost 路由 fixture。所需的 host core 與 Linux yq 下載皆由 tooling.lock.json 鎖定並驗 hash。
通過後，僅 main 的 publish job 具有 contents:write。

scripts/publish.py 預設只是 preview。CI --publish 使用新的暫存 Git index 建立 dist tree，
新 commit 的 parent 是目前 release 分支；以 atomic、非 force push 更新 release 與
rules-<完整 version> tag。既有 tag 的 tree 必須完全相同，不可覆寫；並行更新不符合 fast-forward
時失敗。來源 commit 寫入 commit message。沒有固定週期重建，也沒有自動提升上游資料。

| 引用 | 語意 |
|---|---|
| main | 原始碼、policy、鏡像與文件 |
| release | 最新通過 CI 的浮動 artifact，仍可能受 CDN cache 影響 |
| rules-<SHA-256> | 不變的 artifact tree，適合記錄部署版本與重現 |
| Pi candidate SHA-256 | 私密裝置設定的完整 bytes；另外記錄 public rules version 與基底 hash |

一般訂閱可把 URL 中的 @release 改成具體 tag；不要把浮動 branch 稱為「版本鎖定」。
Pi 將 provider 內嵌在 private candidate，不依賴開機時下載與 CDN 可達性。

回滾 Pi 時使用保留的舊 private profile，重新 proxy-test／proxy-enable 並確認；不更改
既有 artifact tag、不 force-push 舊歷史。核心 fixture 通過不代表 profile 已經部署，也不代表
Shadowrocket 實機已驗收。[CDN 背景](jsdelivr.md)仍可參考，但實際可達性需測量。
