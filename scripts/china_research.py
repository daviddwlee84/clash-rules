#!/usr/bin/env python3
"""分析私有 DNS/CDN 研究資料，或產生不可直接部署的 ChinaServices 候選。"""
import argparse
import copy
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
import sys
import tempfile
from urllib.parse import urlsplit

from compose_profile import parse_yaml, private_location, write_exclusive, unique_pairs
from ruleslib import ROOT, mirror_check, read_rules

SCHEMA = "china-research-v1"
CN_PATH = "vendor/metacubex/geo/geosite/cn.list"
PROVIDER_PATH = "/etc/nikki/run/rpi-rules/china-services.list"
DNS_URLS = {
    "alidns": ["https://dns.alidns.com/dns-query#ChinaServices"],
    "dnspod": ["https://doh.pub/dns-query#ChinaServices"],
}
INPUT_FILES = {"source.yaml", "runtime.yaml", "proxy.list", "geoip.metadb", "state-before.json", "state-after.json",
               "targets.json", "core-version.json", "selectors-before.json", "selectors-after.json", "client-paths.json", "client-paths-after.json", "dns.json", "samples.json", "observations.json", "lan.json"}


def decode(data):
    return json.loads(data, object_pairs_hook=unique_pairs)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def private_read(path, limit=64*1024*1024):
    path = private_location(Path(path).absolute())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd,"rb") as stream:
        a = os.fstat(stream.fileno())
        if not stat.S_ISREG(a.st_mode) or a.st_nlink != 1 or stat.S_IMODE(a.st_mode) != 0o600 or a.st_size > limit:
            raise ValueError("input 必須為 bounded single-link regular file，mode 0600")
        data = stream.read(limit+1)
        b = os.fstat(stream.fileno())
        if (a.st_ino,a.st_size,a.st_mtime_ns)!=(b.st_ino,b.st_size,b.st_mtime_ns):
            raise ValueError("input 在讀取期間改變")
        return data


def load_run(directory):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ValueError("研究目錄必須是 non-symlink 0700 directory")
    manifest = decode(private_read(directory/"manifest.json", 1048576))
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"),dict):
        raise ValueError("不支援的研究 manifest；請使用 Pi collect 輸出")
    if set(manifest["files"]) - INPUT_FILES or not {"source.yaml","runtime.yaml","proxy.list","targets.json","dns.json","samples.json","state-before.json","core-version.json"} <= set(manifest["files"]):
        raise ValueError("manifest 的輸入集合不完整或包含未知路徑")
    if type(manifest.get("state_stable")) is not bool or type(manifest.get("sampling_complete")) is not bool or type(manifest.get("sample_count")) is not int or not 1 <= manifest["sample_count"] <= 5:
        raise ValueError("manifest 狀態／樣本數格式錯誤")
    files = {}
    total = 0
    for name, metadata in manifest["files"].items():
        data = private_read(directory/name)
        total += len(data)
        if total > 64*1024*1024 or metadata.get("sha256")!=sha(data) or metadata.get("bytes")!=len(data):
            raise ValueError("研究輸入的 hash／bytes 不符或總量超限")
        files[name] = data
    state = decode(files["state-before.json"])
    if sha(files["source.yaml"]) != state.get("source_sha256") or sha(files["runtime.yaml"]) != state.get("runtime_sha256") or sha(files["proxy.list"]) != state.get("provider_sha256"):
        raise ValueError("來源／runtime／provider 與 state binding 不符")
    if manifest["state_stable"] and ("state-after.json" not in files or decode(files["state-after.json"]) != state or files.get("selectors-before.json") != files.get("selectors-after.json")):
        raise ValueError("穩定狀態宣告缺少一致的結束證據")
    if manifest["state_stable"] and files.get("client-paths.json") != files.get("client-paths-after.json"):
        raise ValueError("client route 在觀測期間改變")
    version=decode(files["core-version.json"]).get("version")
    if version not in ("1.19.27", "v1.19.27"):
        raise ValueError("快照 core 不是鎖定的 1.19.27")
    return directory, manifest, files


