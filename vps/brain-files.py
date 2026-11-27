#!/usr/bin/env python3
"""File moves between Telma's brain (her sandbox writes it) and sync-brain's own clone (host only).

  export BRAIN DEST QUARANTINE [ROOT_NAME...]   copy her files into DEST, move out instruction files
  apply SRC BRAIN < name-status                 write `git diff --name-status -z` changes from SRC
  gitfiles < paths                              print the -z paths that git on the local machine reads as config
  mergelines BASE OURS THEIRS                   three-way line merge to stdout; where both sides changed the same lines, both stay

Every folder in BRAIN is opened relative to its parent and never through a symlink, so a folder she
swaps for a link mid-run can't send a read or a write outside the brain. Prints only problems, as
Discord text with her names in a code block. Exit 0 ok, 3 refused or failed something, 1 error.
ROOT_NAME: names at the brain's root that come from GitHub (the owner's): not quarantined, and nor is
anything inside them except in Telma's folders (ALLOWED_TOP, sync-brain.py's ALLOWED).
"""
import difflib
import errno
import os
import re
import stat
import sys
import tempfile
import time
import unicodedata

DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
ALLOWED_TOP = {"inbox", "sources", "notes", "guidelines", "decisions", "projects", "intents", "index.md"}
# Files and folders an agent loads as instructions: Hermes, Claude Code, Codex, Cursor, Gemini, Copilot,
# Windsurf, Cline. Matched after folding(): the local machine's disk opens agentſ.md as AGENTS.md.
INSTRUCTIONS = {
    "agents.md", "agents.override.md", "claude.md", "claude.local.md", "gemini.md", ".hermes.md",
    "hermes.md", ".cursorrules", ".windsurfrules", ".clinerules", ".cursor", ".hermes", ".agents",
    ".claude", ".github", ".codex", ".gemini", ".windsurf",
}
# A .git, or a HEAD that makes its folder a bare repo git on the local machine would load config from.
GIT_NAMES = {".git", "head"}
# Read by git on the local machine: her .gitignore in notes/ would hide the owner's new notes from `git add`.
GIT_FILES = {".gitignore", ".gitattributes", ".gitmodules"}
# GitHub refuses bigger files. Sparse ones are refused too: a few KB of her disk, gigabytes once copied.
MAX_FILE = 100 << 20


def folded(name):
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", name).casefold())


def shown(s):
    """A name she chose, safe inside a Discord code block: one line, no backticks, no hidden marks."""
    return "".join(c if c.isprintable() and c != "`" else "\\x%02x" % ord(c) if ord(c) < 256 else "\\u%04x" % ord(c) for c in s)


def block(lines):
    return "```\n" + "\n".join(shown(x) for x in lines) + "\n```"


