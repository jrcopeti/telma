# vps/: Telma's host, and how files get there

This folder holds the copy of every file Telma's host runs: the scripts, her `SOUL.md`, the hooks, the
sandbox Dockerfile, the settings we pin, her jobs and her brain skills. The first half of this page
says what runs on the host and where each file goes. The second half says how to check that the host
still matches this repo and how to deploy a change.

Telma shares one VPS with ticket-bay-bot. The bot's repo describes the same host from its side:
[jrcopeti/ticket-bay-bot vps/host.md](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/host.md).

## Users on this side

| User | What it runs |
|---|---|
| `agent` | Telma: her own Hermes install (`~/.hermes/hermes-agent`), rootless Docker. Her sandbox starts with `--network=none`; web and browser run in her Hermes process on the host. Host-side jobs: [sync-brain](sync-brain.sh), [memory-diff](memory-diff.sh) and [tripwire-health](tripwire-health.sh). Three hooks: the [network guard](guard-network.sh), the [exfil tripwire](exfil-tripwire.py) and the [cron alert](cron-alert.py). |

The bot runs as `ticket-bay-bot`, next to `ticket-bay-app` and `skills-sync`. Both agents' homes are
`750`, so neither can read the other's files.

## Where each file is deployed

`~` is Telma's home, `/home/agent`. [`deploy.manifest`](deploy.manifest) lists each file with its
owner and mode.

| In this repo | On the VPS |
|---|---|
| `sync-brain.sh`, `brain-files.py`, `memory-diff.sh`, `tripwire-health.sh`, `triage-gate.sh` | `~/.hermes/scripts/` |
| `guard-network.sh` | `~/.hermes/agent-hooks/` |
| `exfil-tripwire.py`, `cron-alert.py` | `~/.hermes/agent-hooks/`; their config entries in `*.hooks.yaml` |
| `hermes/SOUL.md` | `~/.hermes/` |
| `hermes/config.overrides.yaml` | merged by hand into `~/.hermes/config.yaml` (below) |
| `hermes/jobs.overrides.yaml`, `hermes/brain-triage-prompt.txt` | checked against `~/.hermes/cron/jobs.json`; the prompt is the `brain-triage` job's prompt |
| `brain-skills/` | the brain repo's `skills/`, which sync-brain brings to `~/brain/skills/` |
| `sandbox/Dockerfile` | `~/sandbox/` |

The deployed `SOUL.md` differs from this copy on purpose: it names the owner where this copy says
`{{OWNER_NAME}}`. The check fills that in from a private, untracked file in the clone's git
directory before comparing, so the name never reaches the repo.

## Her settings

Most of `~/.hermes/config.yaml` is Hermes's own defaults, written by its installer.
[`config.overrides.yaml`](hermes/config.overrides.yaml) holds only the settings chosen for
her: the model and its free fallbacks, the Docker sandbox with no network and its brain mounts, the
brain's skills folder, approvals, and the three hooks under `hooks:`. Two settings,
`terminal.docker_mount_cwd_to_workspace` and `gateway.allow_all_users`, equal Hermes's defaults and
are pinned on purpose. Every key in the overrides file must match the live file; any other key is
Hermes's and the check ignores it.

Hermes also keeps the `terminal:` settings in `~/.hermes/.env`, as `TERMINAL_*`. Change those keys
with `hermes config set`, which writes both files; a hand edit of `config.yaml` alone may leave
`.env` stale. The check compares the two. Hermes's code says `config.yaml` wins for the keys set in
its `terminal:` section, but that hasn't been tested.

## The skills

Her four brain skills (capture, ask-brain, triage, lint) live in the brain repo. Her sandbox mounts
them read-only, but Hermes's own skill editing runs on the host and can write them. A change she
makes to a skill, `AGENTS.md`, `CLAUDE.md` or `taste.md` is never pushed to `main`: sync-brain puts
it on the branch `telma/proposals`, posts the compare link to Discord once, and writes `main`'s
version back into her copy ([ADR 6](../docs/adr/0006-rule-file-changes-go-through-a-proposal.md)).
The owner merges the PR (after the eval, for a skill) or deletes the branch.

[`brain-skills/`](brain-skills/) is a copy of the skills, credited to the MIT brain template they
come from. A change to them goes through a PR on the brain repo. Once it merges, sync-brain brings it
to the host, and a PR here copies the merged file into `brain-skills/`. Skipping that last step makes
the check read "host ahead" for the skill. The bundled skills Hermes installs in `~/.hermes/skills/`
are its own and aren't copied.

## Her jobs

Each is a job in `~/.hermes/cron/jobs.json`; scripts are in `~/.hermes/scripts/`. A job's output
goes to her Discord channel, and the scripts print nothing when all is well, so most runs post
nothing. The tripwire and cron alert hooks post to `#alerts`.

[`jobs.overrides.yaml`](hermes/jobs.overrides.yaml) holds the four jobs' schedules (Berlin time),
scripts, skills and toolsets, and whether each is on: `sync-brain` and `tripwire-health` every
15 minutes, `brain-triage` (an agent run, with [this prompt](hermes/brain-triage-prompt.txt)) hourly
from 08:00 to 00:00, and `memory-diff` ten minutes after each of those. `triage-gate.sh` is
`brain-triage`'s pre-script: it wakes the agent only when `inbox/` holds something it hasn't seen
(it prints `inbox: N items`, never a file name), and always at 09:00, and again each hour while the last run ended in error. A gate that fails still
runs the agent. The check reads only those four jobs from the host.

