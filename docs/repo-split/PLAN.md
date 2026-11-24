# Repo split: Telma and ticket-bay-bot get a repo each

**Goal:** `jrcopeti/telma` holds Telma only. ticket-bay-bot moves to a new public repo,
`jrcopeti/ticket-bay-bot`, with the same layout. The VPS doesn't change.

**Why:** the repos split along the same line as the agents, the trust boundary. A cleaner showcase
comes second. This replaces the hardening plan's "One showcase repo for both agents".

**Done when:** each repo holds only its own agent's files, its CI is green, and the `main` ruleset is on.
No link in Telma's docs points at a file that's gone, and every script deployed on the VPS matches
its copy in one of the two repos.

## Decisions (the owner, 2026-11-19)

- **History stays where it happened.** Telma's `docs/hardening/` is kept whole and frozen at the tag
  `pre-split`. Its links to files that move become permalinks at that tag, so an entry shows the file
  as it was then. The hardening PLAN gets two edits: a frozen line at the top, and the one-repo
  decision marked superseded.
- **Bot repo, fresh history.** One import commit naming `jrcopeti/telma@pre-split`. No `filter-repo`:
  the old history stays readable here, and the bot repo's full-history secret scan covers only what
  was reviewed for it.
- **Same paths.** `vps/ticket-bay-bot/`, `vps/skills-sync/` and `vps/ticket-bay-app/` keep their paths
  in the bot repo. `vps/shared/` goes in both: each agent folder gets its own `memory-diff.sh` and test.
  Shared files (`AGENTS.md`, hooks, gitleaks config, workflows) are rewritten for the bot, not copied.
  The bot's files are copied byte for byte, except the lines the split forces.
- **The bot never writes its own repo.** The ticket-bay-bot GitHub App stays installed on the
  ticket-bay fork only. The bot repo gets Telma's `main` ruleset: PR required, no force push, no
  deletion, `gitleaks` required.
- **Each repo describes the host from its side.** A `vps/host.md` in each repo, with no single owner.
  Both state the rules that span the host in the same words: Hermes moves in lockstep (both installs
  and `/opt/hermes-guard`), and a compromised host means both kill switches, then a rebuild. Each
  links to the other. The kill switches link to each other on `main`.
- **Where the work is tracked.** The split is tracked here. The bot repo carries on in its own
  `docs/hardening/`, which restates only the decisions still in force for the bot.

## Steps

Each step stops for the owner's yes before any commit, push, repo setting or SSH command. From
2026-11-19 on, PRs open without asking and the owner merges them; VPS changes still wait for their yes.

| # | Step | Done when | Status |
|---|---|---|---|
| 1 | **Plan.** This file and the devlog, one PR. | Merged | done (#21) |
| 2 | **Tag.** `pre-split` on `main` after step 1, pushed. | The tag is on GitHub | done (`43a7b25`) |
| 3 | **Bot repo.** Create `jrcopeti/ticket-bay-bot`, public and empty. Build the import from `pre-split`: the bot's files, with only the forced lines changed and a printed diff against the tag for review. Add the bot's `memory-diff.sh` and its test, `AGENTS.md`, `CLAUDE.md`, `.githooks/`, `.gitleaks.toml`, both workflows (bot jobs only), `docs/hardening/{PLAN,DEVLOG}.md` and `vps/host.md`. Push to `main`, then switch on the ruleset. | CI green (tests and gitleaks on the full history), ruleset active | done (`b2a060d`) |
| 4 | **Telma without the bot.** Delete the bot's files. Move `vps/shared/` to `vps/telma/`. Remove the bot jobs from `tests.yml`. Pin the links, freeze the hardening PLAN, add `vps/host.md`, link the kill switch, and update `AGENTS.md`. Opened only after step 3 is green. | Merged, CI green, no link to a missing file | done (#22) |
| 5 | **VPS check.** Read-only over SSH: sha256 of every deployed script against its copy in either repo. | Every deployed script matches, or each difference is explained | done |

## Open

- Done. The files no repo held are now in one: Telma's `guard-network.sh` and sandbox `Dockerfile`
  here (#24 and this PR), the bot's in jrcopeti/ticket-bay-bot (#2, #5 and its sandbox PR).