def entry_type(dfd, name):
    try:
        return stat.S_IFMT(os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return None


def kind(t):
    return {stat.S_IFLNK: "link", stat.S_IFIFO: "fifo", stat.S_IFSOCK: "socket", stat.S_IFCHR: "device",
            stat.S_IFBLK: "device"}.get(t, "not a file")


def open_checked(dfd, name, want):
    """Open name in dfd as type want (S_IFDIR or S_IFREG); None if it's anything else by now."""
    try:
        fd = os.open(name, DIR if want == stat.S_IFDIR else FILE, dir_fd=dfd)
    except OSError:
        return None
    if stat.S_IFMT(os.fstat(fd).st_mode) != want:
        os.close(fd)
        return None
    return fd


def copy_file(fd, dest):
    """Copy in chunks; False if the file grew past MAX_FILE while read."""
    with open(dest, "wb") as f:
        left = MAX_FILE + 1
        while True:
            b = os.read(fd, min(left, 1 << 16))
            if not b:
                return True
            left -= len(b)
            if left <= 0:
                return False
            f.write(b)


def too_big(fd, st):
    # A hole the filesystem reports, not fewer blocks than bytes: compression uses fewer blocks too.
    sparse = st.st_size > 1 << 20 and os.lseek(fd, 0, os.SEEK_HOLE) < st.st_size
    os.lseek(fd, 0, os.SEEK_SET)
    return "sparse" if sparse else "over %d MB" % (MAX_FILE >> 20) if st.st_size > MAX_FILE else None


def copy_tree(dfd, name, dest, refused, rel):
    """Copy dfd/name (a plain file or folder, checked again on open) to the host path dest."""
    t = entry_type(dfd, name)
    want = t if t in (stat.S_IFDIR, stat.S_IFREG) else None
    fd = open_checked(dfd, name, want) if want else None
    if fd is None:
        refused.append("%s (%s)" % (rel, kind(t) if not want else "changed while read"))
        return
    try:
        if want == stat.S_IFREG:
            st = os.fstat(fd)
            why = too_big(fd, st) or (None if copy_file(fd, dest) else "grew while read")
            if why:
                refused.append("%s (%s)" % (rel, why))
                return
            os.chmod(dest, 0o755 if st.st_mode & 0o100 else 0o644)
            return
        os.mkdir(dest)
        for child in sorted(os.listdir(fd)):
            if folded(child) in GIT_NAMES:
                refused.append("%s/%s (a git repo inside the brain)" % (rel, child))
                continue
            copy_tree(fd, child, os.path.join(dest, child), refused, rel + "/" + child)
    finally:
        os.close(fd)


def remove(dfd, name):
    """Delete dfd/name; links are removed, never followed."""
    if entry_type(dfd, name) == stat.S_IFDIR:
        fd = open_checked(dfd, name, stat.S_IFDIR)
        if fd is not None:
            try:
                for child in os.listdir(fd):
                    remove(fd, child)
            finally:
                os.close(fd)
        os.rmdir(name, dir_fd=dfd)
    else:
        os.unlink(name, dir_fd=dfd)


def export(brain, dest, quarantine, root_names):
    refused, moved = [], []
    stamp = time.strftime("%Y-%m-%d-%H%M%S")

    def walk(dfd, rel, out, scan):
        for name in sorted(os.listdir(dfd)):
            path = rel + name
            if rel == "" and name == ".git":
                continue
            if scan and folded(name) in INSTRUCTIONS and not (rel == "" and name in root_names):
                os.makedirs(quarantine, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", path)[:80]
                qdir = tempfile.mkdtemp(prefix="%s-%s-" % (stamp, safe), dir=quarantine)
                inner = []
                copy_tree(dfd, name, os.path.join(qdir, "item"), inner, path)
                remove(dfd, name)
                moved.append("%s -> %s%s" % (path, qdir, " (not all kept: %s)" % ", ".join(inner) if inner else ""))
                continue
            if folded(name) in GIT_NAMES:
                refused.append("%s (a git repo inside the brain)" % path)
                continue
            t = entry_type(dfd, name)
            if t == stat.S_IFDIR:
                fd = open_checked(dfd, name, stat.S_IFDIR)
                if fd is None:
                    refused.append("%s (changed while read)" % path)
                    continue
                try:
                    os.mkdir(os.path.join(out, name))
                    walk(fd, path + "/", os.path.join(out, name),
                         scan and not (rel == "" and name in root_names and name not in ALLOWED_TOP))
                finally:
                    os.close(fd)
            else:
                copy_tree(dfd, name, os.path.join(out, name), refused, path)

    root = os.open(brain, DIR)
    try:
        walk(root, "", dest, True)
    finally:
        os.close(root)
    if moved:
        print("⚠️ sync-brain: moved these out of the brain. Telma may have planted them as instructions: "
              "read them before deleting.\n" + block(moved))
    if refused:
        print("🚫 sync-brain: refused to push. Only plain files and folders go out:\n" + block(refused)
              + "\nNothing was pushed, and nothing will be until they are gone.")
        return 3
    return 0


def open_parent(brain_fd, parts, create):
    """The folder holding parts[-1], walked from the brain's root without following links."""
    fd = os.dup(brain_fd)
    for p in parts[:-1]:
        if entry_type(fd, p) is None:
            if not create:
                os.close(fd)
                raise FileNotFoundError(errno.ENOENT, "gone", p)
            os.mkdir(p, dir_fd=fd)
        nxt = open_checked(fd, p, stat.S_IFDIR)
        os.close(fd)
        if nxt is None:
            raise OSError(errno.ENOTDIR, "not a folder", p)
        fd = nxt
    return fd


def write_in_place(pfd, name, body, mode):
    """Overwrite an existing plain file, keeping its inode: her sandbox may mount it as a single file
    (AGENTS.md), and a mount keeps showing the old inode. Not through a link, a FIFO or a hard link."""
    try:
        fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=pfd)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return False
        os.ftruncate(fd, 0)
        view = memoryview(body)
        while view:
            view = view[os.write(fd, view):]
        os.fchmod(fd, 0o755 if mode & 0o100 else 0o644)
        return True
    finally:
        os.close(fd)


def prune(root, parts):
    """Remove the folders a deleted file leaves empty, deepest first, never a folder at the brain's top level."""
    for k in range(len(parts) - 1, 1, -1):
        try:
            pfd = open_parent(root, parts[:k], False)
        except OSError:
            return
        try:
            os.rmdir(parts[k - 1], dir_fd=pfd)
        except OSError:
            return
        finally:
            os.close(pfd)


def apply(src, brain):
    data = sys.stdin.buffer.read().split(b"\0")
    failed = []
    root = os.open(brain, DIR)
    try:
        for i in range(0, len(data) - 1, 2):
            status, path = data[i].decode()[:1], os.fsdecode(data[i + 1])
            parts = path.split("/")
            try:
                if status == "D":
                    try:
                        pfd = open_parent(root, parts, False)
                    except FileNotFoundError:
                        continue  # its folder is gone already
                    try:
                        if entry_type(pfd, parts[-1]) is not None:
                            remove(pfd, parts[-1])
                    finally:
                        os.close(pfd)
                    prune(root, parts)
                    continue
                st = os.lstat(os.path.join(src, path))
                if not stat.S_ISREG(st.st_mode):
                    raise OSError(errno.EINVAL, "not a plain file on GitHub", path)
                with open(os.path.join(src, path), "rb") as f:
                    body = f.read()
                pfd = open_parent(root, parts, True)
                try:
                    if write_in_place(pfd, parts[-1], body, st.st_mode):
                        continue
                    tmp = ".sync-brain-%d-%d" % (os.getpid(), i)
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o755 if st.st_mode & 0o100 else 0o644, dir_fd=pfd)
                    try:
                        os.write(fd, body)
                    finally:
                        os.close(fd)
                    # rename replaces a link she put there, it never writes through it
                    try:
                        os.rename(tmp, parts[-1], src_dir_fd=pfd, dst_dir_fd=pfd)
                    except OSError:
                        os.unlink(tmp, dir_fd=pfd)
                        raise
                finally:
                    os.close(pfd)
            except OSError as e:
                failed.append("%s (%s)" % (path, e.strerror))
    finally:
        os.close(root)
    if failed:
        print("⚠️ sync-brain: could not update these in Telma's copy of the brain:\n" + block(failed))
        return 3
    return 0


