"""Bind the committed tree without making a tracked file contain its own commit."""
import hashlib
from pathlib import Path
import subprocess


AUDIT_PATH = "results/q3/audit.json"
CONTENT_PATHS = [".", f":(exclude){AUDIT_PATH}"]


def git_bytes(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Cannot read Git checkout metadata") from exc
    if result.returncode:
        raise ValueError("Cannot read Git checkout metadata")
    return result.stdout


def committed_tree(root, ref):
    tree = git_bytes(root, "ls-tree", "-r", "-z", "--full-tree", ref)
    # Parse NUL-delimited entries so spaces, tabs and non-ASCII paths stay exact.
    entries = [entry for entry in tree.split(b"\0") if entry
               and entry.split(b"\t", 1)[1] != AUDIT_PATH.encode("ascii")]
    content = b"".join(entry + b"\0" for entry in entries)
    return {
        "hash_scheme": "sha256-git-ls-tree-v1",
        "excluded_path": AUDIT_PATH,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def checkout_identity(directory="."):
    """Return current HEAD and its content binding; only a source ZIP returns None."""
    root = Path(directory).resolve()
    if not (root / ".git").exists():
        return None
    head = git_bytes(root, "rev-parse", "HEAD").decode("ascii").strip()
    changes = git_bytes(root, "diff", "--name-only", "-z", "HEAD", "--", *CONTENT_PATHS)
    untracked = git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z",
                          "--", *CONTENT_PATHS)
    if changes or untracked:
        raise ValueError("Uncommitted content: commit delivery files before writing/checking the Git audit")
    return {"code_commit": head, "git_tree": committed_tree(root, head)}


def verify_git_binding(record, directory="."):
    if "code_commit" in record:
        raise ValueError("Legacy audit commit record; regenerate using the committed-tree binding")
    current = checkout_identity(directory)
    if current is not None:
        audited_commit = record.get("audited_content_commit")
        if not isinstance(audited_commit, str):
            raise ValueError("Audit has no committed tree origin")
        root = Path(directory).resolve()
        if (record.get("git_tree") != committed_tree(root, audited_commit)
                or record["git_tree"] != current["git_tree"]):
            raise ValueError("Current committed tree differs from the recorded audit")
    return current
