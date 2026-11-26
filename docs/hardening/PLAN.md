# Hardening: split Telma by trust boundary

**Goal:** no agent on the VPS holds all three legs of the lethal trifecta (private data, untrusted
input, a way out). Every control is enforced by permissions, mounts or the network, not by prompts
or command regexes.

**Why:** the safety audit of 2026-11-17 ([audit-before.md](audit-before.md)) found all three legs in
the bug-loop job, and a path from an injected run to code running on the local machine with full
permissions. An injection had already worked once and poisoned Telma's memory.

**Done when:** the safety audit, rerun with probes, shows at least one leg cut for every job, and the
injection test suite passes against both agents. (Met by step 6.)

**State:** steps 0 to 6 are done and were split at tag `pre-split` (2026-11-19): ticket-bay-bot moved
to [jrcopeti/ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot), see
[the repo split](../repo-split/PLAN.md). Steps 7 to 14 were
[reopened 2026-11-25](#reopened-2026-11-25-brain-rule-files-and-hourly-triage), Telma's side only:
step 2's "Telma can't change `skills/`" held for her sandbox, not for her Hermes process on the host.
The full text of steps 0 to 6 and their decisions is in the [devlog](DEVLOG.md).

## Decisions

- **Two agents, one per trust level.** Telma does the brain only; `ticket-bay-bot` does the bug loop
  and PR triage. Separate Linux users on one VPS, each with its own rootless Docker, Hermes home,
  Discord bot and OpenRouter key (with its own credit limit). One repo per agent
  ([the repo split](../repo-split/PLAN.md)).
- **GitHub identity: an App, not a machine account.** `ticket-bay-bot` is a GitHub App installed on
  ticket-bay only (1-hour tokens). Telma has a brain deploy key held by `sync-brain`, git author
  `Telma`. If she needs to act on GitHub, she gets her own App, never the bot's.
- **The owner's skills live in the brain,** written on the local machine and linked into every agent
  by `install.mjs`. Telma pulls them read-only; her changes reach the owner as a proposal branch, never
  `main` (amended 2026-11-25, step 8). Her own Hermes skills (`~/.hermes/skills`) are hers to write;
  the memory diff is the control. Project skills stay in their project.
- **The brain stays one repo.** `skills/`, `AGENTS.md` and `CLAUDE.md` are `:ro` in her sandbox; her
  host process can write them, so `sync-brain` (the only holder of the push key) turns such changes
  into a proposal (step 8) and never runs git in a folder she writes. A separate `brain-skills` repo
  is a possible later ADR, not needed now.
- **The ticket-bay fork gets security patches, not Renovate.** A Dependabot alert on what the VPS runs
  is fixed on the fork's `main` with the smallest version that closes it, one PR by hand.
- **Telma keeps web and browser in chats, as an accepted risk.** No allowlist can cut them. Her
  unattended job, brain-triage, runs without them, so no job holds all three legs. Step 5's canary and
  5b's tripwire are the checks.
- **ticket-bay-bot learns** (memory and `skill_manage` on), and **Telma keeps `skill_manage`** (the
  owner, 2026-11-18). A memory and skills diff goes to Discord (daily for the bot; for Telma after
  each brain-triage, see step 11) and the owner undoes what looks planted. Emptying her memory
  alone doesn't undo what she learned: check her skills and `~/.hermes/skills/.curator_ledger.jsonl`.
- **The bot's allowlist trusts whole platforms, as an accepted risk.** Squid sees only the CONNECT
  host, so any account on `github.com`, `api.github.com` or `registry.npmjs.org` is reachable.
  Narrowing it means TLS inspection or a host-side mirror: not now.
- **An obedient bot can paste its 1-hour token into a public PR, as an accepted risk.** The terminal
  guard blocks the plain ways; the token reaches the fork only and dies within the hour.
- **Detection, not recording (step 5).** Squid's denials go to Discord; a canary link in the brain
  alerts a channel Telma's bot can't read or delete. The canary's file is named nowhere in this repo
  or the brain, only in the token memo: never write it into a doc. Shipping tool-call logs off the VPS is dropped.
- **The exfil tripwire watches and blocks nothing (step 5b).** A `pre_tool_call` hook posts to
  `#alerts` through its own webhook when a web, browser or other off-host call carries brain text
  (published and rule files don't count). Text split, reworded or
  encoded another way gets out unseen: accepted; the fix is a web agent with no brain, deferred on cost.
- **The local machine keeps its skill links** (`~/.claude/skills`, `~/.agents/skills` →
  `~/brain/skills`).

The full text of each decision is in the [devlog](DEVLOG.md#2026-11-26-steps-0-to-6-their-decisions-and-the-old-open-list-trimmed).

## Steps

Each step is one branch and one PR. Steps that change a running agent need the owner's yes first.

| # | Step | Done when | Status |
|---|---|---|---|
| 0 | **Incident response:** rotate the leaked credentials, check for changes nobody asked for, reset the poisoned memory, write a postmortem. | Old credentials are revoked, nothing unexplained is left, postmortem written | done |
| 1 | **Set up ticket-bay-bot:** own Linux user, Docker, Hermes home, Discord bot and key; GitHub App with a host-side 1-hour token; Gmail fetched on the host; `memory`, `cronjob` and `code_execution` off; bug-loop and pr-triage moved to it. | From its sandbox, `ls ~/brain` fails and a search finds no long-lived secret | done |
| 1b | **MCP server for ticket-bay-bot (optional):** TicketBay with seed data, no key, include-list without `my_orders`. | The bot answers "which events are coming up?" through MCP and has no tool that returns customer data | done |
| 2 | **Reduce Telma to the brain:** remove the ticket-bay jobs, gh token, Gmail mount and checkout; brain deploy key on the host only; `skills/` and `AGENTS.md` mounted read-only; `sync-brain` refuses and alerts on commits touching them. | Triage still runs; a commit touching `skills/` is refused and alerted | done |
| 3 | **Egress control:** Telma's sandbox has no network and brain-triage no web or browser toolsets; the bot's sandbox sits behind a squid allowlist (`github.com`, `api.github.com`, `registry.npmjs.org`); npm install scripts off. | A fetch of `example.com` fails from both sandboxes; `api.github.com` works from the bot's; brain-triage has no web or browser tool | done |
| 4 | **Supply chain:** `dmoka/skills` in a folder the bot can't write, updated by an unprivileged `skills-sync` after a 7-day wait and a skills-guard scan; Hermes pinned; Dependabot alerts on the fork. | No root cron jobs; every external input is pinned or gated; Dependabot alerts are on | done |
| 5 | **Detection:** a canary link in the brain alerting `#alerts`; squid's denials posted every 10 minutes; a kill-switch runbook per agent. | Opening the link (locally and through Telma) posts to `#alerts`; a denied fetch from the bot's sandbox posts to ticket-bay | done |
| 5b | **Exfil tripwire:** a detection-only hook on Telma's off-host tools, with a health job. | A web call carrying a brain note posts to `#alerts`; a normal browsing session posts nothing | done |
| 6 | **Verification:** injection suite ([injection-suite.md](injection-suite.md), [results](step6-results.jsonl)) against both agents; safety audit rerun ([audit-after.md](audit-after.md)); before/after table, ADRs and postmortem. | The done-when at the top holds | done |


## Reopened 2026-11-25: brain rule files and hourly triage

**Goal:** a change to a brain rule file (`skills/`, `AGENTS.md`, `CLAUDE.md`, `taste.md`) made on the
VPS reaches the owner as a proposal to review, never as a refusal that blocks her other pushes and
never as a push to `main`. Triage runs hourly, only when the inbox holds something.

**Why:** step 2's read-only mounts cover her sandbox, not her Hermes process on the host, which can
write `skills/`. sync-brain refused those edits and held back her inbox pushes. The story is in the
[devlog](DEVLOG.md#2026-11-25-reopened-for-steps-7-to-12-the-owner-grilled-in-a-claude-code-session).

**Done when:** steps 7 to 14 are done and the docs match what runs (step 12).

### Decisions (the owner, 2026-11-25)

- **Rule files from the VPS become a proposal.** sync-brain pushes allowed paths to `main`, and puts
  her rule-file changes on one branch, `telma/proposals`, on top of `main`. Discord gets the compare
  link once per new proposal. The owner opens the PR and merges it, after an eval when it changes a
  skill. Links, gitlinks and `.git*` files are refused everywhere, prxoposals included.
- **Her copy never stays edited.** Each run writes `main`'s version of a proposed file back into her
  copy. A second edit before the owner decides is added to the open proposal.
- **Deleting the branch means no.** sync-brain drops what it holds and posts once. A branch gone
  because it was merged posts nothing. When `main` changes a file an open proposal also changes, `main`
  wins and the proposal is dropped.
- **The self-improvement review and the curator stay on.** Their edits become proposals.
- **`taste.md` is a proposal like the rest, and writable in her sandbox.** Its two single-file mounts
  are gone. `skills/`, `AGENTS.md` and `CLAUDE.md` stay `:ro` in the sandbox.
- **Triage runs hourly, gated.** `0 0,8-23 * * *` (Berlin). A host pre-script wakes the agent only
  when `inbox/` holds anything besides `README.md`, once per inbox state, and always at 09:00. It
  prints a fixed line (`inbox: N items`), never file names.
- **memory-diff follows triage by ten minutes:** `10 0,8-23 * * *`, a script with no agent that
  posts only when something was saved.

### Facts the steps rely on

- Four callers can write a brain skill in her process: her chats, brain-triage, the self-improvement
  review and the curator. Hermes guards only a delete, and only in a background run. The proposal
  review is the control for all four. Read in Hermes's source, 2026-11-26.
- Hermes ranks local skills (`~/.hermes/skills/`) above `external_dirs`, so a local skill with a
  brain skill's name hides the reviewed one.
- Hermes skips a job's AI call when its pre-script prints nothing or `{"wakeAgent": false}`.

### Steps

Each step is one branch and one PR, with its docs (the table below) in the same PR. Steps that
change the VPS need the owner's yes first.

| # | Step | Status |
|---|---|---|
| 7 | Unblock sync-brain | done 2026-11-25 (brain PRs #3, #4) |
| 8 | Proposals in sync-brain | done 2026-11-25 (#74; deployed `deploy/2026-11-25-1`) |
| 9 | `taste.md` writable | done 2026-11-26 (#87, brain PRs #5, #7) |
| 10 | Watch brain skills | todo |
| 11 | Hourly gated triage | todo |
| 12 | Docs sweep | todo, after 13 and 14 |
| 13 | Leftover temp files anywhere | todo |
| 14 | `index.md` merges by line | todo |

#### 7. Unblock sync-brain (done)

- **Do:** on the VPS, write GitHub's `skills/capture/SKILL.md` over her copy. Send the curator's
  bullet and the inbox's taste line to brain PRs by hand.
- **Done when:** the next sync-brain run is silent and her held-back inbox files are on GitHub.

#### 8. Proposals in sync-brain (done)

- **Do:** split her diff in `vps/sync-brain.sh`: allowed paths to `main`, rule files
  (`^skills/|^(AGENTS|CLAUDE|taste)\.md$`) to `telma/proposals`, force-pushed with a lease and built
  on the open proposal; then write `main`'s versions back into her copy. Post the compare link once
  per new proposal, and once when it is dropped. Everything else outside `ALLOWED` is refused as
  before. Tests in `vps/test-sync-brain.sh`, then an adversarial round.
- **Done when:** a skill edit in her copy is one commit on `telma/proposals` and one Discord post;
  her copy is back to `main`'s; inbox pushes go on meanwhile; deleting the branch posts "dropped"
  once; a merge posts nothing.

#### 9. `taste.md` writable (done)

- **Do:** drop the two `taste.md` `:ro` volumes from `vps/hermes/config.overrides.yaml`. Capture's
  taste section says to insert the line under the right section of `taste.md` (brain PRs #5 and #7).
- **Done when:** a taste correction in a chat shows as a proposal, and `taste.md` on `main` is
  unchanged until the owner merges.

#### 10. Watch brain skills

- **Do:**
  1. `vps/memory-diff.sh` also snapshots `~/brain/skills`, with its test in `vps/test-memory-diff.sh`.
  2. `vps/sync-brain.sh` alerts when a skill in `~/.hermes/skills/` has the name of a brain skill.
- **Done when:** a planted `~/.hermes/skills/capture/` posts once; a brain-skill edit shows in the
  next memory-diff.
- **Needs the owner:** deploy.

#### 11. Hourly gated triage

- **Do:**
  1. Find out what Hermes does when a pre-script exits non-zero (skip, or run without it).
  2. Add `vps/triage-gate.sh` with tests, and list it in `vps/deploy.manifest`.
  3. In `vps/hermes/jobs.overrides.yaml`, give `brain-triage` the gate and `0 0,8-23 * * *`, and
     move `memory-diff` from `30 9,21 * * *` to `10 0,8-23 * * *`.
  4. Update `vps/README.md`'s schedule line and the "Twice a day" comment in `vps/memory-diff.sh`.
- **Done when:** an hour with an empty inbox logs "skipping AI call" and posts nothing; a capture is
  filed within the hour; a run that left items isn't retried until the inbox changes or 09:00; a
  saved edit is posted within the hour.
- **Needs the owner:** deploy; whether to run the eval for the schedule.

#### 12. Docs sweep

- **Do:** after 13 and 14, make every doc in the table below match what runs. Set `AGENTS.md`'s
  "Finished work" line to say hardening is closed again.
- **Done when:**
  - a grep for "twice a day" and "09:00 and 21:00" finds nothing stale;
  - every "read-only" and "refuse" in the docs is checked by hand: the `:ro` mounts of `skills/`,
    `AGENTS.md` and `CLAUDE.md` and the refusal of links, gitlinks and `.git*` files stay true;
  - "she can't change a rule file" and "a rule-file change is refused" are gone, since she can write
    `taste.md` (step 9) and the others become proposals;
  - every doc that names who edits a skill lists all four callers.
- **Needs the owner:** approval of each public doc in its PR; the eval with their yes for `SOUL.md`.

#### 13. Leftover temp files anywhere

- **Do:** in `vps/sync-brain.sh`, refuse a `.hermes-tmp.*` file wherever it is, before the allowlist
  check. The refusal clears once the temp file is gone, so it never holds a file back for good.
- **Done when:** a temp file under `notes/` and one under `skills/` each give the failed-write post
  and push nothing; deleting it lets the next run go out.

#### 14. `index.md` merges by line

- **Do:** in `vps/sync-brain.sh`, merge `index.md` as a three-way line merge against the version
  last synced. Edits on neighbouring lines merge; when both sides change the same line, both versions
  stay (a duplicate is possible and the lint shows it). Not a plain union: it would bring back a line
  the owner deleted.
- **Done when:** she adds a line right after one the owner changed, and the next run pushes both and
  posts nothing; the owner rewrites a line she also touched, and both versions show; the owner
  deletes a line she left alone, and it stays deleted.

#### Evals owed

Merging a skill change into the brain, or changing `SOUL.md` (step 12), needs the eval with the
owner's yes (AGENTS.md). Owed: brain PR #4, #5 and #7 (the capture skill), merged without it on the
owner's decision. The mount (9) and the schedule (11) aren't on AGENTS.md's list; the owner decides.

### Docs to update

| Doc | What changes | Step |
|---|---|---|
| `vps/memory-diff.sh`, `vps/test-memory-diff.sh` | `~/brain/skills` in the snapshot | 10 |
| `vps/hermes/jobs.overrides.yaml`, `vps/deploy.manifest`, new `vps/triage-gate.sh` | schedule, script, manifest entry | 11 |
| `vps/hermes/brain-triage-prompt.txt` | if the gate's line needs a word in the prompt | 11 |
| `vps/README.md` | her jobs (schedule, gate) | 11 |
| `docs/deploy/PLAN.md` | new files in the manifest and drift check | 11 |
| `vps/hermes/SOUL.md` | triage hourly, not twice a day; rule-file changes become a proposal the owner merges (needs the eval) | 12 |
| `docs/threat-model.md` | the brain diagram, rows 3 and 5, brain-triage's schedule, memory-diff's reach | 12 |
| `README.md` | "twice a day", "09:00 and 21:00", "skills and rules read-only", "Her edits can't reach the owner's machine" | 12 |
| `docs/before-after.md` | the brain and sync rows: proposals instead of refusals | 12 |
| `docs/adr/0001-telma-keeps-the-brain.md` | "twice a day" | 12 |
| `AGENTS.md` | the "Finished work" line | 12 |
| Brain: the 2026-11-22 decision, `projects/telma.md`, `notes/hermes-agent-setup-gotchas.md`, `notes/telma-lethal-trifecta-and-safety-audit.md` | amended through capture and triage, not edited here | 12 |

Done in steps 7 to 9: `vps/sync-brain.sh` and its test, `vps/kill-switch.md`, `vps/brain-skills/`,
`vps/hermes/config.overrides.yaml`, ADR 6.

## Open

- **ticket-bay-bot's test gate:** Hermes stopped waiting for a hook after 30 s. Timeout raised to
  300 s on 2026-11-18; check on the next bug-loop run that edits code.
- **Dependabot on the fork:** `zod` (< 4.6.6) and `source-map-js` alerts stay open.
- **Step 4 proof:** the first real skills update or block, once upstream moves past the pin.
- **The owner's calls, no fix planned:** the skills guard matches findings per pattern and path (a
  second `~/.ssh` read in one file passes); the test gate runs `git rev-parse` and `worktree remove`
  on the host in sandbox-written repos (no exec seen, low).
- **Step 6 skips (the owner):** B7 (an injected PR from a second account) and a B1 rerun on the
  fallback models; classic branch protection on the fork's `main` is gone, the `main` ruleset has the
  same rules.


## Rules for this repo

- No secrets or personal data: no keys, webhook URLs, inbox address, Discord IDs, IP addresses,
  private repo names.
- Nothing copied from the course kit. Describe in own words.
- Public docs (README, threat model, ADRs, postmortem) are written by the owner.
