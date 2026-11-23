# The host, from Telma's side

Telma shares one VPS with ticket-bay-bot. The bot's repo describes the same host from its side:
[jrcopeti/ticket-bay-bot vps/host.md](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/host.md).

## Users on this side

| User | What it runs |
|---|---|
| `agent` | Telma: her own Hermes install (`~/.hermes/hermes-agent`), rootless Docker. Her sandbox starts with `--network=none`; web and browser run in her Hermes process on the host. Host-side jobs: [sync-brain](telma/sync-brain.sh), [memory-diff](telma/memory-diff.sh) and [tripwire-health](telma/tripwire-health.sh), plus the [exfil tripwire](telma/exfil-tripwire.py) and [cron alert](telma/cron-alert.py) hooks. |

The bot runs as `ticket-bay-bot`, next to `ticket-bay-app` and `skills-sync`. Both agents' homes are
`750`, so neither can read the other's files.

## Where each file is deployed

Copied by hand; `~` is Telma's home, `/home/agent`.

| In this repo | On the VPS |
|---|---|
| `telma/guard-network.sh` | `~/.hermes/agent-hooks/` |
| `telma/exfil-tripwire.py`, `telma/cron-alert.py` | `~/.hermes/agent-hooks/`; their config entries in `telma/*.hooks.yaml` |
| `telma/sandbox/Dockerfile` | `~/sandbox/` |

## Rules for the whole host

These rules are the same, word for word, in both repos.

- **Hermes moves in lockstep.** Both installs and `/opt/hermes-guard` stay on the same commit. A bump
  is by hand, in all three places.
- **A compromised host means both kill switches, then a rebuild.** Signs: a root login you don't know,
  a changed `/etc`, an unknown process. Run the
  [bot's](https://github.com/jrcopeti/ticket-bay-bot/blob/main/vps/ticket-bay-bot/kill-switch.md) and
  [Telma's](telma/kill-switch.md) kill switches, then rebuild the VPS.
- **Scripts are deployed by hand.** Nothing on the host clones either repo. A change here reaches the
  VPS only when José says yes and copies it.
