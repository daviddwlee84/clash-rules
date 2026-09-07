# 維護工具

Python 3.11+ 的標準函式庫負責建置、鏡像驗證、候選與 host core fixture；沒有 pip／uv
建置依賴。私密 YAML 解析使用 Mike Farah yq v4；CI 將 Linux binary 的 version／SHA-256
鎖在 tooling.lock.json。just 只是轉送引數的薄封裝。

- just check：離線驗證，不寫 dist。
- just build：產生內容定址 artifact；拒絕 dist 中不受管理的檔案。
- just test：unit tests；YAML 重複 key、私密權限、政策保留與鏡像竄改等。
- just native-check --download：首次下載鎖定 core；後續省略該旗標，使用驗 hash 的 cache。
- just sync-upstreams：明確 fetch → review → promote；不與日常 build 混合。
- just compose-profile / propose-rule：新私密檔案 exclusive 寫入；不自動套用。
- just publish-preview：預覽 release/tag；不提交或連線發布。

沒有 broad clean 指令。保留 private baseline、候選與 rollback 資料，避免維護時誤刪。
