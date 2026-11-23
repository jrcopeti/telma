"""Copies her profile into the eval one, pointed at the trial folder, and checks nothing still
points at her brain. Runs on the VPS: python3 - <hers> <eval profile> <trial folder>"""
import json
import re
import shutil
import sys
from pathlib import Path

hers, prof, work = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
state = Path(work).parent.parent  # the eval folder, beside the trial's brain
cfg = re.sub(r"(^\s*- )/home/agent/brain(?=[/:\s]|$)", r"\g<1>" + work, (hers / "config.yaml").read_text(), flags=re.M)
cfg = cfg.replace("command: /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/exfil-tripwire.py",
                  f"command: /usr/bin/env TRIPWIRE_BRAIN={work} TRIPWIRE_NO_POST=1 TRIPWIRE_STATE={state / 'tripwire'}"
                  " /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/exfil-tripwire.py")
cfg = cfg.replace("command: /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/cron-alert.py",
                  f"command: /usr/bin/env CRON_ALERT_NO_POST=1 CRON_ALERT_JOBS={prof / 'cron/jobs.json'}"
                  f" CRON_ALERT_STATE={state / 'cron-alert'} /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/cron-alert.py")
if re.search(r"^\s*- /home/agent/brain", cfg, re.M) or "TRIPWIRE_NO_POST=1" not in cfg:
    sys.exit("config still points at her brain or the tripwire would post")
if cfg.count("cron-alert.py") != cfg.count("CRON_ALERT_NO_POST=1"):
    sys.exit("the cron alert would post")
(prof / "config.yaml").write_text(cfg)
env = (prof / ".env").read_text()
vols = re.search(r"^TERMINAL_DOCKER_VOLUMES=(.*)$", (hers / ".env").read_text(), re.M).group(1)
mounts = [v.replace("/home/agent/brain", work, 1) if v.startswith("/home/agent/brain") else v
          for v in json.loads(json.loads(vols))]
if any(not v.startswith(work) for v in mounts):
    sys.exit("a mount outside the trial folder: " + str([v for v in mounts if not v.startswith(work)]))
line = "TERMINAL_DOCKER_VOLUMES=" + json.dumps(json.dumps(mounts))
env = re.sub(r"^TERMINAL_DOCKER_VOLUMES=.*$", lambda m: line, env, flags=re.M)
(prof / ".env").write_text(env)
shutil.copy2(hers / "SOUL.md", prof / "SOUL.md")
