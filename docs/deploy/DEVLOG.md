# Devlog: deploy

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/deploy-plan` | 1 | merged (#67) |
| `refactor/vps-flatten` | 2 | merged (#68) |
| `feat/drift-check` | 3 | merged (#70) |
| `docs/deploy-step3-done` | 3 | merged (#71) |
| `feat/deploy-script` | 4 | merged (#75) |
| `feat/eval-repo-soul` | 4 | merged (#76) |
| `docs/first-deploy` | 4 | merged (#77) |
| `feat/eval-drift-txt` | 5 | merged (#78) |
| `docs/deploy-step-6` | 6 | merged (#79) |
| `docs/deploy-close-adr` | close | merged (#80) |
| `docs/brain-skills-capture-copy` | after 8 | merged (#85) |
| `docs/vps-readme-deployed-move` | after 8 | merged (#86) |
| `docs/deploy-plan-layout` | plan | PR to open |

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
- Smoke run (owner's yes, `--only T1 -k 1`, $0.004): `<run>.drift.txt` written, the report line read
  "Drift when it started: 16 of 17 in sync, hermes ok, hooks ok, deployed c827547 (exit 1)", the one
  drift being `capture/SKILL.md` host ahead (the open proposal). The smoke run's results aren't committed.

## 2026-11-25: step 6, the bot's intent in the brain

- The brain's intent for ticket-bay-bot's sync now
  records what this repo built, for the bot's repo to copy: the `jobs` and `tree` modes, `check-drift.py`
  and `deploy.py` (the intent's own step 5, built here as step 4), the `deployed` tag's direction table and the owner
  placeholder. Its project note and the index line say the same. Written through the brain's own sync, no code.
- The showcase plan's Open item for the deployment check is struck through and links the deploy plan.
- Left for after this merges: mark the plan closed.

## 2026-11-25: closed

- #79 merged, so every step is done and the done-when holds: the check reports every line in sync
  bar the open `capture/SKILL.md` proposal, `deployed` is set, `deploy.py` has deployed end to end
  (`deploy/2026-11-25-1`), and each eval run writes `<run>.drift.txt`.
- The design is written up in `docs/adr/0007-deploys-are-checked-against-the-repo.md`, and the README
  has a Deploy section.

## 2026-11-25: second deploy, and the capture copy

- `deploy.py` shipped `vps/sync-brain.sh` (the failed-write fix from #82): backup
  `20261125T221341832Z`, tag `deploy/2026-11-25-2`. The check read 16 of 17, so `deployed` stayed on `c827547`.
- The 17th line was `capture/SKILL.md` reading host ahead. The host and the brain's `main` agreed
  (`37679bb0bc8f`); the repo copy was stale since brain PR #4 merged. The plan's rule (copy `vps/brain-skills/`
  after a skill change merges) had not been followed. A PR copied the brain's file over it. No eval: it
  changes what the repo records, not what runs.
- The jobs line's "1 other job(s), not checked" is by design: jobs outside the four named ones are counted, never named.

## 2026-11-25: `deployed` moved to `8188d34`

With the repo copy of `capture/SKILL.md` merged (#85), the check read 17 of 17 in sync, hermes and hooks `ok`.
`python3 vps/deploy.py --deployed` offered the move and the owner said yes; `deployed` is now on `8188d34`.
It was run from a separate terminal: the `!` prefix in an agent session isn't a terminal, so `deploy.py` refuses
it there. No `deploy/` tag came with it, since nothing was copied. `vps/README.md` explains the steps and the two tags, and now also holds what `vps/host.md` said (the users, where each file goes,
her settings, skills and jobs, the host rules); `host.md` is deleted and its links point at the README. The bot's repo still links to `vps/host.md` here.

## 2026-11-26: plan trimmed to instructions

The plan had grown into a log: decisions ran to paragraphs with their history, and the status cells of
steps 3 to 5 carried narrative. It is trimmed to the layout in the brain's guideline (goal, done when, decisions
in one line each, steps with a short description and a status, needs the owner, docs to update, open).
What it dropped is kept below: the full old text, verbatim, from `main` before the trim, including the
old decisions and the long status cells. Old entries above are left as written, as the devlog keeps them.

Open items: the eval gate's verdict and file-name matching, and the gap for toolsets and the Hermes
version, are now in the plan's Open. The job-start race, which the old decision accepted, is back in
Decisions. Two items the review named were closed in later rounds and are not open: the symlink race
on a folder mid-copy (the second adversarial round fixed it with `dir_fd`), and `in_sync` (the offer
comes right after the check, so it can't go stale).

### The plan before the trim

#### Deploy: know what is deployed on the VPS and keep it in sync with this repo

**Goal:** at any time know whether Telma's deployed files, config, jobs and skills match this repo,
and deploy a merged change with one script instead of copying by hand.

**Why:** files are copied by hand and nothing on the host reads the repo, so drift (the repo ahead,
or a hand edit on the host) only shows when someone diffs by hand. The rename's redeploy took an
evening and still missed four files. The eval's stamp covers only `SOUL.md` and `config.yaml`
hashes; the showcase plan called that too thin (owner, 2026-11-24).

**Status:** closed 2026-11-25. Every step below is done and the done-when is met. `capture/SKILL.md` read host ahead until the repo copy caught up with brain PR #4 (see the devlog).

**Done when:** `check-drift.py` reports every manifest line in sync and the hooks and Hermes lines
`ok`, the `deployed` tag is set, `deploy.py` has deployed at least one change end to end, and each
eval run writes the check's summary into its results.

##### Decisions (the owner, 2026-11-24, grill session)

- **Telma's own copy of the bot's design.** Same manifest format and statuses as ticket-bay-bot's design
  (an intent in the owner's brain: deploy manifest, drift check, `deployed` tag), but a separate script in each repo: they're split along the trust boundary, and neither is
  built yet. Whichever repo goes second copies the script and says so in its devlog.
- **`vps/telma/` becomes `vps/`.** Since the split, `vps/` holds only Telma's files; the bot's repo
  keeps one folder per host user and needs it. Host paths don't change.
- **`SOUL.md` is checked, not skipped.** The repo copy's placeholder becomes `{{OWNER_NAME}}`. The
  check fills it from `info/private-values` in `git rev-parse --git-common-dir`, so worktrees share
  it (`OWNER_NAME=…`, never tracked), and compares byte
  for byte. A missing file is an error before ssh, never a skip. This edits the repo copy only, so
  it isn't a SOUL change and needs no eval.
- **Config is a subset check.** Every key in `config.overrides.yaml` must equal the live
  `config.yaml`; other keys are Hermes's and ignored. The live file is parsed on the local machine,
  in memory only, if PR 1 finds it holds no channel IDs; if it does, it's parsed on the host and
  only the overridden keys come back. The `terminal:` keys are also checked against
  `~/.hermes/.env`'s matching `TERMINAL_*` lines, grepped by exact name (not the whole prefix) so
  no secret leaves the host.
- **Skills are compared with what she runs:** the VPS `~/brain/skills/`, file by file, `README.md`
  and `LICENSE` left out. A file on either side only is drift. Not the local machine's brain clone:
  it can be a sync-brain cycle off. Right after a brain skill PR merges, this shows host ahead until
  `vps/brain-skills/` is updated; that's real drift.
- **Jobs get a hand-written `jobs.overrides.yaml`.** The four jobs' schedule, script, skills and
  toolsets, as the `host.md` table says them today, plus whether each is enabled, runs an agent and
  where it delivers (PR 1: a chat's `cronjob` tool can pause a job, the threat model's case);
  `host.md` links to it instead. brain-triage's
  toolsets are the threat model's "no way out for unattended work", and a chat's `cronjob` tool can
  change them. `jobs.json` is read on the host by a short `python3` that prints only those four
  jobs' fields; other jobs (chat-made reminders, personal) are counted, never named. `jobs.json`
  itself is never copied into the repo.
- **ssh as the eval does:** `agents-vps` as root, `su - agent` for her files, read commands only. A
  forced-command key is in Open.
- **Owner, group and mode are checked** for every file (`stat -c '%U:%G %a'`); a change is drift.
  The manifest records what the VPS has when PR 1 starts; anything that looks wrong (a hook she can
  write) goes to the owner as a finding, not a fix in the same PR.
- **Direction comes from the `deployed` tag**, which marks the last commit known to match the host:

  | Host equals main | Host equals the file at `deployed` | Status |
  |---|---|---|
  | yes | – | in sync |
  | no | yes | repo ahead |
  | no | no, main equals `deployed` | host ahead |
  | no | no, main changed too | both changed |
  | file absent on the host | – | missing |
  | file only on the host (a tree) | – | host only |
  | a symlink on the host, or one in the folders above it, never followed | – | link |
  | no | file absent at `deployed` | differs |

  Until the tag exists, a difference is `differs`, no direction. The owner creates it after the first
  clean run; the check never writes a tag. Only the owner moves it, and only when
  every line is in sync (after a partial deploy it stays put, or the files not deployed would read
  `host ahead`); the devlog records the commit and the
  summary line.
- **Output: path, status, owner:group, mode, short hash.** No file contents and no `--diff`; look
  at a flagged file by hand. The `SOUL.md` hash is already public in every eval result, so it isn't
  hidden. It can confirm a guessed owner name (hash the repo copy with each guess); accepted, since
  the name is tied to the GitHub account anyway (owner).
- **`hermes hooks doctor` runs the hooks.** It calls each one with a test payload, so every check
  makes cron-alert post one alert to `#alerts`, session `test-session`, action `?`. Kept: the alert
  says where it came from, and the check runs only on demand, after a deploy and before an eval
  (owner, 2026-11-24, PR 1). The ssh is otherwise read-only: files are read as root, only the
  doctor runs as `agent`.
