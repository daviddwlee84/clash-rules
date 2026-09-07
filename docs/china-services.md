# 境內服務分類、出口與 DNS

建議用獨立 `ChinaServices` 群組，預設 `DIRECT`。分類描述「這是什麼服務」，群組決定
「這台設備目前從哪裡連線」；同一份網域資料可以跨設備共用，出口選擇留在各自的私密 profile。

| 使用情境 | ChinaServices 的選擇 |
|---|---|
| 中國大陸網路，一般境內服務 | DIRECT |
| 境外網路，服務可正常直接使用 | DIRECT |
| 境外網路，服務要求中國大陸出口 | 經驗收的中國大陸節點／家中出口 |

既有日本、香港或其他海外 proxy 不等於中國大陸出口；不能僅因它叫 PROXY 就當成回國線路。
HK/台灣媒體、AI、Apple 等有特殊需求的既有政策保留較高優先權，不能一律被中國服務分類蓋過。

## 使用既有上游資料

不建立另一份手抄的大型中國網域表。已鎖定的
`vendor/metacubex/geo/geosite/cn.list` 可直接作為 `behavior: domain`、`format: text`
的 provider；已包含小紅書、xhscdn、xhslink 等網域。它隨既有 immutable artifact 發布，
來源 commit 與檔案 SHA-256 在 `upstreams.lock.json`，授權見 [THIRD_PARTY.md](../THIRD_PARTY.md)。

[合併片段](../examples/china-services.yaml) 展示 provider、群組與 DNS 的關係。
這個分類目前重用上游 provider，**不是新增一份 rules/china-services.list**；自訂清單仍用於
精確例外。上游 geosite/cn 描述分類，不保證服務所有 CDN IP 都在中國，也不保證沒有共享 CDN。
不要因看到 CNAME 就把整個 `dnse0.com`、`qcloud.com` 或其他共享平台加入某個服務的專用規則。

## DIRECT 還可能慢

`DIRECT` 只說明這一層 core 沒有使用 proxy 節點，不代表 DNS 查詢也直連、CDN 在本地，
或 Wi-Fi、TPROXY、上游網路沒有延遲。`fake-ip` 是映射機制，本身不是代理出口選擇。

若一般 DNS 是 Google/Cloudflare DoH，且以 `#PROXY` 從海外查詢，境內服務可能得到不同
CDN 答案。應對照：相同 hostname／SNI、相同協定、同一台發起端，分別固定不同 DNS 答案，
觀察 TCP、TLS、TTFB 與 HTTP status。302/403 不能直接等同 App 登入、圖片或影片可用。

片段使用 `nameserver-policy`，讓中國服務查詢走境內 DoH；`#ChinaServices` 使 DNS 也遵循
這個分類的出口選擇。其餘網站保留原 DNS。已有 `direct-nameserver` 的 profile 需再檢查
`direct-nameserver-follow-policy`，以及既有 DNS 例外／重疊集合。不要假設 YAML mapping
書寫順序就能解決所有重疊。節點 bootstrap 仍需獨立的 `proxy-server-nameserver`，避免循環解析。
[Mihomo 官方 DNS 設定](https://wiki.metacubex.one/config/dns/)。

DNS 與 routing 的覆蓋範圍必須一起 review，例如同一個媒體域名已有 HKMedia 政策時，
不能無條件讓它改用 ChinaServices 的 DNS。若只改 routing、仍保留海外 DNS，可能依然慢；
若 Pi 本機直連快、client 固定同一 IP 仍慢，還需要檢查 client → Pi 的路徑。

## 受管 Pi 的部署邊界

目前 `just proxy-rules` 只接受已建立的精確 DOMAIN → PROXY 更新，不能拿它更改 DNS、
新增 selector 或引入整份中國網域 provider。這份片段是下一次配置遷移的 review 輸入，
不是宣稱已套用到 Pi。需要以裝置 repo 的 transaction 驗證 profile/provider/DNS hashes、
原生語法、既有連線與 fake-IP 映射、來源持久化，以及失敗後的 matching recovery。

啟用前至少比較小紅書 App 實際 API／圖片／影片域名、一般中國服務、Google、SEF 和既有媒體
例外。公開 repo 保存分類與合併策略，私密節點、設備來源 IP、查詢／瀏覽報告不進 Git。
