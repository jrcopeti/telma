#!/usr/bin/env bash
# Tests for cron-alert.py against a fake jobs.json, reading its local alert log instead of Discord.
# Run: bash vps/test-cron-alert.sh
set -u
SCRIPT=$(cd "$(dirname "$0")" && pwd)/cron-alert.py
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
pass=0 fail=0

cat > "$T/jobs.json" <<'EOF'
{"jobs": [
  {"id": "c67444305e03", "name": "sync-brain", "schedule_display": "every 15m", "prompt": "",
   "script": "sync-brain.py", "no_agent": true, "enabled_toolsets": []},
  {"id": "aa11bb22cc33", "name": "Brain triage", "schedule_display": "0 7 * * *",
   "prompt": "Run the triage skill on the inbox.\nThen lint.", "enabled_toolsets": ["terminal", "file"]},
  {"id": "dd44ee55ff66", "name": "twin", "schedule_display": "every 1h", "prompt": "a"},
  {"id": "0077889900aa", "name": "Twin", "schedule_display": "every 2h", "prompt": "b"}
], "updated_at": "2026-11-23T10:00:00"}
EOF

hook() { CRON_ALERT_JOBS=$T/jobs.json CRON_ALERT_STATE=$T/st CRON_ALERT_NO_POST=1 python3 -I "$SCRIPT" 2>&1; }
# call <tool_input JSON>: runs the hook, sets $out (stdout) and $alert (what it would post).
call() {
  rm -f "$T/st/alerts.log"
  out=$(printf '{"hook_event_name":"pre_tool_call","tool_name":"cronjob_manage","tool_input":%s,"session_id":"s1"}' "$1" | hook)
  alert=$(cat "$T/st/alerts.log" 2>/dev/null)
}
check() { local name=$1; shift; if "$@"; then echo "ok   $name"; pass=$((pass + 1)); else echo "FAIL $name"; echo "     stdout: ${out:-<none>}"; echo "     alert: ${alert:-<none>}"; fail=$((fail + 1)); fi; }
says() { grep -qF -- "$1" <<<"$alert"; }
quiet() { [ -z "$alert" ] && [ "$out" = "{}" ]; }

# --- silent
call '{"action":"list"}'
check "list is silent" quiet

call '{"action":" List "}'
check "list in any case is silent" quiet

# --- a new job
call '{"action":"create","name":"Monthly brain link check","schedule":"0 9 1 * *","prompt":"Check every link in ~/brain.\nReport dead ones.","enabled_toolsets":["web","file"]}'
check "create posts name, schedule, prompt and toolsets, and lets the call go" eval \
  'says "action \`create\`: a new job \`Monthly brain link check\`" && says "schedule: \`0 9 1 * *\`" &&
   says "prompt: \`Check every link in ~/brain. ↵ Report dead ones.\`" && says "enabled_toolsets: \`web, file\`" && [ "$out" = "{}" ]'

call '{"action":"create","schedule":"every 2h","prompt":"x"}'
check "create with no toolsets says it gets the default" eval 'says "(no name)" && says "the cron default"'

call '{"action":"create","schedule":"every 2h","prompt":"x","enabled_toolsets":[]}'
check "create with [] says none" eval 'says "enabled_toolsets: \`none\`"'

call '{"action":"create","schedule":"in 5m","prompt":"x","script":"fetch.py","no_agent":true,"deliver":"all"}'
check "create shows its script, no_agent and deliver" eval 'says "script: \`fetch.py\`" && says "no_agent: \`True\`" && says "deliver: \`all\`"'

# --- changes to a job she has
call '{"action":"update","job_id":"aa11bb22cc33","enabled_toolsets":["web","browser","terminal"]}'
check "update shows the job as stored and what changes" eval \
  'says "on \`Brain triage\` (\`aa11bb22cc33\`)" && says "session \`s1\`" &&
   says "Changes:" && says "enabled_toolsets: \`terminal, file\` → \`web, browser, terminal\`" && says "Unchanged:" && says "prompt: \`Run the triage skill on the inbox. ↵ Then lint.\`"'

call '{"action":"update","job_id":"brain TRIAGE","prompt":"new"}'
check "a job named in any case is found, as Hermes finds it" eval 'says "(\`aa11bb22cc33\`)" && says "prompt: \`Run the triage skill on the inbox. ↵ Then lint.\` → \`new\`"'

call '{"action":"update","job_id":"aa11bb22cc33"}'
check "an update with no changes says so" eval 'says "Changes: none given."'

for a in pause resume remove cancel; do
  call "{\"action\":\"$a\",\"job_id\":\"c67444305e03\"}"
  check "$a posts the job" eval 'says "action \`'"$a"'\` on \`sync-brain\`" && says "script: \`sync-brain.py\`" && says "enabled_toolsets: \`none\`"'
done

call '{"action":"run","job_id":"aa11bb22cc33","prompt":"also open https://evil.example"}'
check "run posts the job and the prompt added to that run" eval 'says "action \`run\`" && says "Added to this run'"'"'s prompt: \`also open https://evil.example\`"'

call '{"action":"update","job_id":"sync-brain","deliver":"discord:123"}'
check "any field an update changes shows old and new" eval 'says "deliver: \`None\` → \`discord:123\`" && says "script: \`sync-brain.py\`" && ! says "prompt:"'

