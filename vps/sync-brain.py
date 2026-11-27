#!/usr/bin/env python3
# Every 15 min (Hermes no-agent job, on the host): push what Telma changed in the brain, pull the rest.
# Her sandbox writes the brain, .git included, so host git never runs there. This keeps its own clone
# in P, copies her files into it with brain-files.py (plain files only, never through a link), pushes
# ALLOWED paths to main and her rule-file changes (PROPOSE) to a branch for the owner to review, then
# writes GitHub's files back into her copy the same way: rule files come back as main has them.
# Silent on success: the job posts whatever this prints to Discord.
#
# Laid out like the bash script it replaced. The bash had no `set -e`: a failed command stopped the run,
# was ignored or fell back, one call at a time. Each git() call below says which, in a comment.
import fcntl
import os
import re
import shutil
import subprocess
import sys
import time

UTF8 = {"encoding": "utf-8", "errors": "surrogateescape"}  # a name is bytes, not always UTF-8
sys.stdout.reconfigure(line_buffering=True, **UTF8)

HOME = os.environ["HOME"]
B = os.environ.get("BRAIN_DIR") or HOME + "/brain"
P = os.environ.get("BRAIN_PUSH_DIR") or HOME + "/.local/share/brain-push"
Q = os.environ.get("BRAIN_QUARANTINE") or HOME + "/brain-quarantine"
KEYS = HOME + "/.config/brain-deploy"


def read_text(path):
    try:
        with open(path, **UTF8) as f:
            return f.read().rstrip("\n")
    except OSError:
        return ""


REMOTE = os.environ.get("BRAIN_REMOTE") or read_text(KEYS + "/remote")
FILES = os.path.dirname(os.path.abspath(__file__)) + "/brain-files.py"
# `$` is \Z: a name ending in a newline must not match as if it didn't.
FOLDERS = r"^(inbox|sources|notes|guidelines|decisions|projects|intents)/"
ALLOWED = FOLDERS + r"|^index\.md\Z"
PROPOSE = r"^skills/|^(AGENTS|CLAUDE|taste)\.md\Z"
PBR = "telma/proposals"
ZERO = "0" * 40

os.environ["GIT_SSH_COMMAND"] = (
    f"ssh -i {KEYS}/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile={KEYS}/known_hosts"
    " -o StrictHostKeyChecking=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=4")
os.environ.update(GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0",
                  GIT_DIR=P + "/.git", GIT_COMMON_DIR=P + "/.git", GIT_WORK_TREE=P)

lock_fd = None  # bash's fd 9: git, ssh and python3 inherit it, so a hung child keeps the lock


class Result:
    def __init__(self, rc, raw):
        self.rc, self.raw = rc, raw
        self.out = raw.decode(**UTF8)
        self.val = self.out.rstrip("\n")  # what `$(...)` would hold
        self.ok = rc == 0


def run(argv, input=None, stdin=None, stdout=subprocess.PIPE, stderr=None, env=None):
    """Run a child with only the lock fd handed down. stderr None: it shows, as in bash."""
    kw = {"input": input.encode(**UTF8) if isinstance(input, str) else input} if input is not None \
        else {"stdin": stdin if stdin is not None else subprocess.DEVNULL}
    try:
        p = subprocess.run(argv, stdout=stdout, stderr=stderr, env=env, pass_fds=(lock_fd,) if lock_fd is not None else (), **kw)
    except OSError as e:  # a program that isn't there fails like a shell's "command not found"
        print(f"{argv[0]}: {e.strerror}", file=sys.stderr)
        return Result(127, b"")
    return Result(p.returncode if p.returncode >= 0 else 128 - p.returncode, p.stdout or b"")


def git(*args, input=None, stdin=None, stdout=subprocess.PIPE, stderr=None, index=None):
    """bash's g(): git in P, no hooks, no fsmonitor, names as they are. Never raises; the caller reads .ok."""
    env = dict(os.environ, GIT_INDEX_FILE=index) if index else None
    return run(["git", "-C", P, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                "-c", "core.quotePath=false", *args], input, stdin, stdout, stderr, env)


