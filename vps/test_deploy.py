"""Tests for deploy.py against a fake host folder (DRIFT_HOST_ROOT), a throwaway repo and its bare origin.
Run: python3 -m unittest vps/test_deploy.py"""
import json
import os
import pty
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_drift import GIT_ENV, OWNER, Fake  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "deploy.py"
EXECUTIONS = "home/agent/.hermes/cron/executions.db"
BACKUPS = "home/agent/.hermes/deploy-backups"
HOOK = "/home/agent/.hermes/agent-hooks/hook.py"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


class DeployFake(Fake):
    """Fake's repo and host, plus deploy.py, a hook, an origin to push to and her cron ledger."""

    def __init__(self, tmp):
        super().__init__(tmp)
        shutil.copy(SCRIPT, self.repo / "vps/deploy.py")
        shutil.copytree(SCRIPT.parent / "remote", self.repo / "vps/remote")
        m = self.repo / "vps/deploy.manifest"
        self.write_repo({"vps/hook.py": "print('hook')\n", "vps/deploy.manifest": m.read_text()
                         + f"vps/hook.py  {HOOK}  exact  {OWNER}  755  reapprove-hook\n",
                         "vps/config.overrides.yaml": (self.repo / "vps/config.overrides.yaml").read_text()
                         + f"hooks:\n  pre_tool_call:\n    - matcher: web\n      command: /usr/bin/python3 -I {HOOK}\n"})
        self.write_host(HOOK, "print('hook')\n", 0o755)
        self.write_host("/h/config.yaml", (self.host / "h/config.yaml").read_text()
                        + f"hooks:\n  pre_tool_call:\n  - matcher: web\n    command: /usr/bin/python3 -I {HOOK}\n", 0o600)
        self.commit()
        self.origin = tmp / "origin.git"
        self.git("init", "-q", "--bare", str(self.origin), cwd=tmp)
        self.git("remote", "add", "origin", str(self.origin))
        self.git("branch", "-M", "main")
        self.push()
        db = self.host / EXECUTIONS
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db) as c:
            c.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL)")
            c.execute("INSERT INTO executions VALUES ('e1', 'job-a', 'completed')")

    def push(self):
        self.git("push", "-q", "origin", "main")

    def change(self, files):
        self.write_repo(files)
        self.commit()
        self.push()

    def running(self, job_id):
        with sqlite3.connect(self.host / EXECUTIONS) as c:
            c.execute("INSERT INTO executions VALUES ('e2', ?, 'running')", (job_id,))

    def env(self):
        return {**os.environ, **GIT_ENV, "DRIFT_HOST_ROOT": str(self.host), "PATH": f"{self.bin}:{os.environ['PATH']}"}

    def terminal(self, answers):
        """A pseudo-terminal with the owner's answers typed ahead, then Ctrl-D for every prompt after
        them: deploy.py only runs at a terminal. Returns (master, slave); the caller closes both."""
        master, slave = pty.openpty()
        os.write(master, answers.encode() + b"\x04" * 40)
        return master, slave

    def deploy(self, *args, answers="", tty=True):
        master, slave = self.terminal(answers) if tty else (None, None)
        try:
            r = subprocess.run(["python3", str(self.repo / "vps/deploy.py"), *args], cwd=self.repo, env=self.env(),
                               stdin=slave if tty else None, input=None if tty else answers,
                               capture_output=True, text=True)
        finally:
            for fd in (master, slave):
                if fd is not None:
                    os.close(fd)
        self.code, self.out = r.returncode, r.stdout + r.stderr
        return self.code

    def lg(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True).stdout.strip()

    def head(self):
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo, capture_output=True,
                              text=True).stdout.strip()

    def host_text(self, path):
        return (self.host / path.lstrip("/")).read_text()

    def backups(self):
        folder = self.host / BACKUPS
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def leftovers(self):
        return [p for p in self.host.rglob("*.deploy-tmp")]


class Deploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")

    def tearDown(self):
        self.tmp.cleanup()

    def test_deploys_a_file_backs_up_the_old_one_and_rechecks_in_sync(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a2\n")
        self.assertEqual(oct((self.f.host / "h/a.sh").stat().st_mode & 0o7777), "0o755")
        [backup] = self.f.backups()
        self.assertEqual((backup / "h/a.sh").read_text(), "echo a\n")
        self.assertIn("--- host /h/a.sh", self.f.out)
        self.assertIn("+echo a2", self.f.out)
        self.assertIn("(repo ahead)", self.f.out)
        self.assertIn("summary: 6 of 6 in sync", self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-1 ", self.f.out)
        self.assertIn("  files: vps/a.sh", self.f.out)
        self.assertIn("  after the copy: summary: 6 of 6 in sync", self.f.out)
        self.assertIn("deployed: moves", self.f.out)
        self.assertEqual(self.f.leftovers(), [])

    def test_a_no_copies_nothing(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="n\n"), 2, self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")
        self.assertIn("nothing deployed", self.f.out)
        self.assertEqual(self.f.backups(), [])

    def test_every_answer_comes_before_any_copy(self):
        self.f.change({"vps/a.sh": "echo a2\n", "vps/hook.py": "print('hook 2')\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", "vps/hook.py", answers="y\nq\n"), 2, self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")
        self.assertEqual(self.f.backups(), [])
        self.assertEqual(self.f.deploy("vps/a.sh", "vps/hook.py", answers="y\n"), 2, self.f.out)  # stdin ends: q
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")

    def test_a_running_job_stops_the_copy_and_leaves_nothing_behind(self):
        self.f.change({"vps/a.sh": "echo a2\n", "vps/hook.py": "print('hook 2')\n"})
        self.f.running("job-b")
        self.assertEqual(self.f.deploy("vps/a.sh", "vps/hook.py", answers="y\ny\n"), 2, self.f.out)
        self.assertIn("a job of hers is running (job id job-b)", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")
        self.assertEqual(self.f.host_text(HOOK), "print('hook')\n")
        self.assertEqual(self.f.leftovers(), [])
        self.assertFalse((self.f.host / BACKUPS).exists() and any((self.f.host / BACKUPS).iterdir()))

    def test_an_unreadable_ledger_stops_the_copy(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        (self.f.host / EXECUTIONS).unlink()
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("couldn't read her running jobs", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")

    def test_a_new_file_is_created_with_its_owner_and_mode(self):
        (self.f.host / "h/a.sh").unlink()
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertIn("(missing)", self.f.out)
        self.assertEqual(oct((self.f.host / "h/a.sh").stat().st_mode & 0o7777), "0o755")

    def test_a_mode_change_alone_is_deployed(self):
        (self.f.host / "h/a.sh").chmod(0o777)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertIn(f"owner and mode: {OWNER} 777 -> {OWNER} 755", self.f.out)
        self.assertEqual(oct((self.f.host / "h/a.sh").stat().st_mode & 0o7777), "0o755")

    def test_in_sync_is_not_asked(self):
        self.assertEqual(self.f.deploy("vps/a.sh"), 2, self.f.out)
        self.assertIn("already in sync", self.f.out)
        self.assertEqual(self.f.backups(), [])

    def test_a_hand_edit_on_the_host_is_named_before_the_yes(self):
        self.f.write_host("/h/a.sh", "echo hand edit\n", 0o755)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertIn("(host ahead)", self.f.out)
        self.assertIn("deploying overwrites it", self.f.out)
        [backup] = self.f.backups()
        self.assertEqual((backup / "h/a.sh").read_text(), "echo hand edit\n")

    def test_a_symlink_on_the_host_is_never_deployed_through(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        target = self.f.host / "elsewhere"
        target.write_text("echo a\n")
        (self.f.host / "h/a.sh").unlink()
        (self.f.host / "h/a.sh").symlink_to(target)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("is a symlink: not deployed", self.f.out)
        self.assertEqual(target.read_text(), "echo a\n")
        self.assertTrue((self.f.host / "h/a.sh").is_symlink())

    def test_redacted_files_are_filled_and_need_an_eval_run(self):
        self.f.change({"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"})
        self.assertEqual(self.f.deploy("vps/SOUL.md", answers="y\n"), 2, self.f.out)
        self.assertIn("needs --eval-run", self.f.out)
        run = "evals/results/2026-11-25T1000-x.jsonl"
        self.f.change({run: json.dumps({"setup": {"telma_commit": "0" * 7}}) + "\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n"), 2, self.f.out)
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.f.repo, capture_output=True,
                              text=True).stdout.strip()
        self.f.change({run: json.dumps({"setup": {"telma_commit": head}}) + "\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.f.host_text("/h/SOUL.md"), "You keep Ana's brain well.\n")
        self.assertIn("takes effect in her next chat", self.f.out)

    def test_an_eval_run_from_before_the_change_is_refused(self):
        run = "evals/results/2026-11-25T1000-x.jsonl"
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.f.repo, capture_output=True,
                              text=True).stdout.strip()
        self.f.change({run: json.dumps({"setup": {"telma_commit": head}}) + "\n"})
        self.f.change({"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/SOUL.md", answers="y\n"), 2, self.f.out)
        self.assertIn("without vps/SOUL.md's last change", self.f.out)

    def test_an_uncommitted_eval_run_is_refused(self):
        self.f.change({"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"})
        run = self.f.repo / "evals/results/local.jsonl"
        run.parent.mkdir(parents=True)
        run.write_text(json.dumps({"setup": {"telma_commit": "HEAD"}}) + "\n")
        self.assertEqual(self.f.deploy("--eval-run", str(run), "vps/SOUL.md", answers="y\n"), 2, self.f.out)
        self.assertIn("not a committed results .jsonl", self.f.out)

    def test_only_main_as_pushed_is_deployed(self):
        self.f.write_repo({"vps/a.sh": "echo a2\n"})
        self.f.commit()  # not pushed
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("deploy main as pushed", self.f.out)
        self.f.push()
        self.f.write_repo({"vps/a.sh": "echo a3\n"})  # uncommitted
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("uncommitted changes", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")

    def test_a_path_not_in_the_manifest_stops(self):
        self.assertEqual(self.f.deploy("vps/nope.sh"), 2, self.f.out)
        self.assertIn("not in vps/deploy.manifest: vps/nope.sh", self.f.out)

    def test_config_jobs_and_skills_are_printed_not_copied(self):
        self.f.change({"vps/config.overrides.yaml": (self.f.repo / "vps/config.overrides.yaml").read_text()
                       .replace("default: m1", "default: m2")})
        config = self.f.host_text("/h/config.yaml")
        self.assertEqual(self.f.deploy("vps/config.overrides.yaml", "vps/jobs.overrides.yaml"), 2, self.f.out)
        self.assertNotIn("hermes config set model.default", self.f.out)
        self.assertIn("fallback_providers, model: not printed without --eval-run", self.f.out)
        self.assertIn("hermes config set terminal.docker_volumes '[\"/a:/b\"]'", self.f.out)
        self.assertNotIn("config set hooks", self.f.out)
        self.assertIn("jobs.json isn't written here", self.f.out)
        self.assertEqual(self.f.deploy("vps/skills/"), 2, self.f.out)
        self.assertIn("vps/skills/ needs --eval-run", self.f.out)
        run = "evals/results/2026-11-25T1000-x.jsonl"
        self.f.change({run: json.dumps({"setup": {"telma_commit": self.f.head()}}) + "\n"})
        self.assertEqual(self.f.deploy("--eval-run", run, "vps/config.overrides.yaml", "vps/skills/"), 2, self.f.out)
        self.assertIn("hermes config set model.default m2", self.f.out)
        self.assertIn("PR on the brain repo", self.f.out)
        self.assertEqual(self.f.host_text("/h/config.yaml"), config)

    def test_a_hook_prints_its_reapproval_and_the_tag_waits(self):
        self.f.change({"vps/hook.py": "print('hook 2')\n"})
        self.f.doctor("1 issue(s) found.  Fix before relying on these hooks.")  # modified since approval
        self.assertEqual(self.f.deploy("vps/hook.py", answers="y\n"), 1, self.f.out)
        self.assertIn(f"hermes hooks revoke '/usr/bin/python3 -I {HOOK}'", self.f.out)
        self.assertIn("hermes chat --accept-hooks", self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-1 ", self.f.out)
        self.assertIn("deployed: stays", self.f.out)
        self.assertNotIn("deployed: moves", self.f.out)

    def test_the_tag_number_counts_up_from_origin(self):
        self.f.git("tag", "-a", f"deploy/{TODAY}-1", "-m", "first")
        self.f.git("push", "-q", "origin", f"deploy/{TODAY}-1")
        self.f.git("tag", "-d", f"deploy/{TODAY}-1")  # on origin only
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertIn(f"tag: deploy/{TODAY}-2 ", self.f.out)

    def origin(self, *args):
        return subprocess.run(["git", *args], cwd=self.f.origin, capture_output=True, text=True).stdout.strip()

    def test_a_yes_makes_and_pushes_the_tag_and_moves_deployed(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        head = self.f.head()
        self.assertEqual(self.origin("rev-parse", "--short", f"deploy/{TODAY}-1^{{commit}}"), head)
        note = self.origin("tag", "-l", "-n20", f"deploy/{TODAY}-1")
        self.assertIn("files: vps/a.sh", note)
        self.assertIn("after the copy: summary: 6 of 6 in sync", note)
        self.assertEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), head)

    def test_a_no_to_the_tag_makes_nothing_and_prints_the_commands(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        before = self.origin("rev-parse", "deployed^{commit}")
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\nn\nn\n"), 0, self.f.out)
        self.assertEqual(self.origin("tag", "-l", "deploy/*"), "")
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)
        self.assertIn(f"git tag -a deploy/{TODAY}-1 ", self.f.out)
        self.assertIn(f"git push origin deploy/{TODAY}-1", self.f.out)

    def test_end_of_input_is_a_no(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.origin("tag", "-l", "deploy/*"), "")
        self.assertNotIn("Traceback", self.f.out)

    def test_a_refused_push_prints_what_to_run_and_exits_as_the_check_did(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        hook = self.f.origin / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\n"), 0, self.f.out)
        self.assertIn(f"deploy/{TODAY}-1 was not pushed", self.f.out)
        self.assertIn(f"git push origin deploy/{TODAY}-1", self.f.out)
        self.assertEqual(self.f.lg("tag", "-l", "deploy/*"), "")  # not left made here, so the commands run as printed
        self.assertNotIn("Traceback", self.f.out)

    def test_deployed_does_not_go_backwards(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        old = self.f.head()
        self.f.change({"vps/a.sh": "echo a3\n"})
        self.f.git("tag", "-f", "deployed")  # on the newer commit
        self.f.git("push", "-q", "-f", "origin", "deployed")
        self.f.git("checkout", "-q", "-B", "main", old)  # main rewound, as after a revert of a revert
        self.f.git("push", "-q", "-f", "origin", "main")
        self.f.write_host("/h/a.sh", "echo a\n", 0o755)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        self.assertIn("stays on", self.f.out)
        self.assertNotEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), old)

    def test_a_hook_awaiting_reapproval_leaves_deployed_until_deployed_alone_runs(self):
        self.f.change({"vps/hook.py": "print('hook 2')\n"})
        before = self.origin("rev-parse", "deployed^{commit}")
        self.f.doctor("1 issue(s) found.  Fix before relying on these hooks.")
        self.assertEqual(self.f.deploy("vps/hook.py", answers="y\ny\n"), 1, self.f.out)
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)
        self.assertIn("run python3 vps/deploy.py --deployed", self.f.out)
        self.assertEqual(self.f.deploy("--deployed", answers="y\n"), 1, self.f.out)  # not re-approved yet
        self.assertIn("deployed stays: check-drift.py exited 1", self.f.out)
        self.f.doctor("All shell hooks look healthy.")
        self.assertEqual(self.f.deploy("--deployed", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), self.f.head())

    def test_deployed_alone_needs_main_as_pushed(self):
        self.f.write_repo({"vps/a.sh": "echo a2\n"})
        self.f.commit()  # not pushed
        self.assertEqual(self.f.deploy("--deployed", answers="y\n"), 2, self.f.out)
        self.assertIn("deploy main as pushed", self.f.out)

    def test_paths_or_deployed_not_both_not_neither(self):
        self.assertEqual(self.f.deploy("--deployed", "vps/a.sh"), 2, self.f.out)
        self.assertEqual(self.f.deploy(), 2, self.f.out)

    def test_a_host_change_after_the_diff_stops_the_copy(self):
        # The host file changes after its diff is read: the fake repo's copy step writes it first.
        script = self.f.repo / "vps/remote/deploy_host.py"
        anchor = "def copy_files():\n"
        self.assertIn(anchor, script.read_text())
        self.f.change({"vps/a.sh": "echo a2\n", "vps/remote/deploy_host.py": script.read_text().replace(
            anchor, anchor + f"    open({str(self.f.host / 'h/a.sh')!r}, 'w').write('echo late\\n')\n", 1)})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 2, self.f.out)
        self.assertIn("changed on the host since its diff was shown", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo late\n")
        self.assertEqual(self.f.backups(), [])

    def test_her_login_profile_output_is_not_a_running_job(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        wrapper = self.f.bin / "bash"
        wrapper.write_text(f"#!/bin/sh\necho 'Welcome to the VPS'\nexec {shutil.which('bash')} \"$@\"\n")
        wrapper.chmod(0o755)
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a2\n")

if __name__ == "__main__":
    unittest.main()
