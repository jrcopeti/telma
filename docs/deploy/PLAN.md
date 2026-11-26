# Deploy: know what is deployed on the VPS and keep it in sync with this repo

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

## Decisions (the owner, 2026-11-24, grill session)

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
  when this check runs, never on a schedule (`memory-diff` watches `memories`, `skills` and the brain's `skills` only).
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

## The manifest

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

## Steps

| # | Step | Check | Status |
|---|---|---|---|
| 1 | **This plan.** | The owner merges it | done (#67) |
| 2 | **PR 0: move `vps/telma/` to `vps/`.** `git mv`; fix CI, `evals/grade.py`, the test scripts' "Run:" lines and the live docs. In the frozen docs fix only the 6 broken links, prose left as history; `AGENTS.md` names this second exception. Then a PR in ticket-bay-bot for its two links to `kill-switch.md` (`vps/host.md` and its own `kill-switch.md`), merged right after this one, and the brain's `projects/telma.md`. Nothing deployed changes. | CI green; no `vps/telma` left outside history prose (devlogs, finished plans and rows) | done (#68) |
| 3 | **PR 1: the check.** `{{OWNER_NAME}}` in `SOUL.md` (and `host.md`); `jobs.overrides.yaml`; `deploy.manifest` with owners and modes read from the VPS; `check-drift.py` with the five modes, the statuses and the host-state lines; tests against a fake host folder (`DRIFT_HOST_ROOT`) covering the status table. First run against the VPS, the `deployed` tag set by the owner. | Every line in sync, hooks and Hermes `ok`, the tag on main | done (#70), after the owner re-approved two hooks; `deployed` on `dcee608` |
| 4 | **PR 2: `deploy.py`.** As decided above, with the `deploy/<date>-<n>` tag. First real use: whatever the check shows repo ahead. | A deploy whose re-check comes back in sync; its `deploy/` tag pushed and `deployed` moved by `deploy.py` | done (#75, #76); first real deploy 2026-11-25: `deploy/2026-11-25-1`, `deployed` on `c827547` |
| 5 | **PR 3: the eval writes `drift.txt`.** Replaces the hash stamp in `eval_profile.py` and the report line. Changes the eval harness, not her setup, so no eval run is needed to merge it. | A run's results has `<run>.drift.txt`, and the report quotes its summary | done (#78); smoke run `--only T1 -k 1` on 2026-11-25 wrote `<run>.drift.txt` (16 of 17 in sync, `capture/SKILL.md` host ahead: the open proposal) and the report quoted it |
| 6 | **Bot's intent in the brain:** the `jobs` and `tree` modes and the copied script. Point the showcase plan's Open item here. | The brain's intent for ticket-bay-bot's sync records the two modes, `deploy.py` and the copied script; the showcase Open item links this plan | done 2026-11-25: brain intent and project note updated through the brain's sync; showcase Open item points here |

## Open

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
