"""Portable source identity for Q2 numerical and export artifacts."""
from pathlib import Path
import subprocess

from common.hashing import RAW_HASH_SCHEME, file_sha256, raw_sha256
from q1.provenance import HASH_SCHEME, artifact_sha256, source_digest


NUMERICAL_FILES = tuple(f"q2/{name}.py" for name in (
    "__init__", "inputs", "model", "solver", "archive", "validation", "run",
)) + (
    "q1/fvm.py", "common/hashing.py", "configs/q2.json", "requirements.lock.txt",
)

DELIVERY_FILES = tuple(f"q2/{name}.py" for name in (
    "provenance", "export", "check_export",
)) + (
    "common/workbooks.py", "scripts/hash_record.mjs",
    "scripts/build_result2.mjs", "scripts/build_result2_stream.py",
)

def portable_artifact_sha256(path):
    """Compatibility entry point for all declared text and binary artifacts."""
    return file_sha256(path)


def git_commit(directory="."):
    """Identify this checkout without decoding its possibly non-ASCII root path."""
    root = Path(directory).resolve()
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            [
                "git", "-c", f"safe.directory={root.as_posix()}",
                "-C", str(root), "rev-parse", "HEAD",
            ],
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
        "source_raw_hash_scheme": RAW_HASH_SCHEME,
        "source_raw_hashes": {path: raw_sha256(root / path) for path in NUMERICAL_FILES},
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
        "source_raw_hash_scheme": RAW_HASH_SCHEME,
        "source_raw_hashes": {path: raw_sha256(root / path) for path in DELIVERY_FILES},
        "source_digest": source_digest(hashes),
        "code_commit": git_commit(root),
    }
