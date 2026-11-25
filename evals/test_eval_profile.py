"""Tests for evals/eval_profile.py's repo SOUL.md: what it sends to the VPS and what it stamps.

    python3 -m unittest evals/test_eval_profile.py
"""
import base64
import subprocess
import sys
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval_profile  # noqa: E402


class Sent:
    """The scripts eval_profile sends to the VPS, with `stdout` as the reply of the stamp's read."""

    def __init__(self, stdout=""):
        self.scripts, self.stdout = [], stdout

    def __call__(self, script, check=True):
        self.scripts.append(script)
        return types.SimpleNamespace(stdout=self.stdout, returncode=0)


class RepoSoulTest(unittest.TestCase):
    def test_the_profile_gets_the_repos_bytes_after_hers_and_only_when_asked(self):
        soul = "You keep Ana's brain.\n".encode()
        with unittest.mock.patch.object(eval_profile, "vps", sent := Sent()):
            eval_profile.sync_profile()
            eval_profile.sync_profile(soul)
        plain, repo = sent.scripts
        self.assertNotIn("EOF_SOUL", plain)
        self.assertIn(base64.b64encode(soul).decode(), repo)
        self.assertGreater(repo.index("EOF_SOUL"), repo.index("shutil.copy2(hers / \"SOUL.md\""))  # hers first, then replaced

    def test_the_stamp_says_which_soul_it_tested(self):
        reply = "Hermes 1\nhost\neval\nc\nec\n"
        with unittest.mock.patch.object(eval_profile, "vps", Sent(reply)):
            host = eval_profile.setup_stamp("b")
            repo = eval_profile.setup_stamp("b", "abc123abc123")
        self.assertEqual((host["soul_source"], "repo_soul_sha" in host), ("host", False))
        self.assertEqual((repo["soul_source"], repo["repo_soul_sha"], repo["eval_soul_sha"]), ("repo", "abc123abc123", "eval"))

    def test_uncommitted_changes_to_the_repos_soul_stop_the_run(self):
        dirty = subprocess.CompletedProcess([], 0, stdout=" M vps/hermes/SOUL.md\n")
        with unittest.mock.patch.object(subprocess, "run", return_value=dirty):
            with self.assertRaises(SystemExit) as e:
                eval_profile.repo_soul()
        self.assertIn("uncommitted", str(e.exception))


if __name__ == "__main__":
    unittest.main()
