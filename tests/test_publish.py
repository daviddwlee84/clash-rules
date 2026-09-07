import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish


class PublishTests(unittest.TestCase):
    def test_local_remote_preserves_history_and_refuses_tag_rewrite(self):
        # All Git objects, commits, tags and pushes are confined to temporary fixture repos.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            remote = Path(directory) / "remote.git"
            root.mkdir()
            env = {**os.environ, "GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture",
                   "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
            def git(*args, cwd=root):
                return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            (root / "README").write_text("public fixture\n")
            git("add", "README")
            git("commit", "-m", "fixture source")
            git("remote", "add", "origin", str(remote))
            git("push", "-u", "origin", "main")
            source = git("rev-parse", "HEAD")
            data = {"version": "a" * 64, "content": "first"}
            def build(output=None):
                manifest = {"version": data["version"]}
                if output is not None:
                    output.mkdir()
                    (output / "manifest.json").write_text(json.dumps(manifest))
                    (output / "rules.list").write_text(data["content"])
                return manifest
            ci = {**env, "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
                  "GITHUB_SHA": source, "GITHUB_EVENT_NAME": "push"}
            with (patch.object(publish, "ROOT", root), patch.object(publish, "build", side_effect=build),
                  patch.dict(os.environ, ci), patch.object(sys, "argv", ["publish.py", "--publish"]),
                  contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                self.assertEqual(publish.main(), 0)
                first = git("rev-parse", "refs/heads/release", cwd=remote)
                self.assertEqual(publish.main(), 0)
                self.assertEqual(git("rev-parse", "refs/heads/release", cwd=remote), first)
                data.update(version="b" * 64, content="second")
                self.assertEqual(publish.main(), 0)
                second = git("rev-parse", "refs/heads/release", cwd=remote)
                self.assertEqual(git("rev-parse", second + "^", cwd=remote), first)
                data["content"] = "different bytes under same version"
                self.assertEqual(publish.main(), 1)
                self.assertEqual(git("rev-parse", "refs/heads/release", cwd=remote), second)
                self.assertEqual(git("rev-parse", "refs/tags/rules-" + "b" * 64, cwd=remote), second)

    def test_preview_performs_no_git_operation(self):
        with (patch.object(sys, "argv", ["publish.py"]), patch.object(publish, "git") as git,
              patch.object(publish, "build", return_value={"version": "a" * 64}),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(publish.main(), 0)
            git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
