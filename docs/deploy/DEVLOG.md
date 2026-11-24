# Devlog: deploy

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/deploy-plan` | 1 | merged (#67) |
| `refactor/vps-flatten` | 2 | merged (#68) |
| `feat/drift-check` | 3 | merged (#70) |
| `docs/deploy-step3-done` | 3 | in review |

## 2026-11-24: design

- Designed in a grill session from the showcase plan's Open item (a deployment check, its own plan)
  and ticket-bay-bot's brain intent (manifest, `check-drift.sh`, `deployed` tag). Neither repo had
  built it yet.
- The owner's calls are the Decisions in the plan. Added on the way: moving `vps/telma/` to `vps/`
  (PR 0), a deploy script (PR 2) and the eval hook-up (PR 3), so the plan grew from one PR to four.
- The check's output was trimmed twice on the owner's "overhead": no hiding of the `SOUL.md` hash
  (it's in every public eval result since 2026-11-20; the owner's name is only in the gitignored
  `evals/results/private/`), no `--diff`, no dedicated no-leak test.
- `jobs.overrides.yaml` kept for the schedules too, not only brain-triage's toolsets and skills,
  which were the security reason for it (owner).

## 2026-11-24: review of the plan

- /code-review found 11 things in the plan. Fixed in the text: the owner creates the tag (the
  check never writes one); a file missing at `deployed` reads `differs`; private values found
  through `git rev-parse --git-common-dir` so worktrees work; `TERMINAL_*` lines grepped by exact
  name; whether `config.yaml` holds channel IDs is checked in PR 1, not assumed; `install` to a
  temp name then `mv -f`, since `install` alone isn't atomic; backups in their own folder.
- The owner's calls on the rest: the tag moves only when every line is in sync (a partial deploy
  would otherwise show the undeployed files as `host ahead`); the `SOUL.md` hash stays, though it
  can confirm a guessed name, as the name is tied to the account; `deploy.sh` takes every yes
  first, then checks no job runs and copies all files at once, so a job never sees half a deploy.

## 2026-11-24: PR 0, `vps/telma/` to `vps/`

- `git mv` of everything in `vps/telma/`; nothing else in the files changed but the `Run:` lines of
  the five test scripts. They find their siblings through `dirname "$0"`, so the move needed no
  code change in them.
- Fixed: `tests.yml`, `evals/grade.py` (the tripwire path), `README.md`'s three rows, `host.md`'s
  links and file table, `kill-switch.md`'s link to `host.md`, and two links in the threat model.
- Frozen `docs/hardening/DEVLOG.md`: the 6 links only. `AGENTS.md` names this as its second
  exception.
- Left as written: `vps/telma` in devlogs (evals, showcase, repo-split), the repo-split and rename
  plans and `docs/evals/PLAN.md`'s done row 8, all history. The step's check now says so; it
  said "outside the frozen docs' prose", too narrow for the other finished docs.
- One link text in the hardening devlog showed the old path; changed with its link.
- Relative-link check over every tracked `.md`: 7 broken before the move and the same 7 after
  (brain-relative examples in the triage skill and lint-1 items, `…` placeholders).
- Outside this repo, `vps/telma/kill-switch.md` is named in ticket-bay-bot (two links, not one:
  `vps/host.md` and its own `kill-switch.md`; `host.md`'s rules are meant word for word in both)
  and in the brain's `projects/telma.md`. The bot's PR is opened beside this one and merged right
  after it: its links are 404 from one merge to the other.

## 2026-11-24: PR 1, the check

- `check-drift.py`, not `.sh`: the subset check parses YAML, the jobs read parses JSON and the
  collector has to run on the VPS and on a Mac (`stat -c` is GNU only), so it is Python throughout.
  The plan's mentions renamed; the devlog's left as written.
- One ssh call: a Python collector on stdin, sending back stat and sha256 per file, `config.yaml`'s
  text (parsed on the local machine, in memory; the VPS survey found no channel IDs in it), the four
  jobs' fields with the prompt as a hash, the overridden `TERMINAL_*` lines only, the three Hermes
  commits and the doctor's last line.
- Read from the VPS for the manifest: every file `agent:agent`; scripts and hooks `755` but
  `brain-files.py` `644`; `SOUL.md` and the Dockerfile `644`; `config.yaml` and `jobs.json` `600`.
  Finding for the owner, not fixed here: the three hooks are owned and writable by `agent`.
- `hermes hooks doctor` runs each hook on a test payload: the survey's run made cron-alert post a
  `test-session` alert. Kept in the check, alert accepted (owner). Gotcha captured in the brain inbox.
- `.env` values are compared the way Hermes writes them (`_quote_env_value`: double quotes and
  backslash escapes when the value holds a quote, `#` or space). The first live run read
  `TERMINAL_DOCKER_VOLUMES` as differing until then.
