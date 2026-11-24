#!/usr/bin/env bash
# Every 15 min (Hermes no-agent job, on the host): push what Telma changed in the brain, pull the rest.
# Her sandbox writes the brain, .git included, so host git never runs there. This keeps its own clone
# in $P, copies her files into it with brain-files.py (plain files only, never through a link), pushes
# only ALLOWED paths, then writes GitHub's changes back into her copy the same way.
# Silent on success: the job posts whatever this prints to Discord.
set -u
B=${BRAIN_DIR:-$HOME/brain}
P=${BRAIN_PUSH_DIR:-$HOME/.local/share/brain-push}
Q=${BRAIN_QUARANTINE:-$HOME/brain-quarantine}
KEYS=$HOME/.config/brain-deploy
REMOTE=${BRAIN_REMOTE:-$(cat "$KEYS/remote" 2>/dev/null)}
FILES=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/brain-files.py
ALLOWED='^(inbox|sources|notes|guidelines|decisions|projects|intents)/|^index\.md$'

export GIT_SSH_COMMAND="ssh -i $KEYS/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$KEYS/known_hosts -o StrictHostKeyChecking=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
export GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0
export GIT_DIR="$P/.git" GIT_COMMON_DIR="$P/.git" GIT_WORK_TREE="$P"
g() { git -C "$P" -c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.quotePath=false "$@"; }
say() { echo "⚠️ sync-brain: $*"; }
# Text git or GitHub wrote, or paths she named, inside a code block: no link previews, no mentions.
block() { printf '```\n'; tr -d '`'; printf '\n```\n'; }
# brain-files.py prints its own alerts (exit 0 or 3); anything else, a crash or a kill, is said here.
helper() {
  local out rc
  out=$(python3 "$FILES" "$@" 2>&1); rc=$?
  if [ "$rc" = 0 ] || [ "$rc" = 3 ]; then [ -z "$out" ] || printf '%s\n' "$out"
  elif [ "$1" = apply ]; then say "her copy of the brain is not fully updated (exit $rc); the next run finishes it first:"; block <<<"$out"
  else say "brain-files.py $1 failed (exit $rc), nothing pushed:"; block <<<"$out"; fi
  return "$rc"
}
# Stops the run if a change from $1 to $2 is outside ALLOWED, adds a link or a gitlink, or touches a
# .gitignore, .gitattributes or .gitmodules (git on the local machine reads them; the owner's own reach her copy).
refuse_outside() {
  local bad
  bad=$( (g diff --name-only --no-renames "$1" "$2" -- || echo "(git diff failed)") | grep -Ev "$ALLOWED"
    g diff --raw --no-renames "$1" "$2" -- | awk '$2 ~ /^1[26]0000$/ { sub(/^[^\t]*\t/, ""); print }'
    g diff --name-only --no-renames -z "$1" "$2" -- | python3 "$FILES" gitfiles || echo "(gitfiles check failed)")
  [ -z "$bad" ] && return
  echo "🚫 sync-brain: refused to push. These paths are outside what Telma may change:"
  block <<<"$bad"
  echo "Nothing was pushed, and nothing will be until they are gone."
  exit 0
}

[ -n "$REMOTE" ] || { say "no remote in $KEYS/remote"; exit 0; }
[ -d "$B" ] || { say "$B is missing"; exit 0; }
mkdir -p "$HOME/.cache" && exec 9>"$HOME/.cache/sync-brain.lock" || exit 0
if ! flock -n 9; then
  # A hung run keeps the lock, its git, ssh and python3 children too: say so once it's been an hour.
  started=$(cat "$HOME/.cache/sync-brain.started" 2>/dev/null)
  case $started in '' | *[!0-9]*) exit 0 ;; esac
  mins=$(( ($(date +%s) - started) / 60 ))
  [ "$mins" -ge 60 ] && say "stuck: a run started $mins min ago still holds the lock, so nothing syncs. Look for a hung git, ssh or python3."
  exit 0
