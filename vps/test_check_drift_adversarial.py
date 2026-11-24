"""Adversarial tests for check-drift.py (PR #70). Run: python3 -m unittest vps/test_check_drift_adversarial.py
Every run goes through Fake (DRIFT_HOST_ROOT set to a temp folder); the one empty-root test runs in-process
with subprocess replaced, so nothing can reach the VPS."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_drift import Fake  # noqa: E402


class Adversarial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fake(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    # 1. A skill file with a non-ASCII name, identical on both sides, should be in sync.
    def test_non_ascii_skill_name_in_sync(self):
        self.f.write_repo({"vps/skills/café/SKILL.md": "# café\n"})
        self.f.commit()
        self.f.write_host("/h/skills/café/SKILL.md", "# café\n")
        s = self.f.run()
        self.assertEqual(s.get("vps/skills/café/SKILL.md"), "in sync", self.f.out)
        self.assertEqual(self.f.code, 0, self.f.out)

    # 2. The tree's root replaced by a symlink: "a symlink on the host, never followed" -> link / drift.
    def test_tree_root_symlink_is_not_followed(self):
        real = self.f.host / "elsewhere-skills"
        shutil.move(str(self.f.host / "h/skills"), str(real))
        (self.f.host / "h/skills").symlink_to(real)
        self.f.run()
        self.assertNotEqual(self.f.code, 0, "a symlinked skills folder reads all in sync:\n" + self.f.out)

    # 2b. A parent folder of an exact file replaced by a symlink.
    def test_parent_dir_symlink_is_not_followed(self):
        real = self.f.host / "elsewhere-h"
        shutil.move(str(self.f.host / "h"), str(real))
        (self.f.host / "h").symlink_to(real)
        self.f.run()
        self.assertNotEqual(self.f.code, 0, "every file behind a symlinked folder reads in sync:\n" + self.f.out)

    # 3. A chat pauses a job (threat model: "pause ... tripwire-health"). Check says in sync.
    def test_paused_job_is_drift(self):
        self.f.jobs[0]["paused"] = True
        self.f.jobs[0]["enabled"] = False
        self.f.write_jobs()
        self.f.run()
        self.assertNotEqual(self.f.code, 0, "a paused job reads in sync:\n" + self.f.out)

    # 3b. A chat flips a script job to an agent run / adds a singular skill / a delivery target.
    def test_job_no_agent_skill_deliver_changes_are_drift(self):
        self.f.jobs[0].update({"no_agent": False, "skill": "planted", "deliver": "somewhere"})
        self.f.write_jobs()
        self.f.run()
        self.assertNotEqual(self.f.code, 0, "job fields outside the five read in sync:\n" + self.f.out)

    # 4. A top-level host README.md that is a symlink to a folder holding a SKILL.md is hidden.
    def test_readme_symlink_to_skill_dir_is_reported(self):
        evil = self.f.host / "evil"
        evil.mkdir()
        (evil / "SKILL.md").write_text("do evil\n")
        (self.f.host / "h/skills/README.md").symlink_to(evil)
        self.f.run()
        self.assertNotEqual(self.f.code, 0, "a README.md link to a skill folder is invisible:\n" + self.f.out)

    # 5. "a host file's text is never printed" (load_yaml docstring, devlog).
    def test_host_yaml_tag_error_never_prints_value(self):
        for doc in ("model:\n  default: !!int sk-secret-123\n", "model:\n  default: !!bool sk-secret-123\n"):
            self.f.write_host("/h/config.yaml", doc, 0o600)
            self.f.run()
            self.assertEqual(self.f.code, 2, self.f.out)
            self.assertNotIn("sk-secret-123", self.f.out)

    # 6. DRIFT_HOST_ROOT set but empty goes to ssh (in-process, subprocess stubbed: nothing runs).
    def test_empty_host_root_never_reaches_ssh(self):
        spec = importlib.util.spec_from_file_location("cd", self.f.repo / "vps/check-drift.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        calls = []

        class Stub:
            @staticmethod
            def run(cmd, **kw):
                calls.append(cmd)
                raise RuntimeError("stubbed")

        mod.subprocess = Stub
        old = os.environ.get("DRIFT_HOST_ROOT")
        os.environ["DRIFT_HOST_ROOT"] = ""
        try:
            try:
                mod.collect({"files": [], "texts": [], "jobs_files": [], "trees": [], "env": [], "jobs": []})
            except (RuntimeError, mod.Stop):
                pass
        finally:
            if old is None:
                del os.environ["DRIFT_HOST_ROOT"]
            else:
                os.environ["DRIFT_HOST_ROOT"] = old
        self.assertFalse([c for c in calls if c[0] == "ssh"], f"empty DRIFT_HOST_ROOT runs: {calls}")


if __name__ == "__main__":
    unittest.main()
