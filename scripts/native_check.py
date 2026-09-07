#!/usr/bin/env python3
"""Verify pinned Mihomo syntax and routing using loopback-only fixture proxy sinks."""
import argparse
import gzip
import http.client
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from compose_profile import compose, read_private
from build import build
from ruleslib import ROOT, read_rules, sha256


def core_path(download=False):
    lock = json.loads((ROOT / "tooling.lock.json").read_text())
    key = platform.system() + "-" + platform.machine()
    if key not in lock["assets"]:
        raise ValueError("native fixture supports the locked Darwin arm64 and Linux x86_64 assets")
    asset = lock["assets"][key]
    directory = ROOT / ".cache/core"
    directory.mkdir(parents=True, exist_ok=True)
    packed = directory / (key + ".gz")
    if packed.is_symlink():
        raise ValueError("core archive must not be a symlink")
    if not packed.exists():
        if not download:
            raise ValueError("locked core is not cached; explicitly run with --download once")
        with urllib.request.urlopen(asset["url"], timeout=45) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if sha256(data) != asset["sha256"]:
            raise ValueError("downloaded core checksum mismatch")
        with packed.open("xb") as output:
            output.write(data)
    data = packed.read_bytes()
    if sha256(data) != asset["sha256"]:
        raise ValueError("cached core checksum mismatch")
    executable = directory / key
    unpacked = gzip.decompress(data)
    if executable.is_symlink():
        raise ValueError("core executable must not be a symlink")
    if executable.exists():
        if executable.read_bytes() != unpacked:
            raise ValueError("cached core executable differs from locked archive")
    else:
        with executable.open("xb") as output:
            output.write(unpacked)
        executable.chmod(0o700)
    version = subprocess.run([str(executable), "-v"], capture_output=True, timeout=5, check=True)
    if b"1.19.27" not in version.stdout:
        raise ValueError("core version mismatch")
    return executable


def native_test(core, path, home):
    result = subprocess.run([str(core), "-t", "-d", str(home), "-f", str(path)],
                            capture_output=True, timeout=30)
    if result.returncode:
        # Native parser diagnostics can contain private profile content.
        raise ValueError("native Mihomo validation failed; private diagnostic output suppressed")


def fixture(core):
    seen = []
    servers = []
    for policy in ("AI", "GENERAL"):
        def handler(policy_name):
            class Sink(socketserver.BaseRequestHandler):
                def read(self, size):
                    data = b""
                    while len(data) < size:
                        chunk = self.request.recv(size - len(data))
                        if not chunk:
                            raise OSError("fixture client closed early")
                        data += chunk
                    return data

                def handle(self):
                    self.request.settimeout(3)
                    greeting = self.read(2)
                    if greeting[0] != 5:
                        seen.append(("unexpected-greeting:" + greeting.hex(), policy_name))
                        return
                    self.read(greeting[1])
                    self.request.sendall(b"\x05\x00")
                    header = self.read(4)
                    if header != b"\x05\x01\x00\x03":
                        seen.append(("unexpected-header:" + header.hex(), policy_name))
                        return
                    host = self.read(self.read(1)[0]).decode("ascii")
                    self.read(2)
                    seen.append((host, policy_name))
                    self.request.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            return Sink
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler(policy))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
        with socket.socket() as controller_reservation:
            controller_reservation.bind(("127.0.0.1", 0))
            controller_port = controller_reservation.getsockname()[1]
    process = None
    temporary = None
    try:
        base = {"mixed-port": port, "bind-address": "127.0.0.1", "allow-lan": False,
                "ipv6": False, "mode": "rule", "log-level": "error",
                "dns": {"enable": True, "nameserver": ["rcode://success"], "enhanced-mode": "redir-host"},
                "proxies": [{"name": "fixture-ai", "type": "socks5", "server": "127.0.0.1",
                             "port": servers[0].server_address[1]},
                            {"name": "fixture-general", "type": "socks5", "server": "127.0.0.1",
                             "port": servers[1].server_address[1]}],
                "proxy-groups": [{"name": "GENERAL", "type": "select", "proxies": ["fixture-general"]}],
                "rules": ["MATCH,GENERAL"]}
        config, _ = compose(base, "fixture-ai", group="AI")
        # Parse every source category; use one harmless sink for non-AI policies.
        for source in sorted((ROOT / "rules").glob("*.list")):
            name = "fixture-" + source.stem
            config["rule-providers"][name] = {"type": "inline", "behavior": "classical",
                                              "payload": read_rules(source)}
        config["external-controller"] = f"127.0.0.1:{controller_port}"
        temporary = tempfile.TemporaryDirectory(prefix="clash-routing-fixture-")
        directory = temporary.name
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config))
        native_test(core, path, directory)
        process = subprocess.Popen([str(core), "-d", directory, "-f", str(path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError("fixture core exited before becoming ready")
            try:
                with opener.open(f"http://127.0.0.1:{controller_port}/providers/rules", timeout=.2) as response:
                    providers = json.load(response).get("providers") or {}
                # Listener readiness precedes asynchronous rule-provider initialization.
                if all((providers.get(name) or {}).get("ruleCount", 0) > 0 for name in config["rule-providers"]):
                    break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.05)
        else:
            raise ValueError("fixture core readiness timed out")
        cases = json.loads((ROOT / "tests/routing-cases.json").read_text())
        for case in cases:
            request = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                # HTTP forwarding forces an outbound dial; CONNECT can be acknowledged lazily.
                request.request("GET", "http://" + case["host"] + "/", headers={"Connection": "close"})
                request.getresponse().read(4096)
            except OSError:
                pass  # The local sink intentionally refuses after recording the route.
            finally:
                request.close()
            observed_deadline = time.monotonic() + 2
            while not any(host == case["host"] for host, _ in seen) and time.monotonic() < observed_deadline:
                time.sleep(.01)
            actual = [policy for host, policy in seen if host == case["host"]]
            if actual != [case["expected"]]:
                raise ValueError("native routing case failed: " + case["host"] + " observed=" + repr(seen))
        process.terminate()
        process.wait(timeout=5)
        process = None
        return len(cases)
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        if temporary is not None:
            temporary.cleanup()
        for server in servers:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly download a missing locked host core.")
    parser.add_argument("--profile", help="Additionally validate this mode-0600 private candidate; no profile output.")
    args = parser.parse_args()
    try:
        build()
        core = core_path(args.download)
        cases = fixture(core)
        digest = None
        if args.profile:
            raw = read_private(args.profile)
            digest = sha256(raw)
            with tempfile.TemporaryDirectory(prefix="clash-private-validation-") as directory:
                path = Path(directory) / "candidate.json"
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(raw)
                native_test(core, path, directory)
        print(json.dumps({"native_version": "1.19.27", "routing_cases_passed": cases,
                          "private_profile_sha256": digest, "hardware_validation": "not-performed"}))
    except Exception as error:
        message = str(error) if type(error) is ValueError else "native check failed: " + type(error).__name__
        print("error: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
