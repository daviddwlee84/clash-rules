#!/usr/bin/env python3
"""One-shot migration: split a monolithic Clash `rules:` block into
categorized, classical-format rule-set source files under `rules/`.

Source of truth for this project's initial content is the inline rule list
that used to live in DockerCompose-V2Ray's Clash client config
(`legacy/example/clash_for_windows.yml`). This script reads that block,
groups each rule by its policy target, strips the target (classical
rule-set files carry the rule MINUS the policy — the policy comes from the
`RULE-SET,<name>,<policy>` line that references them), and writes one
`.list` per category.

Re-runnable and deterministic. After the initial migration you maintain the
`rules/*.list` files by hand; this script is kept for provenance.

Usage:
    python scripts/migrate_from_legacy.py [path/to/clash_for_windows.yml]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# policy target -> output category file (under rules/)
POLICY_TO_FILE = {
    "REJECT": "reject.list",
    "REJECT-DROP": "reject.list",
    "PROXY": "proxy.list",
    "DIRECT": "direct.list",
    "GlobalMedia": "media-global.list",
    "HKMTMedia": "media-hkmt.list",
    "Apple": "apple.list",
}

# rule types that belong in the base config, not in a reusable rule-set
SKIP_TYPES = {"MATCH", "GEOIP", "GEOSITE", "RULE-SET", "SUB-RULE", "FINAL"}

# trailing modifiers that are part of the rule, not the policy
MODIFIERS = {"no-resolve", "src", "tfo", "no-alpn"}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEGACY = (
    REPO_ROOT.parent
    / "DockerCompose-V2Ray"
    / "legacy"
    / "example"
    / "clash_for_windows.yml"
)


def parse_rules(text: str) -> list[list[str]]:
    """Return list of token-lists for each `- TYPE,...` line in `rules:`."""
    out: list[list[str]] = []
    in_rules = False
    for raw in text.splitlines():
        if re.match(r"^rules:\s*$", raw):
            in_rules = True
            continue
        if in_rules:
            # leave the block when we hit another top-level key
            if raw and not raw[0].isspace() and not raw.lstrip().startswith("#"):
                break
            m = re.match(r"^\s*-\s+(.+?)\s*$", raw)
            if not m:
                continue
            body = m.group(1).split("#", 1)[0].strip()  # drop inline comments
            if not body:
                continue
            out.append([t.strip() for t in body.split(",")])
    return out


def classify(tokens: list[str]) -> tuple[str, str] | None:
    """Map a rule's tokens to (category_file, classical_line) or None."""
    rtype = tokens[0].upper()
    if rtype in SKIP_TYPES:
        return None
    # find the policy token: last token that isn't a modifier
    policy_idx = None
    for i in range(len(tokens) - 1, 0, -1):
        if tokens[i] not in MODIFIERS:
            policy_idx = i
            break
    if policy_idx is None:
        return None
    policy = tokens[policy_idx]
    dest = POLICY_TO_FILE.get(policy)
    if not dest:
        return None
    kept = tokens[:policy_idx] + tokens[policy_idx + 1 :]  # rule minus policy
    return dest, ",".join(kept)


HEADERS = {
    "reject.list": "Ad / ISP-hijacking / malware / fake-software domains and IPs -> REJECT",
    "proxy.list": "Sites that should go through the proxy -> PROXY",
    "direct.list": "Mainland-China / CDN / scholar / private-IP domains and IPs -> DIRECT",
    "media-global.list": "International streaming (Netflix, YouTube, Disney+, ...) -> media policy",
    "media-hkmt.list": "HK/Macau/Taiwan-restricted media -> media policy",
    "apple.list": "Apple services -> Apple policy",
}


def main() -> int:
    legacy = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LEGACY
    if not legacy.exists():
        print(f"legacy config not found: {legacy}", file=sys.stderr)
        return 1

    rules = parse_rules(legacy.read_text())
    buckets: dict[str, list[str]] = {f: [] for f in set(POLICY_TO_FILE.values())}
    seen: dict[str, set[str]] = {f: set() for f in buckets}

    skipped = 0
    for tokens in rules:
        res = classify(tokens)
        if res is None:
            skipped += 1
            continue
        dest, line = res
        if line not in seen[dest]:
            seen[dest].add(line)
            buckets[dest].append(line)

    rules_dir = REPO_ROOT / "rules"
    rules_dir.mkdir(exist_ok=True)
    for fname, lines in sorted(buckets.items()):
        header = HEADERS.get(fname, fname)
        body = "\n".join(
            [
                f"# {fname} — {header}",
                f"# Migrated from DockerCompose-V2Ray legacy Clash config.",
                f"# Classical rule-set format (rule minus policy). Maintain by hand.",
                "",
                *lines,
                "",
            ]
        )
        (rules_dir / fname).write_text(body)
        print(f"{fname}: {len(lines)} rules")
    print(f"(skipped {skipped} base/GEOIP/MATCH rules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
