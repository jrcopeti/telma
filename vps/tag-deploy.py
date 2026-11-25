#!/usr/bin/env python3
"""Create and push the deploy tags deploy.py left pending, and move `deployed`. The owner runs it.

python3 vps/tag-deploy.py             each pending deploy/<day>-<n> tag, oldest first, after a yes for
                                      each; `deployed` moves with the newest when its re-check was in
                                      sync, no older one is skipped and `deployed` doesn't go back
python3 vps/tag-deploy.py --deployed  runs check-drift.py now and, if it exits 0, moves `deployed` to
                                      HEAD (main as pushed, nothing uncommitted under vps/)

Pending tags live in the common git dir (deploy-pending/), never in the repo. A tag made here but not
pushed (Ctrl-C, a refused push) is pushed on the next run; one already on origin at the same commit
is cleared. A pending deploy whose commit isn't on origin/main, or whose tag exists at another
commit, stays pending, named. Exit 0 when everything is tagged and `deployed` is where it should be,
1 when something stays (a no, a skip, `deployed` not moved), 2 when it couldn't run.
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("deploy", HERE / "deploy.py")
deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deploy)
drift, git, Stop = deploy.drift, deploy.git, deploy.Stop


class Quit(Exception):
    """The owner answered q, or stdin ended."""


def ask(question):
    try:
        answer = input(f"{question} [y/N/q] ").strip().lower()
    except EOFError:
        raise Quit
    if answer in ("q", "quit"):
        raise Quit
    return answer in ("y", "yes")


def origin_commit(ref):
    """The commit origin's `ref` points at (an annotated tag's peeled one), or None."""
    r = git("ls-remote", "origin", ref, f"{ref}^{{}}", check=False)
    if r.returncode:
        raise Stop(f"git ls-remote origin {ref} failed")
    shas = {line.split("\t")[1]: line.split("\t")[0] for line in r.stdout.decode().splitlines()}
    return shas.get(f"{ref}^{{}}") or shas.get(ref)


def local_commit(ref):
    r = git("rev-parse", "-q", "--verify", f"{ref}^{{commit}}", check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def on_main(commit):
    return git("merge-base", "--is-ancestor", commit, "refs/remotes/origin/main", check=False).returncode == 0


def move_deployed(commit):
    """`deployed` to commit, never backwards: only onto a descendant of where origin has it."""
    now = origin_commit(f"refs/tags/{drift.TAG}")
    if now == commit:
        print(f"{drift.TAG} is on {commit[:7]} already")
        return True
    if now:
        if git("cat-file", "-e", f"{now}^{{commit}}", check=False).returncode:
            git("fetch", "-q", "origin", f"refs/tags/{drift.TAG}:refs/tags/{drift.TAG}", "--force", check=False)
        if git("merge-base", "--is-ancestor", now, commit, check=False).returncode:
            print(f"{drift.TAG} stays on {now[:7]}: {commit[:7]} isn't after it")
            return False
    git("tag", "-f", drift.TAG, commit)
    if git("push", "-q", "-f", "origin", f"refs/tags/{drift.TAG}", check=False).returncode:
        raise Stop(f"{drift.TAG} moved here to {commit[:7]}, but pushing it failed: git push -f origin {drift.TAG}")
    print(f"{drift.TAG} on {commit[:7]}, pushed")
    return True


def tag_one(p):
    """Make and push p's tag, or finish what an interrupted run left. True when it is on origin now."""
    name, commit = p["tag"], p["commit"]
    ref = f"refs/tags/{name}"
    print(f"\n{name} on {commit[:7]}\n  " + "\n  ".join(p["message"][1:]))
    if not on_main(commit):
        print(f"  {commit[:7]} isn't on origin/main: left pending, look at it by hand")
        return False
    there, here = origin_commit(ref), local_commit(ref)
    if there:
        if there != commit:
            print(f"  {name} is on origin at {there[:7]}, not {commit[:7]}: left pending, look at it by hand")
            return False
        print(f"  {name} is on origin already")
    elif here and here != commit:
        print(f"  {name} exists here at {here[:7]}, not {commit[:7]}: left pending, look at it by hand")
        return False
    else:
        if not ask(f"{'push' if here else 'create and push'} {name}?"):
            return False
        if not here:
            git("tag", "-a", name, commit, *[a for m in p["message"] for a in ("-m", m)])
        if git("push", "-q", "origin", ref, check=False).returncode:
            raise Stop(f"{name} is made here, not on origin: push it by running this again, or git push origin {name}")
        print(f"{name} pushed")
    p["file"].unlink()
    return True


def tag_all():
    if git("fetch", "-q", "origin", "main", check=False).returncode:
        raise Stop("git fetch origin main failed: the tags go on commits of main as pushed")
    found = deploy.pending()
    if not found:
        print("nothing pending")
        return 0
    skipped = False
    try:
        for p in found:
            skipped |= not tag_one(p)
    except Quit:
        skipped = True
    newest = found[-1]
    if skipped or not newest["in_sync"]:
        why = "a deploy was skipped" if skipped else "the newest deploy's re-check wasn't in sync"
        print(f"\n{drift.TAG} stays: {why}; once check-drift.py exits 0: python3 vps/tag-deploy.py --deployed")
        return 1
    try:
        if ask(f"move {drift.TAG} to {newest['commit'][:7]}?"):
            return 0 if move_deployed(newest["commit"]) else 1
    except Quit:
        pass
    return 1


def deployed_now():
    head = deploy.preflight()
    check = subprocess.run([sys.executable, str(HERE / "check-drift.py")], capture_output=True, text=True)
    print(check.stdout + check.stderr, end="")
    if check.returncode:
        print(f"{drift.TAG} stays: check-drift.py exited {check.returncode}")
        return 1
    try:
        if ask(f"move {drift.TAG} to {head[:7]}?"):
            return 0 if move_deployed(head) else 1
    except Quit:
        pass
    return 1


def main():
    parser = argparse.ArgumentParser(description="Create and push pending deploy tags.")
    parser.add_argument("--deployed", action="store_true", help="re-check now and move `deployed` to HEAD")
    args = parser.parse_args()
    try:
        return deployed_now() if args.deployed else tag_all()
    except Stop as e:
        print(f"tag-deploy: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
