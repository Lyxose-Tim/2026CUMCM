"""Portable source identity for Q2 numerical and export artifacts."""
from pathlib import Path
import subprocess

from q1.provenance import HASH_SCHEME, artifact_sha256, source_digest
from .inputs import sha256


NUMERICAL_FILES = tuple(f"q2/{name}.py" for name in (
    "__init__", "inputs", "model", "solver", "archive", "provenance",
    "validation", "run", "export", "check_export", "figures", "reproduce", "reports",
)) + (
    "q1/fvm.py", "configs/q2.json", "requirements.lock.txt", "scripts/build_result2.mjs",
)


def git_commit(directory="."):
    """Identify this checkout without decoding its possibly non-ASCII root path."""
    root = Path(directory).resolve()
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="ascii", timeout=5, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def source_snapshot(directory="."):
    root = Path(directory)
    hashes = {path: artifact_sha256(root / path) for path in NUMERICAL_FILES}
    return {
        "source_hash_scheme": HASH_SCHEME,
        "source_hashes": hashes,
        "source_raw_hashes": {path: sha256(root / path) for path in NUMERICAL_FILES},
        "source_digest": source_digest(hashes),
        "code_commit": git_commit(root),
    }


def verify_sources(record, directory="."):
    if record.get("source_hash_scheme") != HASH_SCHEME:
        raise ValueError("Unsupported Q2 source hash scheme")
    if set(record.get("source_hashes", {})) != set(NUMERICAL_FILES):
        raise ValueError("Q2 source scope is incomplete or changed")
    current = source_snapshot(directory)
    changed = [path for path in NUMERICAL_FILES if current["source_hashes"][path] != record["source_hashes"][path]]
    if changed:
        raise ValueError("Current Q2 source mismatch: " + ", ".join(changed))
    if record.get("source_digest") != current["source_digest"]:
        raise ValueError("Recorded Q2 source digest mismatch")
    return {
        "matches": True,
        "source_digest": current["source_digest"],
        "current_code_commit": current["code_commit"],
        "raw_byte_differences": [
            path for path in NUMERICAL_FILES
            if current["source_raw_hashes"][path] != record.get("source_raw_hashes", {}).get(path)
        ],
    }
