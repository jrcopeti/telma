"""Stops the eval's gateway, so the next trial starts with no file-write claims. Only a process
whose own environment names the eval home: never her gateway, whatever a lock file says. Runs on
the VPS: python3 - <eval home> <lock file>..."""
import json
import os
import signal
import sys
import time

home, locks = sys.argv[1].encode(), sys.argv[2:]
pids = set()
for lock in locks:
    try:
        pids.add(int(json.load(open(lock))["pid"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
for pid in pids:
    try:
        env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
    except OSError:
        continue
    if not any(e == b"HERMES_HOME=" + home or e.startswith(b"HERMES_HOME=" + home + b"/") for e in env):
        continue
    for sig, wait in ((signal.SIGTERM, 60), (signal.SIGKILL, 20)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            break
        for _ in range(wait):
            if not os.path.exists(f"/proc/{pid}"):
                break
            time.sleep(0.5)
        if not os.path.exists(f"/proc/{pid}"):
            break
