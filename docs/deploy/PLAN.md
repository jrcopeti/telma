# Deploy: know what is deployed on the VPS and keep it in sync with this repo

**Goal:** check whether Telma's deployed files, config, jobs and skills match this repo, and deploy a
merged change with one script instead of copying by hand. Without the check, drift only shows when
someone diffs by hand.

**Done when:** `check-drift.py` reports every manifest line in sync, with the hooks and Hermes lines
`ok`; the `deployed` tag is set; `deploy.py` has deployed a change end to end; and each eval run
writes the check's summary into its results.

**Status:** closed 2026-11-25. Open work is listed below. The history is in the [devlog](DEVLOG.md).

## Decisions

- **Telma has her own copy of the bot's design.** Same manifest, statuses and `deployed` tag, but a
  separate script in each repo, because the repos split along the trust boundary
  ([ADR 0002](../adr/0002-two-agents-split-by-trust-boundary.md)).
- **`vps/` holds only Telma's files.** Host paths did not change when the folder moved.
- **The check runs from the local machine only,** on demand, never in CI and never as a job of hers
  ([ADR 0007](../adr/0007-deploys-are-checked-against-the-repo.md)).
- **The `deployed` tag gives each status its direction.** It marks the last commit known to match the
  host. Only the owner moves it, and only when every line is in sync.
- **Each deploy gets a permanent `deploy/<date>-<n>` tag.** The script offers it at a terminal, after
  the owner's yes ([ADR 0007](../adr/0007-deploys-are-checked-against-the-repo.md)).
- **`deploy.py` copies only the paths it is given.** Each file gets a diff and a yes. The copy is
  backed up, atomic, and stopped if a job of hers is running. It deploys only `main` as pushed.
- **`SOUL.md`, the skills, the model and the fallback order need an eval run first.** `deploy.py`
  takes that run with `--eval-run`, as [AGENTS.md](../../AGENTS.md) requires.
- **`SOUL.md` is checked as the filled repo copy.** The owner's name comes from a local private values
  file, which is never committed.
- **Config and jobs are checked, never written.** The check compares a subset of `config.yaml` and
  the four jobs in `jobs.overrides.yaml`. `config.yaml`, `.env` and `jobs.json` are never copied, and
  the script prints the commands for the owner to run.
- **Skills are compared with the brain skills on the VPS,** file by file, not with the local clone.
  Tree modes are not checked, only owners.
- **Hooks stay owned by `agent`.** Her sandbox can't reach them. The accepted gap: a hook or config
  change shows only when the check runs, not on a schedule.
- **The eval does not block on drift.** It saves the check's output as `<run>.drift.txt`.
- **`hermes hooks doctor` runs on demand.** Each run posts one test alert to `#alerts`.

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
- A hook change: the owner re-approves it. A `config.yaml` change: the owner runs the `hermes config
  set` commands that the script prints.

## Docs to update

No doc is pending. Each step updated its docs in its own PR.

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
- **`check-drift.py`'s collector is a string.** The owner's rule is code in scripts, not strings
  (brain `taste.md`). Moving `COLLECT` into a file is its own PR.
- **ticket-bay-bot still links to `vps/host.md`,** in its `host.md` and `kill-switch.md`. The fix is
  in that repo. `vps/host.md` was merged into [vps/README.md](../../vps/README.md).
