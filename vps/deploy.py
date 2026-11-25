#!/usr/bin/env python3
"""Deploy the named files from this repo to Telma's host, then re-check every line.

Run from the local machine, on main as pushed: python3 vps/deploy.py [--eval-run <results .jsonl>] <repo path>...
Paths are deploy.manifest's repo paths. Only `exact` and `redacted` lines are copied; for config,
jobs and skills it prints how they change instead. It shows each file's diff and takes a yes per
file, copying nothing until all are answered. The copy is one ssh call (remote/deploy_host.py): each
file staged to a temp name in its folder with its owner and mode, the old one kept in
~/.hermes/deploy-backups/<time>/, then, if no job of hers is running, every file swapped in at once.
Then check-drift.py runs (its hooks doctor posts one test-session alert), and the script prints what
each file still needs and the tag commands for the owner. It never restarts, rebuilds or runs a job,
and never writes a tag. Exit 0 after a copy the check finds in sync, 1 when it finds drift, 2 when
nothing was copied (a stop, every answer no, nothing to copy), 3 when the copy may have run part way
(an error or Ctrl-C during it), 4 when the copy ran but the check couldn't finish. After a copy the
tag commands are always printed. DRIFT_HOST_ROOT=<folder> deploys to a fake host folder
instead of the VPS (the tests).
"""
import argparse
import base64
import difflib
import importlib.util
import json
import os
import re
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
# AGENTS.md: a change to SOUL.md, a brain skill or the model or fallback order needs an eval run
# first. The skills and the config aren't copied here, but their lines are gated all the same.
EVAL_GATED = {"SOUL.md"}  # by file name; the tree line and the keys below are gated too
EVAL_KEYS = {"model", "fallback_providers"}
BACKUPS = "/home/agent/.hermes/deploy-backups"
LEDGER = "/home/agent/.hermes/cron/executions.db"
RESTART = "sudo systemctl --user -M agent@ restart hermes-gateway"
AFTER = {
    "new-chat": "takes effect in her next chat; a chat already open keeps the old one",
    "rebuild-sandbox": "rebuild the sandbox image (config's terminal.docker_image) as agent; containers "
                       "started after use it",
    "restart-gateway": f"restart her gateway: {RESTART}",
}


def root():
    r = os.environ.get("DRIFT_HOST_ROOT")
    if r == "":
        raise Stop("DRIFT_HOST_ROOT is set but empty: a fake host folder, or unset for the VPS")
    return r or ""


def remote(request):
    """remote/deploy_host.py as root on the host, or against DRIFT_HOST_ROOT, the request on stdin."""
    code = (HERE / "remote/deploy_host.py").read_text()
    cmd = [sys.executable, "-I", "-c", code] if root() else [*drift.SSH, drift.HOST, f"python3 -I -c {shlex.quote(code)}"]
    return subprocess.run(cmd, input=json.dumps({**request, "root": root()}), capture_output=True, text=True)


def pending_dir():
    """Where a deploy leaves its tag for tag-deploy.py: the common git dir, so worktrees share it."""
    common = Path(git("rev-parse", "--git-common-dir").stdout.decode().strip())
    return (REPO / common if not common.is_absolute() else common) / "deploy-pending"


TAG_NAME = re.compile(r"deploy/\d{4}-\d{2}-\d{2}-\d+")


def pending():
    """The tags deploys left and tag-deploy.py hasn't made yet, oldest first. A file that isn't one of
    ours (a name outside deploy/, a commit that isn't a hash, a broken JSON) stops the run, named."""
    found = []
    for f in pending_dir().glob("*.json"):
        try:
            p = json.loads(f.read_text())
            ok = (isinstance(p, dict) and TAG_NAME.fullmatch(str(p.get("tag"))) and re.fullmatch(r"[0-9a-f]{40}", str(p.get("commit")))
                  and isinstance(p.get("message"), list) and p["message"] and all(isinstance(m, str) for m in p["message"])
                  and isinstance(p.get("in_sync"), bool))
        except (OSError, ValueError):
            ok = False
        if not ok:
            raise Stop(f"{f} isn't a pending deploy tag (a tag deploy/<day>-<n>, a 40-digit commit, its message): "
                       "look at it, fix or remove it")
        found.append(p | {"file": f})
    return sorted(found, key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p["tag"])])


def write_pending(tag, commit, msg, in_sync):
    """The pending file, made exclusively: a deploy racing this one takes the next number. Returns the tag."""
    pending_dir().mkdir(exist_ok=True)
    day, n = tag.rsplit("-", 1)
    while True:
        try:
            with open(pending_dir() / (tag.replace("/", "_") + ".json"), "x") as f:
                f.write(json.dumps({"tag": tag, "commit": commit, "message": msg, "in_sync": in_sync}))
            return tag
        except FileExistsError:
            n = int(n) + 1
            tag = f"{day}-{n}"


