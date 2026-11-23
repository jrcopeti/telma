"""The trial's brain: the real brain pinned at one commit without the owner's notes about the eval,
checked against the tasks, and each trial's copy built from it (or from the decoy, for chat cases)."""
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BRAIN = Path.home() / "brain"
# Read-only files the mounts expect; the decoy takes them from the real brain.
OVERLAY = ["skills", "AGENTS.md", "CLAUDE.md", "README.md", "install.mjs", ".github", "test"]


def rsync(src, dst):
    subprocess.run(["rsync", "-a", "--delete", f"{src}/", f"{dst}/"], check=True)


# The owner's notes about this eval: in her brain they're real, in a trial they tell her she's being
# tested (step 6 smoke: "the rule-look-alike the eval flags"). They link only to each other.
EVAL_NOTES = ["sha256:558426becce3267da2a46981556369ea9ba5a79655a17259da199687e1bdfc3d",
              "sha256:613ca4a7d5a64921cb679f04155c7d099fe80c071e22017f3240488c3c110135",
              "sha256:fa6ab98416d7e1cf61087db8e2c1880999c242e9da4e58220dc7839fa4c78f0c",
              "sha256:36cfd407d5c0b108b10eb9f4a7ada3c9a40094025c412001e096e9e239a40fee",
              "sha256:e5a59dba8fd2d689c5232aec615fa5d5064659db129d60a09a41b75cf3e45284",
              "sha256:1e712a7014077dddb118ac358dc542ddc0726d4c699f7a19a73ee41563657796",
              "sha256:54a7900eba46c93d9fbad4f3fb8f6a1ea4aa343a1b922663085d8243771ef1a2",
              "sha256:26ae67e227bf6dd3e170940612517f133be527359d69bda51f07a983f9184dc6",
              "sha256:16874a82bed749c9d2fca8a8cd7501d8e8969107835928100b985eb9011cc806",
              "sha256:c18262cc27ef32b0e834b76894d63509ddeea84ae799c5d3863a6c24056928f9"]
# A note linked from elsewhere loses only its words about the eval, or its links to a stripped note, in
# the copy: a passage (as in remove_text) and what takes its place.
EVAL_REWORD = {
    "sha256:8872c75cbe832bd09bc3032ae84e180d0545541ce539d0559e95ed2c04f000da": [{"sha256": "e63966377f3e56a3ae08022c3105d9b696501df8dd9d8c3df20e97672ad5f706", "chars": 52, "with": 'found on 2026-11-21'}],
    "sha256:e0799c989c86870fe7d137f3a632aef3256c8978f8c0e1b9a7817284b0a83d05": [{"sha256": "e1859906de947c82e322ecf76b292fbef4f66cb5c7eb34b39992f616b2b007bc", "chars": 28, "with": '(telma\nrepo)'}],
    "sha256:bf2ccc2a4bfc6101909614111ff79652d31668c582dfdaf5ae98705e59bdecd8": [{"sha256": "3c6e33525f085b78b14ed3243440c14f662ff4730057c77ac9dc971624c67faf", "chars": 28, "with": '(telma repo)'}],
    "sha256:0c33c2c362feb5cdfc8dffe94a5629c81bf43ec8834c132410f3f46629632840": [{"sha256": "931d05bb7404153df9cfdb3f210a0f7bb6397d7ca035c9431a12509658ca95b3", "chars": 65, "with": ''},
                                                                              {"sha256": "98f0a2e171bbe334fe014f8b34343657af99fe834b510eec9351da1c76a7870f", "chars": 75, "with": '2026-11-21 amend decision'}]}
# What still gives the eval away once they're gone.
EVAL_WORDS = re.compile(r"telma[ -]eval|eval-v1|evals/(?:tasks|results|triage)|docs/evals", re.I)


def hashed_paths(pinned):
    """Every file in the pinned brain by `sha256:<hash of its path>`, the way tasks name them."""
    return {"sha256:" + hashlib.sha256(str(p.relative_to(pinned)).encode()).hexdigest(): str(p.relative_to(pinned))
            for p in pinned.rglob("*") if p.is_file()}


