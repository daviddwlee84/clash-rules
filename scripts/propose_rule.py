#!/usr/bin/env python3
"""Turn one private routing observation into a review candidate, never a live rule."""
import argparse
import json
import sys
from pathlib import Path

from build import build
from compose_profile import private_location, read_private, unique_pairs, write_exclusive
from ruleslib import ROOT, domain, read_rules


def propose(report, category):
    if report.get("schema") != "clash-routing-observation-v1":
        raise ValueError("expected a clash-routing-observation-v1 report")
    host = domain(report["domain"])
    sources = {p.stem: read_rules(p) for p in (ROOT / "rules").glob("*.list")}
    if category not in sources:
        raise ValueError("unknown rule category")
    coverage = {}
    for name, rules in sources.items():
        coverage[name] = []
        for rule in rules:
            kind, value, *_ = rule.split(",")
            if ((kind == "DOMAIN" and host == value)
                    or (kind == "DOMAIN-SUFFIX" and (host == value or host.endswith("." + value)))
                    or (kind == "DOMAIN-KEYWORD" and value in host)):
                coverage[name].append(rule)
    observed = report.get("evidence") == "observed-route"
    if report.get("profile_binding", {}).get("stable_during_observation") is False:
        observed = False
    decision = "needs-evidence" if not observed else "already-covered" if coverage[category] else "review-candidate"
    return {"schema": 1, "decision": decision, "domain": host, "category": category,
            "candidate": f"DOMAIN,{host}" if decision == "review-candidate" else None,
            "rules_version": build()["version"], "coverage": coverage,
            "observed_core_version": report.get("core_version"),
            "profile_binding": report.get("profile_binding"),
            "review_required": True,
            "checks": ["Confirm service ownership and required outbound policy.",
                       "Review shared SaaS/CDN scope; exact host is intentional.",
                       "Compare deployed profile/rules version if already covered.",
                       "Never turn a fake-IP address into a permanent IP-CIDR rule."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", required=True, help="New absolute private JSON file.")
    args = parser.parse_args()
    try:
        target = private_location(args.output)
        if target.exists() or not target.parent.is_dir():
            raise ValueError("candidate output must be a new private file")
        report = json.loads(read_private(args.report), object_pairs_hook=unique_pairs)
        result = propose(report, args.category)
        write_exclusive(target, (json.dumps(result, indent=2) + "\n").encode())
        print(json.dumps({"decision": result["decision"], "output": str(target)}))
        return 0
    except Exception as error:
        message = str(error) if type(error) is ValueError else "candidate generation failed: " + type(error).__name__
        print("error: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
