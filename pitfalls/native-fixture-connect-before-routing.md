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
