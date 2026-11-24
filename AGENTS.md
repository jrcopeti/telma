# Telma

Showcase repo for Telma, a Hermes agent on a VPS that keeps its owner's brain. She shares the host
with ticket-bay-bot (jrcopeti/ticket-bay-bot) and nothing else; the repos are split along the same
trust boundary as the agents.

- **Start here:** `docs/rename/PLAN.md` (closing), `docs/showcase/PLAN.md` and `docs/evals/PLAN.md`
  (eval-v1 done; how to run the eval), each with the `DEVLOG.md` beside it. Keep them current.
  Finished work: `docs/hardening/` (frozen) and `docs/repo-split/`.
- **Running agents:** ask the owner before resuming, triggering (`hermes cron run`) or switching on
  any job, every time. After an interrupted command, check what partly ran before saying nothing
  ran: remote commands keep running.
- **Eval before a change:** before changing Telma's model or fallback order, `SOUL.md`, a brain
  skill, her toolsets or the Hermes version, run the eval (`docs/evals/PLAN.md`) with the owner's
  yes. A task that newly fails against the last full run (`evals/results/`) blocks the change.
  Tasks that already failed there don't block it, but say which ones still fail.
- **Hook setup, once per clone:** `git config core.hooksPath .githooks`. The pre-commit hook runs
  gitleaks on staged changes; CI runs it on the full history.
- **No secrets or personal data:** no keys, webhook URLs, inbox address, Discord IDs, IP addresses,
  private repo names.
- **Public prose** (README, threat model, ADRs, before/after): agents draft, the owner approves each
  doc in its PR.
- **Brain inbox:** recent Telma decisions not yet triaged are in `~/brain/inbox/`.