- Mutation check of the tests: the status table, the `.env` check, the stat check, the jobs fields
  and the lockstep each fail a test when broken. The host-side README skip didn't until the tree
  test put a `README.md` on the host.
- First live run: `summary: 17 of 17 in sync, hermes ok, hooks not ok, deployed none`. Hermes
  `ae2a81c` in all three places. Hooks: `guard-network.sh` and `exfil-tripwire.py` were modified on
  2026-11-19 after their approval; re-approving them is the owner's. The tag waits on that.
- /code-review found 10 things. Fixed on the owner's yes: symlinks on the host are reported as
  `link` and never followed (a linked folder in the skills was skipped, a dangling link crashed the
  run); a file only on the host reads `host only`, not `missing`, so a planted skill stands out
  (two rows added to the status table); any error that isn't drift exits 2, and invalid YAML is
  named by line, never printed; `.env` and job names are fetched for the tag's side too, so a
  removed key doesn't turn `repo ahead` into `both changed`; a tree line must end both paths in
  `/`; CI installs `python3-yaml`; no `git show` before the tag exists; `shlex.quote`. Left as is:
  `.env` values built the way Hermes writes them, not parsed the way it reads them (exact for
  today's keys, tested), and the ssh constants not shared with `evals/vps.py`.
- Adversarial test (a fresh agent, Opus): 8 breaking tests, kept as
  `vps/test_check_drift_adversarial.py`. Proved and fixed: a non-ASCII skill name never read in
  sync (git quotes names without `-z`); a symlinked folder above a file or a tree was followed and
  read in sync, now `link`; a bad YAML tag (`!!int`) printed the host value through `ValueError`.
  Its three reasoned findings, checked in Hermes's code at `ae2a81c` and fixed: a pause sets
  `enabled: false` and `no_agent` decides whether a job runs an agent, so `enabled`, `no_agent` and
  `deliver` are now checked; a job's skills are compared as Hermes reads them (`skills`, else the
  old single `skill`); skill discovery walks with `followlinks=True`, so a `README.md` or `LICENSE`
  link is reported, not skipped; an empty `DRIFT_HOST_ROOT` stops the check instead of using ssh.
  The empty-root test's assertion changed from "the first call isn't ssh" to "no call is ssh",
  since the check now stops before any call. Live run after: 17 of 17 in sync.

## 2026-11-24: step 3 done

- The owner re-approved `guard-network.sh` and `exfil-tripwire.py` (`hermes hooks revoke`, then
  `hermes chat --accept-hooks`, gateway restarted): their allowlist entries predated the
  2026-11-19 redeploy, though the files matched the repo.
- Clean run on main at `dcee608` (18:26 Berlin): `summary: 17 of 17 in sync, hermes ok, hooks ok,
  deployed none`. The owner tagged `dcee608` as `deployed` and pushed it.
- The hooks stay owned by `agent` (owner): her file and terminal tools run in the sandbox and
  can't reach them, and root-owned hooks would close little while `config.yaml`, which declares
  them, is hers. The gap that leaves (a hook or config change shows only when the check runs) is
  in the plan's Decisions.

## 2026-11-24: PR 2, the deploy script

- `deploy.py`, not `.sh`, as `check-drift.py` before it: it reuses the check's manifest reader,
  placeholder filling and status table (imported, not copied), and its host side runs as Python on
  the VPS and on a Mac. The plan's mentions renamed; the devlog's left as written. `install` and
  `mv -f` became `os.open(O_EXCL|O_NOFOLLOW)`, `fchown`, `fchmod`, `fsync` and `os.replace`.
- Two ssh calls as root: one reads each named file (stat, hash, bytes, for the diff; a symlink on
  its path is reported, never read through), one copies. Between them the owner answers every
  file. The copy re-checks each file's hash against the one diffed and stops if it changed, stages
  all files and their backups, then asks her cron ledger as `agent` whether a job runs, and only
  then swaps them all in. A stop before the swap removes what it staged.
- A running job, from Hermes's code at `ae2a81c`: `~/.hermes/cron/executions.db`, rows `claimed`
  or `running` (`cron/executions.py`). Read as `agent`, `mode=ro`. A read as root the first time
  made SQLite create `-shm` and `-wal` beside it; they came out `agent:agent`, as SQLite gives a
  root-made journal the database's owner, but `agent` is the safer reader. A wedged row (a crashed
  worker) would block every deploy until Hermes recovers it; the message names the job.
