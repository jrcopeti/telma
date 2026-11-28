# Setup: a SETUP.md that a user's coding agent follows to set up their own Telma

**Goal:** a user hands `setup/SETUP.md` to their coding agent (Claude Code, Codex, Cursor), which sets
up their own Telma on their own host, keeping their own brain, and stops at each 🙋 step where it
needs them. The guide follows the course kit's module 8 guide: a Doctor Agent brief, Step 0
decisions with defaults, a **Done when** check per step, 🙋 stops, secrets typed only in the user's
own terminal, and a Traps section.

**Done when:** a fresh agent with no context from this work has run `setup/SETUP.md` end to end as a
new user on the VPS, Verify passes (with `check-drift.py` clean), the README's Quick Start links the
guide, and the guide carries a "Last verified" date.

**Status:** step 1 in progress. The history is in the [devlog](DEVLOG.md).

## Decisions

- **The user gets their own Telma** with their own brain, Discord server and OpenRouter key; Telma
  only, no ticket-bay-bot and no shared host (owner, 2026-11-27).
- **Three targets, and only Step 1 forks:** a VPS (the default), a Lima VM on a Mac, or a Linux box.
  After Step 1 every step is the same, run through the access Step 0 chose (`ssh`, `limactl shell`
  with scripts on stdin, or local `sudo -iu`). Windows/WSL 2 is one line, untested; Hermes straight
  on macOS is out (no systemd or rootless Docker).
- **`vps/` stays the single source** of every file the setup installs. `setup/` holds only the
  guide, `check-brain.py` and `answers.example`.
- **Five values are filled in on copy and on check:** `{{OWNER_NAME}}`, `{{AGENT_NAME}}` (default
  `Telma`), `{{USER}}` and `{{HOME}}` (default `agent`, `/home/agent`), and `{{TIMEZONE}}`. They come
  from the private values file in the clone's git directory. Files are byte-for-byte the tested ones
  after that substitution, and for the owner every filled file is what is live today. The repo, its
  docs and scripts keep the name Telma.
- **The user is never an existing one.** The module 8 guide creates `agent` too, so a course
  student already has one running Hermes; Step 1 stops and asks for another name if the user exists.
- **Laptop-side scripts read the host and user from `TELMA_HOST` and `TELMA_USER`** (defaults
  `agents-vps`, `agent`), read once in `check-drift.py`, which `deploy.py` and `evals/` reuse.
- **The Discord IDs stay out of the repo.** They live only in Hermes's `.env`; the guide sets them.
- **The brain comes from `brain-template`:** new (the default) or an existing one made from it.
  Telma depends on its layout: her skills live in its `skills/`, the sandbox mounts its rule files,
  and sync-brain pushes only its folders. Notes from another tool: start a fresh brain and drop them
  into `inbox/`; no migration tool.
- **`setup/check-brain.py` checks that contract** (the mounted paths, the four skills, the folders
  sync-brain pushes) in Step 0 and again in Verify, and lists what is missing.
- **The agent refuses to go on while the brain repo is public.** The deploy key with write access is
  a 🙋 step.
- **The model: the agent asks which chain the user wants.** The default is the tested chain in
  `config.overrides.yaml`. A different chain is allowed: the agent says it is untested (the
  injection results differ by model) and goes on with it. No free-only option.
- **No prices anywhere in the guide:** they depend on the model and change (owner, 2026-11-27).
- **The eval is optional,** described for users who want it, run on their own OpenRouter key, and
  only on their yes. It is recommended when they chose an untested chain or Hermes version.
- **The user forks `jrcopeti/telma`** and the agent clones the fork, so `deploy.py`'s tags and the
  user's own changes have a home. Updating is `git merge upstream/main`, then `deploy.py`.
- **Discord only.** The guide says other platforms exist in Hermes but this setup covers only
  Discord: the hooks post through Discord webhooks. `#alerts` is a channel her bot can't read.
- **Every safety piece is set up,** no hardening switch, except **the canary, which is optional**
  (it needs an outside service).
- **Hermes is pinned** in `vps/hermes/VERSION`, which `check-drift.py` compares with the host. A
  newer version is allowed and flagged untested, as a model change is.
- **The acceptance run is on the VPS, as a new user `telma-test`,** deleted afterwards, with its own
  Discord server and `#alerts`. The local machine has no room for a Lima VM. The run skips Step 1b
  (the machine is already locked); the VPS and Lima branches of Step 1 are written from the owner's
  own runs. The test agent touches nothing of `agent`'s or `ticket-bay-bot`'s, and the owner
  approves each job switch-on.

