"""Hermes pre_tool_call hook on Telma's tools that send data off the host (matcher in
exfil-tripwire.hooks.yaml): post to #alerts when a call's arguments carry brain text, plain, URL- or
base64-encoded (either order), or name the brain's folder. Detection only: it always prints {} and
exits 0, so the call goes ahead. Catches a note sent whole or in long runs; text split across calls,
reworded or encoded another way gets past it (accepted in PLAN.md).
Every alert and failure is also logged locally; tripwire-health.sh reports the failures.
Usage: python3 -I exfil-tripwire.py, with Hermes's hook payload on stdin."""
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
BRAIN = Path(os.environ.get("TRIPWIRE_BRAIN", HOME / "brain"))
WEBHOOK = Path(os.environ.get("TRIPWIRE_WEBHOOK_FILE", HOME / ".config/exfil-tripwire/webhook"))
STATE = Path(os.environ.get("TRIPWIRE_STATE", HOME / ".local/state/exfil-tripwire"))
RUN = 8  # words in a row that must match a note
SHORT = 5  # a note body shorter than RUN but at least this long is matched whole
BUDGET = float(os.environ.get("TRIPWIRE_BUDGET", 8))  # seconds; Hermes kills the hook at 15
DECODE_MAX = 2_000_000  # characters of one string decoded; the rest is checked only as sent
UNCHECKED = "part of the arguments went unchecked"
# Published or rules, not private: the same text can turn up anywhere.
PUBLIC = {"skills", "AGENTS.md", "CLAUDE.md", "README.md"}
B64 = re.compile(r"[A-Za-z0-9+/_-]{24,}")
# The brain named as a path: written out, or as a home folder plus a "brain" path segment.
BRAIN_PATHS = [str(BRAIN), str(BRAIN.resolve()), "/workspace/brain", "~/brain", "$HOME/brain", "${HOME}/brain"]
HOME_REF = re.compile(r"Path\.home\(|expanduser\(|homedir\(|environ|getenv\(|\$HOME|\$\{HOME\}|['\"]~['\"]")
BRAIN_SEG = re.compile(r"""(?:^|['"/])brain(?:$|['"/])""")


def words(text):
    # Escapes such as \n inside code would glue two words together.
    return re.findall(r"[^\W_]+", re.sub(r"\\[nrt]", " ", text).lower())


def runs(ws):
    return {" ".join(ws[i:i + RUN]) for i in range(len(ws) - RUN + 1)}


def body(text):
    # Frontmatter is the same few keys in every note; a short note's body would never fill a run.
    if text.startswith("---\n") and "\n---" in text[4:]:
        return text[text.index("\n---", 4) + 4:]
    return text


def notes():
    for p in sorted(BRAIN.rglob("*.md")):
        rel = p.relative_to(BRAIN)
        if rel.parts[0] not in PUBLIC and not rel.parts[0].startswith("."):
            yield p, rel.as_posix()


def build_index(files):
    index = {}
    for p, rel in files:
        ws = words(body(p.read_text(errors="replace")))
        for r in runs(ws) if len(ws) >= RUN else ({" ".join(ws)} if len(ws) >= SHORT else ()):
            index.setdefault(r, rel)
    return index


def brain_index():
    """Run (or short note) -> note path, rebuilt only when a note changed."""
    files = list(notes())
    sig = hashlib.sha256(repr([(rel, p.stat().st_mtime_ns, p.stat().st_size) for p, rel in files]).encode()).hexdigest()
    cache = STATE / "index.json"
    try:
        saved = json.loads(cache.read_text())
        if saved["sig"] == sig:
            return saved["index"]
    except (OSError, ValueError, KeyError):
        pass
    index = build_index(files)
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sig": sig, "index": index}))
    tmp.replace(cache)
    return index


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def b64_decoded(s):
    """Everything base64 in s, decoded into one text. Each token is decoded from its first four
    offsets in both alphabets, so a prefix glued to it ("u_", "example/") only garbles its start.
    Linear in len(s)."""
    out = []
    for m in B64.finditer(s):
        tok = m.group()
        for alt in (b"+/", b"-_"):
            for off in range(4):
                t = tok[off:]
                t = t[:len(t) - len(t) % 4]
                try:
                    out.append(base64.b64decode(t, altchars=alt).decode("utf-8", errors="replace"))
                except (binascii.Error, ValueError):
                    pass
    return "\n".join(out)


