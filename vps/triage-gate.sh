#!/usr/bin/env bash
# Hermes pre-script of brain-triage: wake the agent only when the inbox holds something new, and always at 09:00.
# Prints a fixed line, never a file name (the inbox holds untrusted text). Printing nothing makes Hermes skip the
# AI call. The state file holds a hash of the inbox, so a run that left items is not retried until the inbox changes.
# A run that ended in error is retried each hour (Hermes records it in jobs.json) until one succeeds.
# Any failure here prints a line too: Hermes runs the agent when a pre-script fails, so the gate fails open.
set -u
B=${BRAIN_DIR:-$HOME/brain}
S=${TRIAGE_GATE_STATE:-$HOME/.triage-gate.state}
J=${TRIAGE_JOBS_FILE:-${HERMES_HOME:-$HOME/.hermes}/cron/jobs.json}
hour=${TRIAGE_HOUR:-$(TZ=Europe/Berlin date +%H)}

# Every entry's name, plus the content of regular files, so an edit counts as a change. Only regular files
# are read: a FIFO would block sha256sum forever, and a link or unreadable file still counts by its name.
# One listing feeds the count and the hash, so a capture landing mid-run can't make them disagree.
n=0 state=empty
if [ -d "$B/inbox" ]; then
  L=$(mktemp) || L=
  if [ -n "$L" ] && (cd "$B/inbox" && find . -mindepth 1 ! -type d ! -path ./README.md -print0 | LC_ALL=C sort -z) > "$L"; then
    # NUL-counted, so a newline in a name is one item.
    n=$(tr -cd '\0' < "$L" | wc -c | tr -d ' ')
    state=$(cd "$B/inbox" && { tr '\0' '\n' < "$L"; xargs -0 -r sh -c 'for f; do [ -f "$f" ] && [ ! -L "$f" ] && sha256sum "$f"; done' sh < "$L" 2>/dev/null; } | sha256sum | cut -d' ' -f1)
  else
    echo "⚠️ triage-gate: cannot list $B/inbox, so the agent runs"
    n=1 state=unreadable-$RANDOM$RANDOM
  fi
  rm -f "$L"
fi
[ "$n" = 0 ] && state=empty

last=$(cat "$S" 2>/dev/null || true)
# Hermes sets last_status before this run starts, so it is the previous run's. Unreadable means no retry.
failed=$(python3 -c 'import json,sys
d=json.load(open(sys.argv[1])); d=d.get("jobs", d) if isinstance(d, dict) else d
print(any(j.get("name") == "brain-triage" and j.get("last_status") == "error" for j in d))' "$J" 2>/dev/null)

echo "$state" > "$S" 2>/dev/null || echo "⚠️ triage-gate: cannot write $S, so a run that leaves items will repeat every hour"

if [ "$hour" = 09 ] || { [ "$n" != 0 ] && { [ "$state" != "$last" ] || [ "$failed" = True ]; }; }; then
  echo "inbox: $n items"
fi
exit 0
