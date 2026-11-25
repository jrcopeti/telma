"""Third adversarial round, on commit 662bf0d (finish, confirm, move_deployed, --deployed) and the smoke host side.
Run: python3 -m unittest vps/test_deploy_adversarial3.py"""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_drift import GIT_ENV  # noqa: E402
from test_deploy import TODAY, DeployFake  # noqa: E402

REMOTE = Path(__file__).resolve().parent / "remote"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")
        self.f.git("push", "-q", "origin", "deployed")

    def tearDown(self):
        self.tmp.cleanup()

    def origin(self, *args):
        return subprocess.run(["git", *args], cwd=self.f.origin, capture_output=True, text=True).stdout.strip()

    def reject(self, pattern):
        hook = self.f.origin / "hooks/pre-receive"
        hook.write_text(f"#!/bin/sh\nwhile read o n ref; do case $ref in {pattern}) exit 1;; esac; done\nexit 0\n")
        hook.chmod(0o755)

    def env(self):
        return {**os.environ, **GIT_ENV, "DRIFT_HOST_ROOT": str(self.f.host),
                "PATH": f"{self.f.bin}:{os.environ['PATH']}"}


class Stdin(Base):
    # Criteria: "each with the owner's own yes at the keyboard"; AGENTS.md: only the owner moves tags.
    def test_a_piped_stdin_cannot_create_a_tag_or_move_deployed(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        before = self.origin("rev-parse", "deployed^{commit}")
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n", tty=False), 2, self.f.out)  # an agent's pipe
        self.assertIn("needs a terminal", self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")
        self.assertEqual(self.origin("tag", "-l", "deploy/*"), "", self.f.out)
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)

    def test_yes_piped_in_ahead_of_time_answers_every_prompt(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        before = self.origin("rev-parse", "deployed^{commit}")
        yes = subprocess.Popen(["yes"], stdout=subprocess.PIPE)
        r = subprocess.run(["python3", str(self.f.repo / "vps/deploy.py"), "vps/a.sh"], cwd=self.f.repo,
                           env=self.env(), stdin=yes.stdout, capture_output=True, text=True)
        yes.kill()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.origin("tag", "-l", "deploy/*"), "", "a tag was made from `yes |`")
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)


