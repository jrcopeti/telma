"""deploy.py's host side. Runs as root on the VPS (or against a fake host folder): deploy.py sends this
file as `python3 -I -c <this file>` and the request as JSON on stdin. Two actions.

read: prints each named file's stat, hash and bytes, for the diff. A symlink on a file's path, or a
path that isn't a regular file, is reported, never read through.

copy: stages every file to a temp name in its folder with its owner and mode, keeps the old one in
the backup folder, asks her cron ledger as agent whether a job runs (running_jobs.py), re-hashes
every file, and only then swaps them all in. A stop before the swap removes what it made: exit 4, or
5 for a running job. Exit 6 when the swap itself failed part way. Prints the swapped paths as JSON.

Every path is walked from the root one folder at a time with O_NOFOLLOW, and every later step works
on the folder already opened (dir_fd), so a symlink planted or swapped in at any point is never
followed: her folders are writable by her, and this runs as root. The backups are root's, 0700.
"""
import base64
import grp
import hashlib
import json
import os
import pwd
import shlex
import stat as st
import subprocess
import sys

req = json.loads(sys.stdin.read())
R = req["root"]
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class Unsafe(Exception):
    """A symlink, or something that isn't a plain folder or file, on a path."""


def link_on_path(p):
    """The first symlink on p, its folders included, or None: for the report only."""
    parts = p.split("/")
    for i in range(2, len(parts) + 1):
        if os.path.islink(R + "/".join(parts[:i])):
            return "/".join(parts[:i])
    return None


def open_dir(path):
    """An fd on the folder at path, opened one part at a time without following a symlink. Raises
    FileNotFoundError when a part is missing, Unsafe when one is a link or not a folder."""
    fd = os.open(R or "/", os.O_RDONLY | os.O_DIRECTORY)  # the fake root itself may sit under a link
    for name in [n for n in path.split("/") if n]:
        try:
            nxt = os.open(name, DIR, dir_fd=fd)
        except FileNotFoundError:
            os.close(fd)
            raise
        except OSError as e:
            os.close(fd)
            raise Unsafe("%s: %s is a link or not a folder (%s)" % (path, name, e.strerror))
        os.close(fd)
        fd = nxt
    return fd


def read_file(dfd, name):
    """The regular file's bytes and stat, or None when absent. Raises Unsafe."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Unsafe("%s isn't a plain file (%s)" % (name, e.strerror))
    with os.fdopen(fd, "rb") as f:
        s = os.fstat(f.fileno())
        if not st.S_ISREG(s.st_mode):
            raise Unsafe("%s isn't a plain file" % name)
        return f.read(), s


def describe(s):
    return "%s:%s %o" % (pwd.getpwuid(s.st_uid).pw_name, grp.getgrgid(s.st_gid).gr_name, s.st_mode & 0o7777)


def read_files():
    out = {}
    for p in req["files"]:
        if link_on_path(p):
            out[p] = {"link": link_on_path(p)}
            continue
        try:
            dfd = open_dir(os.path.dirname(p))
            try:
                got = read_file(dfd, os.path.basename(p))
            finally:
                os.close(dfd)
        except FileNotFoundError:
            got = None
        except Unsafe as e:
            out[p] = {"unsafe": str(e)}
            continue
        out[p] = None if got is None else {
            "stat": describe(got[1]), "sha": hashlib.sha256(got[0]).hexdigest(),
            "data": base64.b64encode(got[0]).decode()}
    print(json.dumps(out))


made = []    # (folder fd, name) of each folder or file this run created, removed again on a stop
staged = []  # (folder fd, temp name, name, file request)


def stop(code, msg):
    for dfd, tmp, _, _ in staged:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except FileNotFoundError:
            pass
    for dfd, name in reversed(made):
        try:
            if st.S_ISDIR(os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mode):
                os.rmdir(name, dir_fd=dfd)
            else:
                os.unlink(name, dir_fd=dfd)
        except OSError:
            pass
    print(msg, file=sys.stderr)
    sys.exit(code)


def write_new(dfd, name, data, uid, gid, mode):
    """A new file in the folder dfd: never through a link, never over an existing entry."""
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fchown(out.fileno(), uid, gid)
        os.fchmod(out.fileno(), mode)
        os.fsync(out.fileno())


def backup_dir():
    """The run's backup folder, made by root inside a backups folder root owns and only root opens."""
    parent, name = os.path.split(req["backups"])
    pfd = open_dir(parent)
    try:
        os.mkdir(name, 0o700, dir_fd=pfd)
    except FileExistsError:
        pass
    try:
        bfd = os.open(name, DIR, dir_fd=pfd)
    except OSError as e:
        raise Unsafe("%s is a link or not a folder (%s)" % (req["backups"], e.strerror))
    os.close(pfd)
    s = os.fstat(bfd)
    if s.st_uid != os.geteuid() or s.st_mode & 0o077:
        stop(4, "%s must be root's and closed to others (it is %s)" % (req["backups"], describe(s)))
    try:
        os.mkdir(req["stamp"], 0o700, dir_fd=bfd)
    except FileExistsError:
        stop(4, "backup folder %s/%s already exists" % (req["backups"], req["stamp"]))
    made.append((bfd, req["stamp"]))
    return os.open(req["stamp"], DIR, dir_fd=bfd)


