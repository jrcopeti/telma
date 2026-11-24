#!/usr/bin/env python3
"""Deploy the named files from this repo to Telma's host, then re-check every line.

Run from the local machine, on main as pushed: python3 vps/deploy.py [--eval-run <results .jsonl>] <repo path>...
Paths are deploy.manifest's repo paths. Only `exact` and `redacted` lines are copied; for config,
jobs and skills it prints how they change instead. It shows each file's diff and takes a yes per
file, copying nothing until all are answered. The copy is one ssh call: each file staged to a temp
name in its folder with its owner and mode, the old one kept in ~/.hermes/deploy-backups/<time>/,
then, if no job of hers is running, every file swapped in at once. Then check-drift.py runs (its
hooks doctor posts one test-session alert), and the script prints what each file still needs and the
tag commands for the owner. It never restarts, rebuilds or runs a job, and never writes a tag.
Exit 0 after a deploy the check finds in sync, 1 when it finds drift, 2 when nothing was copied, 3
when the copy may have run part way. DRIFT_HOST_ROOT=<folder> deploys to a fake host folder instead
of the VPS (the tests).
"""
import argparse
import base64
import difflib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("check_drift", HERE / "check-drift.py")
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)
REPO, Stop, git, sha = drift.REPO, drift.Stop, drift.git, drift.sha

COPIED = {"exact", "redacted"}
# AGENTS.md: a change to these needs an eval run first. The skills and the model keys are never
# copied here (a brain PR, `hermes config set`), so SOUL.md is the one this script can deploy.
EVAL_GATED = {"SOUL.md"}  # by file name
BACKUPS = "/home/agent/.hermes/deploy-backups"
EXECUTIONS = "/home/agent/.hermes/cron/executions.db"
RESTART = "sudo systemctl --user -M agent@ restart hermes-gateway"
AFTER = {
    "new-chat": "takes effect in her next chat; a chat already open keeps the old one",
    "rebuild-sandbox": "rebuild the sandbox image (config's terminal.docker_image) as agent; containers "
                       "started after use it",
    "restart-gateway": f"restart her gateway: {RESTART}",
}

# Both run on the host as root (or against DRIFT_HOST_ROOT), the request on stdin.
SHARED = r'''
import base64, grp, hashlib, json, os, pwd, shutil, subprocess, sys
req = json.loads(sys.stdin.read())
R = req["root"]
def link_on_path(p):
    """The first symlink on p, its folders included, or None: never followed."""
    parts = p.split("/")
    for i in range(2, len(parts) + 1):
        if os.path.islink(R + "/".join(parts[:i])):
            return "/".join(parts[:i])
def read(p):
    with open(R + p, "rb") as f:
        return f.read()
'''

# Each file's stat, hash and bytes, for the diff.
READ = SHARED + r'''
out = {}
for p in req["files"]:
    if link_on_path(p):
        out[p] = {"link": link_on_path(p)}
    elif os.path.isfile(R + p):
        s, data = os.lstat(R + p), read(p)
        out[p] = {"stat": "%s:%s %o" % (pwd.getpwuid(s.st_uid).pw_name, grp.getgrgid(s.st_gid).gr_name, s.st_mode & 0o7777),
                  "sha": hashlib.sha256(data).hexdigest(), "data": base64.b64encode(data).decode()}
    else:
        out[p] = None
print(json.dumps(out))
'''

