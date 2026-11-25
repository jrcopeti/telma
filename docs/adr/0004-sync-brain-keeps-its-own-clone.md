# 4. sync-brain keeps its own clone

Status: accepted, 2026-11-19 (amended 2026-11-25 by [ADR 6](0006-rule-file-changes-go-through-a-proposal.md): changes to rule files are proposed, not refused)

## Context

`sync-brain` pushes the brain to GitHub from the host, with a key Telma's sandbox can't see. It used
to run git inside the brain folder her sandbox writes, `.git` included. An audit proved 13 more
ways, on top of three already known, that a sandbox that can write `.git` could get a `skills/`
change pushed, make host git write or move host files, leak another repo, or silence alerts. All
of them came from host git running in that folder.

## Decision

`sync-brain` never runs git in a folder her sandbox can write. It keeps its own clone on the host,
copies her files in as plain files only (no links, FIFOs or nested repos), pushes only the allowed
folders, and copies GitHub's changes back the same way.

## Consequences

- The 16 attacks are closed as a class, instead of patched one at a time.
- `skills/` and rule files can't reach GitHub from her sandbox, which cuts the path to the
  [local machine's skills](../before-after.md#the-worst-path-before).
- Checked by four adversarial rounds; 61 tests run in CI.
