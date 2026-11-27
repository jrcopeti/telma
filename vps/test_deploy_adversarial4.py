"""Fourth adversarial round: deploy.py --skip-eval (a plain flag, no reason)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy import TODAY, DeployFake  # noqa: E402

SOUL = {"vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain well.\n"}


class Skip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = DeployFake(Path(self.tmp.name))
        self.f.change(SOUL)

    def tearDown(self):
        self.tmp.cleanup()

    def origin(self, *a):
        return subprocess.run(["git", *a], cwd=self.f.origin, capture_output=True, text=True).stdout.strip()

    def test_skills_with_soul_refused(self):
        r = self.f.deploy("--skip-eval", "vps/SOUL.md", "vps/skills/", answers="y\ny\ny\n")
        self.assertEqual(r, 2, self.f.out)
        self.assertEqual(self.f.host_text("/h/SOUL.md"), "You keep Ana's brain.\n")

    def test_jobs_with_soul_ungated_by_skip(self):
        self.f.deploy("--skip-eval", "vps/SOUL.md", "vps/jobs.overrides.yaml", answers="n\n")
        self.assertNotIn("Traceback", self.f.out)

    def test_declined_soul_no_waiver_in_tag(self):
        self.f.change({"vps/a.sh": "echo a2\n"})
        self.assertEqual(self.f.deploy("--skip-eval", "vps/SOUL.md", "vps/a.sh", answers="n\ny\ny\ny\n"), 1, self.f.out)
        self.assertNotIn("eval skipped", self.origin("tag", "-l", "-n20", f"deploy/{TODAY}-1"))

    def test_soul_given_twice_and_dot_path(self):
        self.assertEqual(self.f.deploy("--skip-eval", "./vps/SOUL.md", answers="y\n"), 2, self.f.out)


if __name__ == "__main__":
    unittest.main()
