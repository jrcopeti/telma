"""Tests for tag-deploy.py: the tags deploy.py leaves pending, made and pushed to a bare origin.
Run: python3 -m unittest vps/test_tag_deploy.py"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy import TODAY, DeployFake  # noqa: E402


class TagDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.git("tag", "deployed")
        self.f.git("push", "-q", "origin", "deployed")

    def tearDown(self):
        self.tmp.cleanup()

    def tag(self, *args, answers=""):
        return self.f.deploy(*args, answers=answers, script="vps/tag-deploy.py")

    def origin(self, *args):
        return subprocess.run(["git", *args], cwd=self.f.origin, capture_output=True, text=True).stdout.strip()

    def test_a_deploy_in_sync_is_tagged_and_deployed_moves(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("vps/a.sh", answers="y\n"), 0, self.f.out)
        head = self.f.head()
        self.assertEqual(self.tag(answers="y\ny\n"), 0, self.f.out)
        self.assertEqual(self.origin("rev-parse", "--short", f"deploy/{TODAY}-1^{{commit}}"), head)
        self.assertIn("files: vps/a.sh", self.origin("tag", "-l", "-n20", f"deploy/{TODAY}-1"))
        self.assertEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), head)
        self.assertEqual(self.tag(), 0, self.f.out)
        self.assertIn("nothing pending", self.f.out)

    def test_two_deploys_before_tagging_get_two_names_and_tag_in_order(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.f.change({"vps/a.sh": "echo a3\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.assertIn(f"tag: deploy/{TODAY}-2 ", self.f.out)
        self.assertEqual(self.tag(answers="y\ny\ny\n"), 0, self.f.out)
        self.assertLess(self.f.out.index(f"deploy/{TODAY}-1 pushed"), self.f.out.index(f"deploy/{TODAY}-2 pushed"))
        self.assertEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), self.f.head())

    def test_a_skipped_tag_stays_pending_and_deployed_stays(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        before = self.origin("rev-parse", "deployed^{commit}")
        self.assertEqual(self.tag(answers="n\n"), 1, self.f.out)
        self.assertIn("deployed stays: a deploy was skipped", self.f.out)
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)
        self.assertEqual(self.tag(answers="y\ny\n"), 0, self.f.out)

    def test_a_hook_waiting_for_reapproval_moves_deployed_only_after_a_clean_check(self):
        self.f.change({"vps/hook.py": "print('hook 2')\n"})
        self.f.doctor("1 issue(s) found.  Fix before relying on these hooks.")
        self.assertEqual(self.f.deploy("vps/hook.py", answers="y\n"), 1, self.f.out)
        before = self.origin("rev-parse", "deployed^{commit}")
        self.assertEqual(self.tag(answers="y\n"), 1, self.f.out)
        self.assertEqual(self.origin("rev-parse", "deployed^{commit}"), before)
        self.assertEqual(self.tag("--deployed", answers="y\n"), 1, self.f.out)  # still not re-approved
        self.assertIn("deployed stays: check-drift.py exited 1", self.f.out)
        self.f.doctor("All shell hooks look healthy.")
        self.assertEqual(self.tag("--deployed", answers="y\n"), 0, self.f.out)
        self.assertEqual(self.origin("rev-parse", "--short", "deployed^{commit}"), self.f.head())

    def test_a_tag_that_already_exists_is_left_pending(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.f.deploy("vps/a.sh", answers="y\n")
        self.f.git("tag", f"deploy/{TODAY}-1")  # made by hand meanwhile
        self.assertEqual(self.tag(answers="y\n"), 1, self.f.out)
        self.assertIn("already exists: left pending", self.f.out)


if __name__ == "__main__":
    unittest.main()
