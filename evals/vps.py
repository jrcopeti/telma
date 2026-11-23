"""The VPS: where the eval's folders are, and how a script runs there as `agent`."""
import shlex
import subprocess
from pathlib import Path

REMOTE = Path(__file__).resolve().parent / "remote"
HOST = "agents-vps"
# A dropped connection fails in about two minutes instead of hanging the run.
SSH = ["ssh", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4"]
HERS = "/home/agent/.hermes"
# The eval's own Hermes home, outside hers. Her gateway serves every profile under ~/.hermes and
# keeps each session's file-write claims after it ends, so trials run there refused later trials'
# writes, and its claims sat in her live gateway. Here the eval gets its own gateway, stopped after
# every trial.
EVAL_HOME = "/home/agent/eval/home"
PROFILE = f"{EVAL_HOME}/profiles/eval"
SEED = f"{HERS}/profiles/eval"  # the step-2 profile: the eval's .env (OpenRouter key, no Discord token)
EVAL = "/home/agent/eval"
WORK = f"{EVAL}/work/brain"


def vps(script, check=True):
    """Run a bash script on the VPS as `agent`, from stdin, so nothing needs quoting."""
    r = subprocess.run([*SSH, HOST, "su - agent -c 'bash -s'"], input="set -euo pipefail\n"
                       "export XDG_RUNTIME_DIR=/run/user/$(id -u)\n"
                       f"export HERMES_HOME={EVAL_HOME} HERMES_GATEWAY_LOCK_DIR={EVAL}/locks\n"
                       # The read-before-write guard checks paths on the host, where /home/agent/brain
                       # is her live brain, not the copy mounted there: it refused new notes the live
                       # brain already has. In production host and sandbox paths are the same brain.
                       "export HERMES_DISABLE_FILE_STATE_GUARD=1\n" + script,
                       text=True, capture_output=True)
    if check and r.returncode:
        raise RuntimeError(f"VPS step failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    return r


def py(name, *args, out=None, or_else=None):
    """Bash that runs remote/<name> with these arguments, its output to `out` if given, and `or_else`
    if it fails. The file goes in a heredoc, so it reaches the VPS inside the one script vps() sends."""
    text = (REMOTE / name).read_text()
    if "\nEOF_PY\n" in f"\n{text}\n":
        raise ValueError(f"remote/{name} contains its own heredoc end")
    line = " ".join(["python3 -", *(shlex.quote(str(a)) for a in args), *([f"> {shlex.quote(out)}"] if out else []), "<<'EOF_PY'",
                     *([f"|| {or_else}"] if or_else else [])])
    return f"{line}\n{text}\nEOF_PY\n"


def remove_container():
    return "docker rm -f $(docker ps -aq --filter label=hermes-profile=eval) >/dev/null 2>&1 || true\n"


def key_spend(out, settle=False):
    """Writes what OpenRouter has billed the eval's key so far (USD) to `out`, or null. A trial's cost
    is the difference: Hermes' estimate prices every call at the model's cheapest provider, while
    OpenRouter spreads the calls over dearer ones (5× the estimate on 2026-11-22). The eval has its own
    key, so her jobs don't count; the key's limit is a hard cap. With `settle`, it waits out
    OpenRouter's lag (up to 30 s)."""
    return py("key_spend.py", f"{PROFILE}/.env", 6 if settle else 0, out=out, or_else=f"echo null > {shlex.quote(out)}")


def stop_gateway():
    """Stops the eval's gateway (remote/stop_gateway.py). Never fails the script: a stop that loses a
    race with the gateway's own exit must not throw away a trial that already ran, or skip the
    cleanup after it."""
    return py("stop_gateway.py", EVAL_HOME, f"{EVAL_HOME}/gateway.lock", f"{PROFILE}/gateway.lock",
              f"{EVAL}/locks/host-gateway.json", or_else="true")
