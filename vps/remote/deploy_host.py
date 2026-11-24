"""deploy.py's host side. Runs as root on the VPS (or against a fake host folder), the request as JSON
on stdin: python3 -I - < request. Two actions.

read: prints each named file's stat, hash and bytes, for the diff. A symlink on a file's path is
reported, never read through.

copy: stages every file to a temp name in its folder with its owner and mode, keeps the old one in
the backup folder, then asks her cron ledger as agent whether a job runs (running_jobs.py), and only
then swaps them all in. A stop before the swap removes what it made: exit 4, or 5 for a running job.
Exit 6 when the swap itself failed part way. Prints the swapped paths as JSON.
"""
import base64
import grp
import hashlib
import json
import os
import pwd
import shlex
import shutil
import subprocess
import sys

req = json.loads(sys.stdin.read())
R = req["root"]


def link_on_path(p):
    """The first symlink on p, its folders included, or None: never followed."""
    parts = p.split("/")
    for i in range(2, len(parts) + 1):
        if os.path.islink(R + "/".join(parts[:i])):
            return "/".join(parts[:i])
    return None


def read(p):
    with open(R + p, "rb") as f:
        return f.read()


def stat(p):
    s = os.lstat(R + p)
    return "%s:%s %o" % (pwd.getpwuid(s.st_uid).pw_name, grp.getgrgid(s.st_gid).gr_name, s.st_mode & 0o7777)


def read_files():
    out = {}
    for p in req["files"]:
        if link_on_path(p):
            out[p] = {"link": link_on_path(p)}
        elif os.path.isfile(R + p):
            data = read(p)
            out[p] = {"stat": stat(p), "sha": hashlib.sha256(data).hexdigest(),
                      "data": base64.b64encode(data).decode()}
        else:
            out[p] = None
    print(json.dumps(out))


staged, made = [], []


def stop(code, msg):
    for tmp in staged:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    for d in reversed(made):
        shutil.rmtree(d, ignore_errors=True)
    print(msg, file=sys.stderr)
    sys.exit(code)


def mkdirs(path, uid, gid):
    """Each missing folder down to path, owned like the file it backs up."""
    parts = path.split("/")
    for i in range(2, len(parts) + 1):
        d = R + "/".join(parts[:i])
        if not os.path.lexists(d):
            os.mkdir(d, 0o700)
            os.chown(d, uid, gid)
            made.append(d)
        elif os.path.islink(d) or not os.path.isdir(d):
            stop(4, "%s isn't a plain folder" % "/".join(parts[:i]))


def running_jobs():
    """Job ids her cron ledger has claimed or running, read as agent: the last line of output is
    the list as JSON, so anything her login profile prints before it is ignored."""
    r = subprocess.run(req["as_agent"] + ["python3 -I - " + shlex.quote(R + req["ledger"])], input=req["running_code"],
                       capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    try:
        if r.returncode:
            raise ValueError
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        stop(4, "couldn't read her running jobs: " + (r.stderr.strip() or r.stdout.strip())[-300:])


def stage(f, backup):
    p = f["host"]
    if link_on_path(p):
        stop(4, "%s: a symlink appeared on its path" % p)
    now = hashlib.sha256(read(p)).hexdigest() if os.path.isfile(R + p) else None
    if now != f["was"]:
        stop(4, "%s changed on the host since its diff was shown" % p)
    folder = os.path.dirname(R + p)
    if not os.path.isdir(folder):
        stop(4, "%s: its folder doesn't exist" % p)
    tmp = os.path.join(folder, ".%s.deploy-tmp" % os.path.basename(p))
    if os.path.lexists(tmp):
        stop(4, "%s is left from an earlier deploy: look at it, remove it, run again" % tmp[len(R):])
    uid, gid = pwd.getpwnam(f["user"]).pw_uid, grp.getgrnam(f["group"]).gr_gid
    if f["was"] is not None:
        s = os.lstat(R + p)
        mkdirs(backup + os.path.dirname(p), s.st_uid, s.st_gid)
        shutil.copy2(R + p, R + backup + p, follow_symlinks=False)
        os.chown(R + backup + p, s.st_uid, s.st_gid)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    staged.append(tmp)
    with os.fdopen(fd, "wb") as out:
        out.write(base64.b64decode(f["data"]))
        out.flush()
        os.fchown(out.fileno(), uid, gid)
        os.fchmod(out.fileno(), int(f["perm"], 8))
        os.fsync(out.fileno())


def copy_files():
    try:
        if os.path.lexists(R + req["backup"]):
            stop(4, "backup folder %s already exists" % req["backup"])
        for f in req["files"]:
            stage(f, req["backup"])
        jobs = running_jobs()
        if jobs:
            stop(5, "a job of hers is running (job id %s): nothing copied, try again when it ends" % " ".join(jobs))
    except SystemExit:
        raise
    except Exception as e:
        stop(4, "%s: %s" % (type(e).__name__, e))
    done = []
    try:
        for f, tmp in zip(req["files"], staged):
            os.replace(tmp, R + f["host"])
            done.append(f["host"])
    except Exception as e:
        print("swapped %s, then %s: %s" % (", ".join(done) or "nothing", type(e).__name__, e), file=sys.stderr)
        sys.exit(6)
    print(json.dumps(done))


{"read": read_files, "copy": copy_files}[req["action"]]()
