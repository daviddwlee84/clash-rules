#!/usr/bin/env python3
"""Fetch a pinned public snapshot for review, verify offline, or explicitly promote it."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

from ruleslib import ROOT, mirror_check, read_rules, sha256

REPO = "MetaCubeX/meta-rules-dat"
DATA = ["geo/geosite/" + name + ".list" for name in
        ("anthropic", "openai", "google", "github", "cn", "private", "apple-cn", "geolocation-!cn")]
DATA += ["geo/geoip/cn.list", "geo/geoip/private.list"]
PREFIX = "vendor/metacubex/"


def fetch(revision, license_revision, output):
    for value in (revision, license_revision):
        if not re.fullmatch("[0-9a-f]{40}", value):
            raise ValueError("both revisions must be full Git commit SHAs")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("snapshot output must be a new directory")
    jobs = [(path, revision) for path in DATA] + [("LICENSE", license_revision), ("README.md", license_revision)]
    def download(job):
        path, commit = job
        url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("upstream file exceeds 8 MiB")
        data.decode("utf-8")
        return path, commit, url, data
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloaded = list(pool.map(download, jobs))
    files = []
    for path, commit, url, data in downloaded:
        target = output / (PREFIX + path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({"path": PREFIX + path, "upstream_path": path, "url": url,
                      "revision": commit, "sha256": sha256(data), "bytes": len(data)})
    lock = {"schema": 1, "repository": REPO, "data_revision": revision,
            "license_revision": license_revision, "files": files}
    (output / "upstreams.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    previous = ROOT / "upstreams.lock.json"
    before = {entry["path"]: entry["sha256"] for entry in json.loads(previous.read_text())["files"]} if previous.exists() else {}
    differences = [{"path": entry["path"], "before": before.get(entry["path"]),
                    "after": entry["sha256"]} for entry in files if before.get(entry["path"]) != entry["sha256"]]
    candidates = {}
    owned = set(read_rules(ROOT / "rules/ai.list"))
    for name in ("anthropic", "openai"):
        upstream = read_rules(output / (PREFIX + f"geo/geosite/{name}.list"))
        converted = ["DOMAIN-SUFFIX," + x[2:] if x.startswith("+.") else "DOMAIN," + x for x in upstream]
        candidates[name] = sorted(set(converted) - owned)
    report = {"changed_files": differences, "ai_candidates_not_activated": candidates,
              "review": "Review shared CDN/telemetry domains and policy overlap before editing rules/ai.list."}
    (output / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    return {"snapshot": str(output), "changed_files": len(differences),
            "data_revision": revision, "review": str(output / "review.json")}


def promote(snapshot):
    snapshot = Path(snapshot).resolve(strict=True)
    lock = mirror_check(snapshot)
    expected = {PREFIX + path for path in DATA + ["LICENSE", "README.md"]}
    if (lock.get("repository") != REPO or {entry["path"] for entry in lock["files"]} != expected
            or len(lock["files"]) != len(expected)):
        raise ValueError("snapshot is not the expected source inventory")
    if (ROOT / "upstreams.lock.json").exists():
        mirror_check()
    for entry in lock["files"]:
        target = ROOT / entry["path"]
        if target.is_symlink():
            raise ValueError("refusing symlink mirror target")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        with temporary.open("xb") as stream:
            stream.write((snapshot / entry["path"]).read_bytes())
        os.replace(temporary, target)
    target = ROOT / "upstreams.lock.json"
    temporary = ROOT / "upstreams.lock.json.part"
    with temporary.open("xb") as stream:
        stream.write((snapshot / "upstreams.lock.json").read_bytes())
    os.replace(temporary, target)
    return {"promoted": lock["data_revision"], "policy_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Verify the committed mirror without network access.")
    get = commands.add_parser("fetch", help="Download exact revisions into a new review directory.")
    get.add_argument("--revision", required=True)
    get.add_argument("--license-revision", required=True)
    get.add_argument("--output", required=True)
    put = commands.add_parser("promote", help="Explicitly replace the mirror with a verified reviewed snapshot.")
    put.add_argument("snapshot")
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = {"verified_revision": mirror_check()["data_revision"]}
        elif args.command == "fetch":
            result = fetch(args.revision, args.license_revision, args.output)
        else:
            result = promote(args.snapshot)
        print(json.dumps(result))
    except Exception as error:
        print("error: upstream snapshot operation failed: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
