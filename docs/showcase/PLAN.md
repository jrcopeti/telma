# Showcase: the public docs, and what hardening left open

**Goal:** a reader who lands on `jrcopeti/telma` understands what Telma is, what threatens her and
why each control exists, without reading the devlogs. It also tracks the Telma items the frozen
[hardening plan](../hardening/PLAN.md) left open.

**Why:** the hardening, repo split and rename are done, but the repo has no README and no threat model.
Hardening step 6 named ADRs and a before/after table as the owner's, and neither exists yet. The postmortem
does.

**Done when:** the four docs and Telma's live files below are merged, and every item in Open is decided or done.

## Rules

- Agents draft the docs; the owner approves each one in its PR (the owner, 2026-11-19, replacing "the prose is
  the owner's").
- One doc per branch and PR, in this order: threat model, before/after table, ADRs, README last, so
  the README links docs that exist.
- No secrets or personal data, in screenshots and GIFs too.

## Steps

| # | Doc | Notes | Status |
|---|---|---|---|
| 1 | **README** | Written with the `crafting-effective-readmes` skill, "personal" (portfolio) template. Carries the "formerly" line from rename step 7. Shows Telma as a personal assistant with the brain as her main job (capture, ask-brain, triage, reminders, summaries, lookups), her models, and screenshots from the owner (shot list below); ticket-bay-bot is named only in the ADRs, which link its repo. Links the threat model, ADRs, postmortem. | merged (#39); fixes in review |
| 2 | **Threat model** | [threat-model.md](../threat-model.md): the lethal trifecta per session, which leg each control cuts, and the accepted risks from the hardening plan's Decisions. | done (#33) |
| 3 | **ADRs** | [docs/adr/](../adr/), short, one per decision the owner picked: why Telma exists, the two-agent split, one repo per agent, sync-brain's own clone, the exfil tripwire. | done (#38) |
| 4 | **Before/after table** | [before-after.md](../before-after.md), from [audit-before.md](../hardening/audit-before.md) and [audit-after.md](../hardening/audit-after.md). Telma's side only: rows about the shared agent before the split stay, bot-only rows are parked in the brain inbox for ticket-bay-bot's docs. | done (#34, #37) |
| 5 | **Telma's live files** | Copies of what runs on the VPS, so a reader sees her whole setup: her `SOUL.md`; the settings of her `config.yaml` that differ from Hermes's defaults (`config.overrides.yaml`: models, fallback order, sandbox, hooks), with no channel IDs or personal data; the brain-triage cron prompt from `jobs.json`; and the brain skills (capture, triage, lint, ask-brain) from the MIT [brain template](https://github.com/dmoka/brain-template), credited. Never memories, `auth.json`, `channel_directory.json` or anything else in her home. The PR right after eval-v1 step 6 merges, so the skills shown are the final ones (owner, 2026-11-22). The check that the copies match the VPS moved to its own plan (Open, below). | in review |

## Open

Carried over from the frozen hardening plan:

- Should Telma's triage file into `guidelines/` directly, or into a proposals folder the owner promotes?
  Her model once filed a capture as a guideline.
- A deployment check, its own plan and PR (owner, 2026-11-24): what is deployed on the VPS and
  whether this repo's copies match it, files, config and skills, not only the hashes each eval run
  stamps. Like ticket-bay-bot's manifest and drift check. Step 5's first try (compare `SOUL.md` and
  the config hash with the newest run's stamp) was too thin.
- Later detection, not planned: ship tool-call logs off the VPS, so the evidence survives root on the
  host.

- Write the bot's before/after in ticket-bay-bot: its own rows and the overlaps, parked in the brain
  inbox (`2026-11-20-bot-rows-from-telma-before-after.md`, asked 2026-11-20).

Decided:

- ~~Name the owner and the local machine nowhere.~~ Done on the live-files branch (owner,
  2026-11-24): every doc, the frozen ones included, the step 6 results, the tests and the three
  deployed scripts say "the owner" and "the local machine"; `SOUL.md` has a placeholder.

- ~~Repo extras.~~ Done in #39 (owner, 2026-11-20): MIT `LICENSE` for the whole repo, kit-derived
  file included; `SECURITY.md`; private vulnerability reporting, description and topics set on
  GitHub; README diagram, badges, Lessons, Credits and License.

- ~~What each README shows.~~ Telma's shows the brain work; the bug-loop demo is ticket-bay-bot's
  (the owner, 2026-11-19). The brain's showcase intent still says "bug email → PR": update it in the brain.

## Screenshot shot list (the owner captures)

PNGs, or one short GIF, into `docs/assets/screenshots/`. An agent checks each one for personal data
before it's committed. Blur or crop: Discord server and channel names other than Telma's, user names
and avatars other than hers and the owner's, IPs, URLs of private repos, webhook URLs, the canary's link
or file name, and any note with personal content.

1. **Capture:** a chat where the owner says "save this" with a link, and her reply that it's in the inbox.
2. **Ask-brain:** "what does my brain say about …?" and her answer, with links to the notes.
3. **Triage summary:** a brain-triage post in Discord: what she filed, and where.
4. **An alert:** the T6 canary or tripwire post in `#alerts` (crop the source IP).
5. **Optional GIF:** 20 to 30 seconds of 1 then 2.

Retaken 2026-11-24 after her new icon: 1 to 4 plus the capabilities and new-session shots.
