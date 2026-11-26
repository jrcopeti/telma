#!/usr/bin/env bash
# Hourly, ten minutes after brain-triage, as a Hermes no-agent job: print what Telma saved to her memory or
# skills since the last run, and what changed in the brain's skills (~/brain/skills). Memory and skill_manage
# stay on so she learns; this is how the owner sees what she saved, and undoes a bad entry with the restore
# line it prints. A brain-skill change shows here whoever made it: her process, or a merge arriving from GitHub.
# The snapshot repos are outside the sandbox's mounts.
# Silent when nothing changed. The first run only takes the baseline.
set -u
H=${HERMES_HOME:-$HOME/.hermes}
A=${MEMORY_AUDIT:-$HOME/.memory-audit.git}
B=${BRAIN_DIR:-$HOME/brain}
BA=${BRAIN_SKILLS_AUDIT:-$HOME/.brain-skills-audit.git}
MAX=1500
# Hermes starts scripts in $H/scripts, inside the work tree, where the pathspecs below would miss.
cd "$H" || { echo "⚠️ memory-diff: no $H"; exit 0; }
# $1 snapshot repo, $2 work tree. The repo's config is ours: nothing in the work tree is read as config.
g() { local a=$1 w=$2; shift 2; git --git-dir="$a" --work-tree="$w" -c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.quotePath=false "$@"; }

# watch REPO TREE LABEL PATHSPEC...: snapshot the paths, print the diff since the last run. Silent when nothing changed.
# Pathspecs starting ":(exclude)" are Hermes's own bookkeeping files. `add -f` and the attributes below make
# a .gitignore or .gitattributes planted in the work tree (she can write both) unable to hide or blank a change.
watch() {
  local a=$1 w=$2 label=$3 out d nested; shift 3
  if [ ! -d "$a" ]; then
    git init -q --bare "$a" && g "$a" "$w" config core.bare false
  fi
  # Every run, so a repo made by an older version gets it too.
  mkdir -p "$a/info" && echo '* diff' > "$a/info/attributes"
  # A nested repo becomes a gitlink: its files are not snapshotted, so it is said every run.
  nested=$(for d in "$@"; do [[ $d == :* ]] || find "$w/$d" -name .git -not -path "$w/skills/.hub/*" 2>/dev/null; done | head -n 3)
  [ -z "$nested" ] || { echo "⚠️ memory-diff: a nested git folder hides its files from this check:"; echo '```'; echo "${nested//\`/}"; echo '```'; }
  if ! g "$a" "$w" rev-parse -q --verify HEAD >/dev/null; then
    out=$(g "$a" "$w" add -f -A -- "$@" 2>&1 && g "$a" "$w" -c user.name=audit -c user.email=audit@localhost commit -q --allow-empty -m baseline 2>&1) ||
      echo "⚠️ memory-diff: baseline failed: $out"
    return
  fi
  out=$(g "$a" "$w" add -f -A -- "$@" 2>&1) || { echo "⚠️ memory-diff: git add failed: $out"; return; }
  g "$a" "$w" diff --cached --quiet && return
  d=$(g "$a" "$w" diff --cached --stat=80 && echo && g "$a" "$w" diff --cached --unified=1 -- "$@")
  g "$a" "$w" -c user.name=audit -c user.email=audit@localhost commit -qm "$(date -u +%FT%H:%MZ)" 2>&1 || echo "⚠️ memory-diff: commit failed"
  echo "$label (undo: git --git-dir=$a --work-tree=$w restore --source=HEAD~1 -- <path>):"
  # In a code block, backticks stripped: Discord doesn't preview a URL the agent saved (that would send it).
  d=${d//\`/}
  echo '```'; echo "${d:0:$MAX}"; echo '```'
  [ ${#d} -gt $MAX ] && echo "… cut. Full diff: git --git-dir=$a show HEAD"
}

watch "$A" "$H" "🧠 saved to memory or skills since the last check" memories skills \
  ':(exclude)skills/.usage.json' ':(exclude)skills/.usage.json.lock' ':(exclude)skills/.curator_state' \
  ':(exclude)skills/.bundled_manifest' ':(exclude)skills/.hub/audit.log'
if [ -L "$B/skills" ]; then echo "⚠️ memory-diff: $B/skills is a link, so the brain's skills are not watched"
elif [ -d "$B/skills" ] || { [ -d "$BA" ] && [ -d "$B" ]; }; then
  watch "$BA" "$B" "📚 brain skills changed since the last check (a merge from GitHub shows here too)" skills
fi
exit 0