def rev(spec):
    """`rev-parse --verify -q`: the object, or "" if there is none."""
    r = git("rev-parse", "--verify", "-q", spec)
    return r.val if r.ok else ""


def say(text):
    print("⚠️ sync-brain: " + text)


def block(text):
    """Text git or GitHub wrote, or paths she named, inside a code block: no link previews, no mentions.
    Like the bash, the text gets a newline and then another before the closing fence."""
    print("```\n" + text.replace("`", "") + "\n\n```")


def cut100(line):
    """`cut -c1-100`: 100 bytes, through a character if that is where 100 falls."""
    return line.encode(**UTF8)[:100].decode(**UTF8)


def lower(s):
    """ASCII only, as in the C locale (and mawk's tolower)."""
    return s.translate({c: c + 32 for c in range(65, 91)})


def helper(*args, input=None):
    """brain-files.py prints its own alerts (exit 0 or 3); anything else, a crash or a kill, is said here."""
    r = run(["python3", FILES, *args], input, stderr=subprocess.STDOUT)
    if r.rc in (0, 3):
        if r.val:
            print(r.val)
    elif args[0] == "apply":
        say(f"her copy of the brain is not fully updated (exit {r.rc}); the next run finishes it first:")
        block(r.val)
    else:
        say(f"brain-files.py {args[0]} failed (exit {r.rc}), nothing pushed:")
        block(r.val)
    return r.rc


def edit_target(c, tmp):
    """Hermes writes a file as a temp file next to it, then renames it over the target; the rename can't replace a
    read-only mount, and the temp file stays. The rule file beside temp file `tmp` (in commit c) most of whose
    lines the temp file holds (it is that file plus the edit), if it holds half or more and no other file holds
    as large a share; else "unknown"."""
    d = tmp.rpartition("/")[0]
    best, top, tie = "", 0, False
    held = {x for x in git("cat-file", "blob", f"{c}:{tmp}", stderr=subprocess.DEVNULL).out.split("\n") if x}
    # ignored if it fails: no candidates, "unknown"
    listing = git("ls-tree", "-z", "--name-only", c, *([d + "/"] if d else []))
    for f in listing.out.split("\0")[:-1]:
        if not (re.search(PROPOSE, f) and f != tmp):
            continue
        lines = [x for x in git("cat-file", "blob", f"{c}:{f}", stderr=subprocess.DEVNULL).out.split("\n") if x]
        if not lines:
            continue
        pct = sum(1 for x in lines if x in held) * 100 // len(lines)
        if pct > top:
            best, top, tie = f, pct, False
        elif pct == top:
            tie = True
    return best if not tie and top >= 50 else "unknown"


def short(n, text):
    """A list of lines for Discord (2000 characters a post): the first n lines of text, each cut short, then a count."""
    lines = text.split("\n")
    shown = [cut100(x) for x in lines[:n]]
    if len(lines) > n:
        shown.append(f"and {len(lines) - n} more")
    block("\n".join(shown))


def failed_writes(c, tmps):
    """One post for all the temp files (in commit c): what happened once, then each temp file with its target."""
    print("A failed edit left a temp file (Hermes can't rename one over a read-only mount). The edit is lost: "
          "delete the temp file and make the change by hand.")
    rows = [f"temp file: {t}\nedit to:   {edit_target(c, t)}" for t in tmps[:3]]
    if len(tmps) > 3:
        rows.append(f"and {len(tmps) - 3} more")
    block("\n".join(cut100(x) for x in "\n".join(rows).split("\n")))