- **The hooks stay owned by `agent`.** Her file and terminal tools run in the sandbox and can't
  reach `~/.hermes/agent-hooks/`, so they are safe from her (owner, 2026-11-24). Accepted with it: a
  change to a hook or to `config.yaml` by something else running as `agent` on the host shows only
  when this check runs, never on a schedule (`memory-diff` watches `memories` and `skills` only).
- **A tree's mode isn't checked, only its owner.** The skills' modes come from git through
  sync-brain (`644`, `664`, `755` and `775` on the VPS today), not from a deploy (PR 1).
- **Host state too:** the Hermes commit of both installs and `/opt/hermes-guard` (the lockstep
  rule), and `hermes hooks doctor`. One line each, `ok` or what's wrong. Not systemd units: her jobs
  are Hermes cron, and the units are the installer's.
- **Run from the local machine only.** Never in CI (it would need an ssh key to the VPS), never as
  a job of hers (she must not check her own controls). Run on demand, at the end of `deploy.py`,
  and at the start of each eval run.
- **`deploy.py` copies only what it's told.** Paths named on the command line, never "everything
  ahead". It shows each diff and takes a yes per file, copying
  nothing until all are answered, keeps a backup in
  `~/.hermes/deploy-backups/<timestamp>/` (not beside the live file, where a hook loader or a
  `tree` folder would see it; root's, `0700`, so she can't plant a link root would write through), writes each file to a temp name in the target's folder with its
  owner and mode set first and swaps it over the target atomically (`os.replace`, the step's
  `install -o -g -m` and `mv -f` in Python), then runs the whole check. It doesn't write `config.yaml`, `.env` or `jobs.json` (it prints the
  `hermes config set` commands or the job change), and skills go through a brain PR and sync-brain.
  `SOUL.md`, the skills and the model or fallback keys need `--eval-run <results .jsonl>`, per
  `AGENTS.md`: without it the skills line stops and the config line leaves out the `model` and
  `fallback_providers` commands. The run is read from `HEAD`, never the working tree. Every host
  path is opened one folder at a time without following a symlink, and every later step works on
  the folder opened, so a link planted or swapped in mid-copy is never written through (her folders
  are hers; the copy runs as root). A path that isn't a plain file is not deployed. Right before the copy it checks no job of hers is running (it
  stops, copying nothing, if one is), then copies all the files in one quick step, so no job sees
  half the new files and half the old. A job that starts in the moment between that check and the
  swap is accepted (owner, 2026-11-24): closing it would mean holding Hermes's scheduler lock, tied
  to a Hermes internal and still open to a job fired by hand or by her cron tool. It only prints what each file still needs
  after (`after` below); it never restarts, rebuilds or runs a job. It deploys only main as pushed,
  with nothing uncommitted under `vps/`: the re-check reads the checkout, so an uncommitted file
  there could read in sync and move `deployed` to a commit the host doesn't match.
