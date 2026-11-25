# 6. Rule-file changes from the VPS go through a proposal

Status: accepted, 2026-11-25 (amends [ADR 4](0004-sync-brain-keeps-its-own-clone.md): a change to a rule file is no longer refused)

## Context

The brain has a few files that tell agents how to behave: the skills, `AGENTS.md`, `CLAUDE.md` and
`taste.md`. Every agent the owner uses reads them, including the ones on the local machine. Telma's
sandbox can't write them. Her Hermes process, on the host, can: its own learning features edit a
skill after a chat, and a nightly cleanup does the same. The read-only mounts never covered that.

Until now the push script refused any change to these files. That left Telma safe, and it also
stopped everything else: while one skill edit was waiting, none of her notes reached GitHub.

## Decision

The push script splits what Telma changed in two. Notes, decisions and the other ordinary folders
still go to `main`. Changes to the rule files go to one branch, `telma/proposals`, and Discord gets
a link to compare it with `main`. The owner reads the diff and merges it, or deletes the branch.

- Her copy never keeps the change. The script puts `main`'s version back each run, so she only ever
  runs rules the owner has seen.
- A second edit before the owner decides is added to the same branch, not lost. Where two edits
  touch the same lines, both stay and the owner picks.
- Deleting the branch means no. If the owner changes the same file on `main` meanwhile, `main`
  wins: that part of the proposal is dropped, and Discord says so once.
- Links, nested repos and the files git reads as config are still refused, proposals included.

## Consequences

- One skill edit no longer blocks the rest of her work.
- A bad edit to a rule file now costs the owner a review, not a refusal. Nothing runs from it until
  it is merged, and a change to a skill is checked with the eval before the merge.
- The deploy key could already push to `main`, so a branch is no new way out.
- Her Hermes learning stays on, and what it learns about the skills arrives as proposals.
