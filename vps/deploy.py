#!/usr/bin/env python3
"""Deploy the named files from this repo to Telma's host, then re-check every line.

Run from the local machine, on main as pushed: python3 vps/deploy.py [--eval-run <results .jsonl>] <repo path>...
(or --deployed alone, below).
Paths are deploy.manifest's repo paths. Only `exact` and `redacted` lines are copied; for config,
jobs and skills it prints how they change instead. It shows each file's diff and takes a yes per
file, copying nothing until all are answered. The copy is one ssh call (remote/deploy_host.py): each
file staged to a temp name in its folder with its owner and mode, the old one kept in
~/.hermes/deploy-backups/<time>/, then, if no job of hers is running, every file swapped in at once.
Then check-drift.py runs (its hooks doctor posts one test-session alert) and the script prints what
each file still needs. Last it offers the deploy's tag, deploy/<day>-<n> (annotated: the files, the
backup folder, the check's summary line), and, when the check was in sync, `deployed`, each after
the owner's yes and only the owner's: no, q or end of input print the commands to run by hand. It
never restarts, rebuilds or runs a job. `python3 vps/deploy.py --deployed` re-checks now and offers
`deployed` alone (a hook awaiting re-approval leaves the first check not in sync; exit 1 when it
stays, 2 when the check couldn't run). `deployed` only moves forward. It runs only at a terminal.
Exit 0 after a copy the check finds in sync, 1 when it finds drift, 2 when nothing was copied (a stop,
every answer no, nothing to copy), 3 when the copy may have run part way (an error or Ctrl-C during it;
no tag is offered then), 4 when the copy ran but the check couldn't finish. DRIFT_HOST_ROOT=<folder>
deploys to a fake host folder instead of the VPS (the tests, which answer through a pseudo-terminal).
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

sys.dont_write_bytecode = True  # importing check-drift.py must not leave a __pycache__ for the clean-tree check
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


def next_tag(day):
    """deploy/<day>-<n>, n one past the highest taken here or on origin."""
    pattern = f"deploy/{day}-*"
    remote_tags = git("ls-remote", "--tags", "origin", f"refs/tags/{pattern}", check=False)
    if remote_tags.returncode:
        raise Stop("git ls-remote origin failed: the deploy tag's number needs origin's tags")
    taken = git("tag", "-l", pattern).stdout.decode().split()
    taken += [line.split("refs/tags/")[1].removesuffix("^{}") for line in remote_tags.stdout.decode().splitlines()]
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


def check_eval_run(path, results, soul=None):
    """A committed run, made on a commit that has the file's last change. Returns that commit. For
    SOUL.md, `soul` is the filled file about to be written: the run must have tested the repo's SOUL.md
    (`run.py --repo-soul`) and its copy on the eval profile must hash the same as this."""
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
        lines = [json.loads(l) for l in committed.stdout.decode().splitlines() if l.strip()]
        stamp = lines[0]["setup"]
        ran_on = stamp["telma_commit"]
    except (IndexError, ValueError, KeyError, TypeError):
        raise Stop(f"--eval-run {results}: no setup stamp in its first line")
    if soul is not None and any(l.get("setup") != stamp for l in lines if isinstance(l, dict)):
        raise Stop(f"--eval-run {results} holds rows of more than one setup (two runs in one file)")
    if not re.fullmatch(r"[0-9a-f]{7,40}", str(ran_on)):
        raise Stop(f"--eval-run {results}: its telma_commit {ran_on!r} isn't a commit hash")
    changed = git("log", "-1", "--format=%H", "--", path).stdout.decode().strip()
    if git("merge-base", "--is-ancestor", changed, ran_on, check=False).returncode:
        raise Stop(f"--eval-run {results} ran on {ran_on}, without {path}'s last change {changed[:7]}")
    if soul is not None:
        tested = stamp.get("eval_soul_sha")
        if stamp.get("soul_source") != "repo" or not tested or tested != stamp.get("repo_soul_sha"):
            raise Stop(f"--eval-run {results} didn't test the repo's {path}: rerun with run.py --repo-soul")
        if tested != sha(soul)[:12]:
            raise Stop(f"--eval-run {results} tested {path} {tested}, not the file to deploy {sha(soul)[:12]}: rerun with run.py --repo-soul")
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
    now = datetime.now(timezone.utc)  # UTC for the tag's date and the backup's name alike
    next_tag(f"{now:%Y-%m-%d}")  # stops before the copy if origin's tags can't be read; the tag is numbered again at the end

    values = drift.private_values() if any(r["mode"] == "redacted" for r in files) else {}
    repo = drift.Repo()

    def want(row, at_tag=False):
        data = repo.read(row["repo"], at_tag)
        if data is None or row["mode"] != "redacted":
            return data
        return drift.filled(data, row["repo"], values)

    wants = {row["repo"]: want(row) for row in files}
    missing = [p for p, w in wants.items() if w is None]
    if missing:
        raise Stop(f"not in the checkout: {', '.join(missing)}")
    for row in files:
        if Path(row["repo"]).name in EVAL_GATED:
            print(f"{row['repo']}: eval run on {check_eval_run(row['repo'], args.eval_run, wants[row['repo']])}")
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

    stamp = f"{now:%Y%m%dT%H%M%S}{now.microsecond // 1000:03d}Z"  # to the millisecond: two deploys can share a second
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
        print("no tag is offered for a copy that may not have run: when check-drift.py shows what landed, tag by hand",
              file=sys.stderr)
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
    finish(rows, deployed, head, backup, summary, code)
    return {0: 0, 1: 1}.get(code, 4)


def confirm(question):
    """A yes, or nothing: no, q, Ctrl-D and anything else all decline."""
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def origin_ref(ref):
    """(the object origin's `ref` is, the commit it points at), or (None, None). They differ for an
    annotated tag, whose commit is the peeled one."""
    r = git("ls-remote", "origin", ref, f"{ref}^{{}}", check=False)
    if r.returncode:
        raise Stop(f"git ls-remote origin {ref} failed")
    shas = {line.split("\t")[1]: line.split("\t")[0] for line in r.stdout.decode().splitlines()}
    return shas.get(ref), shas.get(f"{ref}^{{}}") or shas.get(ref)


def move_deployed(commit):
    """`deployed` to commit and pushed, never backwards: only onto a descendant of where origin has it,
    and the push leases that place, so a move made meanwhile isn't overwritten. This clone's tag is
    brought to origin's first, since the check reads it."""
    ref = f"refs/tags/{drift.TAG}"
    raw, now = origin_ref(ref)
    if now:
        git("fetch", "-q", "origin", f"+{ref}:{ref}", check=False)
    if now == commit:
        print(f"{drift.TAG} is on {commit[:7]} already")
        return
    if now and git("merge-base", "--is-ancestor", now, commit, check=False).returncode:
        print(f"{drift.TAG} stays on {now[:7]}: {commit[:7]} isn't after it")
        return
    git("tag", "-f", drift.TAG, commit)
    force = f"--force-with-lease={ref}:{raw}" if raw else "--no-force-with-lease"
    if git("push", "-q", force, "origin", ref, check=False).returncode:
        raise Stop(f"{drift.TAG} is on {commit[:7]} here, not pushed (origin's moved, or refused): "
                   f"git push -f origin {drift.TAG}")
    print(f"{drift.TAG} on {commit[:7]}, pushed")


def tag_commands(tag, head, msg):
    return [f"git tag -a {tag} {head[:7]} " + " ".join(f"-m {shlex.quote(m)}" for m in msg),
            f"git push origin {tag}"]


def finish(rows, deployed, head, backup, summary, code):
    """What each file still needs, then the deploy's tag and `deployed`, each after the owner's yes.
    Runs after every copy, so it never raises: what it can't or isn't allowed to do is printed as the
    commands to run by hand, each step on its own, so one failing doesn't hide the other."""
    msg = [f"deploy {head[:7]}", "files: " + ", ".join(r["repo"] for r in deployed),
           f"backup: {backup}/", f"after the copy: {summary}"]
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
    try:
        tag = next_tag(f"{datetime.now(timezone.utc):%Y-%m-%d}")  # counted again here: the window since the start is long
    except Exception as e:
        tag = None
        print(f"\ndeploy: no tag number ({e}); tag by hand")
    if tag:
        print(f"\ntag: {tag} on {head[:7]}\n  " + "\n  ".join(msg[1:]))
    print(f"{drift.TAG}: " + (f"moves to {head[:7]}" if code == 0 else "stays: once check-drift.py exits 0"
          + (" (after the steps above)" if steps else "") + ", run python3 vps/deploy.py --deployed"))

    def step(question, do, by_hand):
        try:
            if confirm(question):
                do()
                return
            print("by hand:\n  " + "\n  ".join(by_hand))
        except (Exception, KeyboardInterrupt) as e:
            print(f"\ndeploy: {e or type(e).__name__}\nby hand:\n  " + "\n  ".join(by_hand), file=sys.stderr)

    def make_tag():
        git("tag", "-a", tag, head, *[a for m in msg for a in ("-m", m)])
        if git("push", "-q", "origin", f"refs/tags/{tag}", check=False).returncode:
            git("tag", "-d", tag, check=False)  # so the commands below can run as printed
            raise Stop(f"{tag} was not pushed (taken on origin meanwhile, or refused)")
        print(f"{tag} pushed")

    if tag:
        step(f"create and push {tag}?", make_tag, tag_commands(tag, head, msg))
    if code == 0:
        step(f"move {drift.TAG} to {head[:7]}?", lambda: move_deployed(head),
             [f"git tag -f {drift.TAG} {head[:7]} && git push -f origin {drift.TAG}"])


def deployed_now():
    """--deployed: re-check now, and with a yes move `deployed` to HEAD (main as pushed) if it is in sync."""
    head = preflight()
    check = subprocess.run([sys.executable, str(HERE / "check-drift.py")], capture_output=True, text=True)
    print(check.stdout + check.stderr, end="")
    if check.returncode:
        print(f"{drift.TAG} stays: check-drift.py exited {check.returncode}")
        return 2 if check.returncode == 2 else 1
    if confirm(f"move {drift.TAG} to {head[:7]}?"):
        move_deployed(head)
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(description="Deploy named files to Telma's host.", allow_abbrev=False)
    parser.add_argument("--eval-run", help="evals/results/<run>.jsonl, needed to deploy SOUL.md")
    parser.add_argument("--deployed", action="store_true", help="no deploy: re-check and move `deployed` to HEAD")
    parser.add_argument("paths", nargs="*", help="repo paths as deploy.manifest names them")
    args = parser.parse_args()
    if bool(args.paths) == args.deployed or (args.deployed and args.eval_run):
        parser.error("name the files to deploy, or --deployed alone")
    if not sys.stdin.isatty():
        print("deploy: needs a terminal: a deploy, its tag and `deployed` are moved only by the owner's own yes "
              "at the keyboard", file=sys.stderr)
        return 2
    try:
        return deployed_now() if args.deployed else deploy(args)
    except Stop as e:
        print(f"deploy: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"deploy: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
