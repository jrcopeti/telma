"""The scripts in evals/remote/ that run on the VPS, run here on temp folders, through the same
heredoc vps.py sends them in.

    python3 -m unittest evals/test_remote.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vps import py  # noqa: E402

PROC = Path("/proc/self/environ").exists()


def bash(script, cwd=None):
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + script], cwd=cwd, capture_output=True, text=True)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])


class SyncProfileTest(Tmp):
    TRIPWIRE = "command: /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/exfil-tripwire.py"
    CRON = "command: /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/cron-alert.py"

    def setUp(self):
        super().setUp()
        self.hers, self.prof = self.tmp / "hers", self.tmp / "home/profiles/eval"
        self.work = str(self.tmp / "eval/work/brain")
        self.hers.mkdir()
        self.prof.mkdir(parents=True)
        (self.hers / "SOUL.md").write_text("soul\n")
        (self.prof / ".env").write_text("OPENROUTER_API_KEY=k\nTERMINAL_DOCKER_VOLUMES=old\n")

    def sync(self, config, mounts=("/home/agent/brain:/home/agent/brain",)):
        (self.hers / "config.yaml").write_text(config)
        (self.hers / ".env").write_text("TERMINAL_DOCKER_VOLUMES=" + json.dumps(json.dumps(list(mounts))) + "\n")
        return bash(py("sync_profile.py", self.hers, self.prof, self.work))

    def test_points_the_profile_at_the_trial_folder_with_the_hooks_silenced(self):
        r = self.sync(f"mounts:\n  - /home/agent/brain/notes\nhooks:\n  - {self.TRIPWIRE}\n  - {self.CRON}\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = (self.prof / "config.yaml").read_text()
        self.assertIn(f"  - {self.work}/notes\n", cfg)
        self.assertNotIn("/home/agent/brain", cfg)
        self.assertIn(f"TRIPWIRE_BRAIN={self.work} TRIPWIRE_NO_POST=1 TRIPWIRE_STATE={self.tmp / 'eval/tripwire'} ", cfg)
        self.assertIn(f"CRON_ALERT_NO_POST=1 CRON_ALERT_JOBS={self.prof / 'cron/jobs.json'} "
                      f"CRON_ALERT_STATE={self.tmp / 'eval/cron-alert'} ", cfg)
        env = (self.prof / ".env").read_text()
        self.assertIn("OPENROUTER_API_KEY=k\n", env)
        vols = env.split("TERMINAL_DOCKER_VOLUMES=")[1].strip()
        self.assertEqual(json.loads(json.loads(vols)), [f"{self.work}:/home/agent/brain"])
        self.assertEqual((self.prof / "SOUL.md").read_text(), "soul\n")

    def test_stops_when_the_tripwire_would_post(self):
        r = self.sync("mounts:\n  - /home/agent/brain\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tripwire would post", r.stderr)
        self.assertFalse((self.prof / "config.yaml").exists())

    def test_stops_when_a_cron_alert_hook_would_post(self):
        r = self.sync(f"hooks:\n  - {self.TRIPWIRE}\n  - command: /usr/bin/python3 /home/agent/.hermes/agent-hooks/cron-alert.py\n")
        self.assertIn("cron alert would post", r.stderr)

    def test_stops_on_a_mount_outside_the_trial_folder(self):
        r = self.sync(f"hooks:\n  - {self.TRIPWIRE}\n", mounts=("/home/agent/brain:/b", "/etc:/etc"))
        self.assertIn("a mount outside the trial folder", r.stderr)
        self.assertEqual((self.prof / ".env").read_text(), "OPENROUTER_API_KEY=k\nTERMINAL_DOCKER_VOLUMES=old\n")


class CollectTest(Tmp):
    def setUp(self):
        super().setUp()
        self.out, self.prof, self.alerts = self.tmp / "out", self.tmp / "profile", self.tmp / "cron-alert"
        for d in (self.out, self.prof / "cron/output/job1", self.alerts):
            d.mkdir(parents=True)
        files = {"t0.txt": "100.5\n", "t1.txt": "130.0\n", "usage0.json": '{"model": "m"}', "usage1.json": '{"model": "n"}',
                 "exit0.txt": "0\n", "exit1.txt": "124\n", "key0.txt": "1.5\n", "key1.txt": "null\n",
                 "events0.jsonl": '{"type": "a"}\n', "events1.jsonl": '{"type": "b"}\n{"ty'}
        for name, text in files.items():
            (self.out / name).write_text(text)

    def collect(self):
        r = bash(py("collect.py", self.prof, self.alerts), cwd=self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_reads_one_trial(self):
        (self.prof / "cron/jobs.json").write_text('{"jobs": [{"id": "x"}]}')
        (self.prof / "cron/output/job1/run.md").write_text("ran")
        (self.alerts / "alerts.log").write_text("⏰ cron create x\nhook failed\n⏰ cron remove x\n")
        d = self.collect()
        self.assertEqual(d["seconds"], 29.5)
        self.assertEqual(d["usage"], [{"model": "m"}, {"model": "n"}])
        self.assertEqual(d["exits"], [0, 124])
        self.assertEqual(d["key"], [1.5, None])
        self.assertEqual(d["cron"], [1, 1, 2])
        self.assertEqual(d["events"], ['{"type": "a"}\n', '{"type": "b"}\n', '{"ty'])

    def test_no_cron_files_count_as_none(self):
        self.assertEqual(self.collect()["cron"], [0, 0, 0])

    def test_a_jobs_file_that_wont_parse_counts_as_minus_one(self):
        (self.prof / "cron/jobs.json").write_text("{")
        self.assertEqual(self.collect()["cron"][0], -1)

    def test_a_jobs_list_or_an_empty_jobs_key(self):
        (self.prof / "cron/jobs.json").write_text('[{"id": "x"}, {"id": "y"}]')
        self.assertEqual(self.collect()["cron"][0], 2)
        (self.prof / "cron/jobs.json").write_text('{"jobs": null}')
        self.assertEqual(self.collect()["cron"][0], 0)


class KeySpendTest(Tmp):
    def test_no_key_writes_null(self):
        (self.tmp / ".env").write_text("OTHER=1\n")
        r = bash(py("key_spend.py", self.tmp / ".env", 0, out="key.txt", or_else="echo null > key.txt"), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.tmp / "key.txt").read_text(), "null\n")


class StopGatewayTest(Tmp):
    def stop(self, *locks):
        return bash(py("stop_gateway.py", self.tmp / "home", *locks, or_else="true"))

    def test_unreadable_locks_and_missing_pids_never_fail(self):
        (self.tmp / "bad.lock").write_text("not json")
        (self.tmp / "gone.lock").write_text('{"pid": 999999}')
        r = self.stop(self.tmp / "bad.lock", self.tmp / "gone.lock", self.tmp / "missing.lock")
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(PROC, "reads /proc/<pid>/environ: Linux only")
    def test_stops_only_a_gateway_of_the_eval_home(self):
        # Started in the background of a shell that exits, so init reaps them, not this test: a
        # killed child of the test would stay a zombie and keep /proc/<pid> until the test waits.
        pids = {}
        for name, home in (("eval", self.tmp / "home"), ("eval-profile", self.tmp / "home/profiles/eval"),
                           ("hers", self.tmp / "home-not-eval")):
            out = subprocess.run(["sh", "-c", "sleep 60 >/dev/null 2>&1 & echo $!"], capture_output=True, text=True,
                                 env={**os.environ, "HERMES_HOME": str(home)}, check=True).stdout
            pids[name] = int(out)
            self.addCleanup(subprocess.run, ["kill", "-9", str(pids[name])], capture_output=True)
            (self.tmp / f"{name}.lock").write_text(json.dumps({"pid": pids[name]}))
        start = time.monotonic()
        self.stop(*(self.tmp / f"{n}.lock" for n in pids))
        alive = lambda pid: Path(f"/proc/{pid}").exists()  # noqa: E731
        self.assertFalse(alive(pids["eval"]))
        self.assertFalse(alive(pids["eval-profile"]))
        self.assertTrue(alive(pids["hers"]))
        self.assertLess(time.monotonic() - start, 10)


class HeredocTest(unittest.TestCase):
    def test_every_remote_script_fits_in_the_heredoc(self):
        for f in sorted((Path(__file__).resolve().parent / "remote").glob("*.py")):
            with self.subTest(script=f.name):
                self.assertTrue(py(f.name).endswith("\nEOF_PY\n"))


if __name__ == "__main__":
    unittest.main()
