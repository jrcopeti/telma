#!/usr/bin/env python3
"""Create and push the deploy tags deploy.py left pending, and move `deployed`. The owner runs it.

python3 vps/tag-deploy.py             each pending deploy/<day>-<n> tag, oldest first, after a yes for
                                      each; `deployed` moves with the newest when its re-check was in
                                      sync and no older one is skipped
python3 vps/tag-deploy.py --deployed  runs check-drift.py now and, if it exits 0, moves `deployed` to
                                      HEAD (main as pushed, nothing uncommitted under vps/)

Pending tags live in the common git dir (deploy-pending/), never in the repo. Exit 0 when done, 1
when something was skipped or `deployed` stays, 2 when it couldn't run.
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


def ask(question):
    try:
        answer = input(f"{question} [y/N/q] ").strip().lower()
    except EOFError:
        answer = "q"
    if answer in ("q", "quit"):
        raise Stop("stopped at q")
    return answer in ("y", "yes")


def move_deployed(commit):
    git("tag", "-f", drift.TAG, commit)
    if git("push", "-q", "-f", "origin", f"refs/tags/{drift.TAG}", check=False).returncode:
        raise Stop(f"{drift.TAG} moved here to {commit[:7]}, but pushing it failed: git push -f origin {drift.TAG}")
    print(f"{drift.TAG} on {commit[:7]}, pushed")


def tag_all():
    found = deploy.pending()
    if not found:
        print("nothing pending")
        return 0
    skipped = False
    for p in found:
        print(f"\n{p['tag']} on {p['commit'][:7]}\n  " + "\n  ".join(p["message"][1:]))
        on_origin = git("ls-remote", "--tags", "origin", f"refs/tags/{p['tag']}", check=False)
        if on_origin.returncode:
            raise Stop("git ls-remote origin failed")
        if on_origin.stdout.strip() or git("rev-parse", "-q", "--verify", f"refs/tags/{p['tag']}",
                                           check=False).returncode == 0:
            print(f"  {p['tag']} already exists: left pending, look at it by hand")
            skipped = True
            continue
        if not ask(f"create and push {p['tag']}?"):
            skipped = True
            continue
        git("tag", "-a", p["tag"], p["commit"], *[a for m in p["message"] for a in ("-m", m)])
        if git("push", "-q", "origin", f"refs/tags/{p['tag']}", check=False).returncode:
            raise Stop(f"{p['tag']} made here, but pushing it failed: git push origin {p['tag']}")
        p["file"].unlink()
        print(f"{p['tag']} pushed")
    newest = found[-1]
    if skipped or not newest["in_sync"]:
        why = "a deploy was skipped" if skipped else "the newest deploy's re-check wasn't in sync"
        print(f"\n{drift.TAG} stays: {why}; once check-drift.py exits 0: python3 vps/tag-deploy.py --deployed")
        return 1
    if ask(f"move {drift.TAG} to {newest['commit'][:7]}?"):
        move_deployed(newest["commit"])
        return 0
    return 1


def deployed_now():
    head = deploy.preflight()
    check = subprocess.run([sys.executable, str(HERE / "check-drift.py")], capture_output=True, text=True)
    print(check.stdout + check.stderr, end="")
    if check.returncode:
        print(f"{drift.TAG} stays: check-drift.py exited {check.returncode}")
        return 1
    if ask(f"move {drift.TAG} to {head[:7]}?"):
        move_deployed(head)
        return 0
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