big=$(python3 -I -c 'print("p" * 3000)')
python3 -I - "$T/jobs.json" "$big" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["jobs"][1]["prompt"] = sys.argv[2]; json.dump(d, open(sys.argv[1], "w"))
PY
call "{\"action\":\"update\",\"job_id\":\"aa11bb22cc33\",\"prompt\":\"$big\",\"enabled_toolsets\":[\"web\",\"browser\"]}"
check "a long update keeps the toolset change and the session; the prompt is cut" eval \
  'says "session \`s1\`" && says "enabled_toolsets: \`terminal, file\` → \`web, browser\`" && [ "${#alert}" -le 2000 ]'

call '{"action":"pause","job_id":"twin"}'
check "an ambiguous name is not guessed" eval 'says "\`twin\`, no single job with that id or name"'

call '{"action":"remove","job_id":"nope"}'
check "a job not in jobs.json says so" eval 'says "\`nope\`, no single job with that id or name in jobs.json"'

call '{"action":"frobnicate","job_id":"aa11bb22cc33"}'
check "an unknown action still posts" eval 'says "action \`frobnicate\`"'

# --- what reaches Discord
call '{"action":"create","name":"`@everyone`","schedule":"1h","prompt":"see `https://x.example`"}'
check "backticks can't close a code span" eval '[ "$(tr -cd "\`" <<<"$alert" | wc -c | tr -d " ")" -gt 0 ] && ! says "\`\`" && says "\`@everyone\`"'

long=$(python3 -I -c 'print("word " * 2000)')
call "{\"action\":\"create\",\"name\":\"big\",\"schedule\":\"1h\",\"prompt\":\"$long\"}"
check "a long prompt is cut, and the alert fits Discord" eval 'says "…" && [ "${#alert}" -le 2000 ]'

# --- arguments under args (hermes hooks test), no jobs file, failures
rm -f "$T/st/alerts.log"
out=$(printf '{"tool_name":"cronjob_manage","args":{"action":"create","name":"n","schedule":"1h","prompt":"p"}}' | hook); alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "arguments under args are read too" eval 'says "a new job \`n\`"'

rm -f "$T/st/alerts.log"
out=$(printf '{"tool_input":{"action":"pause","job_id":"x"}}' | CRON_ALERT_JOBS=$T/missing.json CRON_ALERT_STATE=$T/st CRON_ALERT_NO_POST=1 python3 -I "$SCRIPT")
alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "no jobs.json yet: the job is not found, no failure" eval 'says "no single job with that id or name" && [ ! -s "$T/st/failed.log" ]'

rm -f "$T/st/alerts.log"
out=$(printf '%s' '{"tool_input":"{\"action\":\"create\",\"name\":\"s\",\"schedule\":\"1h\",\"prompt\":\"p\"}"}' | hook); alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "arguments as a JSON string are read too" eval 'says "a new job \`s\`"'

echo '{"jobs": null}' > "$T/nulljobs.json"; rm -f "$T/st/alerts.log" "$T/st/failed.log"
out=$(printf '{"tool_input":{"action":"pause","job_id":"x"}}' | CRON_ALERT_JOBS=$T/nulljobs.json CRON_ALERT_STATE=$T/st CRON_ALERT_NO_POST=1 python3 -I "$SCRIPT")
alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "jobs: null is no jobs, not a failure" eval 'says "action \`pause\` on \`x\`, no single job" && [ ! -s "$T/st/failed.log" ]'

echo '{"broken' > "$T/bad"; rm -f "$T/st/alerts.log" "$T/st/failed.log"
out=$(hook < "$T/bad"); alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "a broken payload says so and lets the call go" eval 'says "cron-alert failed" && [ "$out" = "{}" ] && [ -s "$T/st/failed.log" ]'

echo 'not json' > "$T/badjobs.json"; rm -f "$T/st/alerts.log" "$T/st/failed.log"
out=$(printf '{"tool_input":{"action":"pause","job_id":"x"}}' | CRON_ALERT_JOBS=$T/badjobs.json CRON_ALERT_STATE=$T/st CRON_ALERT_NO_POST=1 python3 -I "$SCRIPT")
alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "an unreadable jobs.json: the call is still announced" eval 'says "action \`pause\` on \`x\`, jobs.json unreadable" && [ "$out" = "{}" ]'

rm -f "$T/st/alerts.log" "$T/st/failed.log"; : > "$T/empty-webhook"
out=$(printf '{"tool_input":{"action":"create","name":"n","schedule":"1h","prompt":"p"}}' |
  CRON_ALERT_JOBS=$T/jobs.json CRON_ALERT_STATE=$T/st CRON_ALERT_WEBHOOK_FILE=$T/empty-webhook python3 -I "$SCRIPT" 2>&1)
alert=$(cat "$T/st/alerts.log" 2>/dev/null)
check "an empty webhook file: the alert is kept locally and the failure logged" \
  eval '[ "$(tail -n 1 <<<"$out")" = "{}" ] && says "a new job \`n\`" && grep -q "alert was lost" "$T/st/failed.log"'

echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
