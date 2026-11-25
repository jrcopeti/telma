# 7. Deploys are checked against the repo, from the local machine

Status: accepted, 2026-11-25

## Context

Telma's setup lives in this repo, but she runs from files on the VPS. They were copied over by hand,
and nothing on the host read the repo. Drift showed up in two ways: the repo ahead of the host (a
merged change nobody copied) and the host ahead of the repo (a hand edit). Both were found only by
diffing file by file. The rename's redeploy took an evening and still missed four files. The eval
only stamped two hashes, `SOUL.md` and `config.yaml`, which said little about what she was running.

## Decision

A manifest, a check and a deploy script, all run by the owner from the local machine.

- **The manifest** (`vps/deploy.manifest`) has one line per file: where it lives in the repo, where
  it lives on the host, how to compare it, its owner and mode, and what it needs after a deploy.
  There are five ways to compare. `exact` is byte for byte. `redacted` fills a placeholder first,
  which is how `SOUL.md` carries `{{OWNER_NAME}}` in the repo; the name comes from a gitignored file
  in the git common directory, so worktrees share it. `subset` checks that every key in
  `config.overrides.yaml` equals the live `config.yaml` and ignores Hermes's own keys. `jobs` checks
  the four jobs' schedule, script, skills, toolsets, enabled flag and delivery against
  `jobs.overrides.yaml`; other jobs are counted, never named. `tree` compares a folder file by file,
  which is how her brain skills are checked, against what she runs on the VPS and not the local clone.
- **The check** (`vps/check-drift.py`) is read-only. It prints one line per manifest entry with a
  status, owner, mode and short hash, and never file contents. It also checks that the three Hermes
  installs are on the same commit and that `hermes hooks doctor` passes.
- **The tag** `deployed` marks the last commit known to match the host, and gives the status a
  direction. A difference where the host still equals the tagged file is "repo ahead". Where the repo
  still equals the tag, it is "host ahead". Where both moved, it is "both changed". Only the owner
  moves the tag, and only when every line is in sync.
- **The deploy script** (`vps/deploy.py`) copies only the files named on the command line, shows each
  diff, takes a yes per file, then does the whole copy at once. It keeps a backup on the host, writes
  each file to a temporary name with the right owner and mode, and swaps it in atomically without
  following a link on the host. It refuses to copy while a job of hers is running. It never writes
  `config.yaml`, `.env` or `jobs.json`: it prints the commands instead. Skills go through a brain PR
  and her sync, not through it. It never restarts anything.
- **Each deploy also gets a permanent tag**, `deploy/<date>-<n>`, because `deployed` moves and keeps
  no history. The tag's message lists the files, the backup folder and the check's summary. The
  script offers both tags at the end, and only at a terminal, after the owner's own yes.
- **A `SOUL.md` change is evaluated before it ships.** `evals/run.py --repo-soul` runs the eval with
  the repo's filled `SOUL.md` in place of her live one. `deploy.py --eval-run` then refuses to write
  `SOUL.md`, a skill or the model keys unless that run's hashes equal the file about to be written.
- **Each eval run saves the check's output** as `<run>.drift.txt` and its report quotes the summary,
  so a result says what setup it tested. The eval does not stop on drift: a run is sometimes meant to
  test a change that isn't deployed yet.

## Consequences

- Drift can be read at any time, in either direction, with no file contents leaving the host.
- A deploy is one command and leaves a tag that says what went out, who agreed and what the host held.
- The check and the script run as root over ssh from the owner's machine. A stolen key from that
  machine gives root already, so this adds nothing, but a forced-command key would shrink it. That
  stays open.
- Hooks Hermes has approved read as not ok after a deploy until they are approved again; the script
  prints the three commands. Her own hooks and config can still be changed by something else running
  as her user, and that shows only when the check runs, not on a schedule.
- The eval is tied to the `SOUL.md` it deploys, but not to the model, skills or config being
  unchanged since the run. Those still come from the host.
- A job that starts between the running-jobs check and the swap is accepted. Closing it would mean
  holding Hermes's scheduler lock, a Hermes internal.
- ticket-bay-bot copies the script and the design in its own repo. The two repos stay separate, as
  the agents are.
