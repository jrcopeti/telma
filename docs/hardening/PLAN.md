# Hardening: split Telma by trust boundary

**Frozen at tag `pre-split` (2026-11-19).** ticket-bay-bot moved to its own repo,
[jrcopeti/ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot); see [the repo split](../repo-split/PLAN.md).

**Goal:** no agent on the VPS holds all three legs of the lethal trifecta (private data, untrusted
input, a way out). Every control is enforced by permissions, mounts or the network, not by prompts
or command regexes.

**Why:** the safety audit of 2026-11-17 ([audit-before.md](audit-before.md)) found all three legs in
the bug-loop job, and a path from an injected run to code running on the local machine with full permissions.
An injection had already worked once and poisoned Telma's memory.

**Done when:** the safety audit, rerun with probes, shows at least one leg cut for every job, and the
injection test suite passes against both agents.

## Decisions

- **Two agents, one per trust level.** Telma does the brain only. `ticket-bay-bot` does the bug loop
  and PR triage. Both run on the same VPS, as separate Linux users with their own rootless Docker and
  Hermes home. Each has its own Discord bot and server (brain-server, ticket-bay).
- ~~**One showcase repo for both agents.** They share the host, the hardening and the threat model.~~
  Superseded 2026-11-19 by [the repo split](../repo-split/PLAN.md): one repo per agent, along the
  trust boundary.
- **One OpenRouter key per agent,** each with its own credit limit.
- **GitHub identity: an App, not a machine account.** `ticket-bay-bot` is a GitHub App owned by the owner's
  account and installed on ticket-bay only; its PRs show as `ticket-bay-bot[bot]`, with 1-hour tokens.
  Telma gets a brain deploy key held by `sync-brain`, with git author `Telma`. If she later needs to act
  on GitHub, she gets her own App (`telma-brain`), never ticket-bay-bot's.
- **The owner's skills live in the brain.** Personal skills used across projects (capture, triage, lint,
  ask-brain) are written on the local machine and pushed; every agent gets them through `install.mjs` links,
  and Telma pulls them read-only. Telma never writes a brain skill: she leaves a note in the inbox instead.
  Her own Hermes skills (`~/.hermes/skills`) are another matter: see the next decision.
  Project skills stay in their project; ticket-bay-bot's skills come from `dmoka/skills`.
- **The ticket-bay fork gets security patches, not Renovate** (the owner, 2026-11-19). Upstream owns its
  dependency versions, so routine updates stay off: the fork would drift from the lessons. A Dependabot
  alert on what the VPS runs is fixed on the fork's `main` with the smallest version that closes it,
  by hand, one PR (#17 did `next`, `better-auth` and the MCP SDK). Renovate (proposes) + ticket-bay-bot
  (reviews) + the owner (merges) is for a repo the owner owns, such as trip-ai.
- **The brain stays one repo.** Telma can't change `skills/` or `AGENTS.md`: they are mounted
  read-only in her sandbox, only `sync-brain` on the host holds the push key, and it refuses commits
  that touch those paths. Splitting out a `brain-skills` repo is a possible later ADR, not needed now.
- **Telma keeps web and browser in chats, as an accepted risk.** They run in her Hermes process on the
  host and need any site, so no allowlist can cut them, and a third agent for web work costs too much
  for now. In chats with the owner she holds all three legs: the brain, the pages she opens, and any URL.
  Her unattended job, brain-triage, runs without web and browser (`enabled_toolsets`), so no job holds
  all three. Discord link previews are a way out no VPS rule closes. Step 5's canary is the check on
  both.
- **ticket-bay-bot learns: memory and `skill_manage` on** (changed in step 4; step 1 had memory off).
  An injected run can save something every later run reads; that's accepted for the learning. A daily
  diff of its memory and skills goes to Discord, and the owner undoes what looks planted. Telma gets the
  same diff, twice a day after brain-triage, which keeps `skill_manage` (in the `skills` toolset).
  **Telma keeps `skill_manage`** (the owner, 2026-11-18), after she used it to write a skill that described
  the canary. Her skills in `~/.hermes/skills` are hers to write; the diff is the control, and the owner
  edits what shouldn't be there. Emptying her memory alone doesn't undo what she learned: check her
  skills and `~/.hermes/skills/.curator_ledger.jsonl` too.
- **The bot's allowlist trusts whole platforms, as an accepted risk** (the owner, 2026-11-19). Squid sees
  only the CONNECT host, so any account on `github.com`, `api.github.com` or `registry.npmjs.org` is
  reachable: an injected email carrying the attacker's own GitHub or npm token could have the bot push,
  open a gist or `npm publish` what it read, or pull a payload from the attacker's repo or package.
  Nothing denies or alerts on it, and the kill switch checks only the bot's fork. Narrowing it means
  TLS inspection, or moving git and `gh` work to the host and npm behind a mirror: not now.
- **An obedient bot can paste its 1-hour token into a public PR, as an accepted risk** (the owner,
  2026-11-19, step 6's B9). The terminal guard blocks the plain ways (`hosts.yml`, `gh auth token`,
  `printenv`); a reworded command or the file tool gets past it. The token reaches the fork only and
  dies within the hour. Not built: a wider guard, revoking the token at the end of each run, or a
  host-side script that checks the PR body before posting.
- **Step 5 detects, it doesn't record.** Shipping tool-call logs off the VPS keeps evidence safe from
  root on the host but alerts on nothing: dropped. Squid's denials are added: a blocked request from the
  bot's sandbox is the clearest sign of an injected run. The canary's file is named nowhere in this
  repo or the brain, only in the token memo, so an attacker who reads either can't avoid it. Its alerts
  go to Discord, in a channel Telma's bot can't read or delete. It is a link, not a fake secret: the
  brain's rules forbid secrets, so Telma flags one; Hermes masks AWS key IDs before she sees them; and a
  bare `canarytokens.com` URL gives itself away. A fake AWS key was tried and dropped: its alert never came.
- **Step 5b watches Telma's web and browser calls for brain text, and blocks nothing.** A hook on
  Hermes's `pre_tool_call` (web and browser, plus the other tools that send data off the host:
  `vision_analyze`, `video_analyze`, `image_generate`, `text_to_speech`, `manage_connections`,
  `computer_use`, `x_search`) posts to `#alerts` when a call's arguments carry 8 words in a row from a
  note, or a short note whole (plain, URL- or base64-decoded, either order), or name the brain's folder (`browser_exec` runs Python, which
  could read a note from disk). It catches the lazy injection: a note pasted into a URL. Text split
  across calls, reworded or encoded another way still gets out unseen: that gap stays accepted, and the
  fix is still prevention (a web agent with no brain), deferred on cost. No marker planted in notes:
  text runs already catch a copied note, Telma would see the marker, and a page can tell her to strip
  it. Published or rule files (`skills/`, `AGENTS.md`, `CLAUDE.md`, `README.md`) don't count. Its own
  webhook, so a hijacked Telma who finds it can delete only the tripwire's posts, not the canary's.
