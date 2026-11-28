# Devlog: setup

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/setup-plan` | 1 | PR to open |

## 2026-11-27: design

- Designed in a grill session, from the README's Quick Start promise of a `SETUP.md` and the course
  kit's module 8 guide as the template. The owner's calls are the Decisions in the plan.
- The owner first ran Telma in a Lima VM on the local machine, so a local target was added beside
  the VPS: Lima on a Mac, and a Linux box.
- An existing brain was narrowed to one made from `brain-template`, because Telma's skills, sandbox
  mounts and sync-brain all depend on its layout. That gave `check-brain.py`.
- `deploy.py` pushes `deploy/<date>-<n>` tags to `origin`, so a plain clone can't update: the fork
  became the default.
- The owner chose the VPS over a new Lima VM for the acceptance run. The real Telma already is
  `agent` there, so the user became a Step 0 value (`{{HOME}}`), and the timezone joined it.
- Prices were dropped from the guide on the owner's call: they depend on the model and change.
- `/code-review` on the first draft found `/home/agent` in 22 files, not two, and the `agent:agent`
  owner column, so `{{HOME}}` was a bigger change than planned, and it touches `SOUL.md`. A fixed
  `agent` was weighed: the local machine had 4.6 GB free (Colima and Docker Desktop VMs hold most
  of the disk), too little for a Lima test. The owner kept the configurable user because the
  module 8 guide creates `agent` too, so a course student already has one. Step 3 split into 3a to
  3c, `{{AGENT_NAME}}` (default Telma) joined `SOUL.md`'s change, and a clash check (step 8) went
  before the run.
- The same review found that `check-drift.py` expects ticket-bay-bot's install (step 2 now covers a
  Telma-only host), that `deploy.py` already reads `drift.HOST`, and docs missing from the table.
  No `vps/` file holds a Discord ID, so the IDs stay in Hermes's `.env`.
