"""Portable source and artifact identity for the shrinking-domain Q4 runs."""
import json
from pathlib import Path
import platform
import importlib.metadata

from common.hashing import TEXT_HASH_SCHEME, verify_file
from q1.provenance import source_digest
from q2.provenance import git_commit, portable_artifact_sha256


NUMERICAL = [
    "q1/fvm.py", "q2/inputs.py", "q2/model.py", "q2/solver.py",
    "q3/solver.py", "q4/__init__.py", "q4/inputs.py", "q4/model.py",
    "q4/solver.py", "q4/run.py", "q4/provenance.py",
    "common/hashing.py", "configs/q2.json", "configs/q4.json", "requirements.lock.txt",
]


def snapshot(directory="."):
    root = Path(directory)
    hashes = {p: portable_artifact_sha256(root / p) for p in NUMERICAL}
    return {
        "hash_scheme": TEXT_HASH_SCHEME,
        "source_hashes": hashes,
        "source_digest": source_digest(hashes),
        "code_commit": git_commit(root),
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ["numpy", "scipy", "openpyxl"]},
    }


def verify_snapshot(record, directory="."):
    if record.get("hash_scheme") != TEXT_HASH_SCHEME:
        raise ValueError("Unsupported Q4 source hash scheme")
    current = snapshot(directory)
    if record["source_hashes"] != current["source_hashes"]:
        raise ValueError("Q4 numerical sources differ from this run")


def load_run(directory):
    import numpy as np
    directory = Path(directory)
    record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if record.get("status") not in {
        "computed", "threshold_not_reached", "root_found_post_state_unavailable"
    }:
        raise ValueError("Incomplete Q4 run")
    verify_snapshot(record["source"])
    for name, digest in record["files"].items():
        verify_file(directory / name, digest)
    with np.load(directory / "fields.npz") as z:
        fields = {key: z[key] for key in z.files}
    return record, fields

