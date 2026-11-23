"""Run the eval: every task, k trials each, on the VPS through the `eval` profile.

    python3 evals/run.py                      # all tasks, k=5
    python3 evals/run.py --only T1 skip-1 -k 1 # a few tasks, one trial each
    python3 evals/run.py --brain-ref skill-x   # the brain at a branch, to test a skill change first

Runs on the local machine and drives the VPS over SSH as user `agent`; nothing is deployed there.
At the start it copies her current setup (SOUL.md, config, skills, memory) into the `eval` profile,
pointed at the trial folder, so the run tests the setup she has now (eval_profile.py). Each trial
(trial.py): a fresh brain copy (brain_copy.py: the real brain at one pinned commit, or the decoy for
chat cases), her memory and skills reset to that start, one Hermes run, then the copy, her report and
her tool calls come back here to be graded. A failed trial's diff of the copy is kept in
evals/results/private/<run>/. One JSONL line per trial in evals/results/<date>-<commit>.jsonl,
public: no report text, and no grader details for tasks on the real brain. The full rows go to
evals/results/private/, which git ignores. Stops at the cost cap; the rest are marked not_run. Ends
with report.py's report, written beside each results file and printed from the private one.
Every run needs the owner's yes (docs/evals/PLAN.md, Rules).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from brain_copy import check_tasks, eval_leaks, item_path, pin_brain, stale_rewords, strip_eval_notes, unhash  # noqa: E402
from eval_profile import setup_stamp, sync_profile  # noqa: E402
from report import write as write_report  # noqa: E402
from trial import trial  # noqa: E402
from vps import PROFILE, WORK, remove_container, stop_gateway, vps  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CAP_USD = 5.0


def check_clean():
    """The task list as committed, since results are stamped with this repo's commit."""
    r = subprocess.run(["git", "status", "--porcelain", "--", "evals/tasks"], cwd=REPO, capture_output=True, text=True)
    if r.returncode or r.stdout.strip():
        sys.exit("evals/tasks has uncommitted changes: commit them first, so the run's commit names its tasks")


def task_sha(task, repo=REPO):
    """A task's definition and the files of this repo it names (items, planted notes, a chat page; for
    a chat case also the decoy brain and its markers), so a report can tell a task that changed from
    one that newly passes. Brain items are in brain_commit."""
    h = hashlib.sha256(json.dumps(task, sort_keys=True).encode())
    names = set()
    def walk(v):
        if isinstance(v, str) and v.startswith("telma:"):
            names.add(v.removeprefix("telma:"))
        elif isinstance(v, (list, dict)):
            for x in v.values() if isinstance(v, dict) else v:
                walk(x)
    walk(task)
    if task.get("chat"):
        decoy = repo / "evals/decoy-brain"
        names |= {str(f.relative_to(repo)) for f in decoy.rglob("*") if f.is_file()}
    for name in sorted(names):
        f = repo / name
        h.update(b"\0" + name.encode() + (b"\1" + f.read_bytes() if f.is_file() else b"\0missing"))
    return h.hexdigest()[:12]


def page_problem(task, pages):
    """Why a chat case can't run: no page, no published URL, or the page changed since publishing."""
    if "page" not in task:
        return "the task names no page"
    entry = pages.get(task["id"])
    if not isinstance(entry, dict) or not entry.get("url"):
        return "no page URL in tasks/pages.json"
    if hashlib.sha256(item_path(task["page"], None).read_bytes()).hexdigest() != entry.get("sha256"):
        return f"{task['page']} changed since it was published: republish it and update tasks/pages.json"
    return None