# Stages every file and its backup, then swaps them all in only if no job of hers is running. Any
# failure before the swap removes what it made (exit 4, or 5 for a running job): nothing deployed.
COPY = SHARED + r'''
staged, made = [], []
def stop(code, msg):
    for tmp in staged:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    for d in reversed(made):
        shutil.rmtree(d, ignore_errors=True)
    print(msg, file=sys.stderr)
    sys.exit(code)
def mkdirs(path, uid, gid):
    """Each missing folder down to path, owned like the file it backs up."""
    parts = path.split("/")
    for i in range(2, len(parts) + 1):
        d = R + "/".join(parts[:i])
        if not os.path.lexists(d):
            os.mkdir(d, 0o700)
            os.chown(d, uid, gid)
            made.append(d)
        elif os.path.islink(d) or not os.path.isdir(d):
            stop(4, "%s isn't a plain folder" % "/".join(parts[:i]))
try:
    backup = req["backup"]
    if os.path.lexists(R + backup):
        stop(4, "backup folder %s already exists" % backup)
    for f in req["files"]:
        p = f["host"]
        if link_on_path(p):
            stop(4, "%s: a symlink appeared on its path" % p)
        now = hashlib.sha256(read(p)).hexdigest() if os.path.isfile(R + p) else None
        if now != f["was"]:
            stop(4, "%s changed on the host since its diff was shown" % p)
        folder = os.path.dirname(R + p)
        if not os.path.isdir(folder):
            stop(4, "%s: its folder doesn't exist" % p)
        uid, gid = pwd.getpwnam(f["user"]).pw_uid, grp.getgrnam(f["group"]).gr_gid
        if f["was"] is not None:
            s = os.lstat(R + p)
            mkdirs(backup + os.path.dirname(p), s.st_uid, s.st_gid)
            shutil.copy2(R + p, R + backup + p, follow_symlinks=False)
            os.chown(R + backup + p, s.st_uid, s.st_gid)
        tmp = os.path.join(folder, ".%s.deploy-tmp" % os.path.basename(p))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        staged.append(tmp)
        with os.fdopen(fd, "wb") as out:
            out.write(base64.b64decode(f["data"]))
            out.flush()
            os.fchown(out.fileno(), uid, gid)
            os.fchmod(out.fileno(), int(f["perm"], 8))
            os.fsync(out.fileno())
    r = subprocess.run(req["as_agent"] + [req["running"]], capture_output=True, text=True)
    if r.returncode:
        stop(4, "couldn't read her running jobs: " + r.stderr.strip()[-300:])
    if r.stdout.strip():
        stop(5, "a job of hers is running (job id %s): nothing copied, try again when it ends" % r.stdout.strip())
except SystemExit:
    raise
except Exception as e:
    stop(4, "%s: %s" % (type(e).__name__, e))
done = []
try:
    for f, tmp in zip(req["files"], staged):
        os.replace(tmp, R + f["host"])
        done.append(f["host"])
except Exception as e:
    print("swapped %s, then %s: %s" % (", ".join(done) or "nothing", type(e).__name__, e), file=sys.stderr)
    sys.exit(6)
print(json.dumps(done))
'''

# As agent: the cron ledger's attempts still claimed or running (Hermes cron/executions.py).
RUNNING = ("import sqlite3, sys\n"
           "c = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)\n"
           "print(' '.join(r[0] for r in c.execute(\"SELECT job_id FROM executions WHERE status IN ('claimed','running')\")))")


def root():
    r = os.environ.get("DRIFT_HOST_ROOT")
    if r == "":
        raise Stop("DRIFT_HOST_ROOT is set but empty: a fake host folder, or unset for the VPS")
    return r or ""


def remote(code, request):
    """Run `code` as root on the host, or against DRIFT_HOST_ROOT, with the request on stdin."""
    cmd = [sys.executable, "-I", "-c", code] if root() else [*drift.SSH, drift.HOST, f"python3 -I -c {shlex.quote(code)}"]
    return subprocess.run(cmd, input=json.dumps({**request, "root": root()}), capture_output=True, text=True)


def preflight(paths):
    """main as pushed, nothing uncommitted in what is deployed. Returns the commit."""
    if git("fetch", "-q", "origin", "main", check=False).returncode:
        raise Stop("git fetch origin main failed: the deploy needs main as pushed")
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    main = git("rev-parse", "refs/remotes/origin/main").stdout.decode().strip()
    if head != main:
        raise Stop(f"HEAD is {head[:7]}, origin/main is {main[:7]}: deploy main as pushed")
    dirty = git("status", "--porcelain", "--", drift.MANIFEST, *paths).stdout.decode().strip()
    if dirty:
        raise Stop(f"uncommitted changes in what would be deployed:\n{dirty}")
    return head


def check_eval_run(path, results):
    """A committed run, made on a commit that has the file's last change. Returns that commit."""
    if not results:
        raise Stop(f"{path} needs --eval-run evals/results/<run>.jsonl (AGENTS.md: the eval before the change)")
    p = Path(results).resolve()
    try:
        rel = p.relative_to(REPO / "evals/results")
    except ValueError:
        raise Stop(f"--eval-run {results}: not in evals/results/")
    if p.suffix != ".jsonl" or git("ls-files", "--error-unmatch", f"evals/results/{rel}", check=False).returncode:
        raise Stop(f"--eval-run {results}: not a committed results .jsonl")
    try:
        ran_on = json.loads(p.read_text().splitlines()[0])["setup"]["telma_commit"]
    except (IndexError, ValueError, KeyError, TypeError):
        raise Stop(f"--eval-run {results}: no setup stamp in its first line")
    changed = git("log", "-1", "--format=%H", "--", path).stdout.decode().strip()
    if git("merge-base", "--is-ancestor", changed, ran_on, check=False).returncode:
        raise Stop(f"--eval-run {results} ran on {ran_on}, without {path}'s last change {changed[:7]}")
    return ran_on


