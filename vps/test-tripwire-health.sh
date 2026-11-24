#!/usr/bin/env bash
# Tests for tripwire-health.sh with a fake hermes and a temp state folder.
# Run: bash vps/test-tripwire-health.sh
set -u
SCRIPT=$(cd "$(dirname "$0")" && pwd)/tripwire-health.sh
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
pass=0 fail=0

allowed="    - /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/exfil-tripwire.py matcher='web_.*' (timeout=15s, ✓ allowed)"
cron="    - /usr/bin/python3 -I /home/agent/.hermes/agent-hooks/cron-alert.py matcher='cronjob_manage' (timeout=15s, ✓ allowed)"
setup() {
  rm -rf "$T/st" "$T/cst" && mkdir -p "$T/st" "$T/cst" && echo 'https://discord.example/api/webhooks/1/x' > "$T/webhook"
  printf '#!/bin/sh\ncat "%s"\n' "$T/hooks" > "$T/hermes" && chmod +x "$T/hermes" && printf '%s\n%s\n' "$allowed" "$cron" > "$T/hooks"
}
run() { out=$(TRIPWIRE_STATE=$T/st CRON_ALERT_STATE=$T/cst TRIPWIRE_WEBHOOK_FILE=$T/webhook HERMES=$T/hermes bash "$SCRIPT" 2>&1); }
check() { local name=$1; shift; if "$@"; then echo "ok   $name"; pass=$((pass + 1)); else echo "FAIL $name"; echo "     output: ${out:-<none>}"; fail=$((fail + 1)); fi; }
says() { grep -qF -- "$1" <<<"$out"; }

setup; run
check "all well: silent" eval '[ -z "$out" ]'

setup; : > "$T/webhook"; run
check "an empty webhook file is reported" eval 'says "missing or empty"'

setup; rm "$T/webhook"; run
check "a missing webhook file is reported" eval 'says "missing or empty"'

setup; printf '%s\n%s\n' "${allowed/✓ allowed/✗ not allowlisted}" "$cron" > "$T/hooks"; run
check "a hook not approved is reported" eval 'says "exfil-tripwire hook is not configured and approved" && ! says "cron-alert"'

setup; printf '%s\n%s\n' "$allowed" "${cron/✓ allowed/✗ not allowlisted}" > "$T/hooks"; run
check "the cron-alert hook not approved is reported" eval 'says "cron-alert hook is not configured and approved" && ! says "exfil-tripwire"'

setup; echo "    - /home/agent/.hermes/agent-hooks/guard-network.sh matcher='terminal' (timeout=10s, ✓ allowed)" > "$T/hooks"; run
check "hooks gone from the config are reported" eval 'says "exfil-tripwire hook is not" && says "cron-alert hook is not"'

setup; printf 'fail one\nfail two\n' > "$T/st/failed.log"; run
check "failures are reported with the last one" eval 'says "2 tripwire failure(s)" && says "Last: fail two"'
run
check "and only once" eval '[ -z "$out" ] && [ "$(grep -c "" "$T/st/failed.log.seen")" = 2 ]'

setup; echo 'cron fail' > "$T/cst/failed.log"; run
check "cron-alert failures are reported" eval 'says "1 cron-alert failure(s)" && says "Last: cron fail" && ! says "tripwire failure"'
run
check "and only once" eval '[ -z "$out" ]'

echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
