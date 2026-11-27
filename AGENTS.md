# Telma

Showcase repo for Telma, a Hermes agent on a VPS that keeps its owner's brain. She shares the host
with ticket-bay-bot (jrcopeti/ticket-bay-bot) and nothing else; the repos are split along the same
trust boundary as the agents.

- **Start here:** `docs/rename/PLAN.md` (closing), `docs/showcase/PLAN.md` and `docs/evals/PLAN.md`
  (eval-v1 done; how to run the eval), `docs/deploy/PLAN.md` (the drift check and deploy script),
  each with the `DEVLOG.md` beside it. Keep them current.
  `docs/hardening/` closes when `SOUL.md` is live (steps 0 to 16 are done; `SOUL.md`'s eval and deploy are owed);
  change its PLAN only for a rename or a fixed link.
  Finished work: `docs/repo-split/`.
- **Running agents:** ask the owner before resuming, triggering (`hermes cron run`) or switching on
  any job, every time. After an interrupted command, check what partly ran before saying nothing
  ran: remote commands keep running.
- **Eval before a change:** before changing Telma's model or fallback order, `SOUL.md`, a brain
  skill, her toolsets or the Hermes version, run the eval (`docs/evals/PLAN.md`; `--repo-soul` for `SOUL.md`) with the owner's
  yes. A task that newly fails against the last full run (`evals/results/`) blocks the change.
  Tasks that already failed there don't block it, but say which ones still fail. The owner can waive
  the eval for one `SOUL.md` deploy with `deploy.py --skip-eval` (`docs/deploy/PLAN.md`);
  only the owner decides that, and nothing else is waivable.
- **Hermes docs:** Context7 library `/nousresearch/hermes-agent` (architecture: `/cclank/hermes-wiki`).
  The running source on the VPS wins when they differ.
- **Hook setup, once per clone:** `git config core.hooksPath .githooks`. The pre-commit hook runs
  gitleaks on staged changes; CI runs it on the full history.
- **No secrets or personal data:** no keys, webhook URLs, inbox address, Discord IDs, IP addresses,
  private repo names.
- **Brain inbox:** recent Telma decisions not yet triaged are in `~/brain/inbox/`.