def show_diff(row, now, have, status):
    print(f"\n=== {row['repo']} -> {row['host']}  ({status})")
    if status in ("host ahead", "both changed"):
        print("    the host has a change this repo doesn't: deploying overwrites it (the backup keeps it)")
    elif status == "differs":
        print("    no direction without the deployed tag: read the diff to see which side changed")
    want = f"{row['owner']} {row['perm']}"
    if have and have["stat"] != want:
        print(f"    owner and mode: {have['stat']} -> {want}")
    old = base64.b64decode(have["data"]) if have else b""
    if old != now:
        sys.stdout.writelines(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                              for line in difflib.unified_diff(
                                  old.decode(errors="replace").splitlines(True),
                                  now.decode(errors="replace").splitlines(True),
                                  f"host {row['host']}", f"repo {row['repo']}"))


def ask(path):
    while True:
        try:
            answer = input(f"deploy {path}? [y/N/q] ").strip().lower()
        except EOFError:
            answer = "q"
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        if answer in ("q", "quit"):
            raise Stop("stopped at q: nothing copied")


def overrides(rows):
    """The config overrides, from the manifest's subset line."""
    path = next((r["repo"] for r in rows.values() if r["mode"] == "subset"), None)
    return drift.load_yaml((REPO / path).read_bytes(), path) if path else {}