def strip_eval_notes(pinned, notes=EVAL_NOTES, reword=EVAL_REWORD):
    """The pinned brain without `notes` and their index lines, and `reword` applied; both name files
    by the hash of their path, like a task. Returns the stripped paths. One the brain no longer has is
    skipped; a note that still names the eval is eval_leaks's."""
    paths = hashed_paths(pinned)
    stripped = [paths[n] for n in notes if n in paths]
    for f in stripped:
        (pinned / f).unlink()
    for n, specs in reword.items():
        if n in paths:
            text = (pinned / paths[n]).read_text()
            for spec in specs:
                if span := passage(text, spec):
                    text = text[:span[0]] + spec["with"] + text[span[1]:]
            (pinned / paths[n]).write_text(text)
    index = pinned / "index.md"
    index.write_text("".join(l for l in index.read_text().splitlines(True) if not any(f"({f})" in l for f in stripped)))
    return stripped


def eval_leaks(pinned, stripped=()):
    """Files in the pinned brain that still name the eval or link to a `stripped` note (a dead link
    lint would fix in every trial). The inbox is skipped: every trial empties it."""
    names = [Path(f).name for f in stripped]
    def leaks(text):
        return EVAL_WORDS.search(text) or any(name in text for name in names)
    return sorted(str(p.relative_to(pinned)) for p in pinned.rglob("*.md")
                  if p.relative_to(pinned).parts[0] != "inbox" and leaks(p.read_text(errors="replace")))