fi
date +%s > "$HOME/.cache/sync-brain.started"
if [ ! -d "$P/.git" ]; then
  mkdir -p "$P" && git init -q -b main "$P" || { say "could not create $P"; exit 0; }
  # Same author as before. Her .git/config is mounted read-only in her sandbox.
  for k in user.name user.email; do
    v=$(git config --file "$B/.git/config" --get "$k" 2>/dev/null) && g config "$k" "$v"
  done
fi
[ -d "$P/.git/rebase-merge" ] || [ -d "$P/.git/rebase-apply" ] && g rebase --abort >/dev/null 2>&1

out=$(g fetch -q "$REMOTE" +main:refs/sync/github 2>&1) || { say "fetch failed:"; block <<<"$out"; exit 0; }
base=$(g rev-parse --verify -q 'refs/sync/github^{commit}') || { say "no main on GitHub"; exit 0; }
# What her copy held after the last run; her changes are her files against it.
given=$(g rev-parse --verify -q 'refs/sync/given^{commit}') || given=$base

# A refresh that didn't finish (killed, or a folder she made unwritable): finish it before reading her
# files, or what GitHub sent her would look like her own change and undo the owner's later work.
if pending=$(g rev-parse --verify -q 'refs/sync/pending^{commit}'); then
  g checkout -q -f --detach "$pending" || { say "checkout failed in $P"; exit 0; }
  g diff --name-status --no-renames -z "$given" "$pending" -- | helper apply "$P" "$B" || exit 0
  g update-ref refs/sync/given "$pending" && g update-ref -d refs/sync/pending && given=$pending
fi

g checkout -q -f --detach "$given" || { say "checkout failed in $P"; exit 0; }
find "$P" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} + || { say "could not empty $P"; exit 0; }
roots=() && while IFS= read -r n; do roots+=("$n"); done < <(g ls-tree --name-only "$given")
helper export "$B" "$P" "$Q" "${roots[@]}" || exit 0
# -f: no .gitignore, hers or GitHub's, hides anything she has. All of it is pushed or refused.
g add -A -f || { say "git add failed in $P"; exit 0; }
hers=$given
if ! g diff --cached --quiet; then
  g commit -q -m "brain: sync $(date -u +%FT%H:%MZ)" || { say "commit failed in $P"; exit 0; }
  hers=$(g rev-parse HEAD)
fi
refuse_outside "$given" "$hers"

new=$hers
if [ "$base" != "$given" ]; then
  if [ "$hers" = "$given" ]; then
    new=$base
  # Only her commit, and no rename detection: an edit must not follow a rename on the local machine into skills/.
  elif g rebase -q -Xno-renames --onto "$base" "$given" >/dev/null 2>&1; then
    new=$(g rev-parse HEAD)
    refuse_outside "$base" "$new"
  else
    conflicts=$(g diff --name-only --diff-filter=U)
    g rebase --abort >/dev/null 2>&1
    echo "⚠️ sync-brain: conflict with GitHub, nothing pushed. Telma and the local machine both changed these:"
    block <<<"$conflicts"
    echo "Copy GitHub's version over hers in $B, then redo her change."
    exit 0
  fi
fi
if [ "$new" != "$base" ]; then
  out=$(g push -q "$REMOTE" "$new:refs/heads/main" 2>&1) || { say "push failed:"; block <<<"$out"; exit 0; }
  g update-ref refs/sync/github "$new"
fi

# Her copy held $hers; it gets what GitHub changed. Pending until it all landed: a failure is finished
# next run, replaying only GitHub's changes, never her own.
g update-ref refs/sync/given "$hers"
[ "$new" = "$hers" ] && exit 0
g update-ref refs/sync/pending "$new"
g checkout -q -f --detach "$new" || { say "checkout failed in $P"; exit 0; }
g diff --name-status --no-renames -z "$hers" "$new" -- | helper apply "$P" "$B" || exit 0
g update-ref refs/sync/given "$new" && g update-ref -d refs/sync/pending