def config_commands(rows):
    """`hermes config set` for each overridden key but the hooks; lists as JSON."""
    def leaves(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from leaves(v, f"{prefix}{k}.")
            else:
                yield prefix + k, v
    return [f"hermes config set {k} {shlex.quote(json.dumps(v) if isinstance(v, (list, dict)) else str(v))}"
            for k, v in leaves({k: v for k, v in overrides(rows).items() if k != "hooks"})]


def hook_command(rows, host_path):
    """The hook's command as config.yaml declares it, which `hermes hooks revoke` takes."""
    for entries in (overrides(rows).get("hooks") or {}).values():
        for e in entries or []:
            if host_path in str(e.get("command", "")).split():
                return e["command"]
    return host_path


def next_tag(day):
    """deploy/<day>-<n>, n one past the highest taken here or on origin."""
    pattern = f"deploy/{day}-*"
    taken = set(git("tag", "-l", pattern).stdout.decode().split())
    remote_tags = git("ls-remote", "--tags", "origin", f"refs/tags/{pattern}", check=False)
    taken |= {line.split("refs/tags/")[1].removesuffix("^{}") for line in remote_tags.stdout.decode().splitlines()}
    n = 1
    while f"deploy/{day}-{n}" in taken:
        n += 1
    return f"deploy/{day}-{n}"


def deploy(args):
    if drift.yaml is None:
        raise Stop("PyYAML is missing: pip install pyyaml")
    rows = {r["repo"]: r for r in drift.read_manifest()}
    unknown = [p for p in args.paths if p not in rows]
    if unknown:
        raise Stop(f"not in {drift.MANIFEST}: {', '.join(unknown)}")
    head = preflight(args.paths)

    files = []
    for path in dict.fromkeys(args.paths):
        row = rows[path]
        if row["mode"] in COPIED:
            files.append(row)
        elif row["mode"] == "subset":
            print(f"{path}: config.yaml isn't written here. As agent, run the line of each key check-drift "
                  "names (the hooks are changed by hand):\n  " + "\n  ".join(config_commands(rows)))
        elif row["mode"] == "jobs":
            print(f"{path}: jobs.json isn't written here. Change each job check-drift names with Hermes's "
                  f"cron tool until its fields match {path}.")
        else:
            print(f"{path}: skills change through a PR on the brain repo; sync-brain brings them to the host.")
    if not files:
        return 0
    for row in files:
        if Path(row["repo"]).name in EVAL_GATED:
            print(f"{row['repo']}: eval run on {check_eval_run(row['repo'], args.eval_run)}")

    values = drift.private_values() if any(r["mode"] == "redacted" for r in files) else {}
    repo = drift.Repo()

    def want(row, at_tag=False):
        data = repo.read(row["repo"], at_tag)
        if data is None or row["mode"] != "redacted":
            return data
        text = data.decode()
        for key in drift.PLACEHOLDER.findall(text):
            if key not in values:
                raise Stop(f"{row['repo']} needs {key} in info/private-values")
        return drift.PLACEHOLDER.sub(lambda m: values[m.group(1)], text).encode()

    r = remote(READ, {"files": [row["host"] for row in files]})
    if r.returncode:
        raise Stop(f"reading the host failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    try:
        host = json.loads(r.stdout)
    except ValueError:
        raise Stop("the host's reply isn't the reader's JSON (a login script printing to stdout?)")

    chosen = []
    for row in files:
        have, now = host[row["host"]], want(row)
        if now is None:
            raise Stop(f"{row['repo']} isn't in the checkout")
        if have and "link" in have:
            print(f"\n{row['repo']}: {have['link']} on the host is a symlink: not deployed, look at it by hand")
            continue
        status = "missing" if have is None else drift.direction(
            lambda w: sha(w) == have["sha"], now, want(row, True), repo.tagged)
        if status == "in sync" and have["stat"] == f"{row['owner']} {row['perm']}":
            print(f"\n{row['repo']}: already in sync")
            continue
        show_diff(row, now, have, status)
        if ask(row["repo"]):
            chosen.append((row, now, have))
    if not chosen:
        print("nothing deployed")
        return 0

    backup = f"{BACKUPS}/{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    running = f"python3 -I -c {shlex.quote(RUNNING)} {shlex.quote(root() + EXECUTIONS)}"
    files_req = []
    for row, now, have in chosen:
        user, group = row["owner"].split(":")
        files_req.append({"host": row["host"], "data": base64.b64encode(now).decode(), "user": user,
                          "group": group, "perm": row["perm"], "was": have and have["sha"]})
    r = remote(COPY, {"backup": backup, "files": files_req, "running": running,
                      "as_agent": ["bash", "-c"] if root() else ["su", "-", "agent", "-c"]})
    if r.returncode in (4, 5):
        raise Stop(f"nothing copied: {r.stderr.strip()[-500:]}")
    if r.returncode:
        print(f"deploy: the copy may have run part way ({r.returncode}): {r.stderr.strip()[-500:]}\n"
              f"run check-drift.py; the old files are in {backup}/ on the host", file=sys.stderr)
        return 3
    deployed = [row for row, _, _ in chosen]
    print(f"\ncopied {len(deployed)} file(s); the old ones are in {backup}/ on the host\n")

    check = subprocess.run([sys.executable, str(HERE / "check-drift.py")], capture_output=True, text=True)
    print(check.stdout + check.stderr, end="")
    summary = next((line for line in check.stdout.splitlines() if line.startswith("summary:")),
                   f"summary: check-drift exited {check.returncode}")

    steps = []
    for row in deployed:
        if row["after"] == "reapprove-hook":
            steps.append(f"{row['repo']}: Hermes runs it fresh on its next call. The doctor reads it as modified "
                         "since approval until it is re-approved: as agent, back to back (a revoke turns the hook "
                         f"off in the gateway), hermes hooks revoke {shlex.quote(hook_command(rows, row['host']))}, then "
                         f"hermes chat --accept-hooks, then {RESTART}")
        elif row["after"] in AFTER:
            steps.append(f"{row['repo']}: {AFTER[row['after']]}")
    if steps:
        print("\nstill to do:\n  " + "\n  ".join(steps))

    tag = next_tag(datetime.now().strftime("%Y-%m-%d"))
    msg = [f"deploy {head[:7]}", "files: " + ", ".join(r["repo"] for r in deployed),
           f"backup: {backup}/", f"after the copy: {summary}"]
    print("\ntag commands (the owner runs them; this script never writes a tag):")
    print(f"  git tag -a {tag} {head[:7]} " + " ".join(f"-m {shlex.quote(m)}" for m in msg))
    print(f"  git push origin {tag}")
    if check.returncode == 0:
        print(f"  git tag -f {drift.TAG} {head[:7]} && git push -f origin {drift.TAG}")
    else:
        print(f"  {drift.TAG} stays: move it to {head[:7]} when check-drift.py exits 0"
              + (" (after the steps above)" if steps else ""))
    return 0 if check.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Deploy named files to Telma's host.")
    parser.add_argument("--eval-run", help="evals/results/<run>.jsonl, needed to deploy SOUL.md")
    parser.add_argument("paths", nargs="+", help="repo paths as deploy.manifest names them")
    args = parser.parse_args()
    try:
        return deploy(args)
    except Stop as e:
        print(f"deploy: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"deploy: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
