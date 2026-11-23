#!/usr/bin/env bash
# Every 15 min (Hermes no-agent job on Telma, on the host): say when the exfil tripwire or the cron
# alert can't alert. Their alerts go to #alerts through one webhook; when that fails, only their
# local logs know. Also says when a hook is no longer in Hermes's config or approved. Silent when
# all is well.
set -u
STATE=${TRIPWIRE_STATE:-$HOME/.local/state/exfil-tripwire}
CRON_STATE=${CRON_ALERT_STATE:-$HOME/.local/state/cron-alert}
WEBHOOK=${TRIPWIRE_WEBHOOK_FILE:-$HOME/.config/exfil-tripwire/webhook}
HERMES=${HERMES:-$(command -v hermes || echo "$HOME/.local/bin/hermes")}
say() { echo "⚠️ tripwire-health: $*"; }

[ -s "$WEBHOOK" ] || say "the webhook file $WEBHOOK is missing or empty: tripwire and cron alerts can't reach #alerts."
hooks=$("$HERMES" hooks list 2>&1)
grep -F 'exfil-tripwire.py' <<<"$hooks" | grep -qF '✓ allowed' ||
  say "the exfil-tripwire hook is not configured and approved (hermes hooks list): web calls go unwatched."
grep -F 'cron-alert.py' <<<"$hooks" | grep -qF '✓ allowed' ||
  say "the cron-alert hook is not configured and approved (hermes hooks list): cron jobs she makes go unannounced."
# failures <name> <state folder>
failures() {
  [ -s "$2/failed.log" ] || return 0
  say "$(grep -c '' "$2/failed.log") $1 failure(s) since the last check. Last: $(tail -n 1 "$2/failed.log")"
  say "Alerts it found are in $2/alerts.log."
  cat "$2/failed.log" >> "$2/failed.log.seen" && : > "$2/failed.log"
}
failures tripwire "$STATE"
failures cron-alert "$CRON_STATE"
exit 0