def mergelines(base, ours, theirs):
    """Three-way merge of byte strings by line (a line ends at \\n only). Each side's changed lines are applied
    as that side wrote them, and the base lines they replace are dropped, so a line one side deleted and the
    other left alone stays deleted. Where both sides changed the same lines, or add at the same spot, both
    versions stay, ours first; an identical edit appears once."""
    def lines_of(text):
        return re.findall(rb"[^\n]*\n|[^\n]+", text)
    b = lines_of(base)
    hunks = []
    for n, text in enumerate((ours, theirs)):
        lines = lines_of(text)
        ops = difflib.SequenceMatcher(None, b, lines, autojunk=False).get_opcodes()
        hunks += [(i1, i2, n, lines[j1:j2]) for tag, i1, i2, j1, j2 in ops if tag != "equal"]
    out, pos, prev = [], 0, None
    for i1, i2, n, r in sorted(hunks, key=lambda h: h[:3]):
        out += b[pos:i1]
        pos = max(pos, i2)
        if prev and prev[:2] == (i1, i2) and prev[3] == r:
            continue
        out += r
        prev = (i1, i2, n, r)
    out += b[pos:]
    # A last line without its newline gets one when something follows it.
    return b"".join(l if l.endswith(b"\n") or k == len(out) - 1 else l + b"\n" for k, l in enumerate(out))


if __name__ == "__main__":
    try:
        if sys.argv[1] == "export":
            sys.exit(export(sys.argv[2], sys.argv[3], sys.argv[4], set(sys.argv[5:])))
        if sys.argv[1] == "apply":
            sys.exit(apply(sys.argv[2], sys.argv[3]))
        if sys.argv[1] == "mergelines":
            sys.stdout.buffer.write(mergelines(*(open(f, "rb").read() for f in sys.argv[2:5])))
            sys.exit(0)
        if sys.argv[1] == "gitfiles":
            for p in sys.stdin.buffer.read().split(b"\0"):
                if p and folded(os.fsdecode(p).rsplit("/", 1)[-1]) in GIT_FILES:
                    print(os.fsdecode(p))
            sys.exit(0)
    except (OSError, IndexError) as e:
        print("⚠️ sync-brain: brain-files.py failed: %s" % shown(str(e)))
        sys.exit(1)
    sys.exit(1)