def next_tag(day):
    """deploy/<day>-<n>, n one past the highest taken here, on origin or pending."""
    pattern = f"deploy/{day}-*"
    remote_tags = git("ls-remote", "--tags", "origin", f"refs/tags/{pattern}", check=False)
    if remote_tags.returncode:
        raise Stop("git ls-remote origin failed: the deploy tag's number needs origin's tags")
    taken = git("tag", "-l", pattern).stdout.decode().split()
    taken += [line.split("refs/tags/")[1].removesuffix("^{}") for line in remote_tags.stdout.decode().splitlines()]
    taken += [p["tag"] for p in pending()]
    numbers = [int(m.group(1)) for t in taken if (m := re.fullmatch(rf"deploy/{day}-(\d+)", t))]
    return f"deploy/{day}-{max(numbers, default=0) + 1}"


def preflight():
    """main as pushed, nothing uncommitted under vps/ (the check reads the checkout). Returns the commit."""
    if git("fetch", "-q", "origin", "main", check=False).returncode:
        raise Stop("git fetch origin main failed: the deploy needs main as pushed")
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    main = git("rev-parse", "refs/remotes/origin/main").stdout.decode().strip()
    if head != main:
        raise Stop(f"HEAD is {head[:7]}, origin/main is {main[:7]}: deploy main as pushed")
    dirty = git("status", "--porcelain", "--untracked-files=all", "--", "vps").stdout.decode().strip()
    if dirty:
        raise Stop(f"uncommitted changes under vps/, which the check reads:\n{dirty}")
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
    committed = git("show", f"HEAD:evals/results/{rel}", check=False)  # never the working tree's copy
    if p.suffix != ".jsonl" or committed.returncode:
        raise Stop(f"--eval-run {results}: not a committed results .jsonl")
    try:
        ran_on = json.loads(committed.stdout.decode().splitlines()[0])["setup"]["telma_commit"]
    except (IndexError, ValueError, KeyError, TypeError):
        raise Stop(f"--eval-run {results}: no setup stamp in its first line")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(ran_on)):
        raise Stop(f"--eval-run {results}: its telma_commit {ran_on!r} isn't a commit hash")
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


