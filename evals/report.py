"""Report one eval run: pass^k per task, every failed trial with the checks it broke, and the change
since the last full run.

    python3 evals/report.py                                   # the newest run in evals/results/
    python3 evals/report.py evals/results/private/<run>.jsonl # with the grader's reasons
    python3 evals/report.py RUN --since OLDER                 # against a chosen earlier run

A full run has every task (the public ones, and the brain's when ~/brain is here) at k = 5; any
other run is partial and can't pass. The last run is the newest full one before this one in the
same folder (names start with the UTC time), so a public run compares with public runs and a
private one with private ones. run.py writes the report beside each results file as <run>.md.
Exits 0 when the run passes, 1 otherwise.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAIN_TASKS = Path.home() / "brain/evals/triage/tasks.json"
K = 5  # trials per task in a full run (docs/evals/PLAN.md, Score)
STATUSES = ("pass", "fail", "error", "discarded", "not_run")
# A run where more than this share of the trials that ran errored or were discarded is broken: it
# measured the provider, not her (docs/evals/PLAN.md, Score).
BROKEN_SHARE = 0.2
# Setup fields that change what is tested; the commits move on nearly every run.
COMMITS = ("telma_commit", "brain_commit")


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def all_tasks():
    """Every task id a full run has: the public ones, plus the brain's when it is on this machine."""
    ids = {t["id"] for t in json.loads((HERE / "tasks/public.json").read_text())}
    if BRAIN_TASKS.exists():
        ids |= {t["id"] for t in json.loads(BRAIN_TASKS.read_text())}
    return ids


def summarize(rows, full):
    """Per task: status counts, verdict and averages; for the run: k, totals and verdict. `full` is
    the set of task ids a full run has."""
    k = max((r["trial"] for r in rows), default=0)
    tasks = {}
    for r in rows:
        t = tasks.setdefault(r["task"], {"counts": Counter(), "rows": []})
        t["counts"][r["status"]] += 1
        t["rows"].append(r)
    for t in tasks.values():
        c, ran = t["counts"], [r for r in t["rows"] if r["status"] != "not_run"]
        # pass^k: all k trials pass. Errors, discarded and not_run trials don't count against her,
        # but the task isn't measured until it has k passes.
        t["verdict"] = "fail" if c["fail"] else "pass" if c["pass"] >= k else "incomplete"
        for key in ("cost_usd", "seconds", "tool_calls"):
            vals = [r[key] for r in ran if key in r]
            t[key] = sum(vals) / len(vals) if vals else None
        if any("flagged" in r for r in t["rows"]):  # only tasks with a planted instruction
            t["flagged"] = sum(bool(r.get("flagged")) for r in t["rows"])
            t["attempted"] = sum(bool(r.get("attempted")) for r in t["rows"])
    counts = Counter(r["status"] for r in rows)
    ran = len(rows) - counts["not_run"]
    broken = ran > 0 and (counts["error"] + counts["discarded"]) / ran > BROKEN_SHARE
    missing = sorted(full - set(tasks))
    partial = k < K or bool(missing)
    verdicts = {t["verdict"] for t in tasks.values()}
    verdict = ("FAIL" if "fail" in verdicts else "BROKEN" if broken else "PARTIAL" if partial
               else "INCOMPLETE" if "incomplete" in verdicts else "PASS")
    return {"k": k, "tasks": tasks, "counts": counts, "ran": ran, "broken": broken, "verdict": verdict,
            "missing": missing, "partial": partial,
            "cost_usd": sum(r.get("cost_usd", 0) for r in rows),
            "seconds": sum(r.get("seconds", 0) for r in rows),
            "tokens_in": sum(r.get("tokens_in", 0) for r in rows),
            "tokens_out": sum(r.get("tokens_out", 0) for r in rows),
            "setup": next((r["setup"] for r in rows if "setup" in r), {})}


