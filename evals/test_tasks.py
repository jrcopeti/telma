"""Checks evals/tasks/tasks.json before anything runs on the VPS, where every trial costs money.
Items in the brain (sources/x.md) can't be checked here: run.py checks them against the pinned brain.

    python3 -m unittest evals/test_tasks.py
"""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "evals"))
import brain_copy  # noqa: E402
from brain_copy import eval_leaks, passage, stale_strips, strip_eval_notes  # noqa: E402

HASHED = re.compile(r"sha256:[0-9a-f]{64}")  # a brain path by its hash (brain_copy.unhash)
FOLDERS = {"intents", "guidelines", "decisions", "projects", "notes"}
TASKS = json.loads((REPO / "evals/tasks/tasks.json").read_text())


def path(item):
    assert item.startswith("telma:"), f"{item}: an item in this repo needs the telma: prefix"
    return REPO / item.removeprefix("telma:")


def ours(t):
    """The task's items that live in this repo."""
    return [i for i in t.get("items", []) if i.startswith("telma:")]


class TasksTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [t["id"] for t in TASKS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_each_task_is_well_formed(self):
        for t in TASKS:
            with self.subTest(task=t["id"]):
                self.assertTrue(set(t) <= {"id", "items", "expect", "why", "chat", "targets", "tells", "page",
                                           "strip", "remove_text", "plant", "contradict", "replaces", "leaves_out"}, set(t))
                e = t["expect"]
                self.assertTrue(isinstance(e, dict) and set(e) <= FOLDERS
                                and all(isinstance(n, int) and n > 0 for n in e.values()))
                for key in ("targets", "tells", "leaves_out"):
                    self.assertTrue(all(isinstance(s, str) and s for s in t.get(key, [])))
                if t.get("chat"):
                    self.assertEqual(e, {})
                    if "page" in t:
                        self.assertTrue(path(t["page"]).is_file())
                else:
                    self.assertTrue(t["items"] or t.get("plant"))
                for f in t.get("plant", []):
                    self.assertTrue(set(f) <= {"path", "from", "index"} and path(f["from"]).is_file(), f)
                    self.assertRegex(f["path"], r"^(intents|guidelines|decisions|projects|notes|sources)/[^/]+\.md$")
                    self.assertEqual("index" in f, not f["path"].startswith("sources/"))
                if "contradict" in t:
                    self.assertEqual(len(t["contradict"]), 2)
                    self.assertTrue(set(t["contradict"]) <= {f["path"] for f in t.get("plant", [])})
                for f, want in t.get("replaces", {}).items():
                    self.assertRegex(f, r"^decisions/[^/]+\.md$")
                    self.assertIn(want, ("superseded", "amended"))
                    self.assertTrue(isinstance(e, dict) and e.get("decisions"), "a replacement files a decision")
                for item in t.get("items", []):
                    # The brain's evals/ never reaches the copy, so an item from there would be missing.
                    self.assertTrue(item.startswith("telma:") or item.startswith(("sources/", "inbox/"))
                                    or HASHED.fullmatch(item), item)
                for f in t.get("strip", []):
                    if not HASHED.fullmatch(f):
                        self.assertRegex(f, r"^(intents|guidelines|decisions|projects|notes)/[^/]+\.md$")
                for f, specs in t.get("remove_text", {}).items():
                    self.assertRegex(f, r"^(intents|guidelines|decisions|projects|notes)/[^/]+\.md$")
                    self.assertTrue(specs and all(set(s) == {"sha256", "chars"} and len(s["sha256"]) == 64
                                                  and type(s["chars"]) is int and s["chars"] > 0 for s in specs))

    def test_every_item_in_this_repo_exists(self):
        for t in TASKS:
            for item in ours(t):
                with self.subTest(item=item):
                    self.assertTrue(path(item).is_file())

    def test_planted_pages_read_as_a_text_only_capture(self):
        # Capture's text-only fetch flattens HTML: the planted text arrives as plain prose.
        for t in TASKS:
            for item in ours(t):
                text = path(item).read_text()
                with self.subTest(item=item):
                    self.assertNotRegex(text, r"<!--|<span|<div|style=")


class PassageTest(unittest.TestCase):
    """remove_text names a passage by its hash and length, so the real text stays in the brain."""

    def spec(self, s):
        return {"sha256": hashlib.sha256(s.encode()).hexdigest(), "chars": len(s)}

    def test_finds_the_passage_once(self):
        self.assertEqual(passage("a — fact. b", self.spec("— fact. ")), (2, 10))

    def test_missing_or_twice_is_none(self):
        self.assertIsNone(passage("abc", self.spec("x")))
        self.assertIsNone(passage("ab ab", self.spec("ab")))
        self.assertIsNone(passage("a", self.spec("longer")))


class EvalNotesTest(unittest.TestCase):
    """Her copy holds no note about this eval, so nothing tells her she's being tested."""

    def test_strips_the_notes_and_their_index_lines_and_finds_what_is_left(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for d in ("decisions", "inbox", "notes"):
            (root / d).mkdir()
        design, amend = "decisions/design.md", "decisions/amend.md"
        hashed = lambda s: "sha256:" + hashlib.sha256(s.encode()).hexdigest()
        (root / design).write_text("# Design\n")
        (root / amend).write_text("# Amend\n")
        (root / "decisions/other.md").write_text("# Other\n\nSee docs/evals/PLAN.md.\n")
        (root / "inbox/x.md").write_text("eval-v1 step 6\n")
        (root / "notes/linker.md").write_text(f"# L\n\n[amend rule](../{amend})\n")
        (root / "notes/price.md").write_text("Pinning is planned (telma\nrepo, eval-v1 step 7).\n")
        (root / "index.md").write_text(f"# Index\n- [Design]({design}) — x\n- [Other](decisions/other.md) — y\n")
        old = "(telma\nrepo, eval-v1 step 7)"
        reword = {hashed("notes/price.md"): [{**PassageTest.spec(None, old), "with": "(telma\nrepo)"}]}
        self.assertEqual(stale_strips(root, [hashed(design), hashed(amend)], reword), [])
        moved = {hashed("notes/price.md"): [{**reword[hashed("notes/price.md")][0], "chars": 5}]}
        self.assertEqual(stale_strips(root, [hashed("decisions/gone.md")], moved),
                         [f"{hashed('decisions/gone.md')}: no such note",
                          f"notes/price.md: passage {moved[hashed('notes/price.md')][0]['sha256'][:12]}"])
        stripped = strip_eval_notes(root, [hashed(design), hashed(amend)], reword)
        self.assertEqual(sorted(stripped), [amend, design])
        self.assertFalse((root / design).exists())
        self.assertEqual((root / "index.md").read_text(), "# Index\n- [Other](decisions/other.md) — y\n")
        self.assertEqual((root / "notes/price.md").read_text(), "Pinning is planned (telma\nrepo).\n")
        self.assertEqual(eval_leaks(root, stripped), ["decisions/other.md", "notes/linker.md"])


class PinBrainTest(unittest.TestCase):
    """The notes come from NOTES_REF, whatever her brain has since; skills and rules from HEAD."""

    def test_notes_from_the_fixed_commit_overlay_from_head(self):
        import subprocess
        import tempfile
        from unittest import mock
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        brain, dest = Path(tmp.name) / "brain", Path(tmp.name) / "out" / "pinned"
        git = ["git", "-C", str(brain), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]

        def commit(files, gone=()):
            for f, text in files.items():
                (brain / f).parent.mkdir(parents=True, exist_ok=True)
                (brain / f).write_text(text)
            for f in gone:
                (brain / f).unlink()
            subprocess.run(git + ["add", "-A"], check=True)
            subprocess.run(git + ["commit", "-qm", "x"], check=True)
            return subprocess.run(git + ["rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

        brain.mkdir()
        subprocess.run(git + ["init", "-q"], check=True)
        notes = commit({"projects/p.md": "old\n", "skills/triage/SKILL.md": "v1\n", "skills/old.md": "x\n",
                        "AGENTS.md": "v1\n", "evals/answers.md": "a\n", "taste.md": "v1\n",
                        "decisions/README.md": "v1\n", "decisions/d.md": "old\n"})
        head = commit({"projects/p.md": "about the eval\n", "notes/new.md": "eval\n", "skills/triage/SKILL.md": "v2\n",
                       "AGENTS.md": "v2\n", "taste.md": "v2\n", "decisions/README.md": "v2\n", "decisions/d.md": "new\n"},
                      gone=["skills/old.md"])
        with mock.patch.object(brain_copy, "BRAIN", brain), mock.patch.object(brain_copy, "NOTES_REF", notes):
            (brain / "notes/draft.md").write_text("a note mid-sync\n")  # notes never reach a trial: fine
            self.assertEqual(brain_copy.pin_brain(dest), head)
            (brain / "skills/triage/SKILL.md").write_text("v3\n")  # a rule a trial would read: refused
            with self.assertRaises(SystemExit):
                brain_copy.pin_brain(Path(tmp.name) / "again")
        self.assertEqual((dest / "projects/p.md").read_text(), "old\n")
        self.assertFalse((dest / "notes/new.md").exists())
        self.assertEqual((dest / "skills/triage/SKILL.md").read_text(), "v2\n")
        self.assertFalse((dest / "skills/old.md").exists())
        self.assertEqual((dest / "AGENTS.md").read_text(), "v2\n")
        self.assertEqual((dest / "taste.md").read_text(), "v2\n")
        self.assertEqual((dest / "decisions/README.md").read_text(), "v2\n")
        self.assertEqual((dest / "decisions/d.md").read_text(), "old\n")
        self.assertFalse((dest / "evals").exists())
        self.assertFalse((dest / "notes/draft.md").exists())


if __name__ == "__main__":
    unittest.main()
