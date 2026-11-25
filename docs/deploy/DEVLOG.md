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

## 2026-11-24: PR 2, `tag-deploy.py`

- The owner's answers to the second round's open items: a script for the tag commands, and the job
  window between the running-jobs check and the swap accepted (plan's deploy bullet).
- `deploy.py` leaves each deploy's tag in `<common git dir>/deploy-pending/<tag>.json` instead of
  printing commands to copy (it prints them only if it can't write the file). `next_tag` counts
  these, so two deploys before tagging get `-1` and `-2`: the second round's expected failure
  passes now.
- `vps/tag-deploy.py`, run by the owner: each pending tag after a yes, oldest first, made and
  pushed, its file removed. A tag that exists already is left pending, to look at by hand.
  `deployed` moves with the newest only when its re-check was in sync and nothing was skipped;
  `--deployed` runs check-drift now (its doctor alert included) and moves `deployed` to HEAD if it
  exits 0, for a hook moved in sync by its re-approval. "Only the owner moves tags" holds: the
  owner runs it and answers each yes.
- Tests: `vps/test_tag_deploy.py`, 5, against the bare origin; 71 across the six suites, in CI.

## 2026-11-25: PR 2, third adversarial review (`tag-deploy.py`)

- A third fresh agent: 17 tests, kept as `vps/test_deploy_adversarial3.py`, in CI. Proved and
  fixed: `deployed` could move backwards (an older pending deploy tagged after `--deployed` had
  moved it forward; now only onto a descendant of origin's); a corrupt pending file crashed
  `tag-deploy.py` with exit 1 and blocked `deploy.py` unnamed (now a stop naming the file, exit 2);
  a pending tag outside `deploy/<day>-<n>`, or an option-shaped one, was created and pushed (the
  name, the 40-digit commit and the message are validated when read).
- Reasoned, fixed: a tag made here but not pushed was stuck "already exists" forever (now pushed
  on the next run; one already on origin at that commit clears its pending file); a pending commit
  not on `origin/main` was tagged (now left pending, named); two deploys at once could overwrite a
  pending file (`write_pending` creates it exclusively and takes the next number); q or end of
  input at the last question exited 2 after the tags were pushed (now 1; `Quit` is not a stop).
- Left, in the plan's Open: `in_sync` is the deploy's own re-check, not a fresh one. The test that
  shows it stays as an expected failure.

## 2026-11-25: PR 2, the smoke test

- `vps/smoke-deploy.py`: runs the real `remote/deploy_host.py` and `running_jobs.py` the way a deploy
  does, against a scratch folder (`/var/tmp/deploy-smoke-<time>`) and a copy of her cron ledger
  made as `agent` through `su` (the original opened read-only, the copy mode `0600`). Checks the
  read, a copy (new bytes, owner `agent:agent`, mode, the old file backed up, no temp file left),
  a running job refused with exit 5, a symlinked folder reported and the copy refused with exit 4,
  and removes the folder. It reads no live file but the ledger, writes none, runs no job.
  `--local` rehearses it on this machine. It covers what the fake host can't: the ssh and `su`
  quoting, her login profile, the real owner change, `dir_fd` on the VPS's Linux.
- Not covered, left to the first real deploy: a real file, the hooks' re-approval, a gateway
  restart.

## 2026-11-25: PR 2, the tag script cut

- The owner asked whether `tag-deploy.py` was overhead (they'd expected the two commands behind a
  script). It was: the pending files in `.git/`, their validation, the resume logic and the
  numbering that counted them were a design of mine, and the third adversarial round's findings
  were nearly all about them. Cut: `tag-deploy.py`, the pending store and `test_tag_deploy.py` and
  `test_deploy_adversarial3.py` are gone.
- Now `deploy.py` ends by asking, each with the owner's own yes at the keyboard: create and push
  `deploy/<day>-<n>`; move `deployed` (only when this run's re-check was in sync, and only forward,
  one `merge-base` check against origin's). No, q, end of input or a failure print the commands.
  Nothing is stored between runs, so a tag the owner declined is just offered again next time at
  the same number. `deploy.py --deployed` re-checks and offers `deployed` alone (the hook
  re-approval case). Kept from round 3: the forward-only rule; the stale-`in_sync` finding no longer
  exists, since the offer comes right after the check.
- The smoke test is untouched: it covers the host side only.

## 2026-11-25: PR 2, fourth adversarial review

- A fourth fresh agent, on the cut and the new smoke test: 16 tests, kept as
  `vps/test_deploy_adversarial3.py`, in CI (the earlier file of that name, for the pending files,
  went with them). The suites now answer through a pseudo-terminal (`DeployFake.terminal`).
- Proved and fixed: a piped stdin (an agent's shell, `yes |`) could create the tag and move
  `deployed`, so the owner's yes at the keyboard wasn't enforced: `deploy.py` now stops before
  anything unless stdin is a terminal; a refused tag push skipped the `deployed` offer, and the
  by-hand list always repeated the tag commands: each step now has its own offer and its own
  commands; a tag name taken on origin during the run left a stale local tag and dead commands: the
  tag is numbered again just before the offer, and a refused push removes the local tag.
- Reasoned, fixed: no tag is offered for a copy that may not have run (exit 3); the `deployed`
  push leases origin's value (the raw ref, which for an annotated tag isn't the commit); `--deployed`
  brings this clone's `deployed` to origin's when it is on the commit already (the check reads it);
  `--deployed` exits 2 when the check couldn't run; abbreviations are off and `--deployed` with
  `--eval-run` is refused.
- The smoke test's host side: `setup` makes the scratch folder itself, so a name that exists is not
  trusted (a link in a pre-made `/var/tmp/deploy-smoke-*` made root chmod outside it); `a.sh` is
  made and chowned before its folder is handed to `agent`, with no ownership change through a
  link; `cleanup` removes only a real `deploy-smoke-*` folder that its own user owns (the parent
  compare checked nothing). A stale-`was` case was added to the smoke test: removing the
  "changed since its diff" check stayed green before.
- Left: the local smoke rehearsal can't tell a missing `fchown` (the local user owns everything);
  the run on the VPS covers it.

- First run of the smoke test on the VPS (2026-11-25): all checks passed, nothing left behind. It
  pre-made the scratch backups folder, so the copy's own creation of it was unchecked; the owner
  made the real `~/.hermes/deploy-backups` by hand (`root:root`, `700`) believing it was needed
  (the copy creates it when missing). The smoke test now leaves it to the copy and checks it comes
  out root's and closed; second run on the VPS passed, 12 checks.

- CI caught what this machine hid: the Linux python writes `__pycache__` beside the source, so
  importing `check-drift.py` left an untracked `vps/__pycache__` and the clean-tree rule refused
  every deploy (40 failures). This machine's python keeps bytecode elsewhere, and a global
  gitignore hid it from `git status`. `deploy.py` no longer writes bytecode, the repo ignores
  `__pycache__/` and `*.pyc`, and a test runs the deploy with bytecode in-tree (it fails without
  the fix). A real deploy on a machine without such a global ignore would have hit it too.
- The second CI run found the backup folder's name, to the second, collided when two deploys of the
  test ran within one second. It now goes to the millisecond (the copy still stops if the folder exists).

- Closed the `SOUL.md` gap (2026-11-25). The eval copied her live `SOUL.md`, so a run never tested the
  text about to ship, and `--eval-run` only checked the run's commit had the change. `run.py
  --repo-soul` now copies the repo's file at `HEAD`, filled by `check-drift.py`'s new `filled()`
  (shared with `deploy.py`), over hers in the eval profile; the stamp says `soul_source: repo` and
  the hash. `deploy.py` takes the run for `SOUL.md` only if `soul_source` is repo and the eval
  copy's hash equals the file to write, so a run of another text, of her live one, or of an old
  stamp is refused. The gate now runs after the file is filled, which moved it after the origin tag read.
- Adversarial round on the `--repo-soul` change (2026-11-25), no forged stamp got past the gate. Fixed:
  an empty repo `SOUL.md` was not copied (a truthiness test) yet stamped as the repo's; the run now
  stops right after the stamp if the eval copy isn't the repo's hash, before any paid trial; bad
  UTF-8 exits cleanly; `deploy.py` refuses a results file holding rows of more than one setup (two
  runs in the same minute and commit share a file). Left as before: the gate doesn't read the run's
  verdict or whether it was partial (the owner reads the report), and the gate is by the repo file's
  name, not the host path.

## 2026-11-25: first real deploy

`deploy.py` shipped hardening step 8 (`vps/sync-brain.sh`, `vps/brain-files.py`), the first use outside
the smoke test. No eval: neither file touches the model, `SOUL.md`, a skill, her toolsets or Hermes.
The by-hand skill overwrite below needed no eval either: it only put GitHub's reviewed `capture/SKILL.md`
over her copy (the owner said yes), and the restore put back text that never ran from `main`.

- Before: `check-drift.py` showed 14 of 17 in sync, the two scripts repo ahead and `capture/SKILL.md`
  host ahead (a curator edit sync-brain refuses). The skill went first, by hand and not through
  `deploy.py`: her edit was copied to root's home, GitHub's version written over hers as `agent:agent`
  `664`, and the check read 15 of 17.
- The run: a diff and a yes per file, one copy, the backup in
  `~/.hermes/deploy-backups/20261125T165748367Z/`, then the check at 17 of 17, hermes and hooks `ok`.
  The owner answered yes to `deploy/2026-11-25-1` and to moving `deployed`; both are on origin, on
  `c827547`, and a later check reads in sync against the moved tag.
- Nothing needed fixing. It ran from the owner's terminal with `! python3 vps/deploy.py <paths>`; an
  agent's shell is refused, as designed, so an agent can only prepare, check and verify afterwards.
- Afterwards her edit was put back from the root copy, to give step 8 a real proposal to open. Until
  that PR is merged or its branch deleted, the check reads `capture/SKILL.md` as host ahead; that is
  the check working, not drift to fix.

## 2026-11-25: step 5, the eval writes `drift.txt`

- `run.py` runs `vps/check-drift.py` at the start (`eval_profile.drift_report()`) and saves its output
  and exit code as `<run>.drift.txt` beside the `.jsonl` and `.md`, in `results/` and `results/private/`.
  The results are flat files, not a folder per run, so the plan's "results folder has `drift.txt`" became a file
  named for the run. A check that fails, hangs or can't start is written down, never a stop. Like any
  check it posts one `test-session` alert from cron-alert.
- `report.py` quotes the summary line and exit code, and the `.drift.txt` name. The Setup line and the
  stamp lose the config hashes (the eval's config is hers rewritten, so they never matched).
- The SOUL.md mismatch rule is one rule: the eval copy must equal what the run meant to test, hers or, with
  `--repo-soul`, the repo's. It moved to `run.py` (`soul_copy_problem`), so a bad copy stops before any
  paid trial for both sources; the report still flags older runs' stamps by the same rule.
- Adversarial round (6 proved, 4 reasoned): the file is public, and a failed check's stderr names the host's
  address or a local path, so only stdout is kept (`exit 2` alone when the check can't run). Non-UTF8 output
  and a non-UTF8 file no longer stop the run or its report; an empty file isn't quoted as a summary; the
  dropped config hashes don't show as a "Setup changed" against older runs. Tests: `test_drift_regressions.py`.
  Accepted: two runs in the same minute and commit share a name, so the second's drift file replaces the
  first's (the results file already has that limit); the owner takes the `<run>.drift.txt` name over `drift.txt`.
- Code review (7 findings, all fixed with the owner's yes): the file also drops the host's own text on the
  `hermes` and `hooks` lines (only ok or not); the stamp's two hashes are read by name, so a missing file no
  longer shifts one into the other; the drift write can't stop a run; the report parses `exit N` and no longer
  doubles "summary:"; the check's timeout is 120 s.
- Not done: the smoke run.
