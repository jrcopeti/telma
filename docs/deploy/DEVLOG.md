# Devlog: deploy

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/deploy-plan` | 1 | merged (#67) |
| `refactor/vps-flatten` | 2 | merged (#68) |
| `feat/drift-check` | 3 | in review |

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