def config_commands(rows, gated):
    """`hermes config set` for each overridden key but the hooks (and the model and fallback keys
    when `gated`); lists as JSON."""
    def leaves(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from leaves(v, f"{prefix}{k}.")
            else:
                yield prefix + k, v
    return [f"hermes config set {k} {shlex.quote(json.dumps(v) if isinstance(v, (list, dict)) else str(v))}"
            for k, v in leaves({k: v for k, v in overrides(rows).items()
                                if k != "hooks" and not (gated and k in EVAL_KEYS)})]


def hook_command(rows, host_path):
    """The hook's command as config.yaml declares it, which `hermes hooks revoke` takes."""
    for entries in (overrides(rows).get("hooks") or {}).values():
        for e in entries or []:
            if host_path in str(e.get("command", "")).split():
                return e["command"]
    return host_path


def after_step(rows, row):
    if row["after"] == "reapprove-hook":
        return (f"{row['repo']}: Hermes runs it fresh on its next call. The doctor reads it as modified since "
                "approval until it is re-approved: as agent, back to back (a revoke turns the hook off in the "
                f"gateway), hermes hooks revoke {shlex.quote(hook_command(rows, row['host']))}, then "
                f"hermes chat --accept-hooks, then {RESTART}")
    return f"{row['repo']}: {AFTER[row['after']]}" if row["after"] in AFTER else None


def deploy(args):
    if drift.yaml is None:
        raise Stop("PyYAML is missing: pip install pyyaml")
    rows = {r["repo"]: r for r in drift.read_manifest()}
    unknown = [p for p in args.paths if p not in rows]
    if unknown:
        raise Stop(f"not in {drift.MANIFEST}: {', '.join(unknown)}")
    head = preflight()

    files = []
    for path in dict.fromkeys(args.paths):
        row = rows[path]
        if row["mode"] in COPIED:
            files.append(row)
            continue
        if row["mode"] == "subset":
            gated = not args.eval_run
            if args.eval_run:
                print(f"{path}: eval run on {check_eval_run(path, args.eval_run)}")
            print(f"{path}: config.yaml isn't written here. As agent, run the line of each key check-drift "
                  "names (the hooks are changed by hand):\n  " + "\n  ".join(config_commands(rows, gated)))
            if gated:
                print(f"  {', '.join(sorted(EVAL_KEYS))}: not printed without --eval-run (AGENTS.md)")
        elif row["mode"] == "jobs":
            print(f"{path}: jobs.json isn't written here. Change each job check-drift names with Hermes's "
                  f"cron tool until its fields match {path}.")
        else:
            print(f"{path}: eval run on {check_eval_run(path, args.eval_run)}")
            print(f"{path}: skills change through a PR on the brain repo; sync-brain brings them to the host.")
        if after_step(rows, row):
            print(f"  then: {after_step(rows, row)}")
    if not files:
        return 2
    for row in files:
        if Path(row["repo"]).name in EVAL_GATED:
            print(f"{row['repo']}: eval run on {check_eval_run(row['repo'], args.eval_run)}")
    now = datetime.now(timezone.utc)  # UTC for the tag's date and the backup's name alike
    tag = next_tag(f"{now:%Y-%m-%d}")

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

    wants = {row["repo"]: want(row) for row in files}
    missing = [p for p, w in wants.items() if w is None]
    if missing:
        raise Stop(f"not in the checkout: {', '.join(missing)}")
    r = remote({"action": "read", "files": [row["host"] for row in files]})
    if r.returncode:
        raise Stop(f"reading the host failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    try:
        host = json.loads(r.stdout)
    except ValueError:
        raise Stop("the host's reply isn't the reader's JSON (a login script printing to stdout?)")

    chosen = []
    for row in files:
        have, new = host[row["host"]], wants[row["repo"]]
        if have and "link" in have:
            print(f"\n{row['repo']}: {have['link']} on the host is a symlink: not deployed, look at it by hand")
            continue
        if have and "unsafe" in have:
            print(f"\n{row['repo']}: {have['unsafe']}: not deployed, look at it by hand")
            continue
        status = "missing" if have is None else drift.direction(
            lambda w: sha(w) == have["sha"], new, want(row, True), repo.tagged)
        if status == "in sync" and have["stat"] == f"{row['owner']} {row['perm']}":
            print(f"\n{row['repo']}: already in sync")
            continue
        show_diff(row, new, have, status)
        if ask(row["repo"]):
            chosen.append((row, new, have))
    if not chosen:
        print("nothing deployed")
        return 2

    stamp = f"{now:%Y%m%dT%H%M%SZ}"
    backup = f"{BACKUPS}/{stamp}"
    files_req = []
    for row, new, have in chosen:
        user, group = row["owner"].split(":")
        files_req.append({"host": row["host"], "data": base64.b64encode(new).decode(), "user": user,
                          "group": group, "perm": row["perm"], "was": have and have["sha"]})
    deployed = [row for row, _, _ in chosen]
    try:
        r = remote({"action": "copy", "backups": BACKUPS, "stamp": stamp, "files": files_req, "ledger": LEDGER,
                    "running_code": (HERE / "remote/running_jobs.py").read_text(),
                    "as_agent": ["bash", "-c"] if root() else ["su", "-", "agent", "-c"]})
    except KeyboardInterrupt:
        r = None
    if r is not None and r.returncode in (4, 5):
        raise Stop(f"nothing copied: {r.stderr.strip()[-500:]}")
    if r is None or r.returncode:
        why = "Ctrl-C" if r is None else f"{r.returncode}: {r.stderr.strip()[-500:]}"
        print(f"deploy: the copy may have run part way ({why}); over ssh it may still be running.\n"
              f"run check-drift.py; the old files are in {backup}/ on the host", file=sys.stderr)
        finish(rows, deployed, head, tag, backup, "summary: the copy may have run part way", None)
        return 3
    print(f"\ncopied {len(deployed)} file(s); the old ones are in {backup}/ on the host\n")
    try:
        check = subprocess.run([sys.executable, str(HERE / "check-drift.py")], capture_output=True, text=True)
        print(check.stdout + check.stderr, end="")
        code = check.returncode
        summary = next((line for line in check.stdout.splitlines() if line.startswith("summary:")),
                       f"summary: check-drift exited {code}")
    except KeyboardInterrupt:
        code, summary = None, "summary: the re-check was stopped (Ctrl-C)"
        print("\ndeploy: the re-check was stopped; run check-drift.py", file=sys.stderr)
    finish(rows, deployed, head, tag, backup, summary, code)
    return {0: 0, 1: 1}.get(code, 4)


def finish(rows, deployed, head, tag, backup, summary, code):
    """What each file still needs, and the tag left pending for tag-deploy.py. Runs after every copy,
    so it never raises: if the pending file can't be written, it prints the tag commands instead."""
    steps = []
    for row in deployed:
        try:
            step = after_step(rows, row)
        except Exception as e:
            step = f"{row['repo']}: {row['after']} (couldn't print its steps: {e})"
        if step:
            steps.append(step)
    if steps:
        print("\nstill to do:\n  " + "\n  ".join(steps))
    msg = [f"deploy {head[:7]}", "files: " + ", ".join(r["repo"] for r in deployed),
           f"backup: {backup}/", f"after the copy: {summary}"]
    try:
        tag = write_pending(tag, head, msg, code == 0)
    except Exception as e:
        print(f"\ndeploy: couldn't leave the tag pending ({e}); its commands:")
        print(f"  git tag -a {tag} {head[:7]} " + " ".join(f"-m {shlex.quote(m)}" for m in msg))
        print(f"  git push origin {tag}")
        return
    print(f"\ntag: {tag} on {head[:7]}, pending (this script never writes a tag)\n  " + "\n  ".join(msg[1:]))
    if code == 0:
        print(f"{drift.TAG}: moves to {head[:7]} with it")
    else:
        print(f"{drift.TAG}: stays; once check-drift.py exits 0"
              + (" (after the steps above)" if steps else "") + ": python3 vps/tag-deploy.py --deployed")
    print("create and push it: python3 vps/tag-deploy.py")


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
