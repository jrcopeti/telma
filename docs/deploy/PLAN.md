# Deploy: know what is deployed on the VPS and keep it in sync with this repo

**Goal:** check whether Telma's deployed files, config, jobs and skills match this repo, and deploy a
merged change with one script. Without the check, drift shows only when someone diffs by hand.

**Done when:** `check-drift.py` reports every manifest line in sync, with the hooks and Hermes lines
`ok`; the `deployed` tag is set; `deploy.py` has deployed a change end to end; and each eval run
writes the check's summary into its results.

**Status:** closed 2026-11-25. Open work is listed below. The history is in the [devlog](DEVLOG.md).

## Decisions

- **One script and one check per repo, as the bot's.** Telma's copy of the bot's design, split along
  the trust boundary ([ADR 0002](../adr/0002-two-agents-split-by-trust-boundary.md)).
- **The check runs from the local machine only,** on demand, never in CI and never as a job of hers
  ([ADR 0007](../adr/0007-deploys-are-checked-against-the-repo.md)).
- **The `deployed` tag sets each status's direction.** Only the owner moves it, and only when every
  line is in sync ([ADR 0007](../adr/0007-deploys-are-checked-against-the-repo.md)).
- **Each deploy gets a `deploy/<date>-<n>` tag,** offered at a terminal after the owner's yes
  ([ADR 0007](../adr/0007-deploys-are-checked-against-the-repo.md)).
- **`deploy.py` copies only the paths it is given,** after a diff and a yes per file, to a backup,
  atomically, and only when no job of hers is running. It deploys only `main` as pushed.
- **A job that starts between that check and the swap is accepted.** Closing the window would mean
  holding Hermes's scheduler lock, which is an internal (owner, 2026-11-24).
- **`SOUL.md`, the skills, the model and the fallback order need `--eval-run` first,** as
  [AGENTS.md](../../AGENTS.md) requires. The owner can waive it for `SOUL.md` alone, per deploy, with `--skip-eval "<reason>"`
  (2026-11-27); the reason (one line) is printed and recorded in the deploy's tag. Skills and the model
  keys still need `--eval-run`. Toolsets and the Hermes version are not gated (see Open).
- **`SOUL.md` is checked as the filled repo copy.** The owner's name comes from a local private values
  file, which is never committed.
- **Config and jobs are checked, never written.** The script prints the `hermes config set` commands
  and the job changes for the owner to run.
- **Skills are compared with the brain skills on the VPS,** file by file. Tree modes are not checked,
  only owners.
- **Hooks stay owned by `agent`.** Her sandbox can't reach them. Accepted gap: a hook or config change
  shows only when the check runs.
- **The eval does not block on drift.** It saves the check's output as `<run>.drift.txt`.
- **`hermes hooks doctor` runs on demand,** and each run posts one test alert to `#alerts`.

## Steps

Each step is one branch and one PR. Steps that change the VPS need the owner's yes first.

| # | Step | Done when | Status |
|---|---|---|---|
| 1 | Write this plan. | The owner merges it. | done 2026-11-24 (#67) |
| 2 | Move `vps/telma/` to `vps/`. | CI is green, and no `vps/telma` is left outside history prose. | done 2026-11-24 (#68) |
| 3 | Build the check: `check-drift.py`, the manifest, `jobs.overrides.yaml`, and `{{OWNER_NAME}}` in `SOUL.md`. | Every manifest line is in sync, the hooks and Hermes lines are `ok`, and `deployed` is set. | done 2026-11-24 (#70, [devlog](DEVLOG.md#2026-11-24-pr-1-the-check)) |
| 4 | Build `deploy.py`, with the `deploy/<date>-<n>` tags. | A deploy's re-check is in sync, its tag is pushed, and `deployed` is moved. | done 2026-11-25 (#75, #76, [devlog](DEVLOG.md#2026-11-25-first-real-deploy)) |
| 5 | Make the eval write `<run>.drift.txt`. | A run's results hold the file, and the report quotes it. | done 2026-11-25 (#78, [devlog](DEVLOG.md#2026-11-25-step-5-the-eval-writes-drifttxt)) |
| 6 | Put the bot's intent in the brain: the `jobs` and `tree` modes and the copied script. | The brain's intent records them, and the showcase plan's Open item links here. | done 2026-11-25 (brain sync, [devlog](DEVLOG.md#2026-11-25-step-6-the-bots-intent-in-the-brain)) |

## Needs the owner

- Each `deploy.py` run, which needs a terminal and a yes per file, and each tag or `deployed` move.
- Any change to `SOUL.md`, a skill, the model or the fallback order: an eval run with the owner's yes
  first.
- Any change to her toolsets or the Hermes version: an eval run with the owner's yes first. The script
  doesn't gate these.
- A hook change: the owner re-approves it. A `config.yaml` change: the owner runs the `hermes config
  set` commands that the script prints.

## Docs to update

| Doc | What changes | Step |
|---|---|---|
| none pending | Each step updated its docs in its own PR. | — |

## Open

- **Forced-command ssh key.** A key in root's `authorized_keys` with `command=…,restrict` that can run
  only a read-only script, instead of root. It guards against a stolen local-machine key, which today
  gives root through `agents-vps` anyway.
- **Terminal values in `config.yaml` and `.env`.** The check flags a difference but doesn't say which
  one Hermes uses. Hermes's code at `ae2a81c` says `config.yaml` wins; this is untested.
- **The eval gate doesn't tie the run to the rest of the setup.** `--eval-run` checks the run's commit
  and `SOUL.md` hash. It doesn't check that the model, skills or config are unchanged since the run.
- **The eval gate doesn't read the verdict.** It ignores whether the run was partial, and it accepts
  a run in which tasks failed. The owner reads the report.
- **The eval gate matches by file name.** It matches the repo file's name, not the host path it writes to.
- **Toolsets and the Hermes version aren't gated.** `deploy.py` has no eval gate for
  `jobs.overrides.yaml`'s toolsets or a Hermes version change, though AGENTS.md requires an eval first.
- **`check-drift.py`'s collector is a string.** The owner's rule is code in scripts, not strings
  (brain `taste.md`). Moving `COLLECT` into a file is its own PR.
- **ticket-bay-bot still links to `vps/host.md`,** in its `host.md` and `kill-switch.md`. The fix is
  in that repo. `vps/host.md` was merged into [vps/README.md](../../vps/README.md).
