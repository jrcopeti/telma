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
from run import EVAL_NOTES, eval_leaks, passage, strip_eval_notes  # noqa: E402

HASHED = re.compile(r"sha256:[0-9a-f]{64}")  # a brain path by its hash (run.unhash)
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
                                           "strip", "remove_text", "plant", "contradict", "replaces"}, set(t))
                e = t["expect"]
                self.assertTrue(e == "ask" or (isinstance(e, dict) and set(e) <= FOLDERS
                                               and all(isinstance(n, int) and n > 0 for n in e.values())))
                for key in ("targets", "tells"):
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
                    self.assertIn(want, ("superseded", "amended", "ask"))
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
        (root / "decisions").mkdir()
        (root / "inbox").mkdir()
        (root / EVAL_NOTES[0]).write_text("# Telma eval: design\n")
        (root / "decisions/other.md").write_text("# Other\n\nSee docs/evals/PLAN.md.\n")
        (root / "inbox/x.md").write_text("eval-v1 step 6\n")
        (root / "notes").mkdir()
        (root / "notes/linker.md").write_text(f"# L\n\n[amend rule](../{EVAL_NOTES[2]})\n")
        (root / "index.md").write_text(f"# Index\n- [Design]({EVAL_NOTES[0]}) — x\n- [Other](decisions/other.md) — y\n")
        strip_eval_notes(root)
        self.assertFalse((root / EVAL_NOTES[0]).exists())
        self.assertEqual((root / "index.md").read_text(), "# Index\n- [Other](decisions/other.md) — y\n")
        self.assertEqual(eval_leaks(root), ["decisions/other.md", "notes/linker.md"])


if __name__ == "__main__":
    unittest.main()
