"""Run the eval: every task, k trials each, on the VPS through the `eval` profile.

    python3 evals/run.py                      # all tasks, k=5
    python3 evals/run.py --only T1 skip-1 -k 1 # a few tasks, one trial each
    python3 evals/run.py --brain-ref skill-x   # the brain at a branch, to test a skill change first
    python3 evals/run.py --repo-soul           # test this repo's SOUL.md instead of her live one, before deploying it
    python3 evals/run.py --check               # only the local checks before a run; no VPS, no cost

Runs on the local machine and drives the VPS over SSH as user `agent`; nothing is deployed there.
At the start it copies her current setup (SOUL.md, config, skills, memory) into the `eval` profile,
pointed at the trial folder, so the run tests the setup she has now (eval_profile.py); with
--repo-soul her SOUL.md is this repo's, filled in the way deploy.py fills it, and the stamp says so. Each trial
(trial.py): a fresh brain copy (brain_copy.py: the real brain's notes at NOTES_REF with her skills and
rules from its HEAD, or the decoy for chat cases), her memory and skills reset to that start, one Hermes run, then the copy, her report and
her tool calls come back here to be graded. A failed trial's diff of the copy is kept in
evals/results/private/<run>/. One JSONL line per trial in evals/results/<date>-<commit>.jsonl,
public: no report text, and no grader details for tasks on the real brain. The full rows go to
evals/results/private/, which git ignores. A run first saves vps/check-drift.py's output as
<run>.drift.txt beside each file (never a stop: a run may test an undeployed change). Stops at the cost cap; the rest are marked not_run. Ends
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
from brain_copy import NOTES_REF, check_tasks, eval_leaks, item_path, pin_brain, strip_eval_notes, unhash  # noqa: E402
from eval_profile import drift_report, repo_soul, setup_stamp, soul_copy_problem, sync_profile  # noqa: E402
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
    one that newly passes. Brain items are in notes_commit (brain_commit before it)."""
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
    ap.add_argument("--brain-ref", help="a brain branch or commit to take skills and rules from instead of ~/brain's HEAD")
    ap.add_argument("--repo-soul", action="store_true", help="copy this repo's vps/hermes/SOUL.md into the eval profile, not her live one")
    ap.add_argument("--check", action="store_true", help="stop after the local checks, before the VPS")
    a = ap.parse_args(argv)
    if not a.check:
        check_clean()
    soul = repo_soul() if a.repo_soul else (None, None)  # also on --check: fails before any VPS cost
    tmp, started = Path(tempfile.mkdtemp()), False
    try:
        brain_commit = pin_brain(tmp / "pinned", a.brain_ref)
        try:
            stripped = strip_eval_notes(tmp / "pinned")
        except ValueError as e:
            sys.exit("EVAL_NOTES or EVAL_REWORD doesn't fit the notes at NOTES_REF; update these:\n  " + "\n  ".join(e.args[0]))
        if leaks := eval_leaks(tmp / "pinned", stripped):
            sys.exit("the brain still names the eval; add these to EVAL_NOTES or reword them:\n  " + "\n  ".join(leaks))
        tasks = json.loads((HERE / "tasks/tasks.json").read_text())
        full = {t["id"] for t in tasks}
        shas = {t["id"]: task_sha(t) for t in tasks}  # before unhash: the definition as committed
        unhash(tasks, tmp / "pinned")
        check_tasks(tasks, tmp / "pinned")  # all of them, so a partial run warns of the rest too
        if a.only:
            tasks = [t for t in tasks if t["id"] in a.only]
        if a.check:
            print(f"ok: skills and rules {brain_commit}, notes {NOTES_REF[:7]} less {len(stripped)} eval notes; "
                  f"all {len(full)} tasks fit" + (f", {len(tasks)} selected" if a.only else ""))
            return
        started = True
        pages_file = HERE / "tasks/pages.json"
        pages = json.loads(pages_file.read_text()) if pages_file.exists() else {}
        drift = drift_report()  # her files against the repo, as the run starts
        sync_profile(soul[0])
        stamp = setup_stamp(brain_commit, soul[1])
        if problem := soul_copy_problem(stamp):  # before any paid trial
            sys.exit(problem)
        stamp["notes_commit"] = NOTES_REF[:7]  # the notes; brain_commit is only OVERLAY (skills and rules)
        stamp["eval_notes_stripped"] = len(stripped)  # the trials ran on notes_commit less these
        stamp["cost_source"] = "openrouter key"  # earlier runs: Hermes' estimate, about 5× too low
        stamp["task_sha"] = {t["id"]: shas[t["id"]] for t in tasks}
        if a.brain_ref:  # a branch run is never the baseline for the brain she has (report.previous)
            stamp["brain_ref"] = a.brain_ref
        name = f"{datetime.now(timezone.utc):%Y-%m-%dT%H%M}-{stamp['telma_commit']}.jsonl"
        out, private = HERE / "results" / name, HERE / "results/private" / name
        private.parent.mkdir(parents=True, exist_ok=True)
        for f in (out, private):
            f.with_suffix(".drift.txt").write_text(drift)
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
