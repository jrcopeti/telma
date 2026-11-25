#!/usr/bin/env python3
"""Whether Telma's deployed files, config, jobs and skills match this repo. Read-only.

Run from the local machine: python3 vps/check-drift.py
One line per file in deploy.manifest (path, status, owner:group, mode, short hash of the host file),
then the Hermes lockstep and `hermes hooks doctor`. The doctor runs each hook once on a test payload,
so cron-alert posts one `test-session` alert per check. Exit 0 when everything is in sync and ok,
1 on drift, 2 when the check can't run. DRIFT_HOST_ROOT=<folder> reads a fake host from that folder
instead of the VPS (the tests).
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

REPO = Path(__file__).resolve().parent.parent
MANIFEST = "vps/deploy.manifest"
HOST = "agents-vps"
SSH = ["ssh", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4"]
TAG = "deployed"
MODES = {"exact", "redacted", "subset", "jobs", "tree"}
TREE_SKIP = {"README.md", "LICENSE"}  # the template's credit, not deployed
INSTALLS = ["/home/agent/.hermes/hermes-agent", "/home/ticket-bay-bot/.hermes/hermes-agent", "/opt/hermes-guard"]
ENV_FILE = "/home/agent/.hermes/.env"
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")

# Runs on the host (or against DRIFT_HOST_ROOT) and prints one JSON object: stat and hashes only,
# config.yaml's text (parsed locally, in memory), the named jobs' fields, the named .env lines.
COLLECT = r'''
import grp, hashlib, json, os, pwd, subprocess, sys
req = json.loads(sys.argv[1])
R = req["root"]
def st(p):
    s = os.lstat(R + p)
    return "%s:%s %o" % (pwd.getpwuid(s.st_uid).pw_name, grp.getgrgid(s.st_gid).gr_name, s.st_mode & 0o7777)
def sha(p):
    with open(R + p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
def link_on_path(p):
    """The first symlink on p, the path's own folders included, or None."""
    parts = p.rstrip("/").split("/")
    for i in range(2, len(parts) + 1):
        if os.path.islink(R + "/".join(parts[:i])):
            return "/".join(parts[:i])
    return None
def entry(p):
    """A file's stat and hash; a symlink (or one on its path) only as one, never followed; None when absent."""
    link = link_on_path(p)
    if link:
        return {"stat": st(link), "sha": None, "link": True}
    return {"stat": st(p), "sha": sha(p)} if os.path.isfile(R + p) else None
def skill_list(j):
    """The skills a job loads, as Hermes reads them (cron/jobs.py _normalize_skill_list)."""
    skills = j.get("skills")
    raw = ([j.get("skill")] if j.get("skill") else []) if skills is None else [skills] if isinstance(skills, str) else list(skills)
    out = []
    for s in raw:
        s = str(s or "").strip()
        if s and s not in out:
            out.append(s)
    return out
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout
out = {"files": {}, "texts": {}, "trees": {}}
for p in req["files"] + req["texts"] + req["jobs_files"]:
    out["files"][p] = entry(p)
for p in req["texts"]:
    if os.path.isfile(R + p) and not link_on_path(p):
        out["texts"][p] = open(R + p).read()
for root in req["trees"]:
    files = {}
    if link_on_path(root):
        out["trees"][root] = {"": entry(root)}
        continue
    for d, dirs, names in os.walk(R + root):
        for n in names + [n for n in dirs if os.path.islink(os.path.join(d, n))]:
            p = os.path.join(d, n)[len(R):]
            files[p[len(root):]] = entry(p)
    out["trees"][root] = files
for p in req["jobs_files"]:
    if not os.path.isfile(R + p) or link_on_path(p):
        continue
    jobs = json.load(open(R + p))["jobs"]
    found = {}
    for j in jobs:
        if j.get("name") in req["jobs"]:
            found.setdefault(j["name"], []).append({
                "schedule": (j.get("schedule") or {}).get("display"), "script": j.get("script"),
                "skills": skill_list(j), "toolsets": j.get("enabled_toolsets"),
                "enabled": j.get("enabled"), "no_agent": j.get("no_agent"), "deliver": j.get("deliver"),
                "prompt_sha": hashlib.sha256((j.get("prompt") or "").encode()).hexdigest()})
    out["jobs"] = {"found": found, "others": sum(1 for j in jobs if j.get("name") not in req["jobs"])}
