"""Prints one trial's outcome as JSON: time, Hermes' usage reports, exit codes, OpenRouter's count
before and after, the cron counts and the event lines. Runs on the VPS in the trial's out folder:
python3 - <eval profile> <cron-alert state folder>"""
import glob
import json
import os
import sys

prof, alert_dir = sys.argv[1], sys.argv[2]
# Cron jobs left in the eval profile, and runs any job made: the reset leaves none, so any here is
# this trial's (T6 #1, 2026-11-22: a page became a monthly job). -1: a jobs.json that won't parse.
try:
    d = json.load(open(f"{prof}/cron/jobs.json"))
    jobs = len(d.get("jobs") or [] if isinstance(d, dict) else d)
except FileNotFoundError:
    jobs = 0
except Exception:
    jobs = -1
runs = sum(os.path.isfile(f) for f in glob.glob(f"{prof}/cron/output/*/*.md"))
# Cron calls the hook announced (cron-alert.py, eval-v1 step 8; its failures don't count);
# 0 before it shipped.
try:
    alerts = sum(line.startswith("⏰") for line in open(f"{alert_dir}/alerts.log", encoding="utf-8", errors="replace"))
except FileNotFoundError:
    alerts = 0
t = [float(open(f).read()) for f in ("t0.txt", "t1.txt")]
print(json.dumps({"seconds": t[1] - t[0],
                  "usage": [json.load(open(f)) for f in sorted(glob.glob("usage*.json"))],
                  "exits": [int(open(f).read()) for f in sorted(glob.glob("exit*.txt"))],
                  "key": [json.loads(open(f).read() or "null") for f in ("key0.txt", "key1.txt")],
                  "cron": [jobs, runs, alerts],
                  "events": [line for f in sorted(glob.glob("events*.jsonl")) for line in open(f)]}))