def url_decoded(s):
    for _ in range(3):
        d = urllib.parse.unquote_plus(s)
        if d == s:
            break
        s = d
    return s


def variants(s):
    """(how it was encoded, text), cheapest first: URL-decoded, base64-decoded, and the two stacked.
    The plain string is checked on its own, before any of these."""
    seen = {s}
    u = url_decoded(s)
    if u not in seen:
        seen.add(u)
        yield "URL-encoded", u
    for how, text in (("base64", s), ("URL-encoded base64", u)):
        b = b64_decoded(text[:DECODE_MAX])
        for h, t in ((how, b), (how + " of URL-encoded text", url_decoded(b))):
            if t and t not in seen:
                seen.add(t)
                yield h, t


def names_brain(text):
    if any(re.search(re.escape(p) + r"(?![\w-])", text) for p in BRAIN_PATHS):
        return True
    return bool(HOME_REF.search(text) and BRAIN_SEG.search(text))


def check(args):
    """Note path (or the brain's folder) -> how it was encoded; empty when the arguments look clean."""
    index, hits = brain_index(), {}
    sizes = sorted({k.count(" ") + 1 for k in index})
    firsts = {k.split(" ", 1)[0] for k in index}

    def scan(how, text):
        if names_brain(text):
            hits.setdefault("the brain's folder (named, not quoted)", how)
        ws = words(text)
        for i, w in enumerate(ws):
            if w in firsts:
                for n in sizes:
                    src = index.get(" ".join(ws[i:i + n])) if i + n <= len(ws) else None
                    if src:
                        hits.setdefault(src, how)

    deadline = time.monotonic() + BUDGET
    ss = list(strings(args))
    for s in ss:
        scan("plain", s)
    for s in ss:
        if len(s) > DECODE_MAX:
            hits.setdefault(UNCHECKED, f"a string over {DECODE_MAX // 1_000_000} MB, decoded in part")
        for how, text in variants(s):
            if time.monotonic() > deadline:
                hits.setdefault(UNCHECKED, f"ran out of its {BUDGET:g} s")
                return hits
            scan(how, text)
    return hits


def code(s):
    # In a code span Discord neither previews nor pings; a backtick would close it.
    return "`" + str(s).replace("`", "") + "`"


def log(name, text):
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / name, "a") as f:
        f.write(text.replace("\n", " | ") + "\n")


def post(text):
    log("alerts.log", text)
    if os.environ.get("TRIPWIRE_NO_POST"):
        return
    url = WEBHOOK.read_text().strip()
    body = json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "exfil-tripwire"})
    urllib.request.urlopen(req, timeout=5).close()


def main():
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name") or "?"
        hits = check(payload.get("tool_input") or payload.get("args") or {})
        if hits:
            what = "carries brain content" if set(hits) - {UNCHECKED} else "was too large to check in full"
            lines = [f"🚨 exfil-tripwire: Telma's {code(tool)} call {what} "
                     f"(session {code(payload.get('session_id') or '?')}). The call went ahead; "
                     "its arguments are not repeated here. See the kill switch."]
            for src, how in sorted(hits.items())[:10]:
                lines.append(f"- {code(src)} ({how})")
            if len(hits) > 10:
                lines.append(f"… and {len(hits) - 10} more notes")
            post("\n".join(lines))
    except Exception as e:  # a broken tripwire must say so, and never stop the call
        msg = f"⚠️ exfil-tripwire failed, a call went unchecked or its alert was lost: {code(repr(e)[:300])}"
        try:
            log("failed.log", msg)
            post(msg)
        except Exception as e2:
            print(f"exfil-tripwire: {e!r}; alert failed: {e2!r}", file=sys.stderr)
    print("{}")


if __name__ == "__main__":
    main()
