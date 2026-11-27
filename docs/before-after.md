# Before and after hardening

On 2026-11-17 a bug email told the agent to save an instruction to its memory, and it did
([postmortem](hardening/postmortem-2026-11-17-prompt-injection.md)). At the time one Hermes agent ran
every job in one Docker sandbox: the brain, the bug loop and PR triage. Two days later the jobs ran
on two agents, Telma for the brain and ticket-bay-bot for the bug loop, each with its own Linux user,
sandbox and credentials.

This page compares the two audits from Telma's side: [before](hardening/audit-before.md) (read-only,
2026-11-17) and [after](hardening/audit-after.md) (with probes from inside each sandbox and an
injection suite, 2026-11-19). The bot's side is in
[jrcopeti/ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot).

## Legs per session

A session leaks data when it holds all three legs: private data, untrusted input and a way out
([threat model](threat-model.md#the-lens-the-lethal-trifecta)).

| Session | Before | After |
|---|---|---|
| bug-loop and PR triage (strangers' emails and PRs, unattended) | **3**: the brain, a token for every repo, open network | 2: moved to ticket-bay-bot, which can't reach the brain |
| brain-triage (captured pages, unattended) | **3**: same sandbox, open network | 2: Telma, no network |
| Telma's chats with the owner | **3** | **3, accepted**: watched by a tripwire and a canary |

Before, every job shared the same legs, so the weakest input reached the strongest data. After, none
of the jobs set up today holds all three. The chats still do, and a chat can create or change a job
so it does; the threat model says why both are accepted.

## Private data

| Item | Before | After |
|---|---|---|
| The brain | read-write in the one sandbox every job used | Telma only: her sandbox, read-write except `skills/`, rule files, `.git/hooks` and `.git/config`; her Hermes process on the host in chats |
| GitHub | classic token (repo, gist, read:org) mounted in the sandbox: every private repo | rotated; Telma has none |
| Brain push | auto-sync pushed whatever the sandbox wrote, every 15 minutes | a deploy key held by `sync-brain` on the host, outside any sandbox |
| Gmail app password | mounted in the sandbox | rotated; the bug loop's mail goes to the bot, and Telma's sandbox has no mail credential |
| OpenRouter key, Discord token | host only | host only, with the new alert webhooks; probes found none in either sandbox |

## Untrusted input

| Source | Before | After |
|---|---|---|
| Bug emails, PRs, npm packages, third-party skills | read or run by the agent that held the brain | the bot's alone; it runs as another Linux user that can't list the brain |
| Captured pages | read by triage, which had the network | read by triage, which has no network and no web tools; four injected pages ignored |
| Pages opened in chats | open network | the accepted risk |
| Discord | the owner only | the owner only, both bots |

## Ways out

| Path | Before | After |
|---|---|---|
| Network from the sandbox | Docker default: anywhere | none |
| Python or Node network code | the command guard only matched `curl`, `wget`, `nc` | no network of its own: loopback only. Telma's `execute_code` can still call her web tools (T6), which the tripwire watches |
| Gists | the token's gist scope | no GitHub token |
| Email over SMTP | the app password could send mail | no mail credential |
| Brain sync | pushed whatever was in the folder, every 15 minutes | pushes Telma's files from its own clone; her changes to `skills/` and rule files go to a `telma/proposals` branch for the owner to merge, and her copy gets `main`'s version back; refuses links and other paths, and alerts |
| Telma's web and browser tools in chats | open | open, on the host: the tripwire and the canary detect, nothing blocks. `web_extract` sends each URL to a third party (Exa) |
| Discord link previews | open | open: any link Telma posts is fetched by Discord; the canary sees it |

## The worst path, before

The local machine's capture, triage, lint and ask-brain skills are links into `~/brain/skills`.
Before, the sandbox could write that folder, so one injected run could:

1. write a poisoned skill into the brain,
2. have auto-sync push it,
3. have the local machine pull it on the next capture,
4. and have Claude Code, Codex or Cursor run it there with full permissions.

After, `skills/` is read-only in Telma's sandbox, the bug loop runs on another Linux user that can't
list the brain, and a change to `skills/` made on the host (Hermes's own skill editing can write it)
never reaches `main`: `sync-brain` puts it on a branch, `telma/proposals`, and her copy goes back to
`main`'s version until the owner merges it.

## Persistence

| Tool | Before | After |
|---|---|---|
| `memory` | on for every job; poisoned once | on in Telma's chats, so she learns; off for brain-triage. A diff goes to the owner |
| `skill_manage` | on for every job | on for brain-triage and Telma's chats; the same diff covers it |
| `cronjob` | on: an injected run could schedule itself | off for brain-triage; on in Telma's chats (the owner's call), and a job made or changed there can get web and browser |
| Root cron jobs | the skills pull | none |

## Detection and response

| Signal | Before | After |
|---|---|---|
| Brain canary | none | a link in the brain that alerts `#alerts` when anything opens it |
| Exfil tripwire | none | a hook on Telma's outbound tools that alerts when a call carries brain text |
| Memory and skill changes | none | a diff of Telma's memory and skills to Discord ten minutes after each hourly triage, when something changed |
| Tripwire health | none | alerts when the tripwire can't alert or its hook is gone |
| sync-brain | pushed silently | alerts on a refused push, and on instruction files it moves to quarantine |
| Kill switch | none | a runbook per agent; `hermes gateway stop --yes`, since without `--yes` it refuses while a session runs |

## What is still open

The [threat model](threat-model.md#accepted-risks) lists what was accepted and why. In short:

- Telma's chats hold all three legs, and a chat can create or change a cron job so it does too, or
  remove the jobs that watch her (memory-diff, tripwire-health).
- The tripwire catches only copied brain text (8 words in a row, or a short note whole); split,
  reworded or re-encoded text gets past it.
- Memory and skills stay writable, so an injection that lands persists until the owner reads the
  diff.
- `web_extract` and Discord link previews send URLs to third parties.
- Triage could still file a capture as a guideline: a prompt forbids it, and her model did it once.
