# Native fixture 回報 observed=[]，debug logging 時卻通過

症狀：`native routing case failed: api.anthropic.com observed=[]`。
單次成功後重跑仍可能失敗；單純等待 listener 或在失敗後 sleep 無法可靠修復。

測試使用 HTTP CONNECT，而 Mihomo 可先確認 inbound tunnel，稍後才進行 outbound handshake。
關閉 client 太早可能尚未到達 localhost sink。API listener 又早於 rule-provider 初始化；
`/providers/rules` 初期可回 `providers: null`。debug logging 改變時序，不能當成修復。

現在 fixture 使用 HTTP forward request，讓 outbound dial 完成後才讀取接收紀錄，並等到
所有測試 inline provider 的 ruleCount 大於 0。所有出口都是 localhost SOCKS5 sink，
只記錄 domain／政策並拒絕轉發，不會連線到測試 domain。這驗證 domain rule 選擇，不是 TLS。

另外修正 temporary directory 的清理順序：先停止 child core，再清理其 home，避免初始化
尚在寫 cache 時得到 `OSError: [Errno 66] Directory not empty`。修正後連續三次各 9 個案例通過。


## Linux CI 後續確認

只等 ruleCount 仍不足：Linux CI 曾再次出現同一錯誤，而增加 logging 後重跑又通過。
[Mihomo v1.19.27 ApplyConfig](https://github.com/MetaCubeX/mihomo/blob/v1.19.27/hub/executor/executor.go)
在 loadProvider(ruleProviders) 之後還會做 runtime.GC，最後才呼叫 tunnel.OnRunning。
因此 provider 已可查詢，不代表 tunnel 已開始接受轉發。

現在啟動時先對 fixture-readiness.invalid 做有期限的本機轉發探針，只有 GENERAL localhost
sink 真正收到它才開始 9 個正式案例。這個 probe 不對外連線，正式案例不因失敗而重試或放寬；
失敗時會回報 public fixture 的 HTTP outcome 與 bounded core log，private profile 的 native
parser 輸出仍不公開。