def in_cn(host, rules):
    return any((host==line[2:] or host.endswith("."+line[2:])) if line.startswith("+.") else host==line for line in rules)


def validate_targets(targets):
    if not isinstance(targets,list) or not 1 <= len(targets) <= 4:
        raise ValueError("targets 必須為 1–4 筆")
    seen = set()
    for target in targets:
        u = urlsplit(target["url"])
        host = u.hostname
        if u.scheme!="https" or u.port not in (None,443) or u.username or u.password or u.query or u.fragment or not host or host in seen:
            raise ValueError("targets 有重複／不安全的 HTTPS URL")
        if not re.fullmatch(r"[a-z0-9.-]+",host) or "." not in host or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",x) for x in host.split(".")):
            raise ValueError("target hostname 格式錯誤")
        seen.add(host)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("target 不接受 IP literal")
        if type(target.get("pilot")) is not bool or not isinstance(target.get("expected_status"),list) or not target["expected_status"]:
            raise ValueError("target 缺少 pilot／expected_status")
        if any(type(n) is not int or not 200 <= n < 400 for n in target["expected_status"]):
            raise ValueError("expected_status 僅接受 2xx／3xx")
    return targets


def summary(manifest, files):
    targets = validate_targets(decode(files["targets.json"]))
    samples = decode(files["samples.json"])
    dns = decode(files["dns.json"])
    grouped = {}
    seen=set()
    hosts={urlsplit(t["url"]).hostname:t for t in targets}
    for row in samples:
        key=(row.get("host"),row.get("resolver"),row.get("vantage"),row.get("ip"),row.get("sample"))
        if key in seen or row.get("host") not in hosts or type(row.get("sample")) is not int or not 0 <= row["sample"] < manifest["sample_count"]:
            raise ValueError("樣本重複、hostname 未宣告或 sample index 無效")
        seen.add(key)
        address=ipaddress.ip_address(row["ip"])
        if address.version!=4 or not address.is_global or address.is_multicast:
            raise ValueError("樣本包含非 public IPv4")
        if row.get("vantage") not in ("pi","client") or row.get("resolver") not in ("baseline",*DNS_URLS):
            raise ValueError("未知的樣本來源／resolver")
        key = (row["host"],row["resolver"],row["vantage"])
        grouped.setdefault(key,[]).append(row)
    results = []
    for (host,resolver,vantage),rows in sorted(grouped.items()):
        expected_status=hosts[host]["expected_status"]
        valid = [x for x in rows if x.get("success") is True and x.get("exitcode")==0 and x.get("ssl_verify_result")==0 and x.get("http_code") in expected_status and x.get("redirect_same_origin") is True and all(type(x.get(k)) in (int,float) and math.isfinite(x[k]) and x[k]>=0 for k in ("time_starttransfer","time_total"))]
        values = [x["time_starttransfer"] for x in valid]
        answers=next((x for x in dns if x["host"]==host and x["resolver"]==resolver),{})
        expected={(ip,n) for ip in answers.get("addresses",[])[:2] for n in range(manifest["sample_count"])}
        complete={(x["ip"],x["sample"]) for x in rows}==expected and bool(expected) and answers.get("outcome")=="answers"
        results.append({"host":host,"resolver":resolver,"vantage":vantage,"planned":len(rows),"successes":len(valid),
                        "median_ttfb":statistics.median(values) if values else None,
                        "median_total":statistics.median([x["time_total"] for x in valid]) if valid else None,
                        "first_sample_total":[x.get("time_total") for x in rows if x.get("sample")==0],
                        "sampled_ips":sorted({x["ip"] for x in rows}),
                        "complete_success":complete and manifest["sample_count"]==5 and len(valid)==len(rows)})
    recommendations = []
    for target in targets:
        host = urlsplit(target["url"]).hostname
        eligible = [x for x in results if x["host"]==host and x["vantage"]=="pi" and x["complete_success"]
                    and any(d["host"]==host and d["resolver"]==x["resolver"] and d.get("outcome")=="answers" for d in dns)]
        answer_groups={}
        for item in eligible:
            answer_groups.setdefault(tuple(item["sampled_ips"]),[]).append(item)
        ranked=sorted(answer_groups.values(),key=lambda group:statistics.median([x["median_ttfb"] for x in group]))
        equivalent=sorted(x["resolver"] for x in ranked[0]) if ranked else []
        # Identical sampled CDN answers cannot establish a resolver-brand speed win.
        choice=("baseline" if "baseline" in equivalent else equivalent[0]) if equivalent else None
        recommendations.append({"host":host,"candidate_to_review":choice if manifest.get("state_stable") is True and manifest.get("sampling_complete") is True else None,
                                "equivalent_sampled_answers":equivalent,
                                "interpretation":"single-window CDN answer-group research; equal answers do not prove a resolver performance difference"})
    return {"schema":"china-research-report-v1","state_stable":manifest.get("state_stable") is True,
            "sampling_complete":manifest.get("sampling_complete") is True,"comparisons":results,
            "dns_outcomes":[{k:d.get(k) for k in ("host","resolver","outcome","rcode","resolver_ad","dnssec")} for d in dns],
            "recommendations":recommendations,"observations":decode(files.get("observations.json",b"[]")),
            "client_paths":decode(files.get("client-paths.json",b"{}")),"lan":decode(files.get("lan.json",b"[]")),"warnings":manifest.get("warnings",[]),
            "fallback_design":"baseline encrypted DNS; retain ChinaServices exit; not implemented as automation",
            "limits":["DNS 差異不等於污染；AD 不是本機獨立 DNSSEC 驗證。",
                      "只比較相同 vantage；controller 時間不當作純 resolver latency。",
                      "首頁／官網不代表 App、登入、圖片、影片或訊息功能驗收。",
                      "部分樣本／狀態變更不提供候選建議；不清 cache、不自動套用。"]}


