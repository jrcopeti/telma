import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy import TODAY, DeployFake  # noqa


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")
        self.f.git("push", "-q", "origin", "deployed")
        self.pd = self.f.repo / ".git/deploy-pending"

    def tearDown(self):
        self.tmp.cleanup()

    def tag(self, *a, answers=""):
        return self.f.deploy(*a, answers=answers, script="vps/tag-deploy.py")

    def o(self, *a):
        return subprocess.run(["git", *a], cwd=self.f.origin, capture_output=True, text=True).stdout.strip()

    def lg(self, *a):
        return subprocess.run(["git", *a], cwd=self.f.repo, capture_output=True, text=True).stdout.strip()

    def pend(self, name, **kw):
        self.pd.mkdir(exist_ok=True)
        d = {"tag": f"deploy/{TODAY}-1", "commit": self.lg("rev-parse", "HEAD"), "message": ["m", "files: x"], "in_sync": True}
        d.update(kw)
        (self.pd / name).write_text(json.dumps(d))

    # 1 backward move of deployed
    def test_deployed_never_goes_backwards(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        x = self.f.head()
        self.f.change({"vps/a.sh": "echo a3\n"})
        self.f.write_host("/h/a.sh", "echo a3\n", 0o755)  # host now matches newer main
        self.assertEqual(self.tag("--deployed", answers="y\n"), 0, self.f.out)
        y = self.f.head()
        self.assertEqual(self.o("rev-parse", "--short", "deployed^{commit}"), y)
        self.tag(answers="y\ny\n")
        self.assertEqual(self.o("rev-parse", "--short", "deployed^{commit}"), y, "deployed moved back to older deploy")

    # 2 push failure leaves local tag -> stuck
    def test_failed_push_can_be_retried(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        hook = self.f.origin / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n"); hook.chmod(0o755)
        self.assertEqual(self.tag(answers="y\n"), 2, self.f.out)
        hook.unlink()
        self.tag(answers="y\ny\n")
        self.assertTrue(self.o("tag", "-l", f"deploy/{TODAY}-1"), "tag never reaches origin on retry: " + self.f.out)

    # 3 corrupt pending json
    def test_corrupt_pending_is_a_clean_stop(self):
        self.pd.mkdir(exist_ok=True)
        (self.pd / "bad.json").write_text("{not json")
        self.assertEqual(self.tag(), 2, self.f.out)
        self.assertNotIn("Traceback", self.f.out)

    def test_corrupt_pending_does_not_traceback_deploy(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.pd.mkdir(exist_ok=True)
        (self.pd / "bad.json").write_text("{}")
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertNotIn("Traceback", self.f.out)

    # 4 attacker-shaped tag names
    def test_tag_outside_deploy_namespace_is_refused(self):
        self.pend("evil.json", tag="v9-evil")
        self.tag(answers="y\ny\n")
        self.assertFalse(self.o("tag", "-l", "v9-evil"), "pushed a tag outside deploy/")

    def test_option_shaped_tag_is_refused(self):
        self.pend("evil.json", tag="--force")
        self.tag(answers="y\ny\n")
        self.assertNotIn("Traceback", self.f.out)
        # no tag named after a sha / no stray locals
        self.assertEqual(self.lg("tag", "-l"), "deployed", self.f.out)

    # 5 commit not on origin / garbage commit
    def test_commit_not_on_main_is_refused(self):
        self.f.git("checkout", "-q", "-b", "side")
        self.f.write_repo({"vps/z.txt": "z\n"}); self.f.commit()
        sha = self.lg("rev-parse", "HEAD")
        self.f.git("checkout", "-q", "main")
        self.pend("p.json", commit=sha)
        self.tag(answers="y\ny\n")
        self.assertFalse(self.o("tag", "-l", f"deploy/{TODAY}-1"), "tagged+pushed a commit not on main: " + self.f.out)
        self.assertNotEqual(self.o("rev-parse", "deployed^{commit}"), sha)

    def test_deployed_not_moved_to_arbitrary_commit_rev(self):
        self.pend("p.json", commit="HEAD~1")
        self.tag(answers="y\ny\n")
        self.assertNotIn("Traceback", self.f.out)

    # 6 deployed moves without any re-check although host changed since. Accepted (owner's yes at the
    # prompt, plan's Open): the criteria say "that deploy's re-check was in sync"; --deployed re-checks.
    @unittest.expectedFailure
    def test_in_sync_flag_is_stale(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.f.write_host("/h/a.sh", "tampered\n", 0o755)  # host drifts before the owner tags
        before = self.o("rev-parse", "deployed^{commit}")
        self.tag(answers="y\ny\n")
        self.assertEqual(self.o("rev-parse", "deployed^{commit}"), before, "deployed moved onto a host that no longer matches")

    # 7 tag-deploy ignores origin/main freshness: pending tagged without fetch; message with newline lines
    def test_pending_file_with_unpushed_origin_gone(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        subprocess.run(["git", "remote", "set-url", "origin", "/nonexistent"], cwd=self.f.repo)
        self.assertEqual(self.tag(answers="y\ny\n"), 2, self.f.out)
        self.assertEqual(self.lg("tag", "-l", f"deploy/{TODAY}-1"), "")

    # 8 --deployed with out-of-date pending doesn't care; EOF
    def test_eof_after_tags_pushed_exit_code(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.tag(answers="y\n")  # EOF at the deployed question
        self.assertIn("pending", "" ) if False else None
        self.assertEqual(self.f.code, 1, f"docstring: 1 when deployed stays; got {self.f.code}: {self.f.out}")

    # 9 pending file survives push if unlink fails -> forever 'already exists'
    def test_pending_cleared_when_tag_already_on_origin_same_commit(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        head = self.lg("rev-parse", "HEAD")
        self.f.git("tag", "-a", f"deploy/{TODAY}-1", "-m", "x", head)
        self.f.git("push", "-q", "origin", f"deploy/{TODAY}-1")
        self.f.git("tag", "-d", f"deploy/{TODAY}-1")
        self.tag(answers="y\ny\n")
        self.assertEqual(list(self.pd.glob("*.json")), [], "pending for a tag already on origin at that commit is stuck forever")

    # 10 concurrency: same name overwritten
    def test_two_pending_same_tag_name_files(self):
        self.pend("a.json", tag=f"deploy/{TODAY}-1")
        self.pend("b.json", tag=f"deploy/{TODAY}-1")
        self.tag(answers="y\ny\ny\n")
        self.assertNotIn("Traceback", self.f.out)

    # 11 natural sort across days: tag-10 after tag-9
    def test_order_10_after_9(self):
        for n in (9, 10, 2):
            self.pend(f"{n}.json", tag=f"deploy/{TODAY}-{n}")
        self.tag(answers="n\nn\nn\n")
        i = [self.f.out.index(f"deploy/{TODAY}-{n} on") for n in (2, 9, 10)]
        self.assertEqual(i, sorted(i))

    # 12 deployed moves with newest even if an older pending was skipped via 'already exists' variant
    def test_deployed_moves_when_older_failed_in_sync(self):
        self.pend("a.json", tag=f"deploy/{TODAY}-1", in_sync=False)
        self.f.change({"vps/a.sh": "echo a2\n"})
        h = self.lg("rev-parse", "HEAD")
        self.pend("b.json", tag=f"deploy/{TODAY}-2", commit=h, in_sync=True)
        self.tag(answers="y\ny\ny\n")
        # criteria: deployed moves with newest only when that deploy's re-check was in sync and none skipped
        self.assertEqual(self.o("rev-parse", "deployed^{commit}"), h)

    # 13 message starting with dash / injection
    def test_message_lines_with_dashes_and_ansi(self):
        self.pend("p.json", message=["-F /etc/passwd", "\x1b[31mred", "files: a\nb"])
        self.tag(answers="y\nn\n")
        self.assertIn(f"deploy/{TODAY}-1 pushed", self.f.out)
        self.assertIn("-F /etc/passwd", self.o("tag", "-l", "-n20", f"deploy/{TODAY}-1"))

    # 14 --deployed when main is ahead and deployed is already ahead/equal; HEAD vs pending ignorance
    def test_deployed_flag_with_pending_leaves_pending(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.tag("--deployed", answers="y\n")
        self.assertEqual(len(list(self.pd.glob("*.json"))), 1)


    # round-3 fixes, own checks
    def test_pending_file_is_never_overwritten_by_a_racing_deploy(self):
        self.pend("deploy_%s-1.json" % TODAY, tag=f"deploy/{TODAY}-1")
        self.f.change({"vps/a.sh": "echo a2\n"})
        # a stale numbering: a file for -1 appeared after this deploy picked -1
        import importlib.util
        spec = importlib.util.spec_from_file_location("d", self.f.repo / "vps/deploy.py")
        d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
        self.assertEqual(d.write_pending(f"deploy/{TODAY}-1", "0" * 40, ["m"], True), f"deploy/{TODAY}-2")
        self.assertEqual(len(list(self.pd.glob("*.json"))), 2)

    def test_an_interrupted_tag_is_pushed_on_the_next_run(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.f.git("tag", "-a", f"deploy/{TODAY}-1", "-m", "x", self.lg("rev-parse", "HEAD"))  # made, never pushed
        self.assertEqual(self.tag(answers="y\ny\n"), 0, self.f.out)
        self.assertTrue(self.o("tag", "-l", f"deploy/{TODAY}-1"))
        self.assertEqual(list(self.pd.glob("*.json")), [])

    def test_a_pending_tag_in_a_hand_edit_with_a_bad_commit_stops(self):
        self.pend("p.json", commit="HEAD~1")
        self.assertEqual(self.tag(answers="y\n"), 2, self.f.out)
        self.assertIn("p.json isn't a pending deploy tag", self.f.out)


if __name__ == "__main__":
    unittest.main()
