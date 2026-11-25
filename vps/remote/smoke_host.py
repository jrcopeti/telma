"""smoke-deploy.py's host side: a scratch folder standing in for the host, away from her live files.
Runs as root (or as the current user for a local rehearsal), the request as JSON on stdin:
python3 -I -c <this file>. Actions:

setup: the scratch tree (an agent-owned folder holding a.sh, root's closed backups folder, her cron
folder), and a copy of her cron ledger made as agent through su, so the real login path is exercised.
mark_running: a `running` row in the scratch ledger.
swap_for_link: the folder holding a.sh replaced by a symlink to another folder.
cleanup: the scratch folder removed, only a real folder named deploy-smoke-* that this user owns.
"""
import json
import os
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys

req = json.loads(sys.stdin.read())
R = req["root"]
HOME = R + "/home/agent"


def own(path, mode):
    """Mode first, while the folder is still root's alone, then the owner, never through a link."""
    os.chmod(path, mode)
    os.chown(path, req["uid"], req["gid"], follow_symlinks=False)


def setup():
    os.mkdir(R, 0o755)  # new, or setup stops: a name that exists already isn't trusted
    os.makedirs(R + "/home/agent/.hermes/cron")
    os.makedirs(HOME + "/smoke")
    for d in (R + "/home", HOME, HOME + "/.hermes"):
        os.chmod(d, 0o755)
    fd = os.open(HOME + "/smoke/a.sh", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
    with os.fdopen(fd, "w") as f:  # made while the folder is still root's, so agent can't plant a link first
        f.write("old\n")
        os.fchown(f.fileno(), req["uid"], req["gid"])
        os.fchmod(f.fileno(), 0o755)
    own(HOME + "/smoke", 0o755)
    own(HOME + "/.hermes/cron", 0o755)
    ledger = R + req["ledger"]
    r = subprocess.run(req["as_agent"] + ["python3 -I - " + shlex.quote(req["ledger_src"]) + " " + shlex.quote(ledger)],
                       input=req["ledger_copy_code"], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr.strip()[-500:], file=sys.stderr)
        sys.exit(2)
    print(json.dumps({"login_output": r.stdout.strip()}))


def mark_running():
    with sqlite3.connect(R + req["ledger"]) as db:
        db.execute("INSERT INTO executions (id, job_id, source, process_id, pid, status, claimed_at) "
                   "VALUES ('smoke', 'smoke-job', 'smoke', 'p', 1, 'running', '2026-01-01T00:00:00Z')")


def swap_for_link():
    os.rename(HOME + "/smoke", HOME + "/smoke.real")
    os.symlink(HOME + "/smoke.real", HOME + "/smoke")


def cleanup():
    name = os.path.basename(R.rstrip("/"))
    s = os.lstat(R)
    if not name.startswith("deploy-smoke-") or not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid():
        print("refusing to remove %s: not a deploy-smoke folder made by this user" % R, file=sys.stderr)
        sys.exit(2)
    shutil.rmtree(R)


{"setup": setup, "mark_running": mark_running, "swap_for_link": swap_for_link, "cleanup": cleanup}[req["action"]]()
