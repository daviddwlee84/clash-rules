"""Shared deterministic rule validation; policy matching remains Mihomo's job."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"}


def domain(value):
    if not value or len(value) > 253 or value != value.lower().rstrip("."):
        raise ValueError("domain must be lowercase without a trailing dot")
    encoded = value.encode("idna").decode("ascii")
    if not all(re.fullmatch(r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?", x) for x in encoded.split(".")):
        raise ValueError("invalid domain")
    return encoded


def validate_rule(rule):
    fields = rule.split(",")
    kind = fields[0]
    if kind not in TYPES:
        raise ValueError("unsupported common Clash/Shadowrocket rule type")
    if len(fields) < 2 or not fields[1] or any(x != x.strip() for x in fields):
        raise ValueError("expected TYPE,payload without policy or whitespace")
    if kind in {"IP-CIDR", "IP-CIDR6"}:
        if len(fields) not in (2, 3) or (len(fields) == 3 and fields[2] != "no-resolve"):
            raise ValueError("CIDR accepts only an optional no-resolve flag")
        network = ipaddress.ip_network(fields[1], strict=True)
        if network.version != (6 if kind == "IP-CIDR6" else 4):
            raise ValueError("CIDR address family does not match its rule type")
    else:
        if len(fields) != 2:
            raise ValueError("domain rules must not contain a policy or extra fields")
        if kind != "DOMAIN-KEYWORD":
            domain(fields[1])
        elif not re.fullmatch(r"[a-z0-9_.-]+", fields[1]):
            raise ValueError("keyword must be a lowercase literal")
    return fields


def read_rules(path):
    return [line.strip() for line in Path(path).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def mirror_check(root=ROOT):
    lock = json.loads((root / "upstreams.lock.json").read_text())
    if lock.get("schema") != 1:
        raise ValueError("unsupported upstream lock")
    if (root / "vendor").is_symlink():
        raise ValueError("vendor root must not be a symlink")
    seen = set()
    for entry in lock["files"]:
        path = root / entry["path"]
        if entry["path"] in seen or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("duplicate or symlinked mirrored input")
        seen.add(entry["path"])
        if not path.is_file() or not path.resolve().is_relative_to((root / "vendor").resolve()):
            raise ValueError("missing or unsafe mirrored input")
        data = path.read_bytes()
        if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
            raise ValueError("mirrored input checksum mismatch: " + entry["path"])
    return lock


def audit(categories):
    duplicates, shadows, keywords = [], [], []
    seen = {}
    for category, rules in categories.items():
        suffixes = []
        for rule in rules:
            kind, value, *_ = validate_rule(rule)
            if rule in seen:
                duplicates.append({"rule": rule, "categories": [seen[rule], category]})
            else:
                seen[rule] = category
            if kind == "DOMAIN-KEYWORD":
                keywords.append({"category": category, "rule": rule})
            if kind in {"DOMAIN", "DOMAIN-SUFFIX"}:
                for previous in suffixes:
                    if value == previous or value.endswith("." + previous):
                        shadows.append({"category": category, "rule": rule,
                                        "covered_by": "DOMAIN-SUFFIX," + previous})
                        break
                if kind == "DOMAIN-SUFFIX":
                    suffixes.append(value)
    return {"duplicates": duplicates, "earlier_suffix_coverage": shadows,
            "broad_keywords": keywords,
            "note": "Cross-category overlaps depend on client policy order; review, do not delete automatically."}
