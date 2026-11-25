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

    def test_an_empty_repo_soul_is_still_copied(self):
        with unittest.mock.patch.object(eval_profile, "vps", sent := Sent()):
            eval_profile.sync_profile(b"")
        self.assertIn("EOF_SOUL", sent.scripts[0])

    def test_the_stamp_says_which_soul_it_tested(self):
        reply = "Hermes 1\nsoul=host\neval=eval\n"
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


class StampTest(unittest.TestCase):
    def test_the_stamp_carries_the_two_soul_hashes_and_no_config_hashes(self):
        with unittest.mock.patch.object(eval_profile, "vps", Sent("Hermes 1\nsoul=host\neval=eval\n")):
            stamp = eval_profile.setup_stamp("b")
        self.assertEqual((stamp["soul_sha"], stamp["eval_soul_sha"]), ("host", "eval"))
        self.assertFalse({"config_sha", "eval_config_sha"} & stamp.keys())

    def test_a_missing_file_does_not_shift_the_other_hash(self):
        with unittest.mock.patch.object(eval_profile, "vps", Sent("Hermes 1\nsoul=\neval=eval\n")):
            stamp = eval_profile.setup_stamp("b")
        self.assertEqual((stamp["soul_sha"], stamp["eval_soul_sha"]), ("", "eval"))

    def test_a_copy_that_is_not_what_the_run_meant_to_test_is_named(self):
        host = {"soul_source": "host", "soul_sha": "h1", "eval_soul_sha": "h1"}
        repo = {"soul_source": "repo", "soul_sha": "h1", "repo_soul_sha": "r1", "eval_soul_sha": "r1"}
        self.assertIsNone(eval_profile.soul_copy_problem(host))
        self.assertIsNone(eval_profile.soul_copy_problem(repo))
        for stamp in ({**host, "eval_soul_sha": "other"}, {**host, "eval_soul_sha": ""},
                      {**repo, "eval_soul_sha": "h1"}, {**repo, "eval_soul_sha": ""}):
            with self.subTest(stamp=stamp):
                self.assertIn("SOUL.md", eval_profile.soul_copy_problem(stamp))


def finished(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout.encode(), stderr=stderr.encode())


class DriftReportTest(unittest.TestCase):
    def run_report(self, **kw):
        with unittest.mock.patch.object(subprocess, "run", **kw) as run:
            return eval_profile.drift_report(), run

    def test_it_is_the_checks_output_and_its_exit_code(self):
        text, run = self.run_report(return_value=finished("a  in sync\nsummary: 1 of 1 in sync\n", code=0))
        self.assertEqual(text, "a  in sync\nsummary: 1 of 1 in sync\nexit 0\n")
        self.assertEqual(run.call_args.args[0][1:], [str(eval_profile.REPO / "vps/check-drift.py")])

    def test_the_hosts_own_text_on_the_hermes_and_hooks_lines_is_dropped(self):
        out = ("a  in sync\n" + "hermes".ljust(44) + " differs: agent 203.0.113.7abc\n" + "hooks".ljust(44)
               + " hook failed at /home/x\nsummary: 1 of 1 in sync, hermes differs, hooks not ok, deployed abc\n")
        text, _ = self.run_report(return_value=finished(out, code=1))
        self.assertEqual(text, "a  in sync\nhermes differs\nhooks not ok\nsummary: 1 of 1 in sync, hermes differs, hooks not ok, deployed abc\nexit 1\n")
        ok, _ = self.run_report(return_value=finished("hermes".ljust(44) + " ok abc\nhooks".ljust(44) + " ok\n"))
        self.assertIn("hermes ok\n", ok)

    def test_drift_is_recorded_not_raised(self):
        text, _ = self.run_report(return_value=finished("SOUL.md  repo ahead\nsummary: 0 of 1 in sync\n", code=1))
        self.assertTrue(text.endswith("exit 1\n"))

    def test_a_check_that_could_not_run_keeps_its_stderr_out_of_the_public_file(self):
        text, _ = self.run_report(return_value=finished(stderr="check-drift: connect to host 203.0.113.7\n", code=2))
        self.assertEqual(text, "exit 2\n")

    def test_a_check_that_hangs_or_is_missing_never_stops_the_run(self):
        for err in (subprocess.TimeoutExpired("x", 1), OSError("no python")):
            with self.subTest(err=err):
                text, _ = self.run_report(side_effect=err)
                self.assertIn("check did not run", text)


if __name__ == "__main__":
    unittest.main()
