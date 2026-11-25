# vps/: what runs on Telma's host, and how it gets there

This folder holds the copy of every file Telma's host runs: the scripts, her `SOUL.md`, the hooks, the
sandbox Dockerfile, the settings we pin and her brain skills. The host never reads this repo. A file
reaches the host only when someone copies it, so two tools here keep the two sides honest:

- `check-drift.py` compares the host with this repo and changes nothing.
- `deploy.py` copies named files to the host, then runs the check again.

Both run from the owner's machine. Neither runs in CI, and Telma never runs them: she must not check
her own controls. The design and the reasons are in `docs/deploy/PLAN.md`; the history is in
`docs/deploy/DEVLOG.md`.

## What gets compared

`deploy.manifest` lists every file with its path in this repo, its path on the host, how to compare it,
and its owner, group and mode. Most files are compared byte for byte. Four are special:

- `SOUL.md` has a placeholder for the owner's name. The check fills it in from a private,
  untracked file in the local clone's git directory, so the name never reaches the repo.
- `config.overrides.yaml` lists only the settings we pin. Each must match the live `config.yaml`;
  everything else in that file belongs to Hermes and is ignored.
- `jobs.overrides.yaml` describes the four scheduled jobs (schedule, script, skills, toolsets, whether
  each is on). The check reads only those jobs from the host. Any other job is counted, never named,
  which is why the check prints "1 other job(s), not checked".
- `brain-skills/` is compared with the skills Telma runs, file by file.

## Reading the check

Run `python3 vps/check-drift.py`. It prints one line per file, then two lines about the host itself:
whether both Hermes installs are on the same commit, and whether `hermes hooks doctor` is happy.
The last line is a summary such as `17 of 17 in sync, hermes ok, hooks ok, deployed 8188d34`.

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
hooks once. That is expected.

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
   restart, a new chat, a sandbox rebuild, or re-approving a hook.
9. It offers the two tags described below. Answer yes only after the check reads in sync.

`SOUL.md`, brain skills and the model keys also need `--eval-run <results .jsonl>`, pointing at the
eval run that passed. Without it the deploy stops on those files.

`deploy.py` does not write `config.yaml`, `.env` or `jobs.json`. For those it prints the
`hermes config set` commands or the job change to make by hand.

Brain skills do not go through `deploy.py`. They change through a PR in the brain repo; once it is
merged, the host's sync job pulls it. Then copy the merged file into `vps/brain-skills/` through a PR
here, so the repo matches what she runs. Skipping that last step is what makes the check read "host
ahead" for a skill.

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
