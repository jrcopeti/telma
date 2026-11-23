"""The `eval` Hermes profile: her setup copied in before a run, and the stamp of what a run tested.
Not `profile.py`: that would shadow the standard library's module of the same name."""
import subprocess
from pathlib import Path

from vps import EVAL, HERS, PROFILE, SEED, WORK, py, stop_gateway, vps

REPO = Path(__file__).resolve().parent.parent
MODEL = "deepseek/deepseek-v4.1-flash"
BUDGET = 300  # the profile's own budget per turn


def sync_profile():
    """Her setup, copied into the eval profile; her memory and skills become each trial's start."""
    # Seeded from the step-2 profile every run (its .env, hooks allowlist and plugins, none of its
    # state), so a rotated key or a half-finished first copy is repaired; then made hers below.
    vps(stop_gateway() + f"""mkdir -p {PROFILE} {EVAL}/locks
rsync -a --exclude 'state.db*' --exclude '*.lock' --exclude logs --exclude sessions \\
  --exclude runtime --exclude cron --exclude cache --exclude backups --exclude sandboxes --exclude projects.db \\
  {SEED}/ {PROFILE}/
""" + py("sync_profile.py", HERS, PROFILE, WORK) + f"""hermes -p eval config set fallback_providers "[]" >/dev/null
hermes -p eval config set agent.run_budget_seconds {BUDGET} >/dev/null
mkdir -p {EVAL}/baseline {EVAL}/out
rsync -a --delete {HERS}/memories/ {EVAL}/baseline/memories/
rsync -a --delete {HERS}/skills/ {EVAL}/baseline/skills/
""")


def setup_stamp(brain_commit):
    """What the run tested: her files and the eval profile's copy of them, which should match."""
    telma = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    out = vps(f"hermes --version | head -1; for f in {HERS}/SOUL.md {PROFILE}/SOUL.md {HERS}/config.yaml {PROFILE}/config.yaml; "
              "do sha256sum $f | cut -c1-12; done").stdout.split("\n")
    return {"telma_commit": telma, "brain_commit": brain_commit, "hermes": out[0], "model": MODEL,
            "soul_sha": out[1], "eval_soul_sha": out[2], "config_sha": out[3], "eval_config_sha": out[4]}