def pin_brain(dest, ref=None):
    """The real brain at its current commit, or at `ref` (a branch with a skill change), without
    history or an old copy of the eval's answers (evals/)."""
    git = ["git", "-C", str(BRAIN)]
    if ref is None and subprocess.run(git + ["status", "--porcelain"], capture_output=True, text=True).stdout.strip():
        sys.exit("~/brain has uncommitted changes: commit or sync them first, so the run pins one brain")
    r = subprocess.run(git + ["rev-parse", "--short", "--verify", "--end-of-options", f"{ref or 'HEAD'}^{{commit}}"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"~/brain has no commit {ref or 'HEAD'}")
    commit = r.stdout.strip()
    dest.mkdir(parents=True)
    archive = subprocess.Popen(git + ["archive", commit], stdout=subprocess.PIPE)
    untar = subprocess.Popen(["tar", "-x", "-C", str(dest)], stdin=archive.stdout)
    archive.stdout.close()  # so archive gets SIGPIPE if tar dies, instead of blocking
    if untar.wait() or archive.wait():
        sys.exit("git archive of ~/brain failed")
    shutil.rmtree(dest / "evals", ignore_errors=True)
    return commit


def passage(text, spec):
    """Where the passage with this hash and length sits in text: (start, end), or None unless it
    is there exactly once. Tasks name real passages by hash, so their text stays out of this repo."""
    n, found = spec["chars"], []
    for i in range(len(text) - n + 1):
        if hashlib.sha256(text[i:i + n].encode()).hexdigest() == spec["sha256"]:
            found.append(i)
    return (found[0], found[0] + n) if len(found) == 1 else None


def unhash(tasks, pinned):
    """Brain paths a task gives as `sha256:<hash of the path>`, so a telling file name stays out of
    this repo, become the path. One that matches no file stays as it is, and check_tasks names it."""
    paths = hashed_paths(pinned)
    for t in tasks:
        for key in ("items", "strip"):
            if key in t:
                t[key] = [paths.get(x, x) for x in t[key]]


def cut(task, f, text):
    """The note without the task's passages, cut one after another as the copy is built."""
    for spec in task["remove_text"][f]:
        span = passage(text, spec)
        if span is None:
            raise ValueError(f"{task['id']}: passage {spec['sha256'][:12]} not found once in {f}")
        text = text[:span[0]] + text[span[1]:]
    return text


def check_tasks(tasks, pinned):
    """Every real task fits the pinned brain, before a trial is paid for: its items, the notes it
    strips and the passages it cuts are all there."""
    problems = []
    for t in tasks:
        if t.get("chat"):
            continue
        for item in t["items"]:
            if not item_path(item, pinned).is_file():
                problems.append(f"{t['id']}: no item {item}")
        problems += [f"{t['id']}: no note {f} to strip" for f in t.get("strip", []) if not (pinned / f).is_file()]
        planted = {f["path"] for f in t.get("plant", [])}
        problems += [f"{t['id']}: no decision {f} to replace" for f in t.get("replaces", {})
                     if (not (pinned / f).is_file() and f not in planted) or f in t.get("strip", [])]
        for f in t.get("plant", []):
            src = REPO / f["from"].removeprefix("telma:")
            section = "## " + f["path"].split("/")[0].capitalize()
            if (pinned / f["path"]).exists():
                problems.append(f"{t['id']}: {f['path']} would overwrite the brain's")
            elif not f["from"].startswith("telma:") or not src.is_file():
                problems.append(f"{t['id']}: no file {f['from']} in this repo to plant")
            elif "index" in f and (section not in (pinned / "index.md").read_text().splitlines()
                                   or not any(l.startswith("# ") for l in src.read_text().splitlines())):
                problems.append(f"{t['id']}: {f['path']} needs a `# ` title and a {section} section in index.md")
        for f in t.get("remove_text", {}):
            if not (pinned / f).is_file():
                problems.append(f"{t['id']}: no note {f} to cut from")
                continue
            try:
                cut(t, f, (pinned / f).read_text())
            except ValueError as e:
                problems.append(str(e))
    if problems:
        sys.exit("tasks don't fit this brain:\n  " + "\n  ".join(problems))


def item_path(item, pinned):
    if item.startswith("telma:"):
        return REPO / item[len("telma:"):]
    if item.startswith("evals/"):
        raise ValueError(f"{item}: an item from this repo needs the telma: prefix")
    return pinned / item


def build_copy(task, local, pinned):
    """The trial's brain, built locally from the pinned brain or the decoy, set up for this task."""
    if task.get("chat"):
        rsync(HERE / "decoy-brain/brain", local)
        for name in OVERLAY:
            src = pinned / name
            if src.is_dir():
                shutil.copytree(src, local / name, dirs_exist_ok=True)
            elif src.is_file():
                shutil.copy2(src, local / name)
    else:
        rsync(pinned, local)
        for p in (local / "inbox").iterdir():
            if p.name != "README.md":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        index = local / "index.md"
        for f in task.get("plant", []):
            plant(local, f)
        for f in task.get("strip", []):
            (local / f).unlink()
            index.write_text("".join(l for l in index.read_text().splitlines(True) if f"({f})" not in l))
        for f in task.get("remove_text", {}):
            (local / f).write_text(cut(task, f, (local / f).read_text()))
        for item in task["items"]:
            src = item_path(item, pinned)
            shutil.copy2(src, local / "inbox" / src.name)
            if not item.startswith(("telma:", "inbox/")):
                (local / item).unlink()  # it moves to the inbox, as before triage filed it
    # The plan's stub, in every copy: if she runs `node sync.mjs` anyway, it does nothing.
    (local / "sync.mjs").write_text('console.log("sync skipped: eval copy");\n')
    # A fresh repo with one commit: a clean `git status` (she reads it and flags stray changes), and
    # no history to read the setup or the answers from. Hooks off: nothing runs from the copy.
    git = ["git", "-C", str(local), "-c", "core.hooksPath=/dev/null", "-c", "user.name=owner", "-c", "user.email=owner@example.com"]
    shutil.rmtree(local / ".git", ignore_errors=True)
    subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "brain"], check=True)


def plant(local, f):
    """A file the task adds to the copy before the run, with its index entry when it is a note, so
    lint's script finds nothing to fix and only its judgment pass can see what was planted."""
    dst = local / f["path"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(item_path(f["from"], None), dst)  # mtime now: lint reads the notes changed recently
    if "index" not in f:
        return
    title = next(l[2:].strip() for l in dst.read_text().splitlines() if l.startswith("# "))
    section = "## " + f["path"].split("/")[0].capitalize()
    lines = (local / "index.md").read_text().splitlines()
    i = lines.index(section) + 1
    while i < len(lines) and lines[i].startswith("- "):
        i += 1
    lines.insert(i, f"- [{title}]({f['path']}) — {f['index']}")
    (local / "index.md").write_text("\n".join(lines) + "\n")

