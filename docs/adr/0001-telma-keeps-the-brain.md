# 1. Telma keeps the brain

Status: accepted (narrowed to the brain only on 2026-11-17, see [ADR 2](0002-two-agents-split-by-trust-boundary.md))

## Context

The owner keeps a second brain: a git repo of markdown notes, decisions and guidelines that their
coding agents read before they work. Notes arrive all day, from a chat, a link or the end of a coding
session, and land unsorted in `inbox/`. Sorting them into the right place is the work that gets
skipped.

At first one agent did both: the bug loop from [AI Agent Engineer](https://aiagentengineer.dev/),
Daniel Moka's course, which reads bug emails and opens pull requests, and the brain.
[ADR 2](0002-two-agents-split-by-trust-boundary.md) split them: the bug loop went to ticket-bay-bot,
and Telma kept the brain.

## Decision

An always-on agent named Telma keeps the brain. She captures what the owner sends her in Discord,
answers "what does my brain say about X?" with links to the notes, triages the inbox hourly (08:00 to midnight) when it holds
something, and posts what she filed.

She runs on Hermes Agent on a VPS:

- **Always on:** triage runs on a schedule, and the owner can reach her from a phone, with no laptop
  open.
- **Hermes, not Claude Code:** any model through OpenRouter with a fallback chain, chat and
  scheduled jobs in one gateway, and memory, so she learns how the owner works.

## Consequences

- An agent with the owner's private notes reads outside text: captured pages and the pages she opens
  in chats. That is the [lethal trifecta](../threat-model.md#the-lens-the-lethal-trifecta), and the
  reason for the [hardening](../before-after.md).
- After the [2026-11-17 injection](../hardening/postmortem-2026-11-17-prompt-injection.md) the bug
  loop moved to [ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot). Telma writes no code
  and opens no pull requests.
- The owner runs the server: updates, disk, backups and alerts.