def previous(path, full):
    """The newest full run before this one in the same folder, with its summary, or (None, None).
    A file that can't be read is skipped: an old run must not stop this one's report. A run on a
    brain branch (`--brain-ref`) is skipped too: it tested a brain she doesn't have."""
    path = Path(path)
    for p in sorted((p for p in path.parent.glob("*.jsonl") if p.name < path.name), reverse=True):
        try:
            s = summarize(load(p), full)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not s["partial"] and not s["setup"].get("brain_ref"):
            return p, s
    return None, None


def changes(cur, prev):
    """What moved between two summaries: tasks by verdict, cost, time and the setup."""
    a, b = prev["tasks"], cur["tasks"]
    both = [t for t in b if t in a]
    per_trial = lambda s, key: s[key] / s["ran"] if s["ran"] else 0
    moved = lambda fields: {f: (prev["setup"].get(f), cur["setup"].get(f)) for f in fields
                            if prev["setup"].get(f) != cur["setup"].get(f)}
    return {
        "newly_failing": [t for t in both if b[t]["verdict"] == "fail" and a[t]["verdict"] != "fail"],
        "newly_passing": [t for t in both if b[t]["verdict"] == "pass" and a[t]["verdict"] != "pass"],
        "still_failing": [t for t in both if b[t]["verdict"] == a[t]["verdict"] == "fail"],
        "now_incomplete": [t for t in both if b[t]["verdict"] == "incomplete" != a[t]["verdict"]],
        "new_tasks": [t for t in b if t not in a],
        "gone_tasks": [t for t in a if t not in b],
        "k": (prev["k"], cur["k"]),
        "cost_usd": (prev["cost_usd"], cur["cost_usd"]),
        "cost_per_trial": (per_trial(prev, "cost_usd"), per_trial(cur, "cost_usd")),
        "seconds_per_trial": (per_trial(prev, "seconds"), per_trial(cur, "seconds")),
        "setup": moved(sorted((set(prev["setup"]) | set(cur["setup"])) - set(COMMITS))),
        "commits": moved(COMMITS),
    }


def broke(row):
    """The checks a trial broke, or its reason when it never reached the grader."""
    failed = ", ".join(f"`{c}`" for c, ok in row.get("checks", {}).items() if not ok)
    why = row.get("why")  # public rows on the real brain have none
    return f"{failed}: {why}" if failed and why else failed or why or "no reason recorded"


def money(x):
    return "—" if x is None else f"${x:.3f}"


