# Telma

Showcase repo for Telma, a Hermes agent on a VPS that keeps its owner's brain. She shares the host
with ticket-bay-bot (jrcopeti/ticket-bay-bot) and nothing else; the repos are split along the same
trust boundary as the agents.

- **Start here:** `docs/rename/PLAN.md` (closing), `docs/showcase/PLAN.md` and `docs/evals/PLAN.md`
  (eval-v1 done; how to run the eval), `docs/deploy/PLAN.md` (the drift check and deploy script),
  each with the `DEVLOG.md` beside it. Keep them current.
  `docs/hardening/PLAN.md` is reopened for steps 7 to 14 (brain rule files, hourly triage, temp files and `index.md` merges);
  steps 0 to 6 are done and trimmed to instructions (full text in its `DEVLOG.md`); change them only for a rename or a fixed link. Finished work: `docs/repo-split/`.
- **Running agents:** ask the owner before resuming, triggering (`hermes cron run`) or switching on
  any job, every time. After an interrupted command, check what partly ran before saying nothing
  ran: remote commands keep running.
- **Eval before a change:** before changing Telma's model or fallback order, `SOUL.md`, a brain
  skill, her toolsets or the Hermes version, run the eval (`docs/evals/PLAN.md`; `--repo-soul` for `SOUL.md`) with the owner's
  yes. A task that newly fails against the last full run (`evals/results/`) blocks the change.
  Tasks that already failed there don't block it, but say which ones still fail.
- **Hook setup, once per clone:** `git config core.hooksPath .githooks`. The pre-commit hook runs
  gitleaks on staged changes; CI runs it on the full history.
- **No secrets or personal data:** no keys, webhook URLs, inbox address, Discord IDs, IP addresses,
  private repo names.
- **Public prose** (README, threat model, ADRs, before/after): agents draft, the owner approves each
  doc in its PR.
- **Brain inbox:** recent Telma decisions not yet triaged are in `~/brain/inbox/`.