Jobs she makes in a chat (a reminder) land in the same file; the cron alert hook posts each one to
`#alerts`. None of them is copied here. The check counts them and never names them, which is why it
prints "1 other job(s), not checked".

## Rules for the whole host

These rules are the same, word for word, in both repos, except the last, which is each repo's own.

- **Hermes moves in lockstep.** Both installs and `/opt/hermes-guard` stay on the same commit. A bump
  is by hand, in all three places.
- **A compromised host means both kill switches, then a rebuild.** Signs: a root login you don't know,
  a changed `/etc`, an unknown process. Run the
  [bot's](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/ticket-bay-bot/kill-switch.md) and
  [Telma's](kill-switch.md) kill switches, then rebuild the VPS.
- **Nothing on the host reads either repo.** A change here reaches the VPS only when the owner says yes
  and runs the deploy below, or copies it by hand.

## Checking the host against this repo

`check-drift.py` compares the host with this repo and changes nothing. `deploy.py` copies named files
to the host, then runs the check again. Both run from the owner's machine. Neither runs in CI, and
Telma never runs them: she must not check her own controls. The design and the reasons are in
`docs/deploy/PLAN.md`; the history is in `docs/deploy/DEVLOG.md`.

Run `python3 vps/check-drift.py`. It prints one line per file in the manifest, then two lines about
the host itself: whether both Hermes installs are on the same commit, and whether
`hermes hooks doctor` is happy. The last line is a summary such as
`17 of 17 in sync, hermes ok, hooks ok, deployed 8188d34`.

| Status | Meaning |
|---|---|
| in sync | The host matches this repo. |
| repo ahead | This repo changed and the host still has the old file. Deploy it. |
| host ahead | Someone changed the host and the repo did not move. Look at it before overwriting. |
| both changed | Both sides moved since the last known match. Resolve by hand. |
| missing | The file is not on the host. |
| host only | A file sits in a watched folder on the host but not in this repo. |
| link | A symlink where a plain file should be. Never followed. |
| differs | The sides differ and there is no `deployed` tag to say which one is newer. |

The check posts one test alert to the alerts channel each time, because the hooks doctor runs the
hooks once. That is expected. It needs an ssh alias `agents-vps` with root access.

## Deploying a change, step by step

1. Merge the change to `main` through its PR. If it touches `SOUL.md`, a brain skill, her toolsets, the
   model or fallback order, or the Hermes version, the eval comes first (see `docs/evals/PLAN.md` and
   `AGENTS.md`).
2. In a normal terminal tab, not an agent's shell: `cd` to the repo, then `git checkout main` and
   `git pull --ff-only`. The deploy refuses to run unless your checkout is `origin/main`, with nothing
   uncommitted under `vps/`.
3. Run `python3 vps/check-drift.py` and confirm the files you mean to ship read "repo ahead".
4. Run `python3 vps/deploy.py <repo path>...`, naming each file, for example
   `python3 vps/deploy.py vps/sync-brain.sh`. It never deploys "everything that is ahead". It
   needs a terminal and stops in a pipe or an agent's shell.
5. For each file it shows the diff and asks yes or no. Nothing is copied until every file is answered.
6. It stops without copying if one of her jobs is running. Wait and run it again.
7. It saves the old files on the host in `~/.hermes/deploy-backups/<timestamp>/`, writes each new file
   under a temporary name with the right owner and mode, then swaps them all in at once.
8. It runs the full check again, then prints what each file still needs, if anything: a gateway
   restart, a new chat, a sandbox rebuild, or re-approving a hook. It prints the commands and runs
   none of them.
9. It offers the two tags described below. Answer yes only after the check reads in sync.

`SOUL.md`, brain skills and the model keys also need `--eval-run <results .jsonl>`, pointing at the
eval run that passed. For `SOUL.md`, commit it and run `python3 evals/run.py --repo-soul` first.
Without the flag the deploy stops on those files.

`deploy.py` does not write `config.yaml`, `.env` or `jobs.json`. For those it prints the
`hermes config set` commands or the job change to make by hand. Brain skills do not go through
`deploy.py` at all: see "The skills" above.

## The two tags

| Tag | What it is | Who moves it |
|---|---|---|
| `deployed` | The last commit known to match the host. One tag, and it moves forward. The check uses it to tell "repo ahead" from "host ahead". | Only the owner, by a yes at the keyboard, and only when every line is in sync. |
| `deploy/<date>-<n>` | A permanent record of one deploy: the files, the backup folder and the check's summary line. One per deploy, never moved. | `deploy.py`, after the owner's yes. |

`deploy.py` offers both at the end of a copy. If a copy leaves something not in sync, it offers only
the dated tag and leaves `deployed` where it is.

To move `deployed` without copying anything, for example after re-approving a hook or after copying a
brain skill into this folder, run `python3 vps/deploy.py --deployed`. It re-checks and, if every line
is in sync, offers to move the tag to your current commit.

To list past deploys: `git tag -l 'deploy/*' -n20`.

## If something looks wrong

- A copy that stops partway exits with code 3 and offers no tag. Run the check, look at what landed,
  and tag by hand only if files did.
- The backups are root's, in `~/.hermes/deploy-backups/` on the host. Copy a file back from there to
  undo a deploy.
- Tests for both tools run against a fake host folder (`DRIFT_HOST_ROOT`) and need no VPS.