- Hooks and restarts, from the same code: a hook runs fresh each call, consent is per command, and
  only the doctor compares the script's mtime with its approval. So the hooks' `after` became
  `reapprove-hook` (plan's `after` bullet), and `deploy.py` prints the revoke, accept and restart.
- Only main as pushed is deployed (`HEAD` equals `origin/main` after a fetch), and nothing
  uncommitted in the manifest or the named paths.
- `--eval-run` takes a committed `evals/results/*.jsonl` whose run was made on a commit that has
  the file's last change. It can't prove more: the eval copies her live `SOUL.md`, so a run before
  a deploy tests the old one. In the plan's Open.
- The deploy history tag (owner, from the step's start): `deploy/<date>-<n>`, printed, never
  written. The number counts tags here and on origin (`git ls-remote`), not with `fetch --tags`,
  which fails on a local `deployed` that differs from origin's.
- The rule in `host.md`, "Scripts are deployed by hand", stays word for word: the bot's `host.md`
  has the same rule, and the owner still says yes to each file.
- Tests: `vps/test_deploy.py`, 19 against the fake host, a bare origin and a fake ledger, in CI
  beside the check's. One live `check-drift.py` run while wiring the tests, by mistake (meant to
  skip it): read-only, its doctor posted the known `test-session` alert.

## 2026-11-24: PR 2, adversarial review and the host code in files

- Adversarial test (a fresh agent, Opus): 10 breaking tests, kept as
  `vps/test_deploy_adversarial.py`, in CI. Fixed: the tag number filled a gap instead of going one
  past the highest; a failed `git ls-remote` was ignored (now the tag is named before the copy, and
  a failed read of origin's tags stops it); an uncommitted file under `vps/` that wasn't named made
  the re-check read in sync and printed a `deployed` move to a commit the host didn't match (now
  nothing uncommitted under `vps/`); "nothing copied" exited 0, not 2 as the docstring says.
- Its reasoned findings, fixed: a re-check that couldn't run exits 4, not 1 (drift); the config line
  prints its `restart-gateway`; a `.deploy-tmp` left by an interrupted deploy stops the copy and is
  named, never removed by root in her folder; `--eval-run` wants a hex commit; the tag's date and
  the backup's name are both UTC; the running-jobs read takes only its last line as JSON, so her
  login profile printing something isn't read as a job.
- Left open: the symlink race on a folder mid-copy (proved, kept as an expected failure, in the
  plan's Open for the owner); `--eval-run` accepts a run whose tasks failed (the plan's Open item on
  `SOUL.md` and the eval covers what it can prove).
- The owner's preference (brain `taste.md`): scripts in code, not strings. The host side moved from
  strings in `deploy.py` to `vps/remote/deploy_host.py` (read and copy, sharing the symlink and
  stat helpers) and `vps/remote/running_jobs.py` (run as `agent`, its code on stdin, so no Python
  quoted through `su`). `check-drift.py`'s `COLLECT` is still a string: merged code, its own PR.

## 2026-11-24: PR 2, second adversarial review

- A second fresh agent: 8 breaking tests, kept as `vps/test_deploy_adversarial2.py`, in CI. The
  owner's calls: gate the model, fallback and skills lines too; close the symlink race.
- Proved and fixed:
  - The backup folders were handed to `agent` before root wrote into them, so a link she planted
    there made root write anywhere. Now `deploy-backups/` must be root's and closed to others, and
    each run's folder is made by root inside it, `0700`.
  - The symlink race from the first round (a folder on the path swapped mid-copy), with the same
    change: every path is opened one folder at a time with `O_NOFOLLOW`, and the read, the backup,
    the temp file and the swap all work on the opened folder (`dir_fd`). The first round's
    expected failure now passes.
  - A folder at a host path read as `missing` and failed only at the swap, after other files were
    swapped. A path that isn't a plain file is now reported and not deployed.
  - An uncommitted edit to a committed eval run was read; the run is now read from `HEAD`.
  - The config and skills lines weren't gated by `--eval-run` (see the plan's deploy bullet).
  - A stop after the copy exited 2 and printed no tag; Ctrl-C during the copy or the re-check gave
    a traceback. After any copy the tag commands are printed (`finish()` never raises); Ctrl-C
    during the copy exits 3, during the re-check 4.
- Reasoned and fixed: every file is hashed again right before the swap; the host script's
  docstring names its real invocation.
- Reasoned, in the plan's Open: a job starting between the running-jobs check and the swap; two
  deploys in a day before the first tag exists (kept as an expected failure).