def md(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ").replace("`", "\\`")


def report_markdown(report):
    lines = ["# ChinaServices 研究報告", "", "工作設定穩定："+str(report["state_stable"])+"；取樣完整："+str(report["sampling_complete"]), "",
             "| Host | Resolver | Vantage | 成功／計畫樣本 | Median TTFB |", "|---|---|---|---:|---:|"]
    for row in report["comparisons"]:
        lines.append(f'| {row["host"]} | {row["resolver"]} | {row["vantage"]} | {row["successes"]}/{row["planned"]} | {row["median_ttfb"]} |')
    lines += ["", "## DNS 與建議", "", "| Host | Resolver | DNS 結果 | AD（resolver 回報） |", "|---|---|---|---|"]
    for row in report["dns_outcomes"]:
        lines.append(f'| {row["host"]} | {row["resolver"]} | {row["outcome"]} | {row["resolver_ad"]} |')
    for row in report["recommendations"]:
        lines.append("\n- "+row["host"]+"：待 review 選擇="+str(row["candidate_to_review"])+"；相同取樣 CDN 答案="+", ".join(row["equivalent_sampled_answers"]))
    lines += ["", "## 分類與優先例外", ""]
    for row in report.get("classification",[]):
        lines.append("- "+row["host"]+"："+row["status"]+"；較高優先規則="+str(row["prior_rule_index"])+"；政策="+str(row["prior_policy"]))
    lines += ["", "## 觀測連線", ""]
    if not report["observations"]:
        lines.append("本輪未捕獲相關連線；不能推論 App 繞過 Pi。")
    for row in report["observations"]:
        lines.append("- "+row["host"]+"："+str(row["rule"])+" → "+" → ".join(md(x) for x in row["chains_core_order"]))
    lines += ["", "## Client 到 Pi 的 TCP 對照", ""]
    for row in report["lan"]:
        lines.append("- port "+str(row["port"])+"："+str(row.get("tcp_seconds",row.get("error"))))
    lines += ["", "## 判讀限制", ""] + ["- "+x for x in report["limits"]]
    lines += ["", "## 下一步", "", "建議只供 review；相同 CDN IP 的時間差不能當成 resolver 品牌差異。",
              "若 LAN TCP 本身很慢，先分開排查 client → Pi；官網／下載連線不是訊息、圖片或影片功能驗收。", ""]
    return "\n".join(lines).encode()


def conflict(rule, host, provider_data, addresses):
    parts = rule.split(",")
    kind = parts[0]
    if kind=="DOMAIN":return parts[1]==host
    if kind=="DOMAIN-SUFFIX":return host==parts[1] or host.endswith("."+parts[1])
    if kind=="DOMAIN-KEYWORD":return parts[1] in host
    if kind=="DOMAIN-REGEX":raise ValueError("DOMAIN-REGEX 的語意需另行 review，不以 Python regex 推測 core")
    if kind=="RULE-SET":
        if parts[1]!="rpi-local-proxy":raise ValueError("未知的較高優先 RULE-SET；先 review")
        return any(x=="DOMAIN,"+host for x in provider_data.decode().splitlines())
    if kind in ("IP-CIDR","IP-CIDR6"):
        network=ipaddress.ip_network(parts[1],strict=False)
        return any(ipaddress.ip_address(ip) in network for ip in addresses if ipaddress.ip_address(ip).version==network.version)
    if kind in ("GEOIP","MATCH"):
        raise ValueError("pilot 插入點前存在無法保留的兜底規則")
    raise ValueError("候選不推測未知規則類型的優先序")


def classify(files, cn_rules):
    source=parse_yaml(files["source.yaml"])
    targets=validate_targets(decode(files["targets.json"]))
    rules=source.get("rules",[])
    position=next((i for i,r in enumerate(rules) if r=="GEOIP,CN,DIRECT"),len(rules)-1)
    answers=decode(files["dns.json"])
    result=[]
    for target in targets:
        host=urlsplit(target["url"]).hostname
        record={"host":host,"cn_member":in_cn(host,cn_rules),"pilot":target["pilot"],
                "prior_rule_index":None,"prior_policy":None,"status":"pilot-eligible" if target["pilot"] else "reference-only"}
        ips=[ip for answer in answers if answer["host"]==host for ip in answer.get("addresses",[])]
        if not record["cn_member"]:record["status"]="outside-cn-dataset"
        for i,rule in enumerate(rules[:position]):
            try:matched=conflict(rule,host,files["proxy.list"],ips)
            except ValueError:
                record["status"]="unsupported-priority-review-required"
                break
            if matched:
                record.update({"prior_rule_index":i,"prior_policy":rule.split(",")[2],"status":"existing-policy-preserved"})
                break
        result.append(record)
    return result


def compose(files, resolver, cn_rules):
    base=parse_yaml(files["source.yaml"])
    runtime=parse_yaml(files["runtime.yaml"])
    targets=validate_targets(decode(files["targets.json"]))
    pilots=[urlsplit(t["url"]).hostname for t in targets if t["pilot"]]
    if not pilots or any(not in_cn(host,cn_rules) for host in pilots):
        raise ValueError("pilot 必須明確指定且屬於鎖定的 geosite/cn")
    if any(k in base for k in ("external-controller","external-controller-tls","secret")) or any(k in (base.get("tls") or {}) for k in ("certificate","private-key","ech-key")):
        raise ValueError("source 不可提供 controller／TLS material")
    expected={"rpi-local-proxy":{"type":"file","behavior":"classical","format":"text","path":"/etc/nikki/run/rpi-rules/proxy.list"}}
    if base.get("rule-providers")!=expected or base.get("proxy-providers"):
        raise ValueError("只接受已快照的 rpi-local-proxy；其他 provider 需先擴充依賴驗證")
    managed_dns={"listen","enhanced-mode","fake-ip-range","direct-nameserver-follow-policy"}
    if {k:v for k,v in base.get("dns",{}).items() if k not in managed_dns}!={k:v for k,v in runtime.get("dns",{}).items() if k not in managed_dns}:
        raise ValueError("source 與 effective DNS 存在未知差異；需先審查 Nikki Mixin")
    names=[x.get("name") for x in base.get("proxy-groups",[])+base.get("proxies",[])]
    if "ChinaServices" in names or len(names)!=len(set(names)):
        raise ValueError("ChinaServices 命名衝突或既有名稱重複")
    if base.get("dns",{}).get("nameserver-policy") or base.get("dns",{}).get("direct-nameserver"):
        raise ValueError("既有 DNS policy/direct-nameserver 需人工審查，拒絕覆寫")
    rules=base.get("rules",[])
    if not rules or not rules[-1].startswith("MATCH,"):
        raise ValueError("source 必須以明確 MATCH 結尾")
    positions=[i for i,r in enumerate(rules) if r=="GEOIP,CN,DIRECT"]
    if len(positions)>1:raise ValueError("多個 CN 兜底位置，拒絕猜測")
    position=positions[0] if positions else len(rules)-1
    dns=decode(files["dns.json"])
    for host in pilots:
        ips=[ip for d in dns if d["host"]==host for ip in d.get("addresses",[])]
        for i,rule in enumerate(rules[:position]):
            if conflict(rule,host,files["proxy.list"],ips):
                raise ValueError(f"pilot {host} 被較高優先規則 #{i} 覆蓋；保留原政策，不產生候選")
    candidate=copy.deepcopy(base)
    candidate["rule-providers"]["china-services-pilot"]={"type":"file","behavior":"domain","format":"text","path":PROVIDER_PATH}
    candidate["proxy-groups"].append({"name":"ChinaServices","type":"select","proxies":["DIRECT"]})
    candidate["rules"].insert(position,"RULE-SET,china-services-pilot,ChinaServices")
    if resolver!="baseline":
        candidate["dns"]["nameserver-policy"]={"rule-set:china-services-pilot":DNS_URLS[resolver]}
    data=("# explicitly reviewed pilot hostnames\n"+"\n".join(sorted(pilots))+"\n").encode()
    return candidate,data,{"pilots":pilots,"rule_insert_index":position,"dns_profile":resolver,
                           "preserved_original_rule_order":True,"nikki_managed_dns_overrides_preserved":sorted(managed_dns),"group_default":"DIRECT","deployable":False}


def candidate(directory, manifest, files, resolver, output, dry_run=False):
    if manifest.get("state_stable") is not True:
        raise ValueError("觀測期間設定不穩定；重新 collect，不能產生候選")
    analysis=summary(manifest,files)
    pilots=[urlsplit(t["url"]).hostname for t in decode(files["targets.json"]) if t["pilot"]]
    if resolver!="baseline":
        if manifest.get("sampling_complete") is not True:
            raise ValueError("取樣不完整；不得以此完成 DNS 候選")
        for host in pilots:
            good=[x for x in analysis["comparisons"] if x["host"]==host and x["resolver"]==resolver and x["vantage"]=="pi" and x["complete_success"]]
            if not good:raise ValueError("選定 resolver 沒有至少五筆完整成功的 Pi 樣本")
    lock=mirror_check()
    cn=read_rules(ROOT/CN_PATH)
    config,data,review=compose(files,resolver,cn)
    if any(r.startswith("GEOIP,") for r in config["rules"]):
        if config.get("geodata-mode",False) or any(r!="GEOIP,CN,DIRECT" for r in config["rules"] if r.startswith("GEOIP,")) or "geoip.metadb" not in files:
            raise ValueError("缺少 exact GeoIP 依賴或未支援資料模式；不臨時下載")
    if any(r.startswith(("GEOSITE,","IP-ASN,")) for r in config["rules"]):
        raise ValueError("未快照的 geodata 依賴")
    if dry_run:
        return {**review,"writes":False,"native_validation":"not-run"}
    from native_check import core_path, native_test
    core=core_path(download=False)
    out=private_location(Path(output).absolute())
    if out.exists() or out.is_symlink():raise ValueError("output 必須是新的私密目錄")
    # Validate a disposable copy; intended Pi paths remain unchanged in candidate.yaml.
    with tempfile.TemporaryDirectory(prefix="china-candidate-validate-") as tmp:
        home=Path(tmp)
        for name,content in {"proxy.list":files["proxy.list"],"china-services.list":data,**({"geoip.metadb":files["geoip.metadb"]} if "geoip.metadb" in files else {})}.items():
            path=home/name;path.write_bytes(content);path.chmod(0o600)
        test=copy.deepcopy(config)
        test["rule-providers"]["rpi-local-proxy"]["path"]=str(home/"proxy.list")
        test["rule-providers"]["china-services-pilot"]["path"]=str(home/"china-services.list")
        test_path=home/"config.json";test_path.write_bytes(encode(test));test_path.chmod(0o600)
        native_test(core,test_path,home)
    out.mkdir(mode=0o700)
    outputs={"candidate.yaml":encode(config),"proxy.list":files["proxy.list"],"china-services.list":data}
    if "geoip.metadb" in files:outputs["geoip.metadb"]=files["geoip.metadb"]
    for name,content in outputs.items():write_exclusive(out/name,content)
    review.update({"schema":"china-services-candidate-v1","research_only":True,"native_syntax":"passed",
                   "native_version":"1.19.27","hardware_acceptance":"not-performed",
                   "source_sha256":sha(files["source.yaml"]),"runtime_sha256":sha(files["runtime.yaml"]),
                   "research_manifest_sha256":sha(private_read(directory/"manifest.json")),
                   "upstream_revision":lock["data_revision"],"cn_sha256":next(x["sha256"] for x in lock["files"] if x["path"]==CN_PATH),
                   "files":{n:{"sha256":sha(v),"bytes":len(v)} for n,v in outputs.items()},
                   "limitations":["現行 proxy-rules 不接受此候選；不得直接 API reload。",
                                  "IP 規則僅檢查本輪 DNS 答案；App 與未觀測域名未驗收。",
                                  "未安裝排程，未套用／flush cache／切換 selector。"]})
    write_exclusive(out/"review.json",encode(review))
    return {"output":str(out),"pilots":review["pilots"],"resolver":resolver,"native_syntax":"passed","deployable":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__,epilog="Exit: 0 output/dry-run; 1 validation/input failure. No live deployment operation exists.")
    subs=parser.add_subparsers(dest="command",required=True)
    for name in ("report","candidate"):
        sub=subs.add_parser(name)
        sub.add_argument("run",type=Path)
        sub.add_argument("--dry-run",action="store_true")
        if name=="report":
            sub.add_argument("--output",type=Path,help="可選：新的私密報告目錄；預設寫在原 run")
        if name=="candidate":
            sub.add_argument("--resolver",choices=["alidns","dnspod","baseline"],required=True)
            sub.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    directory,manifest,files=load_run(args.run)
    if args.command=="candidate":
        result=candidate(directory,manifest,files,args.resolver,args.output,args.dry_run)
    else:
        report=summary(manifest,files)
        mirror_check()
        report["classification"]=classify(files,read_rules(ROOT/CN_PATH))
        report["research_manifest_sha256"]=sha(private_read(directory/"manifest.json"))
        destination=private_location(args.output.absolute()) if args.output else directory
        if args.output and (destination.exists() or destination.is_symlink()):
            raise ValueError("report --output 必須是新目錄")
        if not args.dry_run:
            if args.output:destination.mkdir(mode=0o700)
            write_exclusive(destination/"report.json",encode(report))
            write_exclusive(destination/"report.md",report_markdown(report))
        result={"report":str(destination/"report.md"),"state_stable":report["state_stable"],"comparisons":len(report["comparisons"]),"writes":not args.dry_run}
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    try:main()
    except Exception as error:
        print("error: "+(str(error) if type(error) is ValueError else type(error).__name__)+"；請保留原始資料並修正輸入後重試。",file=sys.stderr)
        sys.exit(1)
