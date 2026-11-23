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
              "sha256:c18262cc27ef32b0e834b76894d63509ddeea84ae799c5d3863a6c24056928f9",
              "sha256:ebbd6c65c80d5424356997943c56b1f65f26d633609e814385f3e8ab14e4a331",
              "sha256:e132ea8ea0644948645646dff4b45407f3ffac46b06a0d4294d6ed43fd4006f3"]
# A note linked from elsewhere loses only its words about the eval, or its links to a stripped note, in
# the copy: a passage (as in remove_text) and what takes its place.
EVAL_REWORD = {
    "sha256:8872c75cbe832bd09bc3032ae84e180d0545541ce539d0559e95ed2c04f000da": [{"sha256": "e63966377f3e56a3ae08022c3105d9b696501df8dd9d8c3df20e97672ad5f706", "chars": 52, "with": 'found on 2026-11-21'}],
    "sha256:e0799c989c86870fe7d137f3a632aef3256c8978f8c0e1b9a7817284b0a83d05": [{"sha256": "e1859906de947c82e322ecf76b292fbef4f66cb5c7eb34b39992f616b2b007bc", "chars": 28, "with": '(telma\nrepo)'}],
    "sha256:bf2ccc2a4bfc6101909614111ff79652d31668c582dfdaf5ae98705e59bdecd8": [{"sha256": "3c6e33525f085b78b14ed3243440c14f662ff4730057c77ac9dc971624c67faf", "chars": 28, "with": '(telma repo)'}],
    "sha256:0c33c2c362feb5cdfc8dffe94a5629c81bf43ec8834c132410f3f46629632840": [{"sha256": "931d05bb7404153df9cfdb3f210a0f7bb6397d7ca035c9431a12509658ca95b3", "chars": 65, "with": ''},
                                                                              {"sha256": "98f0a2e171bbe334fe014f8b34343657af99fe834b510eec9351da1c76a7870f", "chars": 75, "with": '2026-11-21 amend decision'}],
    "sha256:a48746cae70c44e7e105b594aad338ddd105c93c1cb445a40ba6aab785ba69e5": [{"sha256": "d662148ffffa8b8baa75d3e362ebc5145bbfa3455aaa9baf047dea24f64c5547", "chars": 122, "with": ''}],
    "sha256:0f27de5f662fb72cdd63d0c7fcaf895c343c00b9e3ab6c1a249405ebfead6bbd": [{"sha256": "970407ae9461024b6f081b576fe2dccba1b221b7e0233519f477aa4a69c8a4d0", "chars": 51, "with": '; the work now is the public showcase.'},
                                                                              {"sha256": "eed313d5263155b8158defe345c4e0f0a0098a261a0af39d25a0bd25d54df9df", "chars": 155, "with": ' **Next, in order:** showcase step 5'},
                                                                              {"sha256": "cd1ead34092c7a2cca7b18df878da34feb7236cff42df97396258fad778aab4f", "chars": 69, "with": ')'},
                                                                              {"sha256": "c54212f96360b592b5c83b4ed77c2498788807304a8d4e8783628ec4a535861f", "chars": 92, "with": ''},
                                                                              {"sha256": "0d2512dfc03d2a95d001fdb3c34d88ac09b572a897ffed78e600d6e4c7efdd51", "chars": 1830, "with": ''},
                                                                              {"sha256": "5a43e0fe2b91a2216fd0abcbbc9e120ea0bef364b40eef292a4c6706175811b5", "chars": 18, "with": ''},
                                                                              {"sha256": "68d1b392ff122930186e5e316b9038fb87c3fe467811856c3ae71de02d4d97f6", "chars": 41, "with": '`docs/adr/`.'},
                                                                              {"sha256": "f9edc884b23c12d9e9126bf6172a381971858c197abd8256338233a61ad7e1e5", "chars": 27, "with": ''},
                                                                              {"sha256": "d267a5cabb73fbcb5b95ac7943fb5e0ad2f892b01e18de031e6e65af9b037e0b", "chars": 474, "with": ''},
                                                                              {"sha256": "95c21e72f1b721f503b147094e264e4b0bda50ff7c2ad0f7253bba0d3959765c", "chars": 81, "with": 'telma repo `docs/showcase/PLAN.md` (read'}]}
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


def stale_rewords(pinned, reword=EVAL_REWORD):
    """Rewords that no longer fit the pinned brain: the note is gone or the passage isn't there once.
    EVAL_WORDS only catches a few spellings, so a reworded passage that moved can leave prose about
    the eval behind unflagged; on her current brain every reword has to fit."""
    paths = hashed_paths(pinned)
    return [f"{paths.get(n, n)}: " + (f"passage {s['sha256'][:12]}" if n in paths else "no such note")
            for n, specs in reword.items() for s in specs
            if n not in paths or not passage((pinned / paths[n]).read_text(), s)]


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

