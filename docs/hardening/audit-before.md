# Safety audit before hardening (2026-11-17)

Setup: one Hermes agent (Telma) on a VPS, running all jobs in one shared Docker sandbox.
Audit was read-only (inventory and config reads); no probes were run.

**Verdict:** the bug-loop job has all three legs. It reads strangers' emails; its sandbox can read the
brain, a GitHub token for every repo and the Gmail app password; and it can send data out through
PRs, gists, git, open network and Python, which the command guard doesn't check.

## Untrusted input

| Source | Entry point | Risk |
|---|---|---|
| Bug emails | bug-loop, unattended, 09:00 | high: an injection already worked once |
| PRs and comments on the public ticket-bay repo | pr-triage, 08:00 | medium: anyone can open a PR |
| Third-party skills repo, pulled daily | root cron at 07:50, then loaded as skills | medium: supply chain |
| npm packages during `npm ci` | inside the sandbox; install scripts run | medium |
| Web pages captured into the brain inbox | brain-triage, 21:00 | low to medium |
| Discord | only the owner is allowed | low |

## Private data the sandbox can reach

| Item | How | Risk |
|---|---|---|
| The brain | read-write mount | high |
| GitHub token (classic: repo, gist, read:org) | `gh` config mounted read-only | high: every private repo |
| Gmail app password | secrets file mounted read-only | medium: dedicated inbox, can send mail |
| OpenRouter key, Discord bot token | host `.env` only | out of reach |

## Ways out

| Path | What opens it | Risk |
|---|---|---|
| PR description on a public repo | `gh pr create`, the job itself | can't be removed |
| Gists | the token's gist scope | high |
| Open network from the sandbox | Docker default network, no rules | high |
| Python or node network code | the guard only matches curl, wget, nc | high |
| `code_execution` tool | enabled; the guard only watches the terminal tool | high |
| git or npm with any URL | the guard allows URLs in git, gh, npm | medium |
| Email over SMTP | the app password | medium |
| Brain auto-sync | pushes every 15 minutes | a way out and a way in |

## Worst path: the local machine

The local machine's capture, triage, lint and ask-brain skills are symlinks into `~/brain/skills`, which is
writable from the sandbox:

1. An injected run writes a poisoned skill into the brain.
2. `sync-brain` pushes it.
3. The local machine pulls it on the next capture.
4. Claude Code, Codex or Cursor on the local machine runs it with full permissions.

## Persistence

`memory` (poisoned once already) and `cronjob` (an injected run could schedule its own job) let an
injection outlive the run.
