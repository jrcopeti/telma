"""Tests for check-drift.py against a fake host folder (DRIFT_HOST_ROOT) and a throwaway repo.
Run: python3 -m unittest vps/test_check_drift.py"""
import grp
import json
import os
import pwd
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check-drift.py"
OWNER = f"{pwd.getpwuid(os.getuid()).pw_name}:{grp.getgrgid(os.getgid()).gr_name}"
GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
JOBS = {"job-a": {"schedule": "every 15m", "script": "a.sh", "interpreter": "/usr/bin/python3", "skills": [], "toolsets": None,
                  "enabled": True, "no_agent": True, "deliver": "discord"},
        "job-b": {"schedule": "0 9 * * *", "script": None, "interpreter": None, "skills": ["triage"], "toolsets": ["file"],
                  "enabled": True, "no_agent": False, "deliver": "discord", "prompt": "vps/prompt.txt"}}


class Fake:
    """A repo with every manifest mode, and a host folder that matches it."""

    def __init__(self, tmp):
        self.repo, self.host, self.bin = tmp / "repo", tmp / "host", tmp / "bin"
        self.git("init", "-q", str(self.repo), cwd=tmp)
        (self.repo / "vps").mkdir()
        shutil.copy(SCRIPT, self.repo / "vps/check-drift.py")
        self.write_repo({
            "vps/a.sh": "echo a\n",
            "vps/SOUL.md": "You keep {{OWNER_NAME}}'s brain.\n",
            "vps/config.overrides.yaml": "model:\n  default: m1\nterminal:\n  backend: docker\n  cwd: /w\n"
                                         "  docker_volumes:\n    - /a:/b\n",
            "vps/jobs.overrides.yaml": json.dumps(JOBS),
            "vps/prompt.txt": "Run triage.\n",
            "vps/skills/README.md": "credit\n", "vps/skills/LICENSE": "MIT\n",
            "vps/skills/triage/SKILL.md": "# triage\n",
            "vps/deploy.manifest": "\n".join([
                "# repo path  host path  mode  owner:group  perm  after",
                f"vps/a.sh  /h/a.sh  exact  {OWNER}  755  none",
                f"vps/SOUL.md  /h/SOUL.md  redacted  {OWNER}  644  new-chat",
                f"vps/config.overrides.yaml  /h/config.yaml  subset  {OWNER}  600  restart-gateway",
                f"vps/jobs.overrides.yaml  /h/jobs.json  jobs  {OWNER}  600  none",
                f"vps/skills/  /h/skills/  tree  {OWNER}  -  none", ""])})
        (self.repo / ".git/info/private-values").write_text("OWNER_NAME=Ana\n")
        self.commit()
        self.write_host("/h/a.sh", "echo a\n", 0o755)
        self.write_host("/h/SOUL.md", "You keep Ana's brain.\n")
        self.write_host("/h/config.yaml", "model:\n  default: m1\n  provider: x\nterminal:\n  backend: docker\n"
                        "  cwd: /w\n  timeout: 60\n  docker_volumes:\n  - /a:/b\nstreaming: true\n", 0o600)
        self.write_host("/home/agent/.hermes/.env", 'OPENROUTER_API_KEY=sk-secret\nTERMINAL_ENV=docker\n'
                        'TERMINAL_DOCKER_VOLUMES="[\\"/a:/b\\"]"\nTERMINAL_TIMEOUT=60\n', 0o600)
        self.jobs = [{"name": "job-a", "schedule": {"display": "every 15m"}, "script": "a.sh", "interpreter": "/usr/bin/python3", "skills": [],
                      "enabled_toolsets": None, "prompt": "", "enabled": True, "no_agent": True, "deliver": "discord"},
                     {"name": "job-b", "schedule": {"display": "0 9 * * *"}, "script": None, "skills": ["triage"],
                      "enabled_toolsets": ["file"], "prompt": "Run triage.", "enabled": True, "no_agent": False,
                      "deliver": "discord"},
                     {"name": "dentist-reminder", "schedule": {"display": "once"}, "prompt": "call the dentist"}]
        self.write_jobs()
        self.write_host("/h/skills/triage/SKILL.md", "# triage\n")
        guard = self.host / "opt/hermes-guard"
        guard.mkdir(parents=True)
        self.git("init", "-q", cwd=guard)
        self.git("commit", "-q", "--allow-empty", "-m", "v1", cwd=guard)
        for d in ("home/agent/.hermes/hermes-agent", "home/ticket-bay-bot/.hermes/hermes-agent"):
            self.git("clone", "-q", str(guard), str(self.host / d), cwd=tmp)
        self.bin.mkdir()
        self.doctor("All shell hooks look healthy.")

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True,
                       env={**os.environ, **GIT_ENV})

    def write_repo(self, files):
        for path, text in files.items():
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)

    def write_host(self, path, text, mode=0o644):
        p = self.host / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        p.chmod(mode)

    def write_jobs(self):
        self.write_host("/h/jobs.json", json.dumps({"jobs": self.jobs}), 0o600)

    def doctor(self, last_line):
        hermes = self.bin / "hermes"
        hermes.write_text(f"#!/bin/sh\necho 'Checking 3 configured shell hook(s)...'\necho\necho '{last_line}'\n")
        hermes.chmod(0o755)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def run(self):
        env = {**os.environ, **GIT_ENV, "DRIFT_HOST_ROOT": str(self.host),
               "PATH": f"{self.bin}:{os.environ['PATH']}"}
        r = subprocess.run(["python3", str(self.repo / "vps/check-drift.py")], cwd=self.repo, env=env,
                           capture_output=True, text=True)
        self.code, self.out = r.returncode, r.stdout + r.stderr
        return {line[:44].strip(): line[45:59].strip() for line in r.stdout.splitlines()
                if not line.startswith("summary:")}


class CheckDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fake(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def assertStatus(self, statuses, path, want):
        self.assertEqual(statuses.get(path), want, self.f.out)

    def test_everything_in_sync(self):
        s = self.f.run()
        for path in ("vps/a.sh", "vps/SOUL.md", "vps/config.overrides.yaml", "vps/jobs.overrides.yaml",
                     "vps/skills/triage/SKILL.md"):
            self.assertStatus(s, path, "in sync")
        self.assertTrue(s["hermes"].startswith("ok"), self.f.out)
        self.assertEqual(s["hooks"], "ok")
        self.assertIn("summary: 5 of 5 in sync, hermes ok, hooks ok, deployed none", self.f.out)
        self.assertEqual(self.f.code, 0, self.f.out)

    def test_without_the_tag_a_difference_has_no_direction(self):
        self.f.write_host("/h/a.sh", "echo hand edit\n", 0o755)
        self.assertStatus(self.f.run(), "vps/a.sh", "differs")
        self.assertEqual(self.f.code, 1)

    def test_repo_ahead_host_ahead_both_changed(self):
        self.f.git("tag", "deployed")
        self.f.write_repo({"vps/a.sh": "echo a2\n"})
        self.f.commit()
        self.assertStatus(self.f.run(), "vps/a.sh", "repo ahead")
        self.f.write_host("/h/a.sh", "echo hand edit\n", 0o755)
        self.assertStatus(self.f.run(), "vps/a.sh", "both changed")
        self.f.write_repo({"vps/a.sh": "echo a\n"})
        self.assertStatus(self.f.run(), "vps/a.sh", "host ahead")

    def test_a_file_absent_at_the_tag_differs(self):
        self.f.git("tag", "deployed")
        self.f.write_repo({"vps/b.sh": "echo b\n", "vps/deploy.manifest": (self.f.repo / "vps/deploy.manifest")
                           .read_text() + f"vps/b.sh  /h/b.sh  exact  {OWNER}  644  none\n"})
        self.f.write_host("/h/b.sh", "echo old b\n")
        self.assertStatus(self.f.run(), "vps/b.sh", "differs")

    def test_a_file_absent_on_the_host_is_missing(self):
        (self.f.host / "h/a.sh").unlink()
        self.assertStatus(self.f.run(), "vps/a.sh", "missing")

    def test_owner_or_mode_change_is_drift(self):
        (self.f.host / "h/a.sh").chmod(0o777)
        s = self.f.run()
        self.assertStatus(s, "vps/a.sh", "perm differs")
        self.assertIn(f"want {OWNER} 755", self.f.out)
        self.assertEqual(self.f.code, 1)

    def test_redacted_file_is_filled_before_comparing(self):
        self.f.write_host("/h/SOUL.md", "You keep Bea's brain.\n")
        self.assertStatus(self.f.run(), "vps/SOUL.md", "differs")

    def test_a_missing_private_value_stops_before_reading_the_host(self):
        (self.f.repo / ".git/info/private-values").unlink()
        shutil.rmtree(self.f.host)  # reaching the host would fail differently
        self.f.run()
        self.assertEqual(self.f.code, 2)
        self.assertIn("private-values is missing", self.f.out)

    def test_config_names_the_key_that_differs_never_its_value(self):
        self.f.write_host("/h/config.yaml", "model:\n  default: leaked-value\nterminal:\n  backend: docker\n"
                          "  cwd: /w\n  docker_volumes:\n  - /a:/b\n", 0o600)
        s = self.f.run()
        self.assertStatus(s, "vps/config.overrides.yaml", "differs")
        self.assertIn("model.default", self.f.out)
        self.assertNotIn("leaked-value", self.f.out)

    def test_config_terminal_keys_are_checked_in_env(self):
        self.f.write_host("/home/agent/.hermes/.env", 'TERMINAL_ENV=local\nTERMINAL_DOCKER_VOLUMES="[\\"/a:/b\\"]"\n')
        self.assertStatus(self.f.run(), "vps/config.overrides.yaml", "differs")
        self.assertIn(".env TERMINAL_ENV", self.f.out)
        self.assertNotIn("TERMINAL_DOCKER_VOLUMES", self.f.out)

    def test_a_job_changed_by_a_chat_is_drift_and_other_jobs_stay_unnamed(self):
        self.f.jobs[1]["enabled_toolsets"] = ["file", "web"]
        self.f.write_jobs()
        s = self.f.run()
        self.assertStatus(s, "vps/jobs.overrides.yaml", "differs")
        self.assertIn("job-b", self.f.out)
        self.assertIn("1 other job(s)", self.f.out)
        self.assertNotIn("dentist", self.f.out)

    def test_a_job_with_a_wrong_or_missing_interpreter_is_drift(self):
        for value in ("/usr/bin/python3.14", None):
            with self.subTest(interpreter=value):
                self.f.jobs[0]["interpreter"] = value
                self.f.write_jobs()
                self.assertStatus(self.f.run(), "vps/jobs.overrides.yaml", "differs")
                self.assertIn("job-a", self.f.out)
        self.f.jobs[0]["interpreter"] = "/usr/bin/python3"
        self.f.write_jobs()
        self.assertStatus(self.f.run(), "vps/jobs.overrides.yaml", "in sync")

    def test_a_changed_job_prompt_is_drift(self):
        self.f.write_repo({"vps/prompt.txt": "Run triage, then lint.\n"})
        self.assertStatus(self.f.run(), "vps/jobs.overrides.yaml", "differs")

    def test_tree_compares_file_by_file_without_the_credit(self):
        self.f.write_host("/h/skills/planted/SKILL.md", "do evil\n")
        self.f.write_host("/h/skills/README.md", "a credit of its own\n")
        s = self.f.run()
        self.assertStatus(s, "vps/skills/planted/SKILL.md", "host only")
        self.assertStatus(s, "vps/skills/triage/SKILL.md", "in sync")
        self.assertNotIn("README.md", self.f.out)

    def test_a_skill_not_yet_on_the_host_is_missing(self):
        (self.f.host / "h/skills/triage/SKILL.md").unlink()
        self.assertStatus(self.f.run(), "vps/skills/triage/SKILL.md", "missing")

    def test_symlinks_are_reported_never_followed(self):
        target = self.f.host / "elsewhere"
        target.mkdir()
        (target / "SKILL.md").write_text("# triage\n")
        (self.f.host / "h/skills/linked").symlink_to(target)
        (self.f.host / "h/skills/triage/gone.md").symlink_to(self.f.host / "nowhere")
        (self.f.host / "h/SOUL.md").unlink()
        (self.f.host / "h/SOUL.md").symlink_to(target / "SKILL.md")
        s = self.f.run()
        self.assertStatus(s, "vps/skills/linked", "link")
        self.assertStatus(s, "vps/skills/triage/gone.md", "link")
        self.assertStatus(s, "vps/SOUL.md", "link")
        self.assertNotIn("vps/skills/linked/SKILL.md", s)
        self.assertEqual(self.f.code, 1, self.f.out)

    def test_direction_reads_the_tag_side_names_too(self):
        # At the tag the overrides set terminal.timeout, which the host still has; main dropped it.
        self.f.write_repo({"vps/config.overrides.yaml": (self.f.repo / "vps/config.overrides.yaml").read_text()
                           + "  timeout: 60\n"})
        self.f.commit()
        self.f.git("tag", "deployed")
        self.f.write_repo({"vps/config.overrides.yaml": "model:\n  default: m2\nterminal:\n  backend: docker\n"
                           "  cwd: /w\n  docker_volumes:\n    - /a:/b\n"})
        self.assertStatus(self.f.run(), "vps/config.overrides.yaml", "repo ahead")

    def test_invalid_host_yaml_stops_without_printing_it(self):
        self.f.write_host("/h/config.yaml", "model: [unclosed secret-value\n", 0o600)
        self.f.run()
        self.assertEqual(self.f.code, 2, self.f.out)
        self.assertIn("/h/config.yaml isn't valid YAML", self.f.out)
        self.assertNotIn("secret-value", self.f.out)

    def test_a_tree_line_without_trailing_slashes_stops(self):
        m = self.f.repo / "vps/deploy.manifest"
        m.write_text(m.read_text().replace("/h/skills/", "/h/skills"))
        self.f.run()
        self.assertEqual(self.f.code, 2, self.f.out)
        self.assertIn("end in /", self.f.out)

    def test_hermes_out_of_lockstep(self):
        self.f.git("commit", "-q", "--allow-empty", "-m", "v2", cwd=self.f.host / "opt/hermes-guard")
        s = self.f.run()
        self.assertTrue(s["hermes"].startswith("differs"), self.f.out)
        self.assertEqual(self.f.code, 1)

    def test_hooks_doctor_issues(self):
        self.f.doctor("2 issue(s) found.  Fix before relying on these hooks.")
        self.f.run()
        self.assertIn("2 issue(s) found", self.f.out)
        self.assertEqual(self.f.code, 1)


if __name__ == "__main__":
    unittest.main()
