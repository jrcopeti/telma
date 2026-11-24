# The host, from Telma's side

Telma shares one VPS with ticket-bay-bot. The bot's repo describes the same host from its side:
[jrcopeti/ticket-bay-bot vps/host.md](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/host.md).

## Users on this side

| User | What it runs |
|---|---|
| `agent` | Telma: her own Hermes install (`~/.hermes/hermes-agent`), rootless Docker. Her sandbox starts with `--network=none`; web and browser run in her Hermes process on the host. Host-side jobs: [sync-brain](sync-brain.sh), [memory-diff](memory-diff.sh) and [tripwire-health](tripwire-health.sh), plus the [exfil tripwire](exfil-tripwire.py) and [cron alert](cron-alert.py) hooks. |

The bot runs as `ticket-bay-bot`, next to `ticket-bay-app` and `skills-sync`. Both agents' homes are
`750`, so neither can read the other's files.

## Where each file is deployed

`~` is Telma's home, `/home/agent`. [`deploy.manifest`](deploy.manifest) lists each file with its
owner and mode. From the local machine, [`check-drift.py`](check-drift.py) says whether the VPS
still matches the repo, [`deploy.py`](deploy.py) copies the files named to it, after a yes for
each, and [`tag-deploy.py`](tag-deploy.py) tags each deploy in this repo.

| In this repo | On the VPS |
|---|---|
| `sync-brain.sh`, `brain-files.py`, `memory-diff.sh`, `tripwire-health.sh` | `~/.hermes/scripts/` |
| `guard-network.sh` | `~/.hermes/agent-hooks/` |
| `exfil-tripwire.py`, `cron-alert.py` | `~/.hermes/agent-hooks/`; their config entries in `*.hooks.yaml` |
| `hermes/SOUL.md` | `~/.hermes/` |
| `hermes/config.overrides.yaml` | merged by hand into `~/.hermes/config.yaml` (below) |
| `hermes/brain-triage-prompt.txt` | the `brain-triage` job's prompt in `~/.hermes/cron/jobs.json` |
| `brain-skills/` | the brain repo's `skills/`, which sync-brain brings to `~/brain/skills/` |
| `sandbox/Dockerfile` | `~/sandbox/` |

The deployed `SOUL.md` differs from this copy on purpose: it names the owner where this copy says
`{{OWNER_NAME}}`. The check fills that in from a private file outside the repo before comparing.

Most of `~/.hermes/config.yaml` is Hermes's own defaults, written by its installer.
[`config.overrides.yaml`](hermes/config.overrides.yaml) holds only the settings chosen for
her: the model and its free fallbacks, the Docker sandbox with no network and its brain mounts, the
brain's skills folder, approvals, and the three hooks under `hooks:`. Two settings,
`terminal.docker_mount_cwd_to_workspace` and `gateway.allow_all_users`, equal Hermes's defaults and
are pinned on purpose. Every key in it must match the live file.

Hermes also keeps the `terminal:` settings in `~/.hermes/.env`, as `TERMINAL_*`. Change those keys
with `hermes config set`, which writes both files; a hand edit of `config.yaml` alone may leave
`.env` stale. Which of the two Hermes reads when they differ hasn't been tested.

## The skills

Her four brain skills (capture, ask-brain, triage, lint) live in the brain repo, which she reads
read-only. [`brain-skills/`](brain-skills/) is a copy of them, credited to the MIT brain
template they come from. A change to them goes through a PR on the brain repo; update this copy
after it merges. The bundled skills Hermes installs in `~/.hermes/skills/` are its own and aren't
copied.

## Her jobs

Each is a job in `~/.hermes/cron/jobs.json`; scripts are in `~/.hermes/scripts/`. A job's output
goes to her Discord channel, and the scripts print nothing when all is well, so most runs post
nothing. The tripwire and cron alert hooks post to `#alerts`.

[`jobs.overrides.yaml`](hermes/jobs.overrides.yaml) holds the four jobs' schedules (Berlin time),
scripts, skills and toolsets: `sync-brain` and `tripwire-health` every 15 minutes, `brain-triage`
(an agent run, with [this prompt](hermes/brain-triage-prompt.txt)) at 09:00 and 21:00, and
`memory-diff` at 09:30 and 21:30.

Jobs she makes in a chat (a reminder) land in the same file; the cron alert hook posts each one to
`#alerts`. None of them is copied here.

## Rules for the whole host

These rules are the same, word for word, in both repos.

- **Hermes moves in lockstep.** Both installs and `/opt/hermes-guard` stay on the same commit. A bump
  is by hand, in all three places.
- **A compromised host means both kill switches, then a rebuild.** Signs: a root login you don't know,
  a changed `/etc`, an unknown process. Run the
  [bot's](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/ticket-bay-bot/kill-switch.md) and
  [Telma's](kill-switch.md) kill switches, then rebuild the VPS.
- **Scripts are deployed by hand.** Nothing on the host clones either repo. A change here reaches the
  VPS only when the owner says yes and copies it.