def public_row(row, chat):
    """Public rows carry no report text: her answers can quote real brain files. Grader details stay
    only for the chat cases, which run on the decoy, and for trials that never ran (the cap, a page)."""
    return {k: v for k, v in row.items()
            if k not in ("report", "diff", "diff_error") and (chat or k != "why" or row["status"] == "not_run")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--brain-ref", help="a brain branch or commit to pin instead of ~/brain's HEAD")
    a = ap.parse_args(argv)
    check_clean()
    tmp, started = Path(tempfile.mkdtemp()), False
    try:
        brain_commit = pin_brain(tmp / "pinned", a.brain_ref)
        # A branch or an older commit may predate a reword's passage; her current brain may not.
        if not a.brain_ref and (stale := stale_rewords(tmp / "pinned")):
            sys.exit("EVAL_REWORD no longer fits the brain; update these:\n  " + "\n  ".join(stale))
        stripped = strip_eval_notes(tmp / "pinned")
        if leaks := eval_leaks(tmp / "pinned", stripped):
            sys.exit("the brain still names the eval; add these to EVAL_NOTES or reword them:\n  " + "\n  ".join(leaks))
        tasks = json.loads((HERE / "tasks/tasks.json").read_text())
        full = {t["id"] for t in tasks}
        shas = {t["id"]: task_sha(t) for t in tasks}  # before unhash: the definition as committed
        unhash(tasks, tmp / "pinned")
        check_tasks(tasks, tmp / "pinned")  # all of them, so a partial run warns of the rest too
        if a.only:
            tasks = [t for t in tasks if t["id"] in a.only]
        started = True
        pages_file = HERE / "tasks/pages.json"
        pages = json.loads(pages_file.read_text()) if pages_file.exists() else {}
        sync_profile()
        stamp = setup_stamp(brain_commit)
        stamp["eval_notes_stripped"] = len(stripped)  # the trials ran on brain_commit less these
        stamp["cost_source"] = "openrouter key"  # earlier runs: Hermes' estimate, about 5× too low
        stamp["task_sha"] = {t["id"]: shas[t["id"]] for t in tasks}
        if a.brain_ref:  # a branch run is never the baseline for the brain she has (report.previous)
            stamp["brain_ref"] = a.brain_ref
        name = f"{datetime.now(timezone.utc):%Y-%m-%dT%H%M}-{stamp['telma_commit']}.jsonl"
        out, private = HERE / "results" / name, HERE / "results/private" / name
        private.parent.mkdir(parents=True, exist_ok=True)
        run_all(tasks, a.k, pages, tmp, stamp, out, private)
        reports = {}
        for f in (out, private):  # one failing must not cost the other
            try:
                reports[f] = write_report(f, full)
            except (OSError, ValueError, KeyError, TypeError) as e:
                print(f"no report for {f.name}: {type(e).__name__}: {e}")
        print("\n" + reports.get(private, ""), end="")
        print(out.with_suffix(".md") if out in reports else out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # the pinned copy of the real brain
        if started:
            vps(stop_gateway() + remove_container() + f"rm -rf {WORK} {PROFILE}/cron\n", check=False)  # no job outlives the run


def run_all(tasks, trials, pages, tmp, stamp, out, private):
    spent = 0.0
    with out.open("a") as f, private.open("a") as fp:
        for task in tasks:
            for k in range(1, trials + 1):
                problem = page_problem(task, pages) if task.get("chat") else None
                if problem:
                    row = {"task": task["id"], "trial": k, "status": "not_run", "why": problem}
                elif spent >= CAP_USD:
                    row = {"task": task["id"], "trial": k, "status": "not_run", "why": f"cost cap ${CAP_USD} reached"}
                else:
                    try:
                        row = trial(task, k, pages, tmp / "pinned", tmp, private.with_suffix(""))
                    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as e:
                        row = {"task": task["id"], "trial": k, "status": "error", "why": f"{type(e).__name__}: {e}"[:400]}
                    spent += row.get("cost_usd", 0)
                fp.write(json.dumps({**row, "setup": stamp}) + "\n")
                f.write(json.dumps({**public_row(row, task.get("chat")), "setup": stamp}) + "\n")
                f.flush()
                fp.flush()
                print(f"{task['id']:16} {k} {row['status']:9} ${spent:.3f} {row.get('why', '')[:80]}")


if __name__ == "__main__":
    main()
