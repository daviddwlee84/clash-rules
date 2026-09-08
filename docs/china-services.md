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

## 已實作的研究工具

第一版只做只讀收集、分析與**私密候選**，沒有排程、部署、cache flush 或 selector switch。
預設量測小紅書首頁與 WeChat 官網；只有小紅書首頁是 pilot。WeChat 官網並不能代表訊息、
圖片或影片功能；收集期間另保留實際看見的 weixin.qq.com／wechat.com／weixin.com 連線。
沒有捕獲 App 連線時標示不足，不推論 App 都繞過 Pi 或都走 DIRECT。

在 Pi repo 執行（需要已設定 strict SSH、私有 CA、uv 與 yq）：

```sh
just china-research collect --output private/china-run-001 --dry-run
just china-research collect --output private/china-run-001
```

`--targets /ABSOLUTE/private/targets.json` 可覆蓋預設。輸入是 mode 0600 JSON array：

```json
[
  {"url":"https://www.xiaohongshu.com/","expected_status":[200,302],"pilot":true},
  {"url":"https://weixin.qq.com/","expected_status":[200,302],"pilot":false}
]
```

只接受 1–4 個 HTTPS:443 hostname，每個 hostname 一個 URL，不含帳密、query 或 fragment。
不跟隨 redirect、不登入、不爬站、不保存 HTTP body/cookie。要研究 CDN，請明確指定已知的
公開小檔案 URL；不要從登入流量複製 token。較高優先政策衝突的 pilot 不會自動改寫。

DNS 比較包含現行 controller DNS、AliDNS DoH 與 DNSPod DoH。境內 resolver 使用有版本的
endpoint/bootstrap 設定及正確 hostname TLS 驗證；bootstrap IP 不免除憑證驗證，端點失效
會回報 unavailable，不降級明文 DNS 或 insecure TLS。DNS parser 固定 dnspython 2.8.0，
來源 wheel 與 SHA-256 鎖定；uv 隔離環境不改變 SSH 工具的既有可信路徑要求。

HTTP 對照固定 IPv4、HTTP/1.1、User-Agent 與原 hostname/SNI，只替換連線 IP。每個 resolver
最多取兩個 IP、各五次，Pi/client 分開列出；並行上限二、單次上限八秒、整輪量測預算五分鐘。
快照／結束校驗另有有界 SSH timeout；預算到期保留 partial 結果。`--vantage pi` 可先隔離
client 路徑；少於五次（`--samples`）只作探索，不產生已具足夠量測的 DNS 候選。
client 對照會檢查 public IP 與 Pi fake-IP 的 route；若落到本機 TUN、不是經由 Pi 或無法驗證，跳過 client 主動請求，Pi 的獨立量測仍保留。前後 route 也會比對。
第一筆與重複樣本分列，沒有清 cache，因此不能把它們稱作嚴格的 cold/warm cache 實驗。

在 clash-rules repo 分析同一個私密 run：

```sh
just china-research report /ABSOLUTE/RPi-ImmortalWrt/private/china-run-001
just china-research candidate /ABSOLUTE/RPi-ImmortalWrt/private/china-run-001 \
  --resolver alidns --output /ABSOLUTE/private/china-candidate-001 --dry-run
just china-research candidate /ABSOLUTE/RPi-ImmortalWrt/private/china-run-001 \
  --resolver alidns --output /ABSOLUTE/private/china-candidate-001
```

`report.json` 與 `report.md` 保留各來源的成功率、median TTFB/total、取樣 IP、路由證據、
LAN 指標與限制。現行 DNS 的 controller elapsed 含 LAN/API 開銷，不能混同 resolver latency。
候選建議僅按完整成功的 Pi 樣本比較，單次窗口的排名不是自動切換決策。相同取樣 CDN IP 的 resolver 視為同一答案組，不以噪音差異宣稱其中一家較快；若包含 baseline，優先保留它。

重新分析同一份 run 時可加 `report --output /ABSOLUTE/private/new-report`，避免覆寫原報告。

`--resolver` 必須明確選 `alidns`、`dnspod` 或 `baseline`；baseline 保留原 DNS，作為回退參照。
新 DNS 候選需要穩定快照、完整取樣、至少五筆符合預期的 Pi 樣本。403/429、TLS 失敗、異源
redirect、重複樣本或覆蓋不足不會被當成「快且成功」。

本機 localhost native fixtures 另驗證 pilot DNS 分流與 ChinaServices 路由、媒體／SEF 例外及一般網站兜底；這與受管 Pi 的部署驗收分開。

## 候選包含什麼

快照包含原始 source、effective runtime、受管理 provider、GeoIP、開始／結束狀態及 hash。
候選只增添 `ChinaServices`（預設 DIRECT）、精確 pilot provider 與該集合的 DNS policy。
保留原 rule 順序、SEF／媒體例外、節點和 bootstrap；不搬入 runtime controller credential。
DNS 候選沿用量測的 DoH hostname，不加入未量測的備援端點；部署後的 bootstrap 解析與
實際端點 IP 仍需另行驗收，不能由固定 IP 的研究結果推定。
未知 provider、未支援的 DNS 覆寫／優先序或缺少資料依賴會拒絕候選，不猜測或偷偷下載。

`candidate.yaml` 保留擬議 Pi 路徑；隔離驗證副本才將 provider 路徑指向快照檔案。使用已驗
hash 的 Mihomo 1.19.27 與 exact GeoIP 資料做 native `-t`。`review.json` 記錄 source、run、
上游分類與輸出 hashes，並固定 `deployable: false`。語法通過不是 Nikki／Pi 硬體驗收，
**不能把候選交給現行 proxy-rules 或直接 API reload**。

所有輸出 exclusive，不覆寫既有報告或候選；目錄 0700、檔案 0600。兩個 repo 只透過私密
manifest 交換資料，不以硬編碼本機 repo 位置互相 import。這不是數位簽章或對量測真實性的
第三方認證；它用來發現輸入被意外修改、依賴缺失與觀測狀態變更。

## DNS 污染與自動化的後續界線

DoH 保護到 resolver 的傳輸，不能保證 resolver 本身沒有過濾或回覆錯誤。DNSSEC 另提供
資料驗證；本工具只記錄 resolver 回報的 AD，不做本機完整信任鏈驗證。沒有 AD 不代表污染，
也不能把未簽署網域說成已通過 DNSSEC。
[RFC 8484](https://www.rfc-editor.org/rfc/rfc8484.html#section-9)、
[RFC 4033](https://www.rfc-editor.org/rfc/rfc4033.html#section-5)。

不同合法 CDN IP 不需要彼此相同。格式／query identity 錯誤、CNAME loop、私有／保留 IP
不進入網站探測；TLS hostname 不符與非預期回應另行記錄。這些是風險篩選，不是保證能偵測
所有污染。慢、NXDOMAIN、SERVFAIL、302、403 應分層描述，不能直接標成 GFW 問題。

未來自動策略需跨多個窗口確認收益、限制切換頻率並演練回退。預設異常策略是回到原已驗收
的海外加密 DNS，保留服務出口；第一版僅保存此策略與 baseline 候選，沒有自動執行器。