def refuse_outside(a, b, pattern):
    """Stops the run if a change from a to b is outside the pattern, adds a link or a gitlink, or touches a
    .gitignore, .gitattributes or .gitmodules (git on the local machine reads them; the owner's own reach her copy),
    or is a .hermes-tmp.* file (or inside such a folder) anywhere, even under an allowed path (a failed write;
    deleting it lifts the refusal)."""
    live = git("diff", "--name-only", "--no-renames", "--diff-filter=d", "-z", a, b, "--")  # failure: refused below
    tmps = [t for t in live.out.split("\0")[:-1] if re.search(r"(^|/)\.hermes-tmp\.[^/]*(/|\Z)", t)]
    bad = []
    # The name lists are git's own, not -z: git quotes a name with a newline or a control character, and the
    # quoted form is outside every pattern, so such a name is refused.
    names = git("diff", "--name-only", "--no-renames", a, b, "--")
    bad += [x for x in names.out.split("\n")[:-1] + ([] if names.ok else ["(git diff failed)"])
            if not re.search(pattern, x)]
    raw = git("diff", "--raw", "--no-renames", a, b, "--")
    for line in raw.out.split("\n")[:-1]:  # a link (120000) or a gitlink (160000)
        fields = line.split(None, 2)
        if len(fields) > 1 and fields[1] in ("120000", "160000"):
            bad.append(line.partition("\t")[2])
    if not raw.ok:
        bad.append("(git diff failed)")
    z = git("diff", "--name-only", "--no-renames", "-z", a, b, "--")
    gf = run(["python3", FILES, "gitfiles"], z.raw)
    bad += gf.out.split("\n")[:-1]
    if not z.ok or not gf.ok:
        bad.append("(gitfiles check failed)")
    if not live.ok:
        bad.append("(git diff failed)")
    if not bad and not tmps:
        return
    if bad:
        print("🚫 sync-brain: refused to push. These paths are outside what Telma may change:")
        short(8, "\n".join(bad))
    else:
        print("🚫 sync-brain: refused to push. A failed write left a temp file.")
    if tmps:
        failed_writes(b, tmps)
    print("Nothing was pushed, and nothing will be until they are gone.")
    sys.exit(0)


def changes(a, b):
    """Each change from a to b as (path, new mode (0: deleted), new object)."""
    fields = git("diff", "--raw", "--no-renames", "--no-abbrev", "-z", a, b, "--").out.split("\0")
    rows = []
    for meta, path in zip(fields[0::2], fields[1::2]):
        _, nm, _, ns, st = (meta[1:].split() + [""] * 5)[:5]
        rows.append((path, "0" if st == "D" else nm, ns))
    return rows


def subset(parent, a, b, pattern):
    """A commit on parent holding only the changes from a to b whose path matches pattern: b itself if that's
    all of them, parent if there are none. None if git fails."""
    idx = P + "/.git/sync-index"
    silent_rm(idx)
    if not git("read-tree", parent, index=idx).ok:
        return None
    entries = "".join(f"{nm} {ns}\t{path}\0" for path, nm, ns in changes(a, b) if re.search(pattern, path))
    if not git("update-index", "-z", "--index-info", input=entries, index=idx).ok:
        return None
    w = git("write-tree", index=idx)
    if not w.ok:
        return None
    tree = w.val
    if tree == git("rev-parse", parent + "^{tree}").val:
        return parent
    if tree == git("rev-parse", b + "^{tree}").val:
        return b
    c = git("commit-tree", tree, "-p", parent, "-m", "brain: sync " + stamp())
    return c.val if c.ok else None


def stamp():
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())


