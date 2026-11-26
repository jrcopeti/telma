---
name: capture
description: "Save a link, snippet, or decision into the brain inbox. Use when the user says 'save this', 'remember this', 'note this decision', forwards a link, screenshot or pasted text, or at the end of a session when a decision was made or a gotcha was found. Also use when the user corrects you with a reason ('no, do it this way, because…'): that becomes a taste entry. Fast and dumb: one file into inbox/, no sorting — triage does the thinking later."
---

# Capture

Capture is fast and dumb. It writes one file into `inbox/`, runs `node sync.mjs`, and stops. It never sorts, summarizes into notes, or edits existing notes — that is triage's job. The one thing it writes outside `inbox/` is a taste line, in `taste.md`.

## Save something

1. If it is a URL, try to fetch the text. If the page is blocked (login walls are common), keep the URL and the user's words and set `--fetch blocked`. Never fail a capture because a fetch failed.
2. Create the item with the script, content on stdin:
   ```bash
   echo "<fetched or pasted text>" | python3 skills/capture/scripts/new_item.py \
     --title "<short title>" --source "<url | pasted | conversation>" --note "<the user's reason, verbatim>"
   ```
   A link, or text with a URL in it: keep the URL out of the command line (a dev container blocks every shell command with a URL in it). Write the URL to `inbox/.source` and the text to `inbox/.body` with your file tool, then run:
   ```bash
   python3 skills/capture/scripts/new_item.py --title "<short title>" \
     --source-file inbox/.source --body-file inbox/.body --note "<the user's reason, verbatim>"
   ```
   The script deletes both draft files after it writes the item.
3. Run `node sync.mjs` from the brain folder. It commits the new item, pulls, and pushes.
4. Reply in one line: `saved to inbox (<path>)`. If sync.mjs says "NOT pushed", add that to the reply.

## Capture on your own

At the end of a session, capture what would otherwise be lost: a decision and its reason, or a gotcha you ran into. Use `--source conversation` and write the outcome, not a transcript.

## Taste entries

When the user corrects you with a reason, the taste line is
`- <the rule> — because <their reason> (YYYY-MM-DD)`, placed in the right section of `taste.md`
(`## Never` / `## Prefer` / `## Tie-breakers`). Use their words. No reason given? Ask one question
("why?") first. No reason, no entry.

`taste.md` is a rule file, but it is the one you can write: insert the line under the right section
of your copy of it. A change to it never goes straight to main: the host sync puts it on a branch for a PR the owner merges
(`decisions/2026-11-22-brain-skill-changes-go-through-a-pr.md`). So write the line in `taste.md`, not
in `inbox/`, run `node sync.mjs` from the brain folder, and say in the reply that it is waiting for the
owner's review.

## Gotchas

- Capture is triggered by the owner asking to save something, not by a good conversation. In
  casual chat, don't offer to file things or write up what was talked about — "just chatting"
  means answer only, no note.
- Don't create notes or edit the index here. Everything goes through `inbox/`, so nothing skips triage.
  The one exception is a taste line, which goes into `taste.md` (see Taste entries).
- Rule files — `AGENTS.md`, `CLAUDE.md`, `skills/` — are read-only here and their changes go
  through a branch + PR the owner merges. When one should change, capture the proposed edit (exact text,
  location, reason) into `inbox/` and say it needs a PR. `taste.md` is the exception (see Taste
  entries). Never try to write the others: the write fails (read-only mount) or, worse, would land on
  main unreviewed.
- Don't paste secrets or other people's personal data into the brain, even when the user forwards them. Keep the link, drop the secret.
- Screenshots: save the image file into `inbox/` next to the item and describe what it shows in the item's text.