class Failures(Base):
    def test_a_refused_tag_push_still_offers_or_prints_deployed(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.reject("refs/tags/deploy/*")
        before = self.origin("rev-parse", "deployed^{commit}")
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        moved = self.origin("rev-parse", "deployed^{commit}") != before
        printed = "origin deployed" in self.f.out.split("by hand")[-1] if "by hand" in self.f.out else False
        self.assertTrue(moved or printed, "tag push failed: deployed neither moved nor in the by-hand list\n" + self.f.out)

    def test_a_refused_deployed_push_prints_deployed_by_hand_not_the_tag_again(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.reject("refs/tags/deployed")
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\ny\ny\n"), 0, self.f.out)
        tail = self.f.out.split("by hand, as needed:")[-1]
        self.assertIn("git push -f origin deployed", self.f.out)
        self.assertNotIn("git tag -a", tail, "the tag is already pushed; the by-hand list re-offers creating it\n" + self.f.out)

    def test_a_tag_taken_on_origin_during_the_run_gets_the_next_number(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "clone", "-q", "-b", "main", str(self.f.origin), str(other)], check=True, env=self.env())
        hermes = self.f.bin / "hermes"
        hermes.write_text(f"#!/bin/sh\ncd {other} && git -c user.name=t -c user.email=t@e tag -a deploy/{TODAY}-1 "
                          f"-m other HEAD~1 && git push -q origin deploy/{TODAY}-1\n"
                          "echo 'All shell hooks look healthy.'\n")
        hermes.chmod(0o755)
        self.f.deploy("vps/a.sh", answers="y\ny\ny\n")
        self.assertEqual(self.origin("rev-parse", "--short", f"deploy/{TODAY}-2^{{commit}}"), self.f.head(), self.f.out)

    def test_a_tag_taken_after_the_numbering_is_not_left_made_here(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.reject("refs/tags/deploy/*")
        self.f.deploy("vps/a.sh", answers="y\ny\ny\n")
        self.assertEqual(self.f.lg("tag", "-l", "deploy/*"), "", self.f.out)
        self.assertIn(f"git tag -a deploy/{TODAY}-1 ", self.f.out)

    def test_a_copy_that_never_ran_is_not_offered_a_deploy_tag(self):
        src = (self.f.repo / "vps/remote/deploy_host.py").read_text()
        self.f.change({"vps/a.sh": "echo a2\n",
                       "vps/remote/deploy_host.py": src.replace('req = json.loads(sys.stdin.read())',
                                                                 'req = json.loads(sys.stdin.read())\nif req["action"] == "copy": sys.exit(1)', 1)})
        self.assertIn('if req["action"] == "copy"', (self.f.repo / "vps/remote/deploy_host.py").read_text())
        code = self.f.deploy("vps/a.sh", answers="y\ny\ny\n")
        self.assertEqual(code, 3, self.f.out)
        self.assertEqual(self.f.host_text("/h/a.sh"), "echo a\n")
        self.assertEqual(self.origin("tag", "-l", "deploy/*"), "", "a permanent deploy tag for a copy that did nothing")


class Deployed(Base):
    def test_already_on_origin_syncs_the_local_tag(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.f.repo, capture_output=True, text=True).stdout.strip()
        self.f.git("tag", "-f", "deployed")
        self.f.git("push", "-q", "-f", "origin", "deployed")
        self.f.git("tag", "-f", "deployed", "HEAD~1")  # this clone's stale copy
        self.f.write_host("/h/a.sh", "echo a2\n", 0o755)
        self.assertEqual(self.f.deploy("--deployed", answers="y\n"), 0, self.f.out)
        self.assertIn("already", self.f.out)
        local = subprocess.run(["git", "rev-parse", "deployed^{commit}"], cwd=self.f.repo, capture_output=True, text=True).stdout.strip()
        self.assertEqual(local, head, "local deployed stays stale, the direction check reads it")

    def test_an_annotated_deployed_on_origin_moves_forward_and_stays_when_equal(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.git("tag", "-f", "-a", "-m", "m", "deployed", "HEAD~1")
        self.f.git("push", "-q", "-f", "origin", "deployed")
        self.f.write_host("/h/a.sh", "echo a2\n", 0o755)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.f.repo, capture_output=True, text=True).stdout.strip()
        self.assertEqual(self.f.deploy("--deployed", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), head, self.f.out)

    def test_a_diverged_deployed_stays(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.git("checkout", "-q", "-b", "side", "HEAD~1")
        self.f.write_repo({"vps/a.sh": "echo side\n"})
        self.f.commit()
        self.f.git("tag", "-f", "deployed")
        self.f.git("push", "-q", "-f", "origin", "deployed")
        self.f.git("checkout", "-q", "main")
        self.f.write_host("/h/a.sh", "echo a2\n", 0o755)
        before = self.origin("rev-parse", "deployed^{commit}")
        self.f.deploy("--deployed", answers="y\n")
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before, self.f.out)

    def test_ctrl_c_at_the_tag_prompt_prints_the_commands_and_keeps_the_exit_code(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        master, slave = self.f.terminal("y\n")  # the file's yes; the tag prompt then waits on the terminal
        self.addCleanup(lambda: (os.close(master), os.close(slave)))
        p = subprocess.Popen(["python3", "-u", str(self.f.repo / "vps/deploy.py"), "vps/a.sh"], cwd=self.f.repo,
                             env=self.env(), stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(4)
        p.send_signal(signal.SIGINT)
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 0, out)
        self.assertIn(f"git push origin deploy/{TODAY}-1", out)
        self.assertNotIn("Traceback", out)

    def test_deployed_abbreviation_and_extra_options_do_not_smuggle_a_path_run(self):
        self.assertEqual(self.f.deploy("--dep"), 2, self.f.out)  # no abbreviations
        self.assertEqual(self.f.deploy("--deployed", "--eval-run", "x"), 2, self.f.out)


class Smoke(unittest.TestCase):
    def host(self, code_name, req):
        return subprocess.run([sys.executable, "-I", "-c", (REMOTE / code_name).read_text()], input=json.dumps(req),
                              capture_output=True, text=True)

    def setup_req(self, tmp, root):
        src = tmp / "src.db"
        with sqlite3.connect(src) as db:
            db.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, source TEXT NOT NULL, "
                       "process_id TEXT NOT NULL, pid INTEGER NOT NULL, status TEXT NOT NULL, claimed_at TEXT NOT NULL)")
        return {"root": str(root), "parent": str(root.parent), "action": "setup", "ledger": "/home/agent/.hermes/cron/executions.db",
                "ledger_src": str(src), "as_agent": ["bash", "-c"], "uid": os.getuid(), "gid": os.getgid(),
                "ledger_copy_code": (REMOTE / "ledger_copy.py").read_text()}

    def test_setup_into_a_scratch_name_that_already_exists_touches_nothing_outside_it(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            root = t / "parent/deploy-smoke-20261125T120000Z"
            root.mkdir(parents=True)
            target = t / "somewhere-root-owns"
            target.mkdir()
            target.chmod(0o700)
            (root / "home").symlink_to(target)  # planted before the run; /var/tmp is world-writable
            r = self.host("smoke_host.py", self.setup_req(t, root))
            self.assertEqual(oct(target.stat().st_mode & 0o777), "0o700", f"setup chmod'd through the link ({r.returncode}): {r.stderr}")
            self.assertEqual(list(target.iterdir()), [], "setup built its tree inside the link's target")

    def test_a_symlink_planted_in_the_agent_owned_folder_right_after_its_chown_is_not_written_through(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            root = t / "parent/deploy-smoke-20261125T120000Z"
            root.parent.mkdir()
            victim = t / "victim"
            victim.write_text("precious\n")
            req = self.setup_req(t, root)
            code = (REMOTE / "smoke_host.py").read_text()
            # the agent owns <home>/smoke from the chown on; this plays its win of the race to the open()
            hook = ("import os as _o\n_c = _o.chown\n"
                    "def _chown(p, u, g, *a, **k):\n    _c(p, u, g, *a, **k)\n"
                    "    if p.endswith('/home/agent/smoke') and not _o.path.lexists(p + '/a.sh'):\n"
                    f"        _o.symlink({str(victim)!r}, p + '/a.sh')\n"
                    "_o.chown = _chown\n")
            subprocess.run([sys.executable, "-I", "-c", hook + code], input=json.dumps(req), capture_output=True, text=True)
            self.assertEqual(victim.read_text(), "precious\n", "root wrote its a.sh through the agent's symlink")

    def test_mark_running_does_not_write_through_a_journal_symlink_in_the_agent_owned_folder(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            root = t / "parent/deploy-smoke-20261125T120000Z"
            root.parent.mkdir()
            req = self.setup_req(t, root)
            self.assertEqual(self.host("smoke_host.py", req).returncode, 0)
            victim = t / "victim"
            victim.write_text("precious\n")
            (root / "home/agent/.hermes/cron/executions.db-journal").symlink_to(victim)
            self.host("smoke_host.py", {**req, "action": "mark_running", "ledger": req["ledger"]})
            self.assertEqual(victim.read_text(), "precious\n", "root's sqlite wrote its journal through the planted link")

    def test_cleanup_refuses_a_symlinked_scratch_folder(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            keep = t / "keep"
            keep.mkdir()
            (keep / "f").write_text("x")
            parent = t / "parent"
            parent.mkdir()
            (parent / "deploy-smoke-20261125T120000Z").symlink_to(keep)
            self.host("smoke_host.py", {"root": str(parent / "deploy-smoke-20261125T120000Z"), "parent": str(parent), "action": "cleanup"})
            self.assertTrue((keep / "f").exists())


if __name__ == "__main__":
    unittest.main()
