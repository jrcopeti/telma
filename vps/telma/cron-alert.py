"""Hermes pre_tool_call hook on Telma's cron tool (matcher in cron-alert.hooks.yaml): post to #alerts
every cron job she creates, changes, pauses, resumes, runs, cancels or removes, with its name,
schedule, prompt and the tools it gets. A page she reads in a chat can ask for a job that outlives
the chat (eval T6). Detection only, like the exfil tripwire: it always prints {} and exits 0, so the
call goes ahead; a blocking hook can't tell the owner's ask from a page's. `list` is silent.
Every alert and failure is also logged locally; tripwire-health.sh reports the failures.
Usage: python3 -I cron-alert.py, with Hermes's hook payload on stdin."""
import json
import os
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or HOME / ".hermes")
JOBS = Path(os.environ.get("CRON_ALERT_JOBS", HERMES_HOME / "cron/jobs.json"))
# The same #alerts webhook as the exfil tripwire.
WEBHOOK = Path(os.environ.get("CRON_ALERT_WEBHOOK_FILE", HOME / ".config/exfil-tripwire/webhook"))
STATE = Path(os.environ.get("CRON_ALERT_STATE", HOME / ".local/state/cron-alert"))
PROMPT_MAX = 900  # characters of a prompt in the alert; Discord takes 2000 in all
FIELD_MAX = 200
LIMIT = 1990
SILENT = {"list"}
# Shown for a new job and for the fields an update changes, in this order. What makes a job risky:
# its tools, a script it runs, where its output goes.
FIELDS = ["schedule", "prompt", "enabled_toolsets", "skills", "skill", "script", "no_agent", "monitor",
          "monitor_script", "monitor_url", "context_from", "workdir", "deliver", "failure_deliver", "repeat",
          "paused", "name"]


def code(s, limit=FIELD_MAX):
    # In a code span Discord neither previews nor pings; a backtick would close it.
    s = " ↵ ".join(str(s).replace("`", "").splitlines()) or " "
    return "`" + (s if len(s) <= limit else s[:limit] + "…") + "`"


def jobs():
    d = json.loads(JOBS.read_text())
    d = d.get("jobs", []) if isinstance(d, dict) else d
    return d.values() if isinstance(d, dict) else d


def find(ref):
    """The stored job for a job_id or a name, as Hermes resolves it: exact id, then name in any case."""
    js = [j for j in jobs() if isinstance(j, dict)]
    by_name = [j for j in js if str(j.get("name") or "").lower() == str(ref).lower()]
    return next((j for j in js if j.get("id") == ref), None) or (by_name[0] if len(by_name) == 1 else None)


def toolsets(v):
    if v is None:
        return "the cron default (every toolset not disabled in config.yaml)"
    return ", ".join(map(str, v)) if v else "none"


def value(key, v):
    if key == "enabled_toolsets":
        return code(toolsets(v))
    return code(v, PROMPT_MAX if key == "prompt" else FIELD_MAX)


def describe(args):
    action = str(args.get("action") or "?").strip().lower()
    head = f"⏰ cron-alert: Telma's cron tool, action {code(action)}"
    given = {k: args[k] for k in FIELDS if args.get(k) is not None}
    if action == "create":
        lines = [head + f": a new job {code(args.get('name') or '(no name)')}."]
        lines += [f"- {k}: {value(k, v)}" for k, v in given.items() if k != "name"]
        if "enabled_toolsets" not in given:
            lines.append(f"- enabled_toolsets: {value('enabled_toolsets', None)}")
        return lines
    ref, job, why = args.get("job_id"), None, "a job not found in jobs.json"
    try:
        job = find(ref) if ref else None
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as e:
        why = f"jobs.json unreadable: {code(repr(e)[:150])}"
    if not job:
        lines = [head + f" on {code(ref or '(no job_id)')}, {why}."]
    else:
        lines = [head + f" on {code(job.get('name') or '(no name)')} ({code(job.get('id'))}):",
                 f"- schedule: {code(job.get('schedule_display') or job.get('schedule'))}",
                 f"- prompt: {value('prompt', job.get('prompt') or '')}",
                 f"- enabled_toolsets: {value('enabled_toolsets', job.get('enabled_toolsets'))}"]
        if job.get("script"):
            lines.append(f"- script: {code(job['script'])}")
    if action == "update":
        lines.append("Changes:" if given else "Changes: none given.")
        lines += [f"- {k} → {value(k, v)}" for k, v in given.items()]
    elif action == "run" and args.get("prompt"):
        lines.append(f"Added to this run's prompt: {value('prompt', args['prompt'])}")
    return lines


def log(name, text):
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / name, "a") as f:
        f.write(text.replace("\n", " | ") + "\n")


def post(text):
    log("alerts.log", text)
    if os.environ.get("CRON_ALERT_NO_POST"):
        return
    url = WEBHOOK.read_text().strip()
    # No pings, and no link previews (flag 4): a preview would fetch a URL from the prompt.
    body = json.dumps({"content": text, "allowed_mentions": {"parse": []}, "flags": 4}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "cron-alert"})
    urllib.request.urlopen(req, timeout=5).close()


def main():
    try:
        payload = json.load(sys.stdin)
        args = payload.get("tool_input") or payload.get("args") or {}
        if str(args.get("action") or "").strip().lower() not in SILENT:
            lines = describe(args)
            lines.append(f"Session {code(payload.get('session_id') or '?')}. The call went ahead; "
                         "if you didn't ask for this, see the kill switch.")
            text = "\n".join(lines)
            post(text if len(text) <= LIMIT else text[:LIMIT] + "…")
    except Exception as e:  # a broken hook must say so, and never stop the call
        msg = f"⚠️ cron-alert failed, a cron call went unannounced or its alert was lost: {code(repr(e)[:300])}"
        try:
            log("failed.log", msg)
            post(msg)
        except Exception as e2:
            print(f"cron-alert: {e!r}; alert failed: {e2!r}", file=sys.stderr)
    print("{}")


if __name__ == "__main__":
    main()