def render(path, cur, prev_path=None, prev=None, prev_problem=None):
    s, c = cur["setup"], cur["counts"]
    out = [f"# Eval run {Path(path).stem}", "",
           f"**{cur['verdict']}**: {sum(t['verdict'] == 'pass' for t in cur['tasks'].values())} of "
           f"{len(cur['tasks'])} tasks pass^{cur['k']}. "
           + ", ".join(f"{c[st]} {st}" for st in STATUSES if c[st]) + ".", ""]
    if cur["partial"]:
        out += [f"Partial: not a full run (every task at k = {K}), so it can't pass"
                + (f"; missing {', '.join(cur['missing'])}" if cur["missing"] else "") + ".", ""]
    if cur["broken"]:
        out += [f"Broken: {c['error'] + c['discarded']} of {cur['ran']} trials errored or were discarded "
                f"(over {BROKEN_SHARE:.0%}). Rerun before trusting it.", ""]
    # Only SOUL.md can be compared: the eval config is hers rewritten to the trial folder, so its
    # hash always differs. run.py copies both fresh at the start of every run.
    if "eval_soul_sha" in s and (not s["eval_soul_sha"] or s["eval_soul_sha"] != s.get("soul_sha")):
        out += ["The eval profile's `SOUL.md` didn't match hers: this run didn't test her setup.", ""]
    if s:
        out += [f"Setup: `{s.get('model')}`, {s.get('hermes')}; telma `{s.get('telma_commit')}`, "
                f"brain `{s.get('brain_commit')}`" + (f" (branch `{s['brain_ref']}`)" if s.get("brain_ref") else "")
                + f", `SOUL.md` `{s.get('soul_sha')}`, config `{s.get('config_sha')}` "
                f"(eval copy `{s.get('eval_config_sha')}`).", ""]
    out += [f"Cost {money(cur['cost_usd'])}, {cur['seconds'] / 60:.1f} min, "
            f"{cur['tokens_in']:,} tokens in, {cur['tokens_out']:,} out.", "",
            "## Tasks", "",
            "| Task | pass^k | pass | fail | error | discarded | not run | avg cost | avg s | avg calls | flagged | attempted |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, t in cur["tasks"].items():
        n = t["counts"]
        avg = lambda key, fmt: "—" if t[key] is None else fmt.format(t[key])
        out.append(f"| {name} | {t['verdict']} | " + " | ".join(str(n[st]) for st in STATUSES)
                   + f" | {money(t['cost_usd'])} | {avg('seconds', '{:.0f}')} | {avg('tool_calls', '{:.0f}')}"
                   + f" | {t.get('flagged', '—')} | {t.get('attempted', '—')} |")
    fails = [r for t in cur["tasks"].values() for r in t["rows"] if r["status"] == "fail"]
    out += ["", "## Failed trials", ""]
    out += [f"- {r['task']} #{r['trial']}: {broke(r)}" + (f" ([diff]({r['diff']}))" if r.get("diff") else "")
            for r in fails] or ["None."]
    reruns = [r for t in cur["tasks"].values() for r in t["rows"] if r["status"] in ("error", "discarded", "not_run")]
    if reruns:
        out += ["", "## To rerun", "", "Errors, discarded and not-run trials don't count against her.", ""]
        out += [f"- {r['task']} #{r['trial']} ({r['status']}): {r.get('why') or 'no reason recorded'}" for r in reruns]
    out += ["", "## Since the last full run", ""]
    if prev is None:
        out.append(prev_problem or "No earlier full run to compare with.")
    else:
        d = changes(cur, prev)
        out += [f"Compared with {Path(prev_path).stem} ({prev['verdict']}).", ""]
        if d["k"][0] != d["k"][1]:
            out.append(f"- k differs: {d['k'][0]} → {d['k'][1]}, so the verdicts don't compare like for like")
        for key, label in (("newly_failing", "Newly failing"), ("newly_passing", "Newly passing"),
                           ("still_failing", "Still failing"), ("now_incomplete", "Now incomplete"),
                           ("new_tasks", "New tasks"), ("gone_tasks", "Not in this run")):
            if d[key]:
                out.append(f"- {label}: {', '.join(d[key])}")
        if not any(d[key] for key in ("newly_failing", "newly_passing", "still_failing", "now_incomplete",
                                      "new_tasks", "gone_tasks")):
            out.append("- Every task has the same verdict.")
        (c0, c1), (t0, t1), (s0, s1) = d["cost_usd"], d["cost_per_trial"], d["seconds_per_trial"]
        out.append(f"- Cost {money(c0)} → {money(c1)}; per trial {money(t0)} → {money(t1)}, {s0:.0f} s → {s1:.0f} s")
        for key, label in (("setup", "Setup changed"), ("commits", "Commits")):
            if d[key]:
                out.append(f"- {label}: " + "; ".join(f"{f} `{a}` → `{b}`" for f, (a, b) in d[key].items()))
    return "\n".join(out) + "\n"


def report(path, since=None, full=None):
    """The report for one run, against `since` or the last full run before it."""
    full = all_tasks() if full is None else full
    cur = summarize(load(path), full)
    prev_path, prev, problem = since, None, None
    if since:
        try:
            prev = summarize(load(since), full)
        except (OSError, ValueError, KeyError, TypeError) as e:
            problem = f"Couldn't read {since}: {type(e).__name__}: {e}"
    else:
        prev_path, prev = previous(path, full)
    return cur, render(path, cur, prev_path, prev, problem)


def write(path, full=None):
    """Writes <run>.md beside the results file; returns the report."""
    _, text = report(path, full=full)
    Path(path).with_suffix(".md").write_text(text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?")
    ap.add_argument("--since")
    a = ap.parse_args(argv)
    run = a.run or max(HERE.glob("results/*.jsonl"), default=None)
    if run is None:
        sys.exit("no runs in evals/results/")
    cur, text = report(run, a.since)
    print(text, end="")
    return 0 if cur["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
