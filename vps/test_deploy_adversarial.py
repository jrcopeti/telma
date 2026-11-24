"""Adversarial tests for deploy.py, against the fake host (DRIFT_HOST_ROOT) and a bare temp origin.
Run: python3 -m unittest vps/test_deploy_adversarial.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy import TODAY, DeployFake  # noqa: E402


class Attack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")

    def tearDown(self):
        self.tmp.cleanup()

    # PLAN: "n one past the highest on that day, here or on origin"
    def test_tag_number_is_one_past_the_highest_not_the_first_gap(self):
        for n in (1, 3):
            self.f.git("tag", "-a", f"deploy/{TODAY}-{n}", "-m", "x")
            self.f.git("push", "-q", "origin", f"deploy/{TODAY}-{n}")
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-4 ", self.f.out)

    # PLAN: "here or on origin" -- a failed ls-remote must not silently drop origin's tags
    def test_a_failed_ls_remote_is_not_silently_ignored(self):
        self.f.git("tag", "-a", f"deploy/{TODAY}-1", "-m", "x")
        self.f.git("push", "-q", "origin", f"deploy/{TODAY}-1")
        self.f.git("tag", "-d", f"deploy/{TODAY}-1")  # on origin only
        real = shutil.which("git")
        shim = self.f.bin / "git"
        shim.write_text(f'#!/bin/sh\nfor a in "$@"; do [ "$a" = ls-remote ] && exit 128; done\nexec {real} "$@"\n')
        shim.chmod(0o755)
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertNotIn(f"tag: deploy/{TODAY}-1 ", self.f.out)

    # deploy.py docstring: "2 when nothing was copied"
    def test_a_no_exits_2_as_the_docstring_says(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="n\n"), 2, self.f.out)

    def test_a_symlink_only_exits_2_as_the_docstring_says(self):
        target = self.f.host / "elsewhere"
        target.write_text("echo a\n")
        (self.f.host / "h/a.sh").unlink()
        (self.f.host / "h/a.sh").symlink_to(target)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)

    # PLAN: `deployed` "marks the last commit known to match the host"; printed only when every line
    # is in sync. A dirty, unnamed manifest file that matches the host makes the re-check pass while
    # the commit the tag moves to doesn't match the host.
    def test_deployed_is_not_moved_to_a_commit_the_host_does_not_match(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.write_repo({"vps/hook.py": "print('hand fix')\n"})  # uncommitted, not named
        self.f.write_host("/home/agent/.hermes/agent-hooks/hook.py", "print('hand fix')\n", 0o755)
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertNotIn("deployed: moves", self.f.out)

    # PLAN: "It only prints what each file still needs after (`after` below)"; config's after is
    # restart-gateway. REASONED: the expected value is a reading of the plan.
    def test_config_commands_come_with_its_after(self):
        self.f.change({"vps/config.overrides.yaml": (self.f.repo / "vps/config.overrides.yaml").read_text()
                       .replace("default: m1", "default: m2")})
        self.f.deploy("vps/config.overrides.yaml")
        self.assertIn("restart her gateway", self.f.out)

    # A check that couldn't run is reported as drift (exit 1). REASONED: docstring maps 1 to "finds drift".
    def test_a_recheck_that_could_not_run_is_not_called_drift(self):
        (self.f.repo / ".git/info/private-values").unlink()  # check-drift needs it; a.sh doesn't
        self.f.change({"vps/a.sh": "echo a2\n"})
        code = self.f.deploy("vps/a.sh", answers="y\n")
        self.assertIn("check-drift exited 2", self.f.out)
        self.assertNotEqual(code, 1, self.f.out)

    # An interrupted earlier deploy leaves a temp file. Decided in the fix round: the deploy stops,
    # copying nothing, and names the file for the owner to look at (it is root acting in her folder).
    def test_a_leftover_temp_file_is_named_and_nothing_copied(self):
        self.f.write_host("/h/.a.sh.deploy-tmp", "half\n", 0o600)
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("/h/.a.sh.deploy-tmp is left from an earlier deploy", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")

    # AGENTS.md: a task that newly fails blocks the change. Any committed run is accepted, even one
    # whose every task failed. REASONED: the plan only says "needs --eval-run".
    def test_a_failing_eval_run_does_not_unlock_soul(self):
        self.f.change({"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"})
        run = "evals/results/2026-11-25T1000-x.jsonl"
        self.f.change({run: json.dumps({"task": "t", "status": "fail", "setup": {"telma_commit": "HEAD"}}) + "\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n"), 2, self.f.out)

    # PLAN table: a symlink on the path is "never followed"; deploy test says "never deployed through".
    # The folder is swapped for a symlink after COPY's check and before its write (race injected
    # the same way test_deploy.py's test_a_host_change_after_the_diff_stops_the_copy injects one).
    # Closed in the second fix round (owner): every path is opened part by part, O_NOFOLLOW, and later
    # steps work on the opened folder. The swap is injected right before the temp file is written.
    def test_a_folder_swapped_for_a_symlink_mid_copy_is_not_written_through(self):
        elsewhere = self.f.host / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "a.sh").write_text("echo a\n")  # what the copy reads for its backup
        h = self.f.host / "h"
        swap = (f"    if not os.path.exists({str(h) + '.real'!r}):\n"
                f"        os.rename({str(h)!r}, {str(h) + '.real'!r}); os.symlink({str(elsewhere)!r}, {str(h)!r})\n")
        script = self.f.repo / "vps/remote/deploy_host.py"
        src = script.read_text()
        anchor = '    write_new(dfd, tmp, base64.b64decode(f["data"])'
        self.assertIn(anchor, src)
        self.f.change({"vps/a.sh": "echo a2\n", "vps/remote/deploy_host.py": src.replace(anchor, swap + anchor, 1)})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertEqual((elsewhere / "a.sh").read_text(), "echo a\n", self.f.out)


if __name__ == "__main__":
    unittest.main()
