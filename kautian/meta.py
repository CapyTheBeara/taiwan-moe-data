"""
meta.py — the provenance block the browser documents carry.

`kautian/v1/meta.json` and its siblings ride *beside* their container, because a
range-request client fetches the metadata before the bytes. A browser document
has no sidecar: it is fetched whole, cached whole, and the client that has it
needs to answer "is the copy in IndexedDB still the current one?" without a
second round trip. So the same three facts ride inside the document, under
`meta`, and the decoder ignores them — `kautian/web/kautian.mjs` reads only
`format`, `model` and `tables`.

`version` is the cache key, and it is deliberately derived from both halves:
the dataset (`sources`) and the code that projected it (`generatorCommit`).
Re-running the builder over the same databases at the same commit reproduces
it, so a redeploy that changed neither does not evict a client's copy; changing
either changes it.
"""

import datetime
import hashlib
import subprocess
from pathlib import Path

UNKNOWN = "unknown"
VERSION_DIGITS = 12


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generator_commit(repo_root):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return UNKNOWN
    return result.stdout.strip()


def version(commit, sources):
    """A short, stable id over the generator commit and every source digest."""
    digest = hashlib.sha256()
    digest.update(commit.encode("utf-8"))
    for name in sorted(sources):
        digest.update(name.encode("utf-8"))
        digest.update(sources[name].encode("utf-8"))
    return digest.hexdigest()[:VERSION_DIGITS]


def build(sources, repo_root=None):
    """The `meta` block for a document built from the named source files."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    commit = generator_commit(root)
    digests = {name: sha256(path) for name, path in sources.items()}
    return {
        "version": version(commit, digests),
        "generatorCommit": commit,
        "buildDate": datetime.date.today().isoformat(),
        "sources": digests,
    }
