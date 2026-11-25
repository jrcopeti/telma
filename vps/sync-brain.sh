#!/usr/bin/env bash
# Every 15 min (Hermes no-agent job, on the host): push what Telma changed in the brain, pull the rest.
# Her sandbox writes the brain, .git included, so host git never runs there. This keeps its own clone
# in $P, copies her files into it with brain-files.py (plain files only, never through a link), pushes
# ALLOWED paths to main and her rule-file changes (PROPOSE) to a branch for the owner to review, then
# writes GitHub's files back into her copy the same way: rule files come back as main has them.
# Silent on success: the job posts whatever this prints to Discord.
set -u
B=${BRAIN_DIR:-$HOME/brain}
P=${BRAIN_PUSH_DIR:-$HOME/.local/share/brain-push}
Q=${BRAIN_QUARANTINE:-$HOME/brain-quarantine}
KEYS=$HOME/.config/brain-deploy
REMOTE=${BRAIN_REMOTE:-$(cat "$KEYS/remote" 2>/dev/null)}
FILES=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/brain-files.py
ALLOWED='^(inbox|sources|notes|guidelines|decisions|projects|intents)/|^index\.md$'
PROPOSE='^skills/|^(AGENTS|CLAUDE|taste)\.md$'
PBR=telma/proposals

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
# Hermes writes a file as a temp file next to it, then renames it over the target; the rename can't replace a
# read-only mount, and the temp file stays. Says which rule file beside $1 (in commit $2) it is closest to.
failed_write() {
  local dir=${1%/*} f n best= low=999999
  [ "$dir" = "$1" ] && dir=
  while IFS= read -r f; do
    [[ $f =~ $PROPOSE ]] || continue
    n=$(diff <(g cat-file blob "$2:$f" 2>/dev/null) <(g cat-file blob "$2:$1" 2>/dev/null) | wc -l)
    [ "$n" -lt "$low" ] && best=$f low=$n
  done < <(g ls-tree --name-only "$2" ${dir:+"$dir/"})
  echo "A failed edit left a temp file (Hermes can't rename one over a read-only mount). The edit is lost: delete the temp file and make the change by hand."
  printf 'edit to: %s\ntemp file: %s\n' "${best:-a file beside it}" "$1" | block
}
# Stops the run if a change from $1 to $2 is outside the pattern $3, adds a link or a gitlink, or touches a
# .gitignore, .gitattributes or .gitmodules (git on the local machine reads them; the owner's own reach her copy).
refuse_outside() {
  local bad
  bad=$( (g diff --name-only --no-renames "$1" "$2" -- || echo "(git diff failed)") | grep -Ev "$3"
    g diff --raw --no-renames "$1" "$2" -- | awk '$2 ~ /^1[26]0000$/ { sub(/^[^\t]*\t/, ""); print }'
    g diff --name-only --no-renames -z "$1" "$2" -- | python3 "$FILES" gitfiles || echo "(gitfiles check failed)")
  [ -z "$bad" ] && return
  echo "🚫 sync-brain: refused to push. These paths are outside what Telma may change:"
  block <<<"$bad"
  while IFS= read -r tmp; do [ -z "$tmp" ] || failed_write "$tmp" "$2"; done < <(grep -E '(^|/)\.hermes-tmp\.[^/]*$' <<<"$bad")
  echo "Nothing was pushed, and nothing will be until they are gone."
  exit 0
}

declare -A kept dropped all final
# Each change from $1 to $2 as three NUL-ended fields: path, new mode (0: deleted), new object.
changes() {
  local meta path om nm os ns st
  g diff --raw --no-renames --no-abbrev -z "$1" "$2" -- | while IFS= read -r -d '' meta && IFS= read -r -d '' path; do
    read -r om nm os ns st <<<"${meta#:}"
    [ "$st" = D ] && nm=0
    printf '%s\0%s\0%s\0' "$path" "$nm" "$ns"
  done
}
# A commit on $1 holding only the changes from $2 to $3 whose path matches $4: $3 itself if that's all of them,
# $1 if there are none.
subset() {
  local idx=$P/.git/sync-index tree path nm ns
  rm -f "$idx"
  GIT_INDEX_FILE=$idx g read-tree "$1" || return 1
  changes "$2" "$3" | while IFS= read -r -d '' path && IFS= read -r -d '' nm && IFS= read -r -d '' ns; do
    [[ $path =~ $4 ]] && printf '%s %s\t%s\0' "$nm" "$ns" "$path"
  done | GIT_INDEX_FILE=$idx g update-index -z --index-info || return 1
  tree=$(GIT_INDEX_FILE=$idx g write-tree) || return 1
  if [ "$tree" = "$(g rev-parse "$1^{tree}")" ]; then echo "$1"
  elif [ "$tree" = "$(g rev-parse "$3^{tree}")" ]; then echo "$3"
  else g commit-tree "$tree" -p "$1" -m "brain: sync $(date -u +%FT%H:%MZ)"; fi
}
# "mode object" of path $2 in commit $1, empty if it isn't there.
ent() {
  local row mode sha
  row=$(g ls-tree -z "$1" -- "$2" | tr -d '\0') || return 0
  [[ $row == *$'\t'"$2" ]] || return 0
  read -r mode _ sha <<<"${row%%$'\t'*}"
  echo "$mode $sha"
}
# The open proposal $1 against main: all = what it changes, kept = what main hasn't touched, dropped = what
# main changed too. What main now holds as the proposal does (the owner merged it) is in none of them.
read_proposal() {
  local mb path nm ns b m mode sha
  kept=() dropped=() all=()
  [ -n "$1" ] || return 0
  mb=$(g merge-base "$base" "$1" 2>/dev/null) || mb=$(g hash-object -t tree -w --stdin </dev/null)
  while IFS= read -r -d '' path && IFS= read -r -d '' nm && IFS= read -r -d '' ns; do
    all[$path]="$nm $ns"
    b=$(ent "$base" "$path"); m=$(ent "$mb" "$path")
    [ "$nm" = 0 ] && ns= || ns="$nm $ns"
    [ "$b" = "$ns" ] && continue
    if [ "$b" = "$m" ]; then kept[$path]=${all[$path]}; else dropped[$path]=1; fi
  done < <(changes "$mb" "$1")
}
# $3 (her version) merged into $1 (the proposal's) from their common $2; where they collide, both sides' lines stay.
merge3() {
  local d=$P/.git/sync-merge
  mkdir -p "$d" && g cat-file blob "$1" >"$d/o" && g cat-file blob "$2" >"$d/b" && g cat-file blob "$3" >"$d/t" &&
    git merge-file -p --union "$d/o" "$d/b" "$d/t" >"$d/m" 2>/dev/null && g hash-object -w --stdin <"$d/m"
}
# final[path]="mode object" unless main already has it that way.
put() {
  local mode sha
  [ "${2%% *}" = 0 ] && sha= || sha=$2
  [ "$(ent "$base" "$1")" = "$sha" ] || final[$1]=$2
}
# Adds her rule-file changes (hers against given) to the open proposal $cur, or starts one, on top of main.
# Nothing is pushed or deleted unless the proposal changes, so a run that fails halfway repeats safely.
propose() {
  local path nm ns o om go merged same idx=$P/.git/sync-index tree pn out link= slug
  read_proposal "$cur"
  final=()
  for path in "${!kept[@]}"; do put "$path" "${kept[$path]}"; done
  while IFS= read -r -d '' path && IFS= read -r -d '' nm && IFS= read -r -d '' ns; do
    [[ $path =~ $PROPOSE ]] || continue
    if [ "$nm" != 0 ]; then
      o=$(g rev-parse -q --verify "$base:$path"); go=$(g rev-parse -q --verify "$given:$path")
      [ -z "${kept[$path]+x}" ] || { read -r om o <<<"${kept[$path]}"; [ "$om" = 0 ] && o=; }
      [ -n "$go" ] || go=$(g hash-object -t blob -w --stdin </dev/null)
      if [ -n "$o" ] && [ "$o" != "$go" ] && [ "$o" != "$ns" ]; then merged=$(merge3 "$o" "$go" "$ns") && ns=$merged; fi
    fi
    put "$path" "$nm $ns"
  done < <(changes "$given" "$hers")
  same=1; [ ${#final[@]} = ${#all[@]} ] || same=0
  for path in "${!final[@]}"; do [ "${all[$path]-}" = "${final[$path]}" ] || same=0; done
  [ -n "$cur" ] && [ ${#final[@]} -gt 0 ] && [ "$same" = 1 ] && { g update-ref refs/sync/proposed "$cur"; return 0; }
  [ -n "$cur" ] || [ ${#final[@]} -gt 0 ] || return 0
  if [ ${#final[@]} = 0 ]; then
    out=$(g push -q --force-with-lease="refs/heads/$PBR:$cur" "$REMOTE" ":refs/heads/$PBR" 2>&1) || { say "could not delete $PBR:"; block <<<"$out"; return 1; }
    g update-ref -d refs/sync/proposals; g update-ref -d refs/sync/proposed
  else
    rm -f "$idx"
    { GIT_INDEX_FILE=$idx g read-tree "$base" &&
      for path in "${!final[@]}"; do printf '%s\t%s\0' "${final[$path]}" "$path"; done | GIT_INDEX_FILE=$idx g update-index -z --index-info &&
      tree=$(GIT_INDEX_FILE=$idx g write-tree) && pn=$(g commit-tree "$tree" -p "$base" -m "brain: Telma proposes changes to rule files"); } ||
      { say "git failed building the proposal in $P"; return 1; }
    out=$(g push -q --force-with-lease="refs/heads/$PBR:$cur" "$REMOTE" "$pn:refs/heads/$PBR" 2>&1) || { say "push of $PBR failed:"; block <<<"$out"; return 1; }
    g update-ref refs/sync/proposals "$pn"; g update-ref refs/sync/proposed "$pn"
    if [ -z "$cur" ]; then
      case $REMOTE in *github.com[:/]*) slug=${REMOTE#*github.com[:/]}; link=" <https://github.com/${slug%.git}/compare/main...$PBR>" ;; esac
      echo "💡 sync-brain: Telma changed rule files. Her copy runs main's version again; her changes are on the branch $PBR, for you to review and merge:$link"
      printf '%s\n' "${!final[@]}" | block
    fi
  fi
  [ ${#dropped[@]} = 0 ] || { echo "⚠️ sync-brain: dropped from $PBR, because main changed them too (main's version wins):"; printf '%s\n' "${!dropped[@]}" | block; }
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
# Her proposal branch: $cur is its tip, empty once the owner deletes it. $held is what this script last saw there.
heads=$(g ls-remote --heads "$REMOTE" 2>&1) || { say "ls-remote failed:"; block <<<"$heads"; exit 0; }
cur=$(awk -v r="refs/heads/$PBR" '$2 == r { print $1 }' <<<"$heads")
if [ -n "$cur" ]; then
  out=$(g fetch -q "$REMOTE" "+refs/heads/$PBR:refs/sync/proposals" 2>&1) || { say "fetch of $PBR failed:"; block <<<"$out"; exit 0; }
  cur=$(g rev-parse --verify -q 'refs/sync/proposals^{commit}') || { say "no $PBR after fetching it"; exit 0; }
else
  g update-ref -d refs/sync/proposals
fi
held=$(g rev-parse --verify -q 'refs/sync/proposed^{commit}')
if [ -z "$cur" ] && [ -n "$held" ]; then
  read_proposal "$held"
  if [ $((${#kept[@]} + ${#dropped[@]})) -gt 0 ]; then
    echo "🗑️ sync-brain: $PBR was deleted, so Telma's proposal is dropped. Her copy already has main's version of:"
    printf '%s\n' "${!kept[@]}" "${!dropped[@]}" | block
  fi
  g update-ref -d refs/sync/proposed
fi
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
refuse_outside "$given" "$hers" "$ALLOWED|$PROPOSE"

# Her changes under ALLOWED go to main; the rest of what she changed (the rule files) is proposed below.
mine=$(subset "$given" "$given" "$hers" "$ALLOWED") || { say "git failed in $P"; exit 0; }
new=$mine
if [ "$base" != "$given" ]; then
  if [ "$mine" = "$given" ]; then
    new=$base
  # Only her commit, and no rename detection: an edit must not follow a rename on the local machine into skills/.
  elif g checkout -q -f --detach "$mine" && g rebase -q -Xno-renames --onto "$base" "$given" >/dev/null 2>&1; then
    new=$(g rev-parse HEAD)
    refuse_outside "$base" "$new" "$ALLOWED"
  else
    conflicts=$(g diff --name-only --diff-filter=U)
    g rebase --abort >/dev/null 2>&1
    echo "⚠️ sync-brain: conflict with GitHub, nothing pushed. Telma and the local machine both changed these:"
    block <<<"$conflicts"
    echo "Copy GitHub's version over hers in $B, then redo her change."
    exit 0
  fi
fi
# A proposal that can't be saved doesn't hold back main (her notes still go out).
propose; proposed=$?
if [ "$new" != "$base" ]; then
  out=$(g push -q "$REMOTE" "$new:refs/heads/main" 2>&1) || { say "push failed:"; block <<<"$out"; exit 0; }
  g update-ref refs/sync/github "$new"
fi

# Her copy held $hers; it gets what GitHub changed. Pending until it all landed: a failure is finished
# next run, replaying only GitHub's changes, never her own.
# A proposal that couldn't be saved stops here, after main: her copy and `given` stay as they were, so the
# next run finds the same edits, merges them against the same base, and her copy isn't refreshed over them.
[ "$proposed" = 0 ] || exit 0
g update-ref refs/sync/given "$hers"
[ "$new" = "$hers" ] && exit 0
g update-ref refs/sync/pending "$new"
g checkout -q -f --detach "$new" || { say "checkout failed in $P"; exit 0; }
g diff --name-status --no-renames -z "$hers" "$new" -- | helper apply "$P" "$B" || exit 0
g update-ref refs/sync/given "$new" && g update-ref -d refs/sync/pending
