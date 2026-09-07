# 單站排查、術語與 FAQ

先問「哪台 client、哪個 domain、什麼時間、哪個 controller」，再用同一觀測窗口連結
DNS、client route、matched rule／proxy chain 與 HTTP 結果。只看畫面上的最終節點或一行
DIRECT log，無法知道應用的完整載入鏈。不要為了排查而分享完整訂閱或瀏覽 log。

## 術語

| 名稱 | 在診斷中的意思 |
|---|---|
| System Proxy | OS 提供給願意遵守它的應用之 HTTP/SOCKS proxy；不涵蓋所有流量 |
| TUN | 虛擬網路介面接管路由；需要權限，還須檢查 OS 的實際 route |
| TPROXY | Linux 透明攔截方式；本 Pi 的 TCP/UDP 使用它，TUN 保持關閉 |
| Mixin / Merge | GUI 或 Nikki 將設定合成 runtime config 的階段；與原始訂閱不是同一檔案 |
| Service Mode | GUI 透過有權限的服務執行 core；不是分流 policy 本身 |
| fake-ip | DNS 回覆合成地址，稍後由 core 映射回 domain；198.18.0.0/15 不應整理成網站 IP rule |
| redir-host | 以真實 DNS 答案配合域名映射；與 fake-ip 的快取／路由需求不同 |
| rule-provider | 可重用的分類資料；RULE-SET 的 policy 與順序仍由 profile 決定 |
| proxy-provider | 節點資料來源，常含服務端地址與 credential，屬私密內容 |
| select / url-test / fallback | 手選、延遲自選、可用性切換；自動群組不等於固定出口 |
| MATCH | 沒有前面規則命中後的最終政策；應檢查前方的規則與 runtime mode |
| fail-open | 代理失效時既有政策容許直連；不能宣稱為防洩漏 kill switch |

DNS 的 nameserver、proxy-server-nameserver 與 direct-nameserver 分別涉及一般查詢、
代理伺服器域名解析與直連解析；nameserver-policy 可依域名選 resolver。
respect-rules 讓 DNS 連線遵循路由政策，需要避免解析代理節點又依賴該代理的循環。
實際欄位以[官方 DNS 文件](https://wiki.metacubex.one/config/dns/)與鎖定 core 為準。

## 分層判讀

| 現象 | 要收集的證據／下一步 |
|---|---|
| Google 連不上 | 比對指定 Pi DNS 與系統解析、答案分類、每個答案的 route，再看 TLS/HTTP；不能直接定罪為 DNS 污染 |
| Pi 回 fake-IP，client 仍失敗 | 檢查該 fake-IP 是否走 utun；殘留本機 TUN 可能讓封包根本不到 Pi |
| 相同 domain 在兩個 resolver 回不同 IP | CDN、地區化、快取與 IPv4/IPv6 都可能造成差異；差異本身不足以證明注入 |
| connection/log 找不到 | 可能採樣漏過短連線、長連線重用、DoH／ECH 讓 hostname 缺失、client filter 錯誤或未經過該 core；回報 insufficient |
| 規則命中，但 timeout | 分開驗證 node health、出口連線、TLS、服務端狀態；命中不是成功 |
| HTTP 403 / 429 | 已有 HTTP 層回應；檢查地區／帳號／服務政策或 rate limit，不把它當成 DNS 污染 |
| 規則已有 domain 卻走錯群組 | 檢查生效的 artifact/profile、rule/global/direct mode、前置規則、Mixin 與 selector state |
| AI 需要穩定出口 | 用獨立 select 直接引用單一 leaf；手動 review 切換，另行確認供應商實際出口是否固定 |

GFW／網路干擾可能涉及 DNS 注入、IP 阻擋、TLS SNI 或 QUIC 相關過濾、連線重置與可用性下降；
一般故障也會呈現相近症狀。用多層證據降低誤判，避免拿一次 timeout 或 IP 差異當確證。
可參考 [OONI Web Connectivity 方法](https://ooni.org/nettest/web-connectivity/)對 false positive
的說明，以及 [GFW QUIC/SNI 研究](https://gfw.report/publications/usenixsecurity25/data/paper/quic-sni.pdf)。
本工具不自動執行審查探測／流量重放，也不替既有失敗做未經觀測的原因推斷。

## 官方 template 如何使用

| 官方來源 | 適合參考的部分 | 不直接套入本 Pi 的原因 |
|---|---|---|
| [Clash Verge 設定指南](https://www.clashverge.dev/guide/config.html) | 多訂閱 provider、groups、DNS 與 rules 的完整組合範例 | 範例的 controller、IPv6、provider 更新與 DNS 須配合裝置政策 |
| [MetaCubeX 設定 wiki](https://wiki.metacubex.one/config/) | 欄位語意、DNS／TUN／rule-provider 支援 | 最新文件可能描述高於本 Pi 1.19.27 的功能 |
| [Mihomo Meta config.yaml](https://github.com/MetaCubeX/mihomo/blob/Meta/docs/config.yaml) | 全面語法／功能參考 | 可變 branch 的示例不是通用 production profile，也不是依賴鎖 |
| [Verge template 原始碼](https://github.com/clash-verge-rev/clash-verge-rev/blob/main/src-tauri/src/utils/tmpl.rs) | local／merge／script 初始化內容 | 初始化以空 proxies/groups/rules、少量 profile merge 和 identity script 為主，不是一份自動維護的個人分流政策 |
| [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) | 持續產生 geosite／geoip 分類 | 挑必要資料鏡像並鎖定，仍需維護自己的 policy、順序與回歸案例 |

因此保留 clash-rules 的價值在個人政策、例外、review／測試與版本；通用分類重用上游。
MRS 適用 domain／ipcidr provider，不能把包含各種 TYPE 的 classical 檔直接當 MRS。
第一版以易 review 的文字與 inline provider 為主，尚未生成 MRS。

[Pi 操作流程](https://github.com/daviddwlee84/RPi-ImmortalWrt/blob/main/docs/clash-diagnostics.md)
只保存該裝置的 SSH、private CA、TPROXY 與 transaction 邊界；本頁是跨裝置知識的維護位置。