def silent_rm(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def ent(c, path):
    """"mode object" of path in commit c, empty if it isn't there."""
    row = git("ls-tree", "-z", c, "--", path).out.replace("\0", "")
    if not row.endswith("\t" + path):
        return ""
    mode, _, sha = row.split("\t", 1)[0].split(None, 2)
    return f"{mode} {sha}"


def split2(s):
    """`read -r a b`: two fields, empty if missing."""
    f = s.split(None, 1)
    return (f + ["", ""])[:2]


def read_proposal(base, c):
    """The open proposal c against main: all = what it changes, kept = what main hasn't touched, dropped = what
    main changed too. What main now holds as the proposal does (the owner merged it) is in none of them."""
    kept, dropped, all_ = {}, {}, {}
    if not c:
        return all_, kept, dropped
    mb = git("merge-base", base, c, stderr=subprocess.DEVNULL)
    mb = mb.val if mb.ok else git("hash-object", "-t", "tree", "-w", "--stdin", input="").val  # fall back: empty tree
    for path, nm, ns in changes(mb, c):
        all_[path] = f"{nm} {ns}"
        b, m = ent(base, path), ent(mb, path)
        ns = "" if nm == "0" else f"{nm} {ns}"
        if b == ns:
            continue
        if b == m:
            kept[path] = all_[path]
        else:
            dropped[path] = 1
    return all_, kept, dropped


def blob_to(sha, path):
    """Object sha (or nothing, if empty) into the file at path."""
    with open(path, "wb") as f:
        return True if not sha else git("cat-file", "blob", sha, stdout=f).ok


def merge3(o, b, t):
    """t (her version) merged into o (the proposal's) from their common b; where they collide, both sides' lines
    stay. The object, or None."""
    d = P + "/.git/sync-merge"
    try:
        os.makedirs(d, exist_ok=True)
        ok = blob_to(o, d + "/o") and blob_to(b, d + "/b") and blob_to(t, d + "/t")
        if not ok:
            return None
        with open(d + "/m", "wb") as m:  # plain git, not git(): no -C, as before
            if run(["git", "merge-file", "-p", "--union", d + "/o", d + "/b", d + "/t"],
                   stdout=m, stderr=subprocess.DEVNULL).rc != 0:
                return None
        with open(d + "/m", "rb") as m:
            h = git("hash-object", "-w", "--stdin", stdin=m)
        return h.val if h.ok else None
    except OSError:
        return None


def set_index(c, mode, sha):
    """A commit on c with index.md set to mode and object sha (mode 0: gone); c itself if that changes nothing."""
    idx = P + "/.git/sync-index"
    if mode == "0":
        sha = ZERO
    silent_rm(idx)
    if not git("read-tree", c, index=idx).ok:
        return None
    if not git("update-index", "-z", "--index-info", input=f"{mode} {sha}\tindex.md\0", index=idx).ok:
        return None
    w = git("write-tree", index=idx)
    if not w.ok:
        return None
    if w.val == git("rev-parse", c + "^{tree}").val:
        return c
    n = git("commit-tree", w.val, "-p", c, "-m", "brain: sync " + stamp())
    return n.val if n.ok else None


def merge_index(new, given, hers):
    """new, with index.md as her copy's version merged by line into it, against the one last synced (given).
    Git would call neighbouring edits a conflict; here both stay, and where both changed a line, both versions.
    None if it can't be merged."""
    om, oo = split2(ent(hers, "index.md"))
    bm, bo = split2(ent(given, "index.md"))
    if (om, oo) == (bm, bo):
        return new
    h, sha = split2(ent(new, "index.md"))
    # Her change is already in new when an earlier run pushed it and then stopped before moving `given` on.
    if oo and oo == git("rev-parse", "-q", "--verify", "refs/sync/index-pushed").val:
        return new
    if not om:
        # She deleted it: that stands only if the owner left it alone.
        if (h, sha) != (bm, bo):
            return new
        mode, merged = "0", ""
    else:
        # Only a plain file is merged, on both sides: a link or gitlink is no text. The owner deleting it while she
        # edited it is no merge either: her lines alone would be a truncated index.
        if om not in ("100644", "100755"):
            return None
        if h not in ("100644", "100755") and not (not h and not bo):
            return None
        d = P + "/.git/sync-merge"
        try:
            os.makedirs(d, exist_ok=True)
            if not (blob_to(bo, d + "/b") and blob_to(sha, d + "/o") and blob_to(oo, d + "/t")):
                return None
            with open(d + "/m", "wb") as m:
                secs = os.environ.get("BRAIN_MERGE_SECS") or "20"
                if run(["timeout", secs, "python3", FILES, "mergelines", d + "/b", d + "/o", d + "/t"], stdout=m).rc != 0:
                    return None
            with open(d + "/m", "rb") as m:
                hm = git("hash-object", "-w", "--stdin", stdin=m)
        except OSError:
            return None
        if not hm.ok:
            return None
        merged = hm.val
        mode = h or om
    return set_index(new, mode, merged)


def propose(base, given, hers, cur):
    """Adds her rule-file changes (hers against given) to the open proposal cur, or starts one, on top of main.
    Nothing is pushed or deleted unless the proposal changes, so a run that fails halfway repeats safely.
    False if the proposal could not be saved."""
    all_, kept, dropped = read_proposal(base, cur)
    final = {}

    def put(path, val):
        sha = "" if val.split(" ")[0] == "0" else val
        if ent(base, path) != sha:
            final[path] = val

    for path, val in kept.items():
        put(path, val)
    for path, nm, ns in changes(given, hers):
        if not re.search(PROPOSE, path):
            continue
        if nm != "0":
            o, go = rev(f"{base}:{path}"), rev(f"{given}:{path}")
            if path in kept:
                om, o = split2(kept[path])
                if om == "0":
                    o = ""
            if not go:
                go = git("hash-object", "-t", "blob", "-w", "--stdin", input="").val
            if o and o != go and o != ns:
                merged = merge3(o, go, ns)
                if merged:
                    ns = merged
        put(path, f"{nm} {ns}")
    same = len(final) == len(all_) and all(all_.get(p) == v for p, v in final.items())
    if cur and final and same:
        git("update-ref", "refs/sync/proposed", cur)  # ignored if it fails
        return True
    if not cur and not final:
        return True
    if not final:
        r = git("push", "-q", f"--force-with-lease=refs/heads/{PBR}:{cur}", REMOTE, f":refs/heads/{PBR}",
                stderr=subprocess.STDOUT)
        if not r.ok:
            say(f"could not delete {PBR}:")
            block(r.val)
            return False
        git("update-ref", "-d", "refs/sync/proposals")  # ignored if it fails
        git("update-ref", "-d", "refs/sync/proposed")  # ignored if it fails
    else:
        idx = P + "/.git/sync-index"
        silent_rm(idx)
        entries = "".join(f"{val}\t{path}\0" for path, val in final.items())
        ok = git("read-tree", base, index=idx).ok and git("update-index", "-z", "--index-info", input=entries, index=idx).ok
        w = git("write-tree", index=idx) if ok else None
        pn = git("commit-tree", w.val, "-p", base, "-m", "brain: Telma proposes changes to rule files") if w and w.ok else None
        if not (pn and pn.ok):
            say(f"git failed building the proposal in {P}")
            return False
        pn = pn.val
        r = git("push", "-q", f"--force-with-lease=refs/heads/{PBR}:{cur}", REMOTE, f"{pn}:refs/heads/{PBR}",
                stderr=subprocess.STDOUT)
        if not r.ok:
            say(f"push of {PBR} failed:")
            block(r.val)
            return False
        git("update-ref", "refs/sync/proposals", pn)  # ignored if it fails
        git("update-ref", "refs/sync/proposed", pn)  # ignored if it fails
        if not cur:
            link = ""
            m = re.search(r"github\.com[:/]", REMOTE)
            if m:
                slug = REMOTE[m.end():]
                link = f" <https://github.com/{slug[:-4] if slug.endswith('.git') else slug}/compare/main...{PBR}>"
            print("💡 sync-brain: Telma changed rule files. Her copy runs main's version again; her changes are on "
                  f"the branch {PBR}, for you to review and merge:{link}")
            block("\n".join(final))
    if dropped:
        print(f"⚠️ sync-brain: dropped from {PBR}, because main changed them too (main's version wins):")
        block("\n".join(dropped))
    return True


def fm_name(data):
    """The frontmatter name in the first 8 KB of a SKILL.md: CRLF, a BOM, quotes and a trailing comment tolerated
    (a comment alone is no name); lowercase; an empty one is no name. None if there is none."""
    lines = data[:8192].decode(**UTF8).split("\n")
    if lines[-1] == "":
        lines.pop()
    for n, line in enumerate(lines, 1):
        if n == 1:
            line = re.sub(r"^﻿", "", line)
        line = re.sub(r"\r\Z", "", line)
        if n == 1 and line != "---" or n > 1 and line == "---":
            return None
        if line.startswith("name:"):
            line = re.sub(r"^name:[ \t]*", "", line)
            line = re.sub(r"(^|[ \t]+)#.*\Z", "", line, count=1, flags=re.S)
            line = re.sub(r"^[\"']|[\"'][ \t]*\Z", "", line)
            line = re.sub(r"[ \t]+\Z", "", line)
            return lower(line) if line else None
    return None


def names_of(paths, read):
    """Names of the SKILL.md paths: the folder's name, then the frontmatter's, from read(path) (bytes, or None)."""
    names = []
    for f in paths:
        n = f[:f.rindex("/")] if "/" in f else f
        n = n.rsplit("/", 1)[-1]
        if "\n" not in n:
            names.append(lower(n))
        fm = fm_name(read(f) or b"")
        if fm:
            names.append(fm)
    return names


def read_head(path):
    """The first 8 KB of a file, none if it isn't one (a file she made huge must not hold the run, and its lock)."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            return f.read(8192)
    except OSError:
        return b""


def main():
    global lock_fd
    if not REMOTE:
        say(f"no remote in {KEYS}/remote")
        return 0
    if not os.path.isdir(B):
        say(f"{B} is missing")
        return 0
    try:
        os.makedirs(HOME + "/.cache", exist_ok=True)
        lock_fd = os.open(HOME + "/.cache/sync-brain.lock", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        if lock_fd < 3:  # stdin or stdout was closed: a child's own fd 0 to 2 would replace the lock
            lock_fd, low = fcntl.fcntl(lock_fd, fcntl.F_DUPFD_CLOEXEC, 10), lock_fd
            os.close(low)
    except OSError:
        return 0
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # A hung run keeps the lock, its git, ssh and python3 children too: say so once it's been an hour.
        started = read_text(HOME + "/.cache/sync-brain.started")
        if re.fullmatch(r"[0-9]+", started) and (int(time.time()) - int(started)) // 60 >= 60:
            say(f"stuck: a run started {(int(time.time()) - int(started)) // 60} min ago still holds the lock, "
                "so nothing syncs. Look for a hung git, ssh or python3.")
        return 0
    try:
        with open(HOME + "/.cache/sync-brain.started", "w") as f:
            f.write(f"{int(time.time())}\n")
    except OSError:
        pass
    if not os.path.isdir(P + "/.git"):
        try:
            os.makedirs(P, exist_ok=True)
            ok = run(["git", "init", "-q", "-b", "main", P]).ok  # plain git, not git(): no -C
        except OSError:
            ok = False
        if not ok:
            say(f"could not create {P}")
            return 0
        # Same author as before. Her .git/config is mounted read-only in her sandbox.
        for k in ("user.name", "user.email"):
            v = run(["git", "config", "--file", B + "/.git/config", "--get", k], stderr=subprocess.DEVNULL)
            if v.ok:
                git("config", k, v.val)  # ignored if it fails
    if os.path.isdir(P + "/.git/rebase-merge") or os.path.isdir(P + "/.git/rebase-apply"):
        git("rebase", "--abort", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # ignored if it fails

    r = git("fetch", "-q", REMOTE, "+main:refs/sync/github", stderr=subprocess.STDOUT)
    if not r.ok:  # stops the run
        say("fetch failed:")
        block(r.val)
        return 0
    base = rev("refs/sync/github^{commit}")
    if not base:  # stops the run
        say("no main on GitHub")
        return 0

    # Hermes ranks a skill in $HERMES_HOME/skills above the brain's, so one with a brain skill's name (folder or
    # frontmatter name, any case) hides the reviewed version. Posted once per set of names.
    lst = git("ls-tree", "-r", "-z", "--name-only", base, "--", "skills")
    if lst.ok:  # else the scan is skipped
        brain = {n for n in names_of([f for f in lst.out.split("\0")[:-1] if re.search(r"(^|/)SKILL\.md\Z", f)],
                                     lambda f: git("cat-file", "blob", f"{base}:{f}").raw) if n}
        # -L: Hermes may follow a linked folder. Bounded, since she can link anywhere; -type f skips a folder named
        # SKILL.md; only the top .hub is Hermes's. A cut scan is said, never taken for a complete one.
        hs = (os.environ.get("HERMES_HOME") or HOME + "/.hermes") + "/skills"
        try:
            with open(P + "/.git/skill-find", "wb") as found:
                f = run(["timeout", "20", "find", "-L", hs, "-maxdepth", "5", "-name", "SKILL.md", "-type", "f",
                         "!", "-path", hs + "/.hub/*", "-print0"], stdout=found, stderr=subprocess.DEVNULL)
            with open(P + "/.git/skill-find", "rb") as found:
                local = found.read().decode(**UTF8).split("\0")[:-1]
        except OSError:  # no file to write the list to: the scan is skipped, as the bash's redirect did
            f, local = None, []
        if f and f.rc == 124:
            say(f"the scan of {hs} took over 20 s and was cut, so a skill with a brain skill's name may be missed. "
                "Look for links or a flood of files there.")
        shadowed = "\n".join(sorted(brain & set(names_of(local, read_head))))
        seen = HOME + "/.cache/sync-brain.shadowed"
        if not shadowed:
            silent_rm(seen)
        elif shadowed != read_text(seen):
            print("⚠️ sync-brain: a skill in her Hermes home has a brain skill's name, so it hides the reviewed one. "
                  "Look in ~/.hermes/skills/ and delete it:")
            block(shadowed)
            try:
                with open(seen, "w", **UTF8) as f:
                    f.write(shadowed + "\n")
            except OSError:
                pass

    # Her proposal branch: cur is its tip, empty once the owner deletes it. held is what this script last saw there.
    r = git("ls-remote", "--heads", REMOTE, stderr=subprocess.STDOUT)
    if not r.ok:  # stops the run
        say("ls-remote failed:")
        block(r.val)
        return 0
    cur = "\n".join(f[0] for f in (x.split() for x in r.val.split("\n")) if len(f) > 1 and f[1] == "refs/heads/" + PBR)
    if cur:
        r = git("fetch", "-q", REMOTE, f"+refs/heads/{PBR}:refs/sync/proposals", stderr=subprocess.STDOUT)
        if not r.ok:  # stops the run
            say(f"fetch of {PBR} failed:")
            block(r.val)
            return 0
        cur = rev("refs/sync/proposals^{commit}")
        if not cur:  # stops the run
            say(f"no {PBR} after fetching it")
            return 0
    else:
        git("update-ref", "-d", "refs/sync/proposals")  # ignored if it fails
    held = rev("refs/sync/proposed^{commit}")
    if not cur and held:
        _, kept, dropped = read_proposal(base, held)
        if kept or dropped:
            print(f"🗑️ sync-brain: {PBR} was deleted, so Telma's proposal is dropped. Her copy already has main's version of:")
            block("\n".join([*kept, *dropped]))
        git("update-ref", "-d", "refs/sync/proposed")  # ignored if it fails
    # What her copy held after the last run; her changes are her files against it.
    given = rev("refs/sync/given^{commit}") or base

    # A refresh that didn't finish (killed, or a folder she made unwritable): finish it before reading her
    # files, or what GitHub sent her would look like her own change and undo the owner's later work.
    pending = rev("refs/sync/pending^{commit}")
    if pending:
        if not git("checkout", "-q", "-f", "--detach", pending).ok:  # stops the run
            say(f"checkout failed in {P}")
            return 0
        d = git("diff", "--name-status", "--no-renames", "-z", given, pending, "--")  # ignored if it fails
        if helper("apply", P, B, input=d.raw) != 0:  # stops the run
            return 0
        if git("update-ref", "refs/sync/given", pending).ok and git("update-ref", "-d", "refs/sync/pending").ok:
            given = pending

    if not git("checkout", "-q", "-f", "--detach", given).ok:  # stops the run
        say(f"checkout failed in {P}")
        return 0
    failed = False
    for name in os.listdir(P):
        if name == ".git":
            continue
        try:
            path = P + "/" + name
            shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.unlink(path)
        except OSError:
            failed = True
    if failed:  # stops the run
        say(f"could not empty {P}")
        return 0
    roots = git("ls-tree", "--name-only", given).out.split("\n")[:-1]
    if helper("export", B, P, Q, *roots) != 0:  # stops the run
        return 0
    # -f: no .gitignore, hers or GitHub's, hides anything she has. All of it is pushed or refused.
    if not git("add", "-A", "-f").ok:  # stops the run
        say(f"git add failed in {P}")
        return 0
    hers = given
    if not git("diff", "--cached", "--quiet").ok:  # an error counts as a change: the commit then says so
        if not git("commit", "-q", "-m", "brain: sync " + stamp()).ok:  # stops the run
            say(f"commit failed in {P}")
            return 0
        hers = git("rev-parse", "HEAD").val
    refuse_outside(given, hers, ALLOWED + "|" + PROPOSE)

    # Her changes under ALLOWED go to main (index.md is merged by line afterwards); the rest of what she changed
    # (the rule files) is proposed below.
    mine = subset(given, given, hers, FOLDERS)
    if mine is None:  # stops the run
        say(f"git failed in {P}")
        return 0
    new = mine
    if base != given:
        if mine == given:
            new = base
        # Only her commit, and no rename detection: an edit must not follow a rename on the local machine into skills/.
        elif git("checkout", "-q", "-f", "--detach", mine).ok and git(
                "rebase", "-q", "-Xno-renames", "--onto", base, given, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).ok:
            new = git("rev-parse", "HEAD").val
            refuse_outside(base, new, ALLOWED)
        else:  # stops the run
            conflicts = git("diff", "--name-only", "--diff-filter=U").val
            git("rebase", "--abort", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # ignored if it fails
            print("⚠️ sync-brain: conflict with GitHub, nothing pushed. Telma and the local machine both changed these:")
            block(conflicts)
            print(f"Copy GitHub's version over hers in {B}, then redo her change.")
            return 0
    # A failed merge holds back only her changes to index.md: the rest goes out, and the next run tries again.
    idxfail, idx_src = False, ""
    merged = merge_index(new, given, hers)
    if merged is not None:
        if merged != new:
            idx_src = split2(ent(hers, "index.md"))[1]
            new = merged
    else:
        idxfail = True
        say("could not merge index.md (git failed, a version too big to merge in time, the owner deleted it, "
            "or it is not a plain file). Her changes to it wait; everything else goes out.")
    # A proposal that can't be saved doesn't hold back main (her notes still go out).
    proposed = propose(base, given, hers, cur)
    if new != base:
        r = git("push", "-q", REMOTE, f"{new}:refs/heads/main", stderr=subprocess.STDOUT)
        if not r.ok:  # stops the run
            say("push failed:")
            block(r.val)
            return 0
        git("update-ref", "refs/sync/github", new)  # ignored if it fails
        # Remember whose index.md is in main now, if a run that stops below repeats this one.
        if idx_src:
            git("update-ref", "refs/sync/index-pushed", idx_src)  # ignored if it fails

    # Her copy held hers; it gets what GitHub changed. Pending until it all landed: a failure is finished
    # next run, replaying only GitHub's changes, never her own.
    # A proposal that couldn't be saved stops here, after main: her copy and `given` stay as they were, so the
    # next run finds the same edits, merges them against the same base, and her copy isn't refreshed over them.
    if not proposed:
        return 0
    # While her index.md changes wait, `given` keeps the index.md it had, so the next run still sees them, and
    # her copy's index.md is not written over.
    done_new = new
    if idxfail:
        gm, gs = split2(ent(given, "index.md"))
        hers = set_index(hers, gm or "0", gs)
        done_new = set_index(new, gm or "0", gs) if hers is not None else None
        if hers is None or done_new is None:  # stops the run
            say(f"git failed in {P}")
            return 0
    git("update-ref", "refs/sync/given", hers)  # ignored if it fails
    git("update-ref", "-d", "refs/sync/index-pushed")  # ignored if it fails
    if done_new == hers:
        return 0
    git("update-ref", "refs/sync/pending", done_new)  # ignored if it fails
    if not git("checkout", "-q", "-f", "--detach", done_new).ok:  # stops the run
        say(f"checkout failed in {P}")
        return 0
    d = git("diff", "--name-status", "--no-renames", "-z", hers, done_new, "--")  # ignored if it fails
    if helper("apply", P, B, input=d.raw) != 0:  # stops the run
        return 0
    # The run's exit status is that of its last command, as in the bash.
    return git("update-ref", "refs/sync/given", done_new).rc or git("update-ref", "-d", "refs/sync/pending").rc


if __name__ == "__main__":
    sys.exit(main())