- **Each deploy gets a permanent tag** (owner, 2026-11-24, step 4). `deployed` moves, so it keeps no
  history; the devlog records each move only while this plan is open; the backups on the host don't
  name a commit. So `deploy.py` ends by offering an annotated tag, `deploy/<date>-<n>` (the UTC date,
  as in the backup folder's name; `n` one past the highest on that day, here or on origin, and no
  copy when origin's tags can't be read), on the deployed commit, whose message holds the files, the
  backup folder and the check's summary line after the copy. `git tag -l 'deploy/*' -n20` lists
  every deploy. It lives in the repo, where she can't write; a tag push isn't a merge, so no PR per
  deploy; it outlasts this plan. Only the owner moves tags (AGENTS.md rule, unchanged): the script
  runs only at a terminal (a pipe, `yes |` or an agent's shell stops it before anything), and makes
  and pushes the tag only after the owner's own yes at the keyboard; no, q, end of input or a
  refused push print the commands to run by hand, each step on its own, and nothing is stored
  between runs. The tag is numbered again just before it is offered, since the deploy can take long. The same for
  `deployed`, offered only when that run's re-check was in sync, and only forward: onto a descendant
  of where origin has it, and the push leases that place, so a move made meanwhile isn't overwritten.
  Otherwise it stays, per the rule above, until `deploy.py --deployed` re-checks and finds it in
  sync (after a hook's re-approval, say). A copy that may not have run (exit 3) is offered no tag:
  the owner looks at the check and tags by hand if files landed.
- **The eval doesn't block on drift.** It writes the check's summary to `drift.txt` in its results,
  in place of today's hash stamp: a run is sometimes meant to test an undeployed change.

##### The manifest

`vps/deploy.manifest`, plain text, one line per file, whitespace-separated, read by `while read`:

```
# repo path          host path                      mode      owner:group  perm  after
vps/sync-brain.sh    /home/agent/.hermes/scripts/…  exact     …            …     none
vps/hermes/SOUL.md   /home/agent/.hermes/SOUL.md    redacted  …            …     new-chat
```

- **Modes:** `exact` (byte for byte), `redacted` (placeholders filled first), `subset` (config
  keys), `jobs` (`jobs.overrides.yaml` and the triage prompt against `jobs.json`), `tree` (a folder,
  file by file). `jobs` and `tree` are new to the bot's design; its brain intent gets them too.
- **`after`:** `none`, `restart-gateway`, `new-chat`, `rebuild-sandbox` or `reapprove-hook`.
  Hermes (`ae2a81c`, `agent/shell_hooks.py`) spawns a hook script fresh on every call, so a new hook
  runs without a restart. Consent is per event and command, not per file, but the doctor compares
  the script's mtime with the one recorded at approval, so after a deploy the check reads `hooks not
  ok` until the hook is re-approved: `hermes hooks revoke '<command>'` (the gateway drops the hook
  within about 30 seconds), `hermes chat --accept-hooks`, a gateway restart, back to back. The three
  hooks' lines say `reapprove-hook`, and `deploy.py` prints those three commands for each.

##### Steps

| # | Step | Check | Status |
|---|---|---|---|
| 1 | **This plan.** | The owner merges it | done (#67) |
| 2 | **PR 0: move `vps/telma/` to `vps/`.** `git mv`; fix CI, `evals/grade.py`, the test scripts' "Run:" lines and the live docs. In the frozen docs fix only the 6 broken links, prose left as history; `AGENTS.md` names this second exception. Then a PR in ticket-bay-bot for its two links to `kill-switch.md` (`vps/host.md` and its own `kill-switch.md`), merged right after this one, and the brain's `projects/telma.md`. Nothing deployed changes. | CI green; no `vps/telma` left outside history prose (devlogs, finished plans and rows) | done (#68) |
| 3 | **PR 1: the check.** `{{OWNER_NAME}}` in `SOUL.md` (and `host.md`); `jobs.overrides.yaml`; `deploy.manifest` with owners and modes read from the VPS; `check-drift.py` with the five modes, the statuses and the host-state lines; tests against a fake host folder (`DRIFT_HOST_ROOT`) covering the status table. First run against the VPS, the `deployed` tag set by the owner. | Every line in sync, hooks and Hermes `ok`, the tag on main | done (#70), after the owner re-approved two hooks; `deployed` on `dcee608` |
| 4 | **PR 2: `deploy.py`.** As decided above, with the `deploy/<date>-<n>` tag. First real use: whatever the check shows repo ahead. | A deploy whose re-check comes back in sync; its `deploy/` tag pushed and `deployed` moved by `deploy.py` | done (#75, #76); first real deploy 2026-11-25: `deploy/2026-11-25-1`, `deployed` on `c827547` |
| 5 | **PR 3: the eval writes `drift.txt`.** Replaces the hash stamp in `eval_profile.py` and the report line. Changes the eval harness, not her setup, so no eval run is needed to merge it. | A run's results has `<run>.drift.txt`, and the report quotes its summary | done (#78); smoke run `--only T1 -k 1` on 2026-11-25 wrote `<run>.drift.txt` (16 of 17 in sync, `capture/SKILL.md` host ahead: the open proposal) and the report quoted it |
| 6 | **Bot's intent in the brain:** the `jobs` and `tree` modes and the copied script. Point the showcase plan's Open item here. | The brain's intent for ticket-bay-bot's sync records the two modes, `deploy.py` and the copied script; the showcase Open item links this plan | done 2026-11-25: brain intent and project note updated through the brain's sync; showcase Open item points here |

##### Open

- ~~How a `SOUL.md` change is evaluated before it is deployed.~~ **Done 2026-11-25:** `run.py
  --repo-soul` makes the eval profile use the repo's filled `SOUL.md`, and `deploy.py --eval-run`
  requires the run's `eval_soul_sha` and `repo_soul_sha` to equal the hash of the file it is about
  to write (`docs/evals/PLAN.md`). Still open: the run isn't tied to the model, skills or config
  being unchanged since; those come from the host as before.

- A forced-command ssh key (`command=…,restrict` in root's `authorized_keys`) that can only run a
  read-only script, instead of root. It guards against a stolen local-machine key, which today
  gives root through `agents-vps` anyway.
- Which of `config.yaml` and `.env` Hermes reads when their `terminal:` values differ (from
  `host.md`, now `vps/README.md`). The check catches them differing; it doesn't say which one wins. Hermes's code at
  `ae2a81c` (`apply_terminal_config_to_env`) says `config.yaml` wins for the keys set in its
  `terminal:` section; untested.

## 2026-11-27: `--skip-eval`

The owner chose to deploy the repo's `SOUL.md` (hardening step 12) without the eval, and `deploy.py`
had no way to say so. Added `--skip-eval`: for `SOUL.md` only, an alternative to `--eval-run`,
refused with `--deployed`. It takes no reason, because a typed one would go into the deploy's tag
and so into a public repo; the tag says only "eval skipped by the owner". The skills and the model
keys stay gated. The tag holds the waiver only when a gated file was in the deploy. Code review's seven
findings were all fixed in the same PR.
