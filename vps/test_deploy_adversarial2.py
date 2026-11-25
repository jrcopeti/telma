"""Second adversarial round for deploy.py, against the fake host (DRIFT_HOST_ROOT) and a bare temp origin.
Run: python3 -m unittest vps/test_deploy_adversarial2.py"""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_drift import GIT_ENV  # noqa: E402
from test_deploy import HOOK, TODAY, DeployFake, run_line  # noqa: E402


class Attack2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")

    def tearDown(self):
        self.tmp.cleanup()

    def head(self):
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.f.repo, capture_output=True,
                              text=True).stdout.strip()

    def popen(self, *args, answers=""):
        master, slave = self.f.terminal(answers)
        p = subprocess.Popen(["python3", str(self.f.repo / "vps/deploy.py"), *args], cwd=self.f.repo,
                             env=self.f.env(), stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: (os.close(master), os.close(slave)))
        return p

    def wait_for(self, marker, timeout=30):
        end = time.time() + timeout
        while not marker.exists():
            self.assertLess(time.time(), end, "marker never appeared")
            time.sleep(0.05)

    # The backup's folders are made by root and chowned to the file's owner (agent), then root
    # copies the old file into them with copy2 (follows a symlink at the destination) and chowns
    # it (os.chown follows too). A symlink she plants in her new folder between the two is written
    # through. Not the Open race (a folder on the deployed file's path): this is the backup's path.
    def test_a_symlink_planted_at_the_backup_path_is_not_written_through(self):
        victim = self.f.host / "victim"
        victim.write_text("root's file\n")
        script = self.f.repo / "vps/remote/deploy_host.py"
        src = script.read_text()
        # Rewritten for the fixed copy: planted in the backup folder right before the old file is kept.
        anchor = "    write_new(folder, os.path.basename(p), data, os.geteuid()"
        self.assertIn(anchor, src)
        plant = f"    os.symlink({str(victim)!r}, os.path.basename(p), dir_fd=folder)\n"
        self.f.change({"vps/a.sh": "echo a2\n", "vps/remote/deploy_host.py": src.replace(anchor, plant + anchor, 1)})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertEqual(victim.read_text(), "root's file\n", self.f.out)

    # PLAN: "copies all the files in one quick step, so no job sees half the new files and half the
    # old"; the copy stages every file and stops before the swap on any problem. A folder at a host
    # path reads as `missing`, stages fine, and fails only at os.replace, after a.sh was swapped.
    def test_a_folder_at_a_host_path_does_not_leave_half_the_files_swapped(self):
        self.f.change({"vps/a.sh": "echo a2\n", "vps/hook.py": "print('hook 2')\n"})
        hook = self.f.host / HOOK.lstrip("/")
        hook.unlink()
        hook.mkdir()
        code = self.f.deploy("vps/a.sh", "vps/hook.py", answers="y\ny\n")
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n", f"exit {code}\n{self.f.out}")

    # check_eval_run's docstring: "A committed run". It checks the path is tracked, then reads the
    # working tree's bytes; preflight only checks vps/ for uncommitted changes.
    def test_an_uncommitted_edit_to_a_committed_eval_run_is_refused(self):
        old = self.head()
        run = "evals/results/2026-11-25T1000-x.jsonl"
        self.f.change({run: run_line(old)})  # before SOUL's change
        self.f.change({"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n"), 2, self.f.out)  # sanity
        (self.f.repo / run).write_text(run_line(self.head()))  # not committed
        code = self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n")
        self.assertEqual(code, 2, self.f.out)
        self.assertEqual(self.f.host_text("/h/SOUL.md"), "You keep Ana's brain.\n")

    # PLAN, deploy.py bullet: "`SOUL.md`, the skills and the model or fallback keys need
    # `--eval-run <results .jsonl>`, per `AGENTS.md`." The config line prints a ready
    # `hermes config set model.default …` with no eval run.
    def test_a_model_key_change_needs_an_eval_run(self):
        self.f.change({"vps/config.overrides.yaml": (self.f.repo / "vps/config.overrides.yaml").read_text()
                       .replace("default: m1", "default: m2")})
        self.f.deploy("vps/config.overrides.yaml")
        self.assertNotIn("hermes config set model.default m2", self.f.out)
        self.assertIn("--eval-run", self.f.out)

    # Docstring: "2 when nothing was copied ..., 4 when the copy ran but the check couldn't". A stop
    # raised after the copy (here the hook's after-step reading an invalid config.overrides.yaml)
    # falls to main's `except Stop`: exit 2 and "deploy: ..." though the hook was swapped, and no tag
    # commands (PLAN: "deploy.py ends by printing an annotated tag").
    def test_a_stop_after_the_copy_does_not_exit_nothing_copied(self):
        cfg = (self.f.repo / "vps/config.overrides.yaml").read_text() + "broken: [unclosed\n"
        self.f.change({"vps/hook.py": "print('hook 2')\n", "vps/config.overrides.yaml": cfg})
        code = self.f.deploy("vps/hook.py", answers="y\n")
        self.assertEqual(self.f.host_text(HOOK), "print('hook 2')\n", self.f.out)  # it was copied
        self.assertEqual(code, 4, self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-1 ", self.f.out)

    # Docstring: "3 when the copy may have run part way". Ctrl-C while the copy call runs (here
    # held in the running-jobs read) ends in a KeyboardInterrupt traceback: no exit 3, no word that
    # the copy may have run, no backup folder named. Over ssh the remote side keeps running.
    def test_an_interrupt_during_the_copy_exits_3(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        marker = Path(self.tmp.name) / "copy-started"
        wrapper = self.f.bin / "bash"
        wrapper.write_text(f"#!/bin/sh\n[ -e {marker} ] || {{ touch {marker}; sleep 3; }}\n"
                           f"exec {shutil.which('bash')} \"$@\"\n")
        wrapper.chmod(0o755)
        p = self.popen("vps/a.sh", answers="y\n")
        self.wait_for(marker)
        p.send_signal(signal.SIGINT)  # to deploy.py only, as when ssh's far end keeps running
        out = p.stdout.read()
        p.wait(30)
        self.assertEqual(p.returncode, 3, out)
        self.assertIn("may have run part way", out)

    # Docstring: "4 when the copy ran but the check couldn't"; PLAN: deploy.py "ends by printing" the
    # deploy tag. Ctrl-C during the re-check (its hooks doctor, an ssh call) after a copy that
    # succeeded: traceback, no exit 4, no tag commands for a deploy that happened.
    def test_an_interrupt_during_the_recheck_exits_4_and_still_prints_the_tag(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        marker = Path(self.tmp.name) / "doctor-started"
        hermes = self.f.bin / "hermes"
        hermes.write_text(f"#!/bin/sh\ntouch {marker}\nsleep 5\necho 'All shell hooks look healthy.'\n")
        hermes.chmod(0o755)
        p = self.popen("vps/a.sh", answers="y\n")
        self.wait_for(marker)
        p.send_signal(signal.SIGINT)
        out = p.stdout.read()
        p.wait(30)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a2\n", out)  # the copy ran
        self.assertEqual(p.returncode, 4, out)
        self.assertIn(f"tag: deploy/{TODAY}-1 ", out)

    # Two deploys on one day: the first one's tag, made with the owner's yes, is counted by the second.
    def test_two_deploys_the_same_day_get_two_tag_names(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        first = self.f.out
        self.f.change({"vps/a.sh": "echo a3\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-1 ", first)
        self.assertIn(f"tag: deploy/{TODAY}-2 ", self.f.out)

if __name__ == "__main__":
    unittest.main()
