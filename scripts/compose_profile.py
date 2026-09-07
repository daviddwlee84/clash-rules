#!/usr/bin/env python3
"""Compose a private Pi candidate; preserve general policy, pin AI to one leaf node."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

from build import build
from ruleslib import ROOT, mirror_check, read_rules, sha256

LIMIT = 4194304


def private_location(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("private paths must be absolute and non-symlink")
    if path.resolve().is_relative_to(ROOT) and not path.resolve().is_relative_to(ROOT / "private"):
        raise ValueError("private files inside this repo must stay below ignored private/")
    return path


def read_private(path):
    path = private_location(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= LIMIT):
            raise ValueError("private input must be single-link, regular, mode 0600 and 1 byte-4 MiB")
        content = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("private input changed while reading")
    return content


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration key")
        result[key] = value
    return result


def parse_yaml(content):
    yq = shutil.which("yq")
    if not yq:
        raise ValueError("Mike Farah yq v4 is required to parse the private base")
    result = subprocess.run([yq, "-o=json", ".", "-"], input=content, capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("private YAML parsing failed (details suppressed)")
    try:
        value = json.loads(result.stdout, object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("private YAML must contain one mapping") from exc
    if not isinstance(value, dict):
        raise ValueError("private YAML must contain one mapping")
    return value


def compose(base, node, *, group="AI-stable"):
    candidate = copy.deepcopy(base)
    if any(k in base for k in ("external-controller", "external-controller-tls", "secret")):
        raise ValueError("use the managed Pi tested source; controller keys belong to Nikki")
    if any(k in (base.get("tls") or {}) for k in ("certificate", "private-key", "ech-key")):
        raise ValueError("controller TLS material must not enter the private profile")
    providers = copy.deepcopy(base.get("rule-providers") or {})
    for provider in list(providers.values()) + list((base.get("proxy-providers") or {}).values()):
        if provider.get("type") != "inline":
            raise ValueError("offline candidate requires materialized inline providers")
    if "geosite:" in json.dumps(base.get("dns") or {}).lower():
        raise ValueError("materialize DNS geosite dependencies before composing an offline candidate")
    groups = candidate.get("proxy-groups") or []
    nodes = candidate.get("proxies") or []
    names = [entry.get("name") for entry in nodes + groups]
    if len(names) != len(set(names)) or any(not isinstance(name, str) for name in names):
        raise ValueError("proxy and group names must be unique")
    matches = [entry for entry in nodes if entry.get("name") == node]
    if len(matches) != 1 or matches[0].get("type") in {"direct", "reject", "pass"}:
        raise ValueError("AI policy must name exactly one concrete existing proxy node")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", group) or group in names:
        raise ValueError("AI group must have a new safe name; rebuild from the retained original base")
    if any(name.startswith("self-") for name in providers):
        raise ValueError("self-* provider names are reserved; rebuild from the retained original base")
    providers["self-ai"] = {"type": "inline", "behavior": "classical",
                            "payload": list(dict.fromkeys(read_rules(ROOT / "rules/ai.list")))}
    translated, materialized = [], []
    for rule in base.get("rules") or []:
        if not isinstance(rule, str):
            raise ValueError("base rules must be strings")
        fields = rule.split(",")
        if fields[0] == "GEOSITE":
            raise ValueError("GEOSITE dependencies must be materialized explicitly before composition")
        if fields[0] == "GEOIP":
            if len(fields) not in (3, 4) or fields[1] not in {"CN", "private"} or (len(fields) == 4 and fields[3] != "no-resolve"):
                raise ValueError("only mirrored CN/private GEOIP rules can be materialized")
            name = "self-geoip-" + fields[1].lower()
            providers[name] = {"type": "inline", "behavior": "ipcidr",
                               "payload": read_rules(ROOT / f"vendor/metacubex/geo/geoip/{fields[1].lower()}.list")}
            translated.append(",".join(["RULE-SET", name] + fields[2:]))
            materialized.append({"source": fields[1], "position": len(translated),
                                 "entries": len(providers[name]["payload"])})
        else:
            translated.append(rule)
    if not translated or not translated[-1].startswith("MATCH,"):
        raise ValueError("base must end in an explicit MATCH policy")
    candidate["proxy-groups"] = groups + [{"name": group, "type": "select", "proxies": [node]}]
    candidate["rule-providers"] = providers
    candidate["rules"] = [f"RULE-SET,self-ai,{group}"] + translated
    candidate["profile"] = {**(candidate.get("profile") or {}), "store-selected": True}
    return candidate, materialized


def write_exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--expected-base-sha256", required=True, help="Digest from the managed Pi context.")
    parser.add_argument("--policy", required=True, help='Private JSON: {"ai_node":"existing leaf name","ai_group":"AI-stable"}')
    parser.add_argument("--output", required=True, help="New absolute private YAML path; JSON is emitted as valid YAML.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report digests without writing files.")
    args = parser.parse_args()
    try:
        output = private_location(args.output)
        report_path = Path(str(output) + ".report.json")
        if output.exists() or report_path.exists() or report_path.is_symlink() or not output.parent.is_dir():
            raise ValueError("candidate and sidecar destinations must be new files in an existing private directory")
        mirror_check()
        manifest = build()
        raw = read_private(args.base)
        if sha256(raw) != args.expected_base_sha256:
            raise ValueError("base differs from the expected managed profile digest")
        policy = json.loads(read_private(args.policy), object_pairs_hook=unique_pairs)
        if set(policy) - {"ai_node", "ai_group"} or "ai_node" not in policy:
            raise ValueError("private policy accepts only ai_node and optional ai_group")
        base = parse_yaml(raw)
        candidate, materialized = compose(base, policy["ai_node"], group=policy.get("ai_group", "AI-stable"))
        data = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode()
        if len(data) > LIMIT:
            raise ValueError("candidate exceeds the Pi 4 MiB profile limit")
        report = {"schema": 1, "base_sha256": sha256(raw), "profile_sha256": sha256(data),
                  "rules_version": manifest["version"], "bytes": len(data), "ai_group_added": True,
                  "existing_groups_preserved": True, "general_rule_order_preserved": True,
                  "geoip_materialized": materialized, "native_validation": "required",
                  "deployment": "not-applied", "dry_run": args.dry_run,
                  "notes": ["AI uses one explicit leaf; node provider egress can still change.",
                            "Existing Pi fail-open remains; no continuous egress guarantee.",
                            "Mirrored AI additions are review candidates, not automatically activated."]}
        if not args.dry_run:
            write_exclusive(output, data)
            write_exclusive(report_path, (json.dumps(report, indent=2) + "\n").encode())
        print(json.dumps(report))
    except Exception as error:
        message = str(error) if type(error) is ValueError else "private composition failed: " + type(error).__name__
        print("error: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
