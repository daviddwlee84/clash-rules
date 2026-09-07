import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build import build
from compose_profile import compose, parse_yaml, read_private
from propose_rule import propose
from ruleslib import ROOT, mirror_check, validate_rule


class RuleTests(unittest.TestCase):
    def base(self):
        return {"proxies": [{"name": "fixture-node", "type": "http", "server": "127.0.0.1", "port": 1}],
                "proxy-groups": [{"name": "GENERAL", "type": "select", "proxies": ["fixture-node"]}],
                "dns": {"enable": True, "nameserver": ["rcode://success"]},
                "rules": ["DOMAIN-SUFFIX,google.com,GENERAL", "GEOIP,CN,DIRECT", "MATCH,GENERAL"]}

    def test_offline_reproducible_build(self):
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            a, b = Path(directory) / "a", Path(directory) / "b"
            self.assertEqual(build(a), build(b))
            for p in a.rglob("*"):
                if p.is_file():
                    self.assertEqual(p.read_bytes(), (b / p.relative_to(a)).read_bytes())

    def test_bad_rule_fields_and_ip_families(self):
        for rule in ("DOMAIN,", "DOMAIN,example.com,PROXY", "IP-CIDR,2001:db8::/32",
                     "IP-CIDR,192.0.2.1/24", "RULE-SET,foo", "USER-AGENT,abc"):
            with self.assertRaises(ValueError):
                validate_rule(rule)
        validate_rule("IP-CIDR6,2001:db8::/32,no-resolve")

    def test_mirror_tampering_fails_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vendor").mkdir()
            (root / "vendor/test").write_text("changed")
            (root / "upstreams.lock.json").write_text(json.dumps(
                {"schema": 1, "files": [{"path": "vendor/test", "bytes": 7, "sha256": "0" * 64}]}))
            with self.assertRaises(ValueError):
                mirror_check(root)

    def test_preserve_base_and_materialize_geoip(self):
        original = self.base()
        backup = copy.deepcopy(original)
        result, converted = compose(original, "fixture-node")
        self.assertEqual(original, backup)
        self.assertEqual(result["proxy-groups"][:-1], original["proxy-groups"])
        self.assertEqual(result["dns"], original["dns"])
        self.assertEqual(result["rules"][-1], original["rules"][-1])
        self.assertEqual(result["proxy-groups"][-1]["proxies"], ["fixture-node"])
        self.assertEqual(converted[0]["source"], "CN")
        self.assertEqual(result["rule-providers"]["self-geoip-cn"]["type"], "inline")

    def test_no_nested_auto_ai_or_controller_injection(self):
        with self.assertRaises(ValueError):
            compose(self.base(), "GENERAL")
        base = self.base()
        base["external-controller"] = "127.0.0.1:9090"
        with self.assertRaises(ValueError):
            compose(base, "fixture-node")

    def test_remote_provider_is_not_an_offline_bundle(self):
        base = self.base()
        base["rule-providers"] = {"remote": {"type": "http", "url": "https://example.invalid/rules"}}
        with self.assertRaises(ValueError):
            compose(base, "fixture-node")

    def test_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "private.json"
            p.write_text("{}")
            p.chmod(0o644)
            with self.assertRaises(ValueError):
                read_private(str(p))
            p.chmod(0o600)
            self.assertEqual(read_private(str(p)), b"{}")

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_yaml(b"mode: rule\nmode: global\n")

    def test_proposals_require_evidence_and_remain_exact(self):
        report = {"schema": "clash-routing-observation-v1", "domain": "new.example.com",
                  "evidence": "insufficient"}
        self.assertEqual(propose(report, "ai")["decision"], "needs-evidence")
        report["evidence"] = "observed-route"
        self.assertEqual(propose(report, "ai")["candidate"], "DOMAIN,new.example.com")
        report["domain"] = "api.anthropic.com"
        self.assertEqual(propose(report, "ai")["decision"], "already-covered")
        report["profile_binding"] = {"stable_during_observation": False}
        self.assertEqual(propose(report, "ai")["decision"], "needs-evidence")


if __name__ == "__main__":
    unittest.main()
