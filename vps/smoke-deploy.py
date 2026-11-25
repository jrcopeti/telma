#!/usr/bin/env python3
"""A smoke test of deploy.py's host side: the real remote/deploy_host.py and running_jobs.py, run the
way a deploy runs them, against a scratch folder, never her live files.

python3 vps/smoke-deploy.py           over ssh to the VPS as root, `su - agent` for the ledger read
python3 vps/smoke-deploy.py --local   a rehearsal on this machine, as the current user

A scratch folder deploy-smoke-<time> under /var/tmp holds a file owned by agent, a root-owned closed
backups folder and a copy of her cron ledger (made by `agent`, the original opened read-only). It
checks the read, a copy, a refused symlink, a refused running job and what is left behind, then
removes the folder. No job runs and no live file is read but the ledger. Exit 0 when every check
passed, 1 when one failed, 2 when it couldn't run.
"""
import argparse
import base64
import grp
import importlib.util
import json
import os
import pwd
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("deploy", HERE / "deploy.py")
deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deploy)
drift = deploy.drift
LEDGER = deploy.LEDGER


def host_script(name, request, local):
    """remote/<name> as root on the VPS (or here), the request on stdin."""
    code = (HERE / "remote" / name).read_text()
    cmd = [sys.executable, "-I", "-c", code] if local else [*drift.SSH, drift.HOST, f"python3 -I -c {shlex.quote(code)}"]
    return subprocess.run(cmd, input=json.dumps(request), capture_output=True, text=True)


def agent_ids():
    """agent's uid and gid on the VPS."""
    r = subprocess.run([*drift.SSH, drift.HOST, "id -u agent; id -g agent"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"smoke-deploy: couldn't read agent's ids: {r.stderr.strip()[-300:]}")
    uid, gid = r.stdout.split()
    return int(uid), int(gid)


def main():
    parser = argparse.ArgumentParser(description="Smoke test of deploy.py's host side.")
    parser.add_argument("--local", action="store_true", help="rehearse on this machine")
    local = parser.parse_args().local
    parent = tempfile.mkdtemp(prefix="deploy-smoke-parent-") if local else "/var/tmp"
    root = f"{parent}/deploy-smoke-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    names = "%s:%s" % (pwd.getpwuid(os.getuid()).pw_name, grp.getgrgid(os.getgid()).gr_name) if local else "agent:agent"
    src = f"{parent}/source-ledger.db" if local else LEDGER
    as_agent = ["bash", "-c"] if local else ["su", "-", "agent", "-c"]
    ids = (os.getuid(), os.getgid()) if local else agent_ids()
    failed = []

    def check(what, ok, detail=""):
        print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f"  ({detail})" if detail and not ok else ""))
        if not ok:
            failed.append(what)

    def request(**kw):
        return {"root": root, "parent": parent, **kw}

    if local:
        import sqlite3
        with sqlite3.connect(src) as db:
            db.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, source TEXT NOT NULL, "
                       "process_id TEXT NOT NULL, pid INTEGER NOT NULL, status TEXT NOT NULL, claimed_at TEXT NOT NULL)")
    try:
        r = host_script("smoke_host.py", request(action="setup", ledger=LEDGER, ledger_src=src, as_agent=as_agent,
                                                  ledger_copy_code=(HERE / "remote/ledger_copy.py").read_text(),
                                                  uid=ids[0], gid=ids[1]), local)
        if r.returncode:
            print(f"smoke-deploy: setup failed: {r.stderr.strip()[-500:]}", file=sys.stderr)
            return 2
        login = json.loads(r.stdout.splitlines()[-1])["login_output"]
        check("her cron ledger copied as agent (no job running in the copy)", login.splitlines()[-1:] == ["0"], login)

        path = "/home/agent/smoke/a.sh"
        new = b"new\n"
        r = host_script("deploy_host.py", request(action="read", files=[path]), local)
        got = json.loads(r.stdout)[path] if r.returncode == 0 else None
        check("read: the file, its owner and mode, its bytes", bool(got) and got["stat"].endswith(" 755")
              and base64.b64decode(got["data"]) == b"old\n", r.stderr.strip()[-300:] or str(got))
        was = got and got["sha"]
        user, group = names.split(":")
        copy = request(action="copy", backups="/home/agent/.hermes/deploy-backups",
                       stamp="smoke-1", ledger=LEDGER, running_code=(HERE / "remote/running_jobs.py").read_text(),
                       as_agent=as_agent, files=[{"host": path, "data": base64.b64encode(new).decode(), "user": user,
                                                  "group": group, "perm": "755", "was": was}])

        r = host_script("deploy_host.py", copy, local)
        check("copy: exit 0, the swapped path printed", r.returncode == 0 and json.loads(r.stdout) == [path],
              f"{r.returncode}: {r.stderr.strip()[-300:]}")
        r = host_script("deploy_host.py", request(action="read", files=[path]), local)
        after = json.loads(r.stdout)[path]
        check("copy: new bytes, owner and mode as asked", base64.b64decode(after["data"]) == new and after["stat"] == f"{names} 755",
              after["stat"])
        r = subprocess.run([*(["bash", "-c"] if local else [*drift.SSH, drift.HOST]), "find " + shlex.quote(root)
                            + " -name '*.deploy-tmp' -o -path '*deploy-backups/smoke-1/*' -type f"], capture_output=True, text=True)
        check("copy: the old file kept in a backup, no temp file left",
              "smoke-1" in r.stdout and ".deploy-tmp" not in r.stdout, r.stdout)

        copy["stamp"], copy["files"][0]["was"] = "smoke-2", after["sha"]
        r = host_script("smoke_host.py", request(action="mark_running", ledger=LEDGER), local)
        check("a running job marked in the scratch ledger", r.returncode == 0, r.stderr.strip()[-300:])
        r = host_script("deploy_host.py", copy, local)
        check("a running job: nothing copied, exit 5, named", r.returncode == 5 and "smoke-job" in r.stderr, f"{r.returncode}: {r.stderr.strip()[-300:]}")

        host_script("smoke_host.py", request(action="swap_for_link"), local)
        r = host_script("deploy_host.py", request(action="read", files=[path]), local)
        check("a symlinked folder: reported, never read through", "link" in (json.loads(r.stdout).get(path) or {}), r.stdout[-300:])
        copy["stamp"] = "smoke-3"
        r = host_script("deploy_host.py", copy, local)
        check("a symlinked folder: the copy stops, exit 4", r.returncode == 4, f"{r.returncode}: {r.stderr.strip()[-300:]}")
    finally:
        r = host_script("smoke_host.py", request(action="cleanup"), local)
        check("the scratch folder removed", r.returncode == 0, r.stderr.strip()[-300:])
        if local:
            import shutil
            shutil.rmtree(parent, ignore_errors=True)
    print("\n" + ("smoke test: all passed" if not failed else f"smoke test: {len(failed)} failed: " + "; ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
