#!/usr/bin/env python3
"""Build offline rule artifacts, or --check without writing output. Python 3.12+."""
import argparse
import json
from pathlib import Path
import sys

from ruleslib import ROOT, audit, mirror_check, read_rules, sha256, validate_rule


def build(output=None):
    lock = mirror_check()
    categories = {p.stem: read_rules(p) for p in sorted((ROOT / "rules").glob("*.list"))}
    if not categories:
        raise ValueError("no rule sources")
    for category, rules in categories.items():
        for index, rule in enumerate(rules, 1):
            try:
                validate_rule(rule)
            except ValueError as exc:
                raise ValueError(f"{category}:{index}: {exc}") from exc
    review = audit(categories)
    artifacts = {}
    counts = []
    for category, original in categories.items():
        rules = list(dict.fromkeys(original))
        counts.append(f"{category}\t{len(rules)}")
        banner = f"# {category} | {len(rules)} rules | https://github.com/daviddwlee84/clash-rules\n"
        text = (banner + "\n".join(rules) + "\n").encode()
        artifacts[f"clash/{category}.list"] = text
        artifacts[f"shadowrocket/{category}.list"] = text
        artifacts[f"clash/{category}.yaml"] = (banner + "payload:\n" + "".join(
            "  - " + json.dumps(rule, ensure_ascii=False) + "\n" for rule in rules)).encode()
    artifacts["MANIFEST.txt"] = ("category\trules\n" + "\n".join(counts) + "\n").encode()
    artifacts["review.json"] = (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode()
    artifacts["upstreams.lock.json"] = (ROOT / "upstreams.lock.json").read_bytes()
    artifacts["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    artifacts["THIRD_PARTY.md"] = (ROOT / "THIRD_PARTY.md").read_bytes()
    for entry in lock["files"]:
        artifacts[entry["path"]] = (ROOT / entry["path"]).read_bytes()
    entries = {name: sha256(data) for name, data in sorted(artifacts.items())}
    version = sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())
    manifest = {"schema": 1, "version": version, "files": entries,
                "categories": {key: len(set(value)) for key, value in categories.items()}}
    artifacts["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    if output:
        output = Path(output)
        if output.is_symlink():
            raise ValueError("output must not be a symlink")
        if output.exists():
            existing = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file() or p.is_symlink()}
            if existing - set(artifacts) or any(p.is_symlink() for p in output.rglob("*")):
                raise ValueError("output contains unmanaged files or symlinks; use a new output directory")
        for name, data in artifacts.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "dist"))
    args = parser.parse_args()
    try:
        print(json.dumps(build(None if args.check else args.output), sort_keys=True))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
