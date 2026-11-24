# Devlog: showcase

## Branches

| Branch | Step | State |
|---|---|---|
| `docs/rename-devlog-and-showcase` | plan | merged (#31) |
| `docs/threat-model` | 2 | merged (#33) |
| `docs/before-after` | 4 | merged (#34) |
| `fix/threat-model-review` | 2 | merged (#35) |
| `fix/before-after-review` | 4 | merged (#37) |
| `docs/adrs` | 3 | open |

## 2026-11-19: plan

- The README, threat model, ADRs and before/after table were named in `AGENTS.md` and hardening step 6,
  but no plan tracked them. Hardening step 6 shows "done" while two of its docs don't exist.
- José chose a new plan for them, which also takes Telma's open items from the frozen hardening plan.
  Lessons 8.5 and 8.6 moved to jrcopeti/ticket-bay-bot's own plan, because they run on the bot.

## 2026-11-19: order, scope, and who writes

- José changed the rule: agents draft the public docs, he approves each in its PR. `AGENTS.md` and the
  plan's Rules say so now.
- His calls: the README uses the `crafting-effective-readmes` skill with the portfolio template;
  Telma's README shows the brain work only and links the bot for the bug loop; José captures the
  screenshots from a shot list (in the plan); threat model first, README last.
- Threat model drafted from the frozen hardening docs (audit-after, injection suite, step 6 results,
  postmortem, kill switch). Checked against the hardening devlog: brain-triage has no memory or
  cronjob tool; chats keep both (José's call in step 2).
- The public docs say "the owner", not "José": the threat model and `AGENTS.md` changed. The rest of
  the docs follow later (open item in the plan).

## 2026-11-20: chat tools stay

- Asked whether to cut the `cronjob` toolset in chats, or web and browser. The owner's call: leave
  them all as they are. Not checked: whether a job created from a chat runs with the chat's web
  tools, which would make it an unattended job with all three legs.

## 2026-11-20: before/after table

- Threat model merged (#33). Drafted the before/after table from the two audits, as tables per leg,
  per session, persistence and detection, plus the skill path to the local machine that motivated `skills/` read-only.
- It covers both agents: before hardening one agent ran the bug loop and the brain, so a Telma-only
  table would hide the main fix (the split). It links ticket-bay-bot's repo for the bot's depth.
- Says "the owner" throughout. Needs the owner's approval in the PR.
- `/code-review` on #34: ten findings, all held. Fixed: memory is on for the bot (step 4), not off;
  `skill_manage` row; both agents' diffs; Telma's `execute_code` can call her web tools; Discord
  previews and Exa; ruleset on the fork with the owner's bypass; which `.git` parts are read-only;
  tripwire-health and sync-brain alerts; the open list now matches the threat model's accepted risks.
- Audit asked by the owner: keep Telma's rows, park the bot's for its own docs, keep overlaps here and
  write them there too. Cut the bot-only rows (its legs, App token, squid, customer data, PR body,
  ruleset, denied egress, its open risks) and the bot halves of shared rows; folded bug emails, PRs,
  npm and third-party skills into one "moved to the bot" row. Parked list in the brain inbox.

## 2026-11-20: threat model review fixes

- `/code-review` on #33 after it merged; nine of ten findings held. Fixed on `fix/threat-model-review`:
  proof cells that cited model refusals (T4, T5, T7) as if they tested a control; the terminal guard
  overstated (a regex on one tool, and its secret paths are the bot's); the unchecked chat-made cron
  job now stated next to "no unattended job holds all three legs"; refusal vs quarantine in
  sync-brain; memory-diff relays injectable text to Discord; the diagram (web tools pointed at the
  owner, ragged right edge).
- Not fixed here: plan and devlog status (done in #34), new "José" lines in the plan (the open rename
  item covers them).

## 2026-11-20: review of the merged table

- #34 was merged with the Telma-only cut in it; `/code-review` on that commit. Fixed: Telma's
  sandbox is loopback only (the "no DNS" probe was the bot's); "her `execute_code`" names Telma;
  the moved bot jobs keep their leg count, so "no unattended job holds all three" stays checkable.
  Dropped the PLAN.md fix: #35 merged, so the threat model's Mac rename is done.
- Not changed: a memory write in a chat shows in the diff only after the next triage. The threat
  model says the same, so the page matches it; the owner can decide whether to name the gap.

## 2026-11-20: ADRs

- The owner picked five, Telma's creation first, and asked for short docs. Each one fits on a
  screen: context, decision, consequences. Sources: the brain's decisions and project note, the
  hardening plan and the threat model.
- ADR 1 says she started as the coding employee in an AI agent engineering course, without naming or
  linking it; the brain's showcase intent asks for a link to the course where possible.
- `/code-review` on the branch: nine findings, all held. Fixed: ADR 2 said strangers' input no longer
  reaches the brain (captured and chat pages still do) and dropped the unchecked chat-made cron job;
  ADR 3 said the hardening docs are frozen (the tag is, the files were edited since); ADR 4's count
  (13 on top of three known); ADR 5 left out the brain-folder trigger and browser tools, and named the
  canary without saying what it is; plan step 4 and #37 marked merged; the course link moved to Open.

## 2026-11-20: the chat-made cron job, checked

- The owner had Telma set a medicine reminder from a chat. Its job got `enabled_toolsets: []` (zero
  tools: the model chose it). Read Hermes's code on the VPS, read-only: the chat's `cronjob` tool
  stores whatever toolsets the model asks for (`tools/cronjob_tools.py`), a job without a list gets
  `hermes-cron`, the same core tools as the CLI, web and browser included (`cron/scheduler.py`), and
  the only cap, `agent.disabled_toolsets`, applies to chats too. So a chat can schedule an unattended
  job with all three legs.
- The owner's call: no fix, mark it checked. Threat model, before/after and ADR 2 now say so, and
  list it as an accepted risk. Not checked: whether the tripwire hook fires inside cron runs.
- `/code-review` after the update: seven findings, six held. The chat's `cronjob` tool can also
  update, pause, run and remove any job (checked on the VPS: `_JOB_ACTIONS` in
  `tools/cronjob_tools.py`, no check on who made the job), so a chat can give brain-triage web or
  remove memory-diff and tripwire-health. The docs now say so, "none of the scheduled jobs" became
  "the jobs set up today", and ADR 5 names the removable health job. ADR 1's date and two long lines
  fixed. Kept ADR 4's 16: the three earlier breaks share the cause, and the redesign covers them.

## 2026-11-20: README draft

- Drafted with screenshot placeholders so the text can be reviewed while the owner takes the shots;
  `docs/assets/` comes with the images, each checked for personal data before it's committed.
- Short, like the ADRs: what she is, the three brain jobs (capture, ask-brain, triage) with a shot
  each, the safety story in a few lines linking the threat model, before/after and ADRs, a
  ticket-bay-bot section with its repo link, and the "formerly Tania" line from the rename plan.
- Says "the owner", with no gendered pronoun for them. ADRs (step 3) marked done (#38).
- Owner's review: "What she does" broadened to a personal assistant (reminders, summaries, web
  lookups, memory), with the brain as her main job; a Models section lists the main model and the
  fallback chain from the brain's model decision, and says the chain is the owner's pick and
  Hermes takes any list. The reminder example is neutral on purpose: no health detail.
- Owner's review: the safety section read as a list of flaws. Rewritten as "Built to be safe":
  what was done after the injection (split, no network for triage, read-only skills, tripwire and
  canary, injection suite), with the accepted risks left to the threat model's link.
- Research on similar self-hosted agent repos (Odysseus, Missy, NabaOS, Alvin Bot): they state trust
  assumptions, name prompt injection and give a private way to report. This repo had no LICENSE, no
  SECURITY.md, no description or topics (community profile 0%). The owner chose MIT for everything,
  `guard-network.sh` included, and asked for all of it in this PR.
- Screenshots in place, all 220px wide; the avatar is a 256px copy of the owner's icon (free for public use). Checked each: no IPs, webhooks, private repos, canary or other people, and no GPS or device metadata. Blurred the old name in `alerts.jpg` and the owner's name in `brain-triage.jpg`, amended into the unpushed commit so the originals never reached GitHub.
- The owner gave the course link: README credits and ADR 1 now name and link AI Agent Engineer by
  Daniel Moka. Open item closed.
- `/code-review` on #39: eight findings, all held (one in part). Fixed: "no way out for unattended
  work" (only triage; chat-made jobs can get web and browser), "tools that touch the brain run in
  the sandbox" (browser_exec on the host can read notes), "every control works outside the model"
  (the threat model names where only the model stands), the obedient-model lesson (one case ran on
  north-mini-code, then direct probes), plan status and the repo-extras item, ADR 1's long line,
  extra blank lines.
- Owner's correction: "no way out for unattended work" was right. Checked Telma's jobs on the VPS
  (read-only): brain-triage has terminal, file, skills and todo only; sync-brain, memory-diff and
  tripwire-health are no-agent scripts; the chat-made reminder has zero toolsets and is paused.
  Reverted that bullet and the "jobs scheduled from a chat" clause. Kept "file and shell tools run
  in the sandbox": `browser_exec` runs Python as a subprocess of her host process (read in
  `tools/browser_use_cli.py`); reading a note that way was not tested.
- Owner's fixes after merging #39: the avatar overlapped the title's rule, so it now sits centered
  above a centered title. Screenshots at 220px in tables were unreadable: now two per row at 49%
  width, singles at the same width. ticket-bay-bot is out of the README (diagram line and its
  section); ADR 2 now links its repo.
- Owner added `capabilities.jpg` (Telma describing what she does and won't do), placed under the
  "What she does" list. Checked: no private data or location metadata.
- Owner disliked mixed sizes side by side: every screenshot is now one per row, centered, 420px
  wide, then cut to 320px at the owner's request.

## 2026-11-24: new screenshots for her new icon

- Her Discord icon changed, so the owner retook the shots into `docs/assets/screenshots/`: the
  avatar, capabilities, capture (two shots: the request with her reads, then her "saved to inbox"
  reply), ask-brain, triage, new session and the tripwire alert. The README points at them; the
  eleven old jpgs and the old avatar are deleted.
- The two capture shots arrived named `ask-1` and `ask-2`; renamed to `capture-1` and `capture-2`
  to match what they show. Ask-brain is two shots now (`ask-1`: the question and her reads;
  `ask-2`: her answer with the note links), down from three.
- Checked each: no IPs, webhooks, private repos, canary or other people, and no GPS or device
  metadata (only macOS's "Screenshot" comment). The owner's Discord username is blurred in
  `capture-1`, `capabilities` and `ask-1` (owner's request). Channel and thread names, a cron job
  ID and a Hermes session ID show; none of them identify anyone or open anything.
- Owner's correction: the "started as the coding employee in AI Agent Engineer" line in the README
  credits is true only of ticket-bay-bot. Removed.