## Steps

Each step is one branch and one PR. Steps 2 to 4 change the drift check and deploy for the owner's
Telma too; each ends with `check-drift.py` clean against the live host and nothing to deploy.

| # | Step | Done when | Status |
|---|---|---|---|
| 1 | Write this plan and its devlog; link them from AGENTS.md. | The owner merges it. | in progress |
| 2 | Read `TELMA_HOST` and `TELMA_USER` once in `check-drift.py`; make `deploy.py`, the smoke scripts and `evals/` use them instead of `agents-vps` and `/home/agent`. Make `INSTALLS` cover a host with Telma alone; the bot's install and `/opt/hermes-guard` are checked only where present. | Tests cover unset and set values and a Telma-only fake host; the owner's check is clean. | todo |
| 3a | Fill placeholders in the manifest's host path and owner column (`{{HOME}}`, `{{USER}}`) and in `subset` mode before comparing; `deploy.py` prints the `hermes config set` commands filled. | Tests cover a home other than `/home/agent` in every mode. | todo |
| 3b | Put `{{HOME}}` in `deploy.manifest`, `config.overrides.yaml`, `brain-triage-prompt.txt` and both `*.hooks.yaml`, and `{{TIMEZONE}}` in `config.overrides.yaml`. | The owner's check is clean with the placeholders filled. | todo |
| 3c | Put `{{HOME}}` and `{{AGENT_NAME}}` in `SOUL.md`. | The eval ran with the owner's yes, or the owner waived it; the owner's check is clean. | todo |
| 4 | Pin Hermes: add `vps/hermes/VERSION`; `check-drift.py` compares it with `hermes --version`. | The check reports the version line; a fake host with another version shows drift. | todo |
| 5 | Write `setup/check-brain.py`, its tests and its CI job. | It passes on a copy of `brain-template` and names each missing path on a broken copy. | todo |
| 6 | Generalise `vps/kill-switch.md` (any host is the default, ticket-bay-bot one aside), and write `~` for the agent user's home in `vps/README.md` and `brain-skills/README.md`. | Each reads correctly for a host with Telma alone under another user. | todo |
| 7 | Write `setup/SETUP.md` and `setup/answers.example`, plus a CI check that every `vps/` path the guide names exists. | The guide covers Step 0 to Verify and Updating; CI is green. | todo |
| 8 | Check `telma-test` can't clash with the live agents: systemd unit names, gateway ports, rootless Docker, `/opt/hermes-guard`, the network guard's uid rules, alert webhooks. | Each shared piece is listed in the devlog as separate or handled, and the owner says go. | todo |
| 9 | Run the guide as `telma-test` on the VPS with a fresh agent; fix the guide and add Traps from the run; link it from the README; add "Last verified"; delete `telma-test`. | Verify passes on the run, `check-drift.py` is clean for `telma-test`, and the user is gone afterwards. | todo |

## Needs the owner

- A yes before each `check-drift.py` or `deploy.py` run against the live host (steps 2 to 4, 9).
- Step 3c: the eval with the owner's yes, or the owner's waiver; it changes `SOUL.md`.
- Step 8: the go for a second Hermes on the live host.
- Step 9: a yes to create `telma-test`; the 🙋 steps (a throwaway Discord server, a test brain from
  the template, an OpenRouter key); a yes for each job switch-on; a yes to delete the user.
- Any eval run: the owner's yes first.

## Docs to update

| Doc | What changes | Step |
|---|---|---|
| [AGENTS.md](../../AGENTS.md) | "Start here" names this plan. | 1 |
| [vps/README.md](../../vps/README.md) | `TELMA_HOST`, `TELMA_USER`, the placeholders, the values file, `VERSION`. | 2–4 |
| [docs/evals/PLAN.md](../evals/PLAN.md) | How to run the eval against another host and user. | 2 |
| [docs/deploy/PLAN.md](../deploy/PLAN.md) | The filled-`SOUL.md` and values-file decisions cover the new placeholders. | 3a |
| [vps/kill-switch.md](../../vps/kill-switch.md), [vps/brain-skills/README.md](../../vps/brain-skills/README.md) | Any host and user. | 6 |
| [README.md](../../README.md) | Quick Start links `setup/SETUP.md`. | 9 |

## Open

- **The Lima and VPS branches of Step 1 aren't re-run** by the acceptance run; they rest on the
  owner's earlier runs.
