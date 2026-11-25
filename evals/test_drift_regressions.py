"""Regressions the adversarial round found in the drift.txt change: the public file must not leak, and a
bad check or file must never stop a run or its report."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval_profile  # noqa: E402
import report  # noqa: E402
from test_report import SETUP, run  # noqa: E402

IP = "203.0.113.77"


class LeakTest(unittest.TestCase):
    def test_a_failed_ssh_does_not_put_the_hosts_ip_in_the_public_drift_file(self):
        """check-drift.py's reading failure prints ssh's stderr tail; ssh names the resolved address."""
        with tempfile.TemporaryDirectory() as d:
            ssh = Path(d, "ssh")
            ssh.write_text(f"#!/bin/sh\necho 'ssh: connect to host {IP} port 22: Operation timed out' >&2\nexit 255\n")
            ssh.chmod(ssh.stat().st_mode | stat.S_IEXEC)
            env = {**os.environ, "PATH": d + os.pathsep + os.environ["PATH"]}
            env.pop("DRIFT_HOST_ROOT", None)
            with unittest.mock.patch.dict(os.environ, env, clear=True):
                text = eval_profile.drift_report()
        self.assertNotIn(IP, text, text)

    def test_the_report_does_not_quote_a_stderr_line_with_an_ip(self):
        """No `summary:` line (exit 2): report.py quotes lines[0], the raw stderr."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "2026-11-02T1000-bbb.jsonl")
            p.write_text("".join(json.dumps(r) + "\n" for r in run({"a": ["pass"]}, k=1)))
            p.with_suffix(".drift.txt").write_text(f"check-drift: reading the host failed (255): connect to {IP}\nexit 2\n")
            with unittest.mock.patch.object(report, "K", 1):
                text = report.report(p, full={"a"})[1]
        self.assertNotIn(IP, text)


class RobustTest(unittest.TestCase):
    def test_a_file_line_that_starts_with_hermes_or_hooks_is_not_rewritten(self):
        out = ("hermes/SOUL.md".ljust(44) + " repo ahead agent:agent 644 abc123\n"
               + "hermes".ljust(44) + " ok\n" + "hooks".ljust(44) + " 3 not approved\n")
        with unittest.mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout=out.encode(), stderr=b"")):
            text = eval_profile.drift_report()
        self.assertEqual(text, out.splitlines()[0] + "\nhermes ok\nhooks not ok\nexit 1\n")

    def test_non_utf8_output_does_not_crash_the_run(self):
        with unittest.mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout=b"\xff\nsummary: x\n", stderr=b"")):
            text = eval_profile.drift_report()  # run.py calls it bare, before sync_profile
        self.assertTrue(text.endswith("summary: x\nexit 1\n"))

    def test_a_non_utf8_drift_file_does_not_break_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "2026-11-02T1000-bbb.jsonl")
            p.write_text("".join(json.dumps(r) + "\n" for r in run({"a": ["pass"]}, k=1)))
            p.with_suffix(".drift.txt").write_bytes(b"\xff\xfe\nexit 1\n")
            with unittest.mock.patch.object(report, "K", 1):
                report.report(p, full={"a"})

    def test_an_empty_drift_file_is_not_quoted_as_a_summary(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "2026-11-02T1000-bbb.jsonl")
            p.write_text("".join(json.dumps(r) + "\n" for r in run({"a": ["pass"]}, k=1)))
            p.with_suffix(".drift.txt").write_text("")
            with unittest.mock.patch.object(report, "K", 1):
                text = report.report(p, full={"a"})[1]
        self.assertNotIn("(no exit)", text)

    def test_old_rows_with_config_sha_do_not_show_as_a_setup_change(self):
        old = {**SETUP, "config_sha": "c1", "eval_config_sha": "ec"}
        a = report.summarize([{**r, "setup": old} for r in run({"a": ["pass"]}, k=1)], {"a"})
        b = report.summarize(run({"a": ["pass"]}, k=1), {"a"})
        self.assertNotIn("config_sha", report.changes(b, a)["setup"])


if __name__ == "__main__":
    unittest.main()
