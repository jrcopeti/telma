# Devlog: deploy

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/deploy-plan` | 1 | in review |
| `refactor/vps-flatten` | 2 | in review |

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
