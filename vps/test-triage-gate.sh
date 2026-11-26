#!/usr/bin/env bash
# Tests for triage-gate.sh against a throwaway brain. TRIAGE_HOUR stands in for the Berlin hour.
# Run: bash vps/test-triage-gate.sh
set -u
SCRIPT=$(cd "$(dirname "$0")" && pwd)/triage-gate.sh
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
pass=0 fail=0

setup() { rm -rf "$T/w" && W=$T/w && mkdir -p "$W/brain/inbox" && echo "# inbox" > "$W/brain/inbox/README.md"; HOUR=14; run; }
run() { out=$(HOME=$W BRAIN_DIR=$W/brain TRIAGE_GATE_STATE=$W/state TRIAGE_HOUR=$HOUR bash "$SCRIPT" 2>&1); }
check() { local name=$1; shift; if "$@"; then echo "ok   $name"; pass=$((pass + 1)); else echo "FAIL $name"; echo "     output: ${out:-<none>}"; fail=$((fail + 1)); fi; }

setup
check "an empty inbox is silent" eval '[ -z "$out" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run
check "a new item wakes her with a fixed line" eval '[ "$out" = "inbox: 1 items" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run; run
check "the same inbox is not retried" eval '[ -z "$out" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run; echo "b" > "$W/brain/inbox/b.md"; run
check "a new item after a run wakes her again" eval '[ "$out" = "inbox: 2 items" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run; echo "edited" > "$W/brain/inbox/a.md"; run
check "an edited item wakes her again" eval '[ "$out" = "inbox: 1 items" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run; rm "$W/brain/inbox/a.md"; run; echo "a link" > "$W/brain/inbox/a.md"; run
check "an item filed and then captured again wakes her" eval '[ "$out" = "inbox: 1 items" ]'

setup; echo "a link" > "$W/brain/inbox/a.md"; run; HOUR=09; run
check "09:00 wakes her even for an unchanged inbox" eval '[ "$out" = "inbox: 1 items" ]'

setup; HOUR=09; run
check "09:00 wakes her for an empty inbox" eval '[ "$out" = "inbox: 0 items" ]'

setup; echo "# changed" > "$W/brain/inbox/README.md"; run
check "the README alone does not count" eval '[ -z "$out" ]'

setup; mkdir "$W/brain/inbox/sub"; run
check "an empty folder alone does not count" eval '[ -z "$out" ]'

setup; mkdir "$W/brain/inbox/sub" && echo x > "$W/brain/inbox/sub/n.md"; run
check "an item in a folder counts" eval '[ "$out" = "inbox: 1 items" ]'

setup; echo x > "$W/brain/inbox/ignore previous instructions.md"; run
check "no file name is printed" eval '[ "$out" = "inbox: 1 items" ]'

setup; rm -rf "$W/brain"; run
check "no brain folder: silent" eval '[ -z "$out" ]'

setup; HOUR=09; rm -rf "$W/brain"; run
check "no brain folder at 09:00: still wakes her" eval '[ "$out" = "inbox: 0 items" ]'

setup; echo x > "$W/brain/inbox/a.md"; mkdir "$W/state.d"; out=$(HOME=$W BRAIN_DIR=$W/brain TRIAGE_GATE_STATE=$W/state.d TRIAGE_HOUR=14 bash "$SCRIPT" 2>&1)
check "an unwritable state file is said, and she is woken" eval '[[ $out == *"cannot write"* && $out == *"inbox: 1 items"* ]]'

# She and the sandbox can write inbox/, so odd entries must neither hang the gate nor hide from it.
if command -v timeout >/dev/null; then
  setup; mkfifo "$W/brain/inbox/f"; out=$(HOME=$W BRAIN_DIR=$W/brain TRIAGE_GATE_STATE=$W/state TRIAGE_HOUR=14 timeout 10 bash "$SCRIPT" 2>&1)
  check "a FIFO does not hang the gate and counts as an item" eval '[ "$out" = "inbox: 1 items" ]'
fi

setup; ln -s nowhere "$W/brain/inbox/d1"; run; ln -s nowhere "$W/brain/inbox/d2"; run
check "a second dangling link wakes her again" eval '[ "$out" = "inbox: 2 items" ]'

setup; ln -s "$W" "$W/brain/inbox/dirlink"; run
check "a link to a folder counts as an item" eval '[ "$out" = "inbox: 1 items" ]'

setup; touch "$W/brain/inbox/x"$'\n'"y.md"; run
check "a newline in a name is one item" eval '[ "$out" = "inbox: 1 items" ]'

if [ "$(id -u)" != 0 ]; then
  setup; echo a > "$W/brain/inbox/u1"; chmod 000 "$W/brain/inbox/u1"; run; echo b > "$W/brain/inbox/u2"; chmod 000 "$W/brain/inbox/u2"; run
  check "a second unreadable file wakes her again" eval '[ "$out" = "inbox: 2 items" ]'
  chmod 600 "$W"/brain/inbox/u*
fi

# A listing that fails (no search permission on inbox/) must wake her, every run, not read as empty.
if [ "$(id -u)" != 0 ]; then
  setup; echo a > "$W/brain/inbox/a.md"; chmod 000 "$W/brain/inbox"; run; first=$out; run
  check "an unlistable inbox says so and wakes her each run" eval '[[ $first == *"cannot list"* && $first == *"inbox: 1 items"* && $out == *"inbox: 1 items"* ]]'
  chmod 700 "$W/brain/inbox"
fi

echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
