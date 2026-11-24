# Devlog: repo split

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/repo-split` | 1 | merged (#21) |
| `chore/remove-bot` | 4 | merged (#22) |
| `chore/add-guard-network` | Open | merged (#24) |
| `chore/sandbox-dockerfile-and-close-split` | Open | merged (#25) |

## 2026-11-19: plan

- Decisions made with the owner in one grilling session. They're in [PLAN.md](PLAN.md).
- Found before starting: #19 (step 6) was stacked on #18's branch and merged into it three seconds
  after #18 merged into `main`, so step 6 never reached `main`. #20 brought it over unchanged. Check a
  stacked PR's base before merging it.
- Count before the split: 14 relative links in `docs/hardening/` point at files that move
  (`vps/ticket-bay-bot/`, `vps/skills-sync/`, `vps/ticket-bay-app/`, `vps/shared/`).

## 2026-11-19: tag and bot repo (the owner said yes)

- `pre-split` tagged on `43a7b25` (#21's merge) and pushed.
- [jrcopeti/ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot) created, public. Import commit
  `b2a060d`. Of the 26 files, 17 match `pre-split` byte for byte, modes included. Changed:
  `memory-diff.sh` and its test (comments and the `Run:` path), the kill switch (links), the gitleaks
  title, and `tests.yml` (bot jobs only). New: `AGENTS.md`, `vps/host.md`, `docs/hardening/{PLAN,DEVLOG}.md`.
- Before the push, every test ran from the new tree, Docker egress included. gitleaks found nothing.
  CI is green on `b2a060d`: secret-scan and the 5 test jobs.
- Ruleset `main` copied from Telma's: no bypass, deletion and force push blocked, PR and `gitleaks`
  required.
- Gotcha: `tests.yml` jobs have blank lines inside them, so a split on blank lines dropped their
  steps. Split on job headers instead.

## 2026-11-19: Telma without the bot

- Removed `vps/ticket-bay-bot/`, `vps/skills-sync/` and `vps/ticket-bay-app/`. `vps/shared/` became
  `vps/telma/memory-diff.sh` and its test, with only the header comment and the `Run:` path changed.
  `tests.yml` keeps Telma's 3 jobs.
- 14 links in the hardening DEVLOG now point at `pre-split`, and each path exists at the tag. Every
  relative link in the repo still resolves.
- Hardening PLAN: a line at the top says it's frozen, and the one-repo decision is marked superseded.
- New `vps/host.md`. Its host-wide rules match the bot repo's word for word, with only the link targets
  differing. The kill switches link to each other.

## 2026-11-19: VPS checksum (read-only)

sha256 of 16 deployed files against the two repos, over SSH, nothing changed. 14 match byte for byte:
Telma's 4 (`sync-brain.sh`, `brain-files.py`, `tripwire-health.sh`,
`exfil-tripwire.py`), the bot's `pull-repos.sh` and `squid-denials.sh`, skills-sync's two scripts and
its cron file, the egress `compose.yaml` and `squid.conf`, and the app's `Dockerfile`, `.dockerignore`
and `compose.yaml` (`/opt/ticket-bay-app`). Both deployed `memory-diff.sh` copies are the `pre-split`
file. Each repo's copy differs from it in comment lines only. A redeploy is optional.

Found: six deployed scripts that no repo has ever held (Open in [PLAN.md](PLAN.md)).

Gotcha: in zsh, a loop variable named `path` overwrites `PATH`, and every command after it is "not found".

## 2026-11-19: guard-network.sh into the repo

- Added `vps/telma/guard-network.sh`, copied from `/home/agent/.hermes/agent-hooks/` byte for byte
  (mode 755). The owner: publish it despite the course kit's license. It is the kit's hook with 4 lines
  changed. Read first: it holds no secret, only patterns (`/opt/secrets`, `app-password`) it blocks.
- The bot's deployed copy is identical to this one; it gets its own PR in jrcopeti/ticket-bay-bot.
- `vps/host.md` now maps the file to its path on the VPS. No test yet: the hook needs a Hermes payload.

## 2026-11-19: second checksum, the split is done

Read-only over SSH, sha256 of every non-test file in both repos against the VPS. All match except
three, each explained: both `memory-diff.sh` copies (comment lines only, as before) and the bot's
`support-inbox` (the inbox address, kept out of the repo). Not deployed as files: the
`exfil-tripwire.hooks.yaml` snippet, which lives inside Hermes's `config.yaml`.

Found: each agent's sandbox `Dockerfile` (`~/sandbox/`) was in no repo. Not course-kit code, no
secret. Telma's is added here byte for byte; the bot's differs in one line (`AGENT_EMAIL` build arg)
and goes to its own repo. Every "Done when" condition now holds: CI green and the `main` ruleset on in
both repos, no dead relative link in either.