def keep(stamp_fd, p, data, s):
    """The old file, under the run's backup folder at its own path; root's, its mode kept. Inside a
    folder only root opens, so nothing else can race these steps."""
    folder = stamp_fd
    for name in [n for n in os.path.dirname(p).split("/") if n]:
        try:
            os.mkdir(name, 0o700, dir_fd=folder)
            made.append((folder, name))
        except FileExistsError:
            pass
        folder = os.open(name, DIR, dir_fd=folder)
    write_new(folder, os.path.basename(p), data, os.geteuid(), os.getegid(), s.st_mode & 0o7777)
    made.append((folder, os.path.basename(p)))


def running_jobs():
    """Job ids her cron ledger has claimed or running, read as agent: the last line of output is
    the list as JSON, so anything her login profile prints before it is ignored."""
    r = subprocess.run(req["as_agent"] + ["python3 -I - " + shlex.quote(R + req["ledger"])],
                       input=req["running_code"], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    try:
        if r.returncode:
            raise ValueError
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        stop(4, "couldn't read her running jobs: " + (r.stderr.strip() or r.stdout.strip())[-300:])


def current_sha(dfd, name):
    got = read_file(dfd, name)
    return got and hashlib.sha256(got[0]).hexdigest()


def stage(f, stamp_fd):
    p = f["host"]
    name = os.path.basename(p)
    try:
        dfd = open_dir(os.path.dirname(p))
    except FileNotFoundError:
        stop(4, "%s: its folder doesn't exist" % p)
    got = read_file(dfd, name)
    if (got and hashlib.sha256(got[0]).hexdigest()) != f["was"]:
        stop(4, "%s changed on the host since its diff was shown" % p)
    tmp = ".%s.deploy-tmp" % name
    try:
        os.stat(tmp, dir_fd=dfd, follow_symlinks=False)
        stop(4, "%s/%s is left from an earlier deploy: look at it, remove it, run again" % (os.path.dirname(p), tmp))
    except FileNotFoundError:
        pass
    if got:
        keep(stamp_fd, p, got[0], got[1])
    write_new(dfd, tmp, base64.b64decode(f["data"]), pwd.getpwnam(f["user"]).pw_uid,
              grp.getgrnam(f["group"]).gr_gid, int(f["perm"], 8))
    staged.append((dfd, tmp, name, f))


def copy_files():
    try:
        stamp_fd = backup_dir()
        for f in req["files"]:
            stage(f, stamp_fd)
        jobs = running_jobs()
        if jobs:
            stop(5, "a job of hers is running (job id %s): nothing copied, try again when it ends" % " ".join(jobs))
        for dfd, _, name, f in staged:  # last look, right before the swap
            if current_sha(dfd, name) != f["was"]:
                stop(4, "%s changed on the host during the copy" % f["host"])
    except SystemExit:
        raise
    except Unsafe as e:
        stop(4, str(e))
    except Exception as e:
        stop(4, "%s: %s" % (type(e).__name__, e))
    done = []
    try:
        for dfd, tmp, name, f in staged:
            os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
            done.append(f["host"])
    except Exception as e:
        print("swapped %s, then %s: %s" % (", ".join(done) or "nothing", type(e).__name__, e), file=sys.stderr)
        sys.exit(6)
    print(json.dumps(done))


{"read": read_files, "copy": copy_files}[req["action"]]()
