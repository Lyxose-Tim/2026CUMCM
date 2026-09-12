"""Portable source identity for Q2 numerical and export artifacts."""
import hashlib
from pathlib import Path
import subprocess

from q1.provenance import HASH_SCHEME, artifact_sha256, source_digest
from .inputs import sha256


NUMERICAL_FILES = tuple(f"q2/{name}.py" for name in (
    "__init__", "inputs", "model", "solver", "archive", "validation", "run",
)) + (
    "q1/fvm.py", "configs/q2.json", "requirements.lock.txt",
)

DELIVERY_FILES = tuple(f"q2/{name}.py" for name in (
    "provenance", "export", "check_export",
)) + ("scripts/build_result2.mjs", "scripts/build_result2_stream.py")

JAVASCRIPT_TEXT_SUFFIXES = {".js", ".mjs", ".cjs"}


def portable_artifact_sha256(path):
    """Extend the repository's LF-normalized text hash to JavaScript modules."""
    path = Path(path)
    if path.suffix.lower() in JAVASCRIPT_TEXT_SUFFIXES:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return artifact_sha256(path)


def git_commit(directory="."):
    """Identify this checkout without decoding its possibly non-ASCII root path."""
    root = Path(directory).resolve()
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="ascii", timeout=5, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def source_snapshot(directory="."):
    root = Path(directory)
    hashes = {path: portable_artifact_sha256(root / path) for path in NUMERICAL_FILES}
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
    if not set(NUMERICAL_FILES).issubset(record.get("source_hashes", {})):
        raise ValueError("Q2 numerical source scope is incomplete")
    current = source_snapshot(directory)
    changed = [path for path in NUMERICAL_FILES if current["source_hashes"][path] != record["source_hashes"][path]]
    if changed:
        raise ValueError("Current Q2 source mismatch: " + ", ".join(changed))
    return {
        "matches": True,
        "source_digest": current["source_digest"],
        "recorded_full_source_digest": record.get("source_digest"),
        "current_code_commit": current["code_commit"],
        "raw_byte_differences": [
            path for path in NUMERICAL_FILES
            if current["source_raw_hashes"][path] != record.get("source_raw_hashes", {}).get(path)
        ],
    }


def delivery_snapshot(directory="."):
    root = Path(directory)
    hashes = {path: portable_artifact_sha256(root / path) for path in DELIVERY_FILES}
    return {
        "source_hash_scheme": HASH_SCHEME,
        "source_hashes": hashes,
        "source_raw_hashes": {path: sha256(root / path) for path in DELIVERY_FILES},
        "source_digest": source_digest(hashes),
        "code_commit": git_commit(root),
    }