env = {}
if req["env"] and os.path.isfile(R + req["env_file"]):
    for line in open(R + req["env_file"]):
        name, _, value = line.rstrip("\n").partition("=")
        if name in req["env"]:
            env[name] = value
out["env"] = env
out["commits"] = {}
for d in req["installs"]:
    code, text = run(["git", "-c", "safe.directory=*", "-C", R + d, "rev-parse", "HEAD"])
    out["commits"][d] = text.strip() if code == 0 else None
code, text = run(req["as_agent"] + ["hermes hooks doctor"])
lines = [l for l in text.splitlines() if l.strip()]
out["doctor"] = {"code": code, "last": lines[-1].strip() if lines else ""}
print(json.dumps(out))
'''


class Stop(Exception):
    """The check can't run: a bad manifest, a missing private value, ssh failed."""


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True)
    if check and r.returncode:
        raise Stop(f"git {' '.join(args)}: {r.stderr.decode().strip()}")
    return r


def read_manifest():
    rows = []
    for n, line in enumerate((REPO / MANIFEST).read_text().splitlines(), 1):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if len(fields) != 6 or fields[2] not in MODES:
            raise Stop(f"{MANIFEST}:{n}: want repo path, host path, mode, owner:group, perm, after")
        row = dict(zip(["repo", "host", "mode", "owner", "perm", "after"], fields))
        if (row["mode"] == "tree") != row["repo"].endswith("/") or (row["mode"] == "tree") != row["host"].endswith("/"):
            raise Stop(f"{MANIFEST}:{n}: a tree's two paths end in /, other paths don't")
        rows.append(row)
    return rows


def private_values():
    """KEY=value lines from info/private-values in the common git dir, so worktrees share it."""
    common = Path(git("rev-parse", "--git-common-dir").stdout.decode().strip())
    path = (REPO / common if not common.is_absolute() else common) / "info" / "private-values"
    if not path.is_file():
        raise Stop(f"{path} is missing: it holds the values redacted files need (OWNER_NAME=…)")
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            values[key.strip()] = value.strip()
    return values


def filled(data, path, values):
    """A redacted repo file with each {{KEY}} replaced from info/private-values."""
    text = data.decode()
    for key in PLACEHOLDER.findall(text):
        if key not in values:
            raise Stop(f"{path} needs {key} in info/private-values")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text).encode()


class Repo:
    """A repo file now (the checkout) or at the `deployed` tag; None when absent."""

    def __init__(self):
        self.tagged = git("rev-parse", "-q", "--verify", f"refs/tags/{TAG}", check=False).returncode == 0

    def read(self, path, at_tag=False):
        if not at_tag:
            p = REPO / path
            return p.read_bytes() if p.is_file() else None
        if not self.tagged:
            return None
        r = git("show", f"{TAG}:{path}", check=False)
        return r.stdout if r.returncode == 0 else None

    def tree(self, folder, at_tag=False):
        """Relative path -> bytes, tracked files only, the template's credit left out."""
        args = ["ls-tree", "-rz", "--name-only", TAG, "--", folder] if at_tag else ["ls-files", "-z", "--", folder]
        names = [n for n in git(*args).stdout.decode().split("\0") if n]
        rel = [n[len(folder):] for n in names]
        return {r: self.read(folder + r, at_tag) for r in rel if r not in TREE_SKIP}


def direction(host_matches, want_now, want_tag, tagged):
    """The status table in docs/deploy/PLAN.md. host_matches(want) says whether the host equals it."""
    if want_now is None:
        return "host only"
    if host_matches(want_now):
        return "in sync"
    if not tagged or want_tag is None:
        return "differs"
    if host_matches(want_tag):
        return "repo ahead"
    return "host ahead" if want_now == want_tag else "both changed"


def subset_diff(want, have, prefix=""):
    """Keys in `want` whose value differs in `have`, by name only; dicts compared key by key."""
    have = have if isinstance(have, dict) else {}
    diff = []
    for key, value in want.items():
        if isinstance(value, dict) and isinstance(have.get(key), dict):
            diff += subset_diff(value, have[key], f"{prefix}{key}.")
        elif key not in have or have[key] != value:
            diff.append(prefix + key)
    return diff


def env_name(key):
    """Hermes's .env name for a terminal key (TERMINAL_CONFIG_ENV_MAP); `cwd` isn't mirrored."""
    return None if key == "cwd" else "TERMINAL_ENV" if key == "backend" else f"TERMINAL_{key.upper()}"


def env_value(value):
    """The .env line's value as Hermes writes it (_terminal_env_value, then _quote_env_value)."""
    text = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
    if text and ("#" in text or '"' in text or "'" in text or any(c.isspace() for c in text)):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def env_diff(overrides, env):
    diff = []
    for key, value in ((overrides or {}).get("terminal") or {}).items():
        name = env_name(key)
        if name and env.get(name) != env_value(value):
            diff.append(f".env {name}")
    return diff


def load_yaml(data, where):
    """Parsed YAML, or a stop that names the line only: a host file's text is never printed."""
    try:
        return yaml.safe_load(data) or {}
    except Exception as e:  # a bad tag raises ValueError or KeyError, carrying the value
        mark = getattr(e, "problem_mark", None)
        raise Stop(f"{where} isn't valid YAML" + (f" (line {mark.line + 1})" if mark else ""))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(request):
    root = os.environ.get("DRIFT_HOST_ROOT")
    if root == "":
        raise Stop("DRIFT_HOST_ROOT is set but empty: a fake host folder, or unset for the VPS")
    request = {**request, "root": root or "", "installs": INSTALLS, "env_file": ENV_FILE,
               "as_agent": ["bash", "-c"] if root else ["su", "-", "agent", "-c"]}
    arg = json.dumps(request)
    if root:
        cmd = [sys.executable, "-I", "-c", COLLECT, arg]
    else:
        cmd = [*SSH, HOST, f"python3 -I - {shlex.quote(arg)}"]
    r = subprocess.run(cmd, input=None if root else COLLECT, capture_output=True, text=True)
    if r.returncode:
        raise Stop(f"reading the host failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise Stop("the host's reply isn't the collector's JSON (a login script printing to stdout?)")


def check():
    if yaml is None:
        raise Stop("PyYAML is missing: pip install pyyaml")
    rows = read_manifest()
    values = private_values() if any(r["mode"] == "redacted" for r in rows) else {}
    repo = Repo()

    def fill(data, path):
        return None if data is None else filled(data, path, values)

    def jobs_want(path, at_tag):
        """The overrides with each prompt file read at the same commit, as a hash."""
        data = repo.read(path, at_tag)
        if data is None:
            return None
        want = load_yaml(data, path)
        if not all(isinstance(job, dict) for job in want.values()):
            raise Stop(f"{path}: every job is a map of its fields")
        for job in want.values():
            prompt = job.pop("prompt", None)
            text = repo.read(prompt, at_tag) if prompt else b""
            job["prompt_sha"] = sha(text.decode().removesuffix("\n").encode()) if text is not None else None
        return want

    # Read every repo side first: a missing private value stops the check before ssh.
    wants = []
    for row in rows:
        mode, path = row["mode"], row["repo"]
        if mode == "exact":
            wants.append((repo.read(path), repo.read(path, True)))
        elif mode == "redacted":
            wants.append((fill(repo.read(path), path), fill(repo.read(path, True), path)))
        elif mode == "subset":
            wants.append(tuple(None if d is None else load_yaml(d, path)
                               for d in (repo.read(path), repo.read(path, True))))
        elif mode == "jobs":
            wants.append((jobs_want(path, False), jobs_want(path, True)))
        else:
            wants.append((repo.tree(path), repo.tree(path, True) if repo.tagged else {}))

    # Names from both sides, so the tag's side is judged against what the host has for it too.
    env_names = sorted({n for row, pair in zip(rows, wants) if row["mode"] == "subset" for w in pair
                        for n in (env_name(k) for k in ((w or {}).get("terminal") or {})) if n})
    jobs = sorted({n for row, pair in zip(rows, wants) if row["mode"] == "jobs" for w in pair for n in (w or {})})
    host = collect({"files": [r["host"] for r in rows if r["mode"] in ("exact", "redacted")],
                    "texts": [r["host"] for r in rows if r["mode"] == "subset"],
                    "jobs_files": [r["host"] for r in rows if r["mode"] == "jobs"],
                    "trees": [r["host"] for r in rows if r["mode"] == "tree"],
                    "env": env_names, "jobs": jobs})

    lines = []

    def status_of(f, matches, now, tag):
        if f is None:
            return "missing"
        if f.get("link"):
            return "link"
        return direction(matches, now, tag, repo.tagged)

    def line(path, status, stat, digest, row, notes=()):
        want = f"{row['owner']} {row['perm']}"
        if stat and row["perm"] == "-":
            ok_stat = stat.split()[0] == row["owner"]
        else:
            ok_stat = stat == want
        if stat and not ok_stat and status != "link":  # a link's own mode means nothing
            status = "perm differs" if status == "in sync" else status + " +perm"
            notes = [*notes, f"want {want}"]
        owner, _, perm = (stat or "- -").partition(" ")
        lines.append((status, f"{path:<44} {status:<14} {owner:<13} {perm:<4} {digest[:12] if digest else '-':<12}"
                      + (f"  {', '.join(notes)}" if notes else "")))

    for row, (now, tag) in zip(rows, wants):
        mode = row["mode"]
        if mode in ("exact", "redacted"):
            f = host["files"][row["host"]]
            status = status_of(f, lambda w: sha(w) == f["sha"], now, tag)
            line(row["repo"], status, f and f["stat"], f and f["sha"], row)
        elif mode == "subset":
            f = host["files"][row["host"]]
            text = host["texts"].get(row["host"])
            have = load_yaml(text, row["host"]) if text is not None else None
            diff = lambda w: subset_diff(w, have) + env_diff(w, host["env"])
            status = status_of(f, lambda w: not diff(w), now, tag)
            line(row["repo"], status, f and f["stat"], f and f["sha"], row,
                 diff(now) if text is not None and now is not None else ())
        elif mode == "jobs":
            f = host["files"][row["host"]]
            found = (host.get("jobs") or {}).get("found", {})
            have = {name: hits[0] for name, hits in found.items() if len(hits) == 1}

            def jobs_diff(want):
                return [name for name, fields in want.items() if have.get(name) != fields]
            status = status_of(f, lambda w: not jobs_diff(w), now, tag)
            notes = jobs_diff(now) if status not in ("missing", "link") and now is not None else []
            notes = [f"{n} ×{len(found[n])}" if len(found.get(n, [])) > 1 else n for n in notes]
            others = (host.get("jobs") or {}).get("others")
            if others is not None:
                notes.append(f"{others} other job(s), not checked")
            line(row["repo"], status, f and f["stat"], None, row, notes)
        else:
            have = {p: v for p, v in host["trees"][row["host"]].items() if p not in TREE_SKIP or (v or {}).get("link")}
            for rel in sorted(set(now) | set(have)):
                f = have.get(rel)
                status = status_of(f, lambda w: sha(w) == f["sha"], now.get(rel), tag.get(rel))
                line(row["repo"] + rel, status, f and f["stat"], f and f["sha"], row)

    commits = host["commits"]
    if None not in commits.values() and len(set(commits.values())) == 1:
        hermes = f"ok {next(iter(commits.values()))[:12]}"
    else:
        hermes = "differs: " + ", ".join(f"{d} {(c or 'unreadable')[:12]}" for d, c in commits.items())
    doctor = host["doctor"]
    hooks = "ok" if doctor["code"] == 0 and doctor["last"] == "All shell hooks look healthy." \
        else doctor["last"] or f"doctor failed ({doctor['code']})"

    for _, text in lines:
        print(text)
    print(f"{'hermes':<44} {hermes}")
    print(f"{'hooks':<44} {hooks}")
    drift = [s for s, _ in lines if s != "in sync"]
    tag = git("rev-parse", "--short", TAG, check=False).stdout.decode().strip() if repo.tagged else "none"
    print(f"summary: {len(lines) - len(drift)} of {len(lines)} in sync, hermes {hermes.split()[0].rstrip(':')}, "
          f"hooks {'ok' if hooks == 'ok' else 'not ok'}, {TAG} {tag}")
    return 0 if not drift and hermes.startswith("ok") and hooks == "ok" else 1


def main():
    try:
        return check()
    except Stop as e:
        print(f"check-drift: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # exit 1 means drift; anything unexpected means the check didn't run
        print(f"check-drift: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
