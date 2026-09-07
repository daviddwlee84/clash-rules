# 持續政策維護與觀測

Status: deferred

目前先完成 bounded 單站觀測、review candidate、離線 public artifact 與私密 Pi candidate。
以下需要獨立設計，不因有 REST API 就假設已具備。

1. 時段 summary／收集器：明確來源、時區、採樣與斷線 gaps、連線重用／關閉事件、計數去重、
   log retention、磁碟配額及私密 export。現有 active snapshots 不能回推歷史或可靠總流量。
2. 批量 domain/IP 整理：排除 fake-IP、共享 CDN、內部 hostname 與偶發遙測，保留服務擁有權證據；
   只能產生候選，不能因「連過」就判定永遠 PROXY／DIRECT。
3. 自動 upstream PR：限定 owner/repo/commit、資料 diff 與 license diff、CI 回歸、review 後提升。
   Agent 可整理證據與正反例，不可自主部署至多設備。
4. 多設備版本 registry：public rules version、private base/profile digest、client/core 與驗收狀態，
   staged rollout／canary／rollback；TUN 和 TPROXY 分開 adapter。
5. 私密 provider／加密：SOPS/age recipients、金鑰遺失復原、撤銷／rotation、訂閱的 access control、
   TLS 與 at-rest encryption 分開。不可把隱藏 URL 稱為加密。
6. AI 出口運維：手動換 leaf、出口 IP 變動證據、服務 403/429 與帳號狀態區分；保持一般群組政策。
7. fail-closed：若需求變更需獨立網路安全與復原設計、真實硬體失效試驗；現有 Pi 仍 fail-open。

完成標準是各項都有可重現證據、保留期限／失敗狀態，以及可審查的 private/public 邊界。