- **The local machine keeps its skill links** (`~/.claude/skills`, `~/.agents/skills` → `~/brain/skills`).
  Copies would break `install.mjs`'s links-only design.

## Steps

Each step is one branch and one PR. Steps that change a running agent need the owner's yes first.

| # | Step | Done when | Status |
|---|---|---|---|
| 0 | **Incident response.** Rotate the classic GitHub token and the Gmail app password. Check gists, cron jobs, Telma's memory and the brain's git log for changes nobody asked for. Reset the poisoned memory. Write a blameless postmortem. | Old credentials are revoked, nothing unexplained is left, postmortem written | done |
| 1 | **Set up ticket-bay-bot.** New Linux user, rootless Docker, Hermes home, Discord bot, OpenRouter key with a limit. GitHub App scoped to ticket-bay, with a host-side script that mints a 1-hour token per run. Gmail fetched on the host; the agent gets the email as a file. Tools `memory`, `cronjob` and `code_execution` off. Move bug-loop and pr-triage to it. | From its sandbox, `ls ~/brain` fails and a search finds no long-lived secret | done |
| 1b | **MCP server for ticket-bay-bot (optional).** Run TicketBay with seed data as its own Linux user, and connect its MCP server with no key (public tools only) and a tool include-list without `my_orders` (customer data would bring back the private-data leg). | The bot answers "which events are coming up?" through MCP, and has no tool that returns customer data | done |
| 2 | **Reduce Telma to the brain.** Remove the ticket-bay jobs, the gh token, the Gmail mount and the ticket-bay checkout. Move her to brain-server. Brain deploy key held by `sync-brain` on the host only. `skills/` and `AGENTS.md` mounted read-only; `sync-brain` refuses and alerts on commits that touch them. | Triage still runs; a commit touching `skills/` is refused and alerted | done |
| 3 | **Egress control.** Telma's sandbox gets no network, and brain-triage runs without the web and browser toolsets. ticket-bay-bot's sandbox joins an internal Docker network whose only way out is a squid allowlist (`github.com`, `api.github.com`, `registry.npmjs.org`); npm install scripts are off. | A Python fetch of `example.com` fails from both sandboxes; `api.github.com` works from the bot's; brain-triage's session has no web or browser tool | done |
| 4 | **Supply chain.** `dmoka/skills` in a folder the bot can't write, owned by an unprivileged `skills-sync` user. It updates itself after a 7-day wait, and only if Hermes's skills guard finds nothing new. Hermes pinned. Dependabot alerts (not version-update PRs) on the ticket-bay fork. | No root cron jobs; every external input is pinned or gated; Dependabot alerts are on | done |
| 5 | **Detection.** A canary in the brain: a canarytokens.org URL token behind a link that doesn't show its domain, alerting to a brain-server `#alerts` channel Telma's bot can't see. A no-agent job on the bot posts squid's denials to ticket-bay every 10 minutes. A kill-switch runbook per agent. | Opening the link (from the local machine, and through Telma in a chat) posts to `#alerts`; a denied fetch from the bot's sandbox posts to ticket-bay | done |
| 5b | **Exfil tripwire.** A detection-only Hermes hook on Telma's tools that send data off the host (web, browser and seven more): when a call's arguments carry brain content (8-word runs or a short note whole, also URL- and base64-decoded) or name the brain's folder, it posts to `#alerts` through its own webhook. Blocks nothing. A health job says when it can't alert. | A web call carrying a brain note posts to `#alerts`; a normal browsing session posts nothing | done |
| 6 | **Verification.** Injection test suite (the email that worked, lesson 8.5's email 2, new ones) run against both agents. Safety audit rerun with probes. Before/after table, ADRs and postmortem written by the owner. Cases in [injection-suite.md](injection-suite.md), results in [step6-results.jsonl](step6-results.jsonl), audit in [audit-after.md](audit-after.md). | The done-when at the top holds | done |

## Open

- ticket-bay-bot's test gate: Hermes stopped waiting for a hook after 30 s, so a red verdict came too late.
  Timeout raised to 300 s on 2026-11-18; check on the next bug-loop run that edits code.

- `zod` (< 4.6.6) and `source-map-js` Dependabot alerts on the fork stay open (the critical `next`,
  `better-auth` and MCP SDK ones were fixed and deployed on 2026-11-19, `e9da215`).
- Step 4 proof still to see: the first real skills update or block (no upstream commit since the pin
  yet).

- Steps 0–4 review: three fixes merged (#12) and deployed 2026-11-19. The rest, in this order (one
  branch and one PR each; anything that changes the VPS needs the owner's yes):
  1. ~~`fix/sync-brain-push-guard`~~ **done** (#13, deployed and checked live 2026-11-19). The host
     never runs git in a folder Telma writes: sync-brain keeps its own clone in
     `~/.local/share/brain-push` and copies her files in with `brain-files.py`. Four adversarial
     rounds; 61 tests on git 2.56. Live: step 2's done-when holds, links, FIFOs and a `HEAD` file
     from her sandbox are refused, an edit on the local machine to `AGENTS.md` shows in her sandbox, and her first
     push went out as `Telma`. Rollback: `sync-brain.sh.bak-redesign-*` (devlog).
  2. ~~`fix/bot-workdir-and-pins`~~ **done** (deployed 2026-11-19). bug-loop and pr-triage-morning
     have no workdir any more: Hermes loads no project context file for them, runs their pre-scripts
     elsewhere, and its 6-hourly worktree sweep (host `git status`) no longer looks at the clone. The
     test gate's path rewrite fixed. `postgres:17` and `node:22-bookworm-slim` pinned by digest.
     Both jobs checked with a run; a planted `.hermes.md` didn't reach pr-triage-morning's answer.
  3. ~~`audit/skills-sync-and-egress`~~ **done** (#16, deployed 2026-11-19). Both modules attacked by a fresh agent, skills-sync twice. skills-sync: the scan saw a
     `git archive` copy that upstream's `export-ignore` can trim, of three folders only. Now each
     commit is checked out fresh in a throwaway clone and scanned whole, and the bot's folder is
     rewritten to match; links leaving the repo block; over 50 MB or 5,000 files isn't unpacked; a
     commit upstream force-pushed away during the wait is never taken (the owner); the status can't carry
     mentions or links. Squid: an IP whose reverse DNS says `github.com` got a tunnel (`dstdomain`
     without `-n`), and squid-denials skipped `TCP_DENIED_ABORTED`; image now 6.6-24.04 LTS. Whole-platform trust: accepted
     risk (Decisions).
  The owner's calls, no fix planned: the skills guard matches findings per pattern and path (a
  second `~/.ssh` read in the same file passes); the test gate runs `git rev-parse` and
  `worktree remove` on the host in sandbox-written repos (no exec seen, low).
  Dropped: the memory-diff cut splitting a character (both gateways run `LANG=C.UTF-8`) and Discord's
  length count (Hermes splits long posts and keeps code blocks closed). A model-written memory summary
  job was designed and dropped: the owner asks Telma for one in a chat when they want it.

- Moved 2026-11-19: Telma's open items (the triage-to-`guidelines/` question, shipping tool-call logs
  off the VPS) to [the showcase plan](../showcase/PLAN.md); lessons 8.5 and 8.6 on ticket-bay-bot to
  [jrcopeti/ticket-bay-bot](https://github.com/jrcopeti/ticket-bay-bot/blob/main/docs/hardening/PLAN.md).
- Step 6: classic branch protection on the fork's `main` is gone; left so (the owner): the `main` ruleset has
  the same rules. B7 (an injected PR from a second account) skipped, and no B1 rerun on the fallback
  models (the owner).

## Rules for this repo

- No secrets or personal data: no keys, webhook URLs, inbox address, Discord IDs, IP addresses,
  private repo names.
- Nothing copied from the course kit. Describe in own words.
- Public docs (README, threat model, ADRs, postmortem) are written by the owner.
