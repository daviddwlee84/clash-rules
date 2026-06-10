#!/usr/bin/env python3
"""Build categorized rule-set sources (`rules/*.list`) into per-client
output formats under `dist/`.

Single source of truth -> one build -> many client formats:

    rules/<cat>.list  (classical, hand-maintained)
        -> dist/clash/<cat>.list   (Clash/mihomo: behavior classical, format text)
        -> dist/clash/<cat>.yaml   (Clash/mihomo: behavior classical, format yaml)
        -> dist/shadowrocket/<cat>.list  (Shadowrocket RULE-SET)

The classical text body is identical across Clash and Shadowrocket, so a
single maintained list feeds every client — no per-client patching.

Validates each line first; exits non-zero on any bad rule so CI fails loudly.
Pure stdlib, no dependencies.

Usage:
    python scripts/build.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / "rules"
DIST = REPO_ROOT / "dist"

# rule types valid inside a classical rule-provider / Shadowrocket RULE-SET
ALLOWED_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD", "DOMAIN-REGEX",
    "IP-CIDR", "IP-CIDR6", "IP-SUFFIX", "IP-ASN", "GEOIP",
    "DST-PORT", "SRC-PORT", "SRC-IP-CIDR", "PROCESS-NAME", "PROCESS-PATH",
    "USER-AGENT", "URL-REGEX", "AND", "OR", "NOT",
}
# never valid inside a rule-set (these are top-level routing constructs)
FORBIDDEN_TYPES = {"MATCH", "RULE-SET", "SUB-RULE", "FINAL"}


def read_rules(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def validate(cat: str, lines: list[str]) -> list[str]:
    errors = []
    for i, line in enumerate(lines, 1):
        rtype = line.split(",", 1)[0].upper()
        if rtype in FORBIDDEN_TYPES:
            errors.append(f"{cat}:{i}: '{rtype}' not allowed in a rule-set: {line}")
        elif rtype not in ALLOWED_TYPES:
            errors.append(f"{cat}:{i}: unknown rule type '{rtype}': {line}")
    return errors


def main() -> int:
    sources = sorted(RULES_DIR.glob("*.list"))
    if not sources:
        print("no rules/*.list found", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    parsed: dict[str, list[str]] = {}
    for src in sources:
        cat = src.stem
        lines = read_rules(src)
        # dedupe, preserve order
        seen, uniq = set(), []
        for ln in lines:
            if ln not in seen:
                seen.add(ln)
                uniq.append(ln)
        parsed[cat] = uniq
        all_errors += validate(cat, uniq)

    if all_errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        print("\n".join(all_errors), file=sys.stderr)
        return 1

    clash_dir = DIST / "clash"
    sr_dir = DIST / "shadowrocket"
    clash_dir.mkdir(parents=True, exist_ok=True)
    sr_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for cat, lines in sorted(parsed.items()):
        banner = f"# {cat} | {len(lines)} rules | https://github.com/daviddwlee84/clash-rules"
        text_body = banner + "\n" + "\n".join(lines) + "\n"
        yaml_body = banner + "\npayload:\n" + "".join(f"  - '{ln}'\n" for ln in lines)

        (clash_dir / f"{cat}.list").write_text(text_body)
        (clash_dir / f"{cat}.yaml").write_text(yaml_body)
        (sr_dir / f"{cat}.list").write_text(text_body)
        manifest.append(f"{cat}\t{len(lines)}")

    (DIST / "MANIFEST.txt").write_text(
        "category\trules\n" + "\n".join(manifest) + "\n"
    )
    total = sum(len(v) for v in parsed.values())
    print(f"built {len(parsed)} categories, {total} rules total -> {DIST}")
    for line in manifest:
        print("  " + line.replace("\t", ": "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
