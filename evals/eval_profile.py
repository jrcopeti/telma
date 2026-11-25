"""The `eval` Hermes profile: her setup copied in before a run, the stamp of what a run tested, and the drift check's note.
Not `profile.py`: that would shadow the standard library's module of the same name."""
import base64
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

from vps import EVAL, HERS, PROFILE, SEED, WORK, py, stop_gateway, vps

REPO = Path(__file__).resolve().parent.parent
MODEL = "deepseek/deepseek-v4.1-flash"
BUDGET = 300  # the profile's own budget per turn
SOUL = "vps/hermes/SOUL.md"


def repo_soul():
    """This repo's SOUL.md at HEAD with the owner's name filled in, the file deploy.py would write
    (it reads HEAD too), and its hash as stamped. Stops if the working tree's copy differs."""
    if subprocess.run(["git", "status", "--porcelain", "--", SOUL], cwd=REPO, capture_output=True, text=True).stdout.strip():
        sys.exit(f"{SOUL} has uncommitted changes: commit them first, so the run tests the file deploy.py reads")
    sys.dont_write_bytecode = True  # importing check-drift.py must not leave a __pycache__ in vps/
    spec = importlib.util.spec_from_file_location("check_drift", REPO / "vps/check-drift.py")
    drift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift)
    try:
        data = drift.filled(drift.git("show", f"HEAD:{SOUL}").stdout, SOUL, drift.private_values())
    except (drift.Stop, UnicodeDecodeError) as e:
        sys.exit(str(e))
    return data, hashlib.sha256(data).hexdigest()[:12]


def sync_profile(soul=None):
    """Her setup, copied into the eval profile; her memory and skills become each trial's start.
    With `soul` (repo_soul()'s bytes), the repo's SOUL.md replaces her live one in the profile."""
    # Seeded from the step-2 profile every run (its .env, hooks allowlist and plugins, none of its
    # state), so a rotated key or a half-finished first copy is repaired; then made hers below.
    vps(stop_gateway() + f"""mkdir -p {PROFILE} {EVAL}/locks
rsync -a --exclude 'state.db*' --exclude '*.lock' --exclude logs --exclude sessions \\
  --exclude runtime --exclude cron --exclude cache --exclude backups --exclude sandboxes --exclude projects.db \\
  {SEED}/ {PROFILE}/
""" + py("sync_profile.py", HERS, PROFILE, WORK) + (
        f"base64 -d > {PROFILE}/SOUL.md <<'EOF_SOUL'\n{base64.b64encode(soul).decode()}\nEOF_SOUL\n" if soul is not None else "") + f"""hermes -p eval config set fallback_providers "[]" >/dev/null
hermes -p eval config set agent.run_budget_seconds {BUDGET} >/dev/null
mkdir -p {EVAL}/baseline {EVAL}/out
rsync -a --delete {HERS}/memories/ {EVAL}/baseline/memories/
rsync -a --delete {HERS}/skills/ {EVAL}/baseline/skills/
""")


def setup_stamp(brain_commit, soul_sha=None):
    """What the run tested: her files and the eval profile's copy of SOUL.md. The two SOUL.md hashes match
    unless the run used the repo's (`soul_source` "repo", `repo_soul_sha` its hash), when the eval's
    copy should match that one instead (soul_copy_problem). Whether her files match the repo is drift_report's."""
    telma = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    out = vps(f"hermes --version | head -1; for f in {HERS}/SOUL.md {PROFILE}/SOUL.md; "
              "do sha256sum $f | cut -c1-12; done").stdout.split("\n")
    return {"telma_commit": telma, "brain_commit": brain_commit, "hermes": out[0], "model": MODEL,
            "soul_sha": out[1], "eval_soul_sha": out[2],
            "soul_source": "host" if soul_sha is None else "repo", **({} if soul_sha is None else {"repo_soul_sha": soul_sha})}


def soul_copy_problem(stamp):
    """Why the eval profile's SOUL.md isn't the file the run meant to test (hers, or the repo's with
    --repo-soul), or None. Checked before any paid trial."""
    repo = stamp["soul_source"] == "repo"
    want = stamp.get("repo_soul_sha" if repo else "soul_sha")
    if stamp["eval_soul_sha"] and stamp["eval_soul_sha"] == want:
        return None
    return f"the eval profile's SOUL.md is {stamp['eval_soul_sha']!r}, not {'the repo' if repo else 'her'}'s {want}: the copy failed"


def drift_report():
    """What vps/check-drift.py says about her deployed files right now, and its exit code, as the text
    for <run>.drift.txt. Never stops the run: a run may be meant to test an undeployed change.
    Only its stdout (file names, statuses, short hashes) is kept: the file is public, and its stderr
    can name the host's address or a local path."""
    try:
        r = subprocess.run([sys.executable, str(REPO / "vps/check-drift.py")], cwd=REPO, capture_output=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"check did not run: {type(e).__name__}\n"
    return r.stdout.decode(errors="replace") + f"exit {r.returncode}\n"
