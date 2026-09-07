#!/usr/bin/env python3
"""Publish validated artifacts without rewriting release history; preview by default."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build import build
from ruleslib import ROOT


def git(*args, data=None, env=None, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True,
                          env=env, check=check).stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Write objects and push; only in GitHub Actions on main.")
    args = parser.parse_args()
    try:
        manifest = build()
        tag = "rules-" + manifest["version"]
        if not args.publish:
            print(json.dumps({"dry_run": True, "branch": "release", "immutable_tag": tag}))
            return 0
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("GITHUB_REF") != "refs/heads/main"
                or os.environ.get("GITHUB_EVENT_NAME") == "pull_request"):
            raise ValueError("publishing requires the main-branch GitHub Actions workflow")
        source = git("rev-parse", "HEAD")
        if source != os.environ.get("GITHUB_SHA"):
            raise ValueError("source checkout does not match the workflow commit")
        git("fetch", "origin", "--tags")
        parent = git("rev-parse", "--verify", "refs/remotes/origin/release", check=False)
        existing = git("rev-parse", "--verify", "refs/tags/" + tag, check=False)
        with tempfile.TemporaryDirectory(prefix="clash-release-") as directory:
            output = Path(directory) / "dist"
            build(output)
            index = Path(directory) / "index"
            env = {**os.environ, "GIT_INDEX_FILE": str(index),
                   "GIT_AUTHOR_NAME": "github-actions[bot]", "GIT_COMMITTER_NAME": "github-actions[bot]",
                   "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                   "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
            git("read-tree", "--empty", env=env)
            for path in sorted(p for p in output.rglob("*") if p.is_file()):
                blob = git("hash-object", "-w", "--stdin", data=path.read_bytes())
                git("update-index", "--add", "--cacheinfo", "100644", blob,
                    path.relative_to(output).as_posix(), env=env)
            tree = git("write-tree", env=env)
            if existing and git("rev-parse", tag + "^{tree}") != tree:
                raise ValueError("immutable artifact tag already exists with different content")
            previous_tree = git("rev-parse", parent + "^{tree}") if parent else None
            commit = parent if previous_tree == tree else git(
                "commit-tree", tree, *(["-p", parent] if parent else []),
                data=f"build: {tag}\n\nSource-Commit: {source}\n".encode(), env=env)
            refs = [commit + ":refs/heads/release"]
            if not existing:
                refs.append(commit + ":refs/tags/" + tag)
            # No force: a concurrent remote update fails instead of discarding history.
            git("push", "--atomic", "origin", *refs)
        print(json.dumps({"published": True, "version": manifest["version"], "source": source}))
        return 0
    except Exception as error:
        message = str(error) if type(error) is ValueError else "publication failed: " + type(error).__name__
        print("error: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
