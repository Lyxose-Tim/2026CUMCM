"""Portable input/code/data identity, valid in a source ZIP as well as Git."""
import json
from pathlib import Path
import platform
import importlib.metadata

from common.hashing import TEXT_HASH_SCHEME, file_record, verify_file
from q1.provenance import source_digest
from q2.provenance import portable_artifact_sha256, git_commit


NUMERICAL = ["q1/fvm.py", "q2/model.py", "q2/inputs.py", "q2/solver.py",
             "q2/archive.py", "q1/provenance.py", "q2/provenance.py",
             "q3/__init__.py", "q3/solver.py", "q3/run.py", "q3/provenance.py",
             "common/hashing.py", "configs/q2.json", "configs/q3.json", "requirements.lock.txt"]


def snapshot(directory="."):
    root = Path(directory)
    hashes = {p: portable_artifact_sha256(root / p) for p in NUMERICAL}
    return {"hash_scheme": TEXT_HASH_SCHEME, "source_hashes": hashes,
            "source_digest": source_digest(hashes), "code_commit": git_commit(root),
            "python": platform.python_version(),
            "packages": {p: importlib.metadata.version(p) for p in ["numpy", "scipy", "openpyxl"]}}


def verify_snapshot(record, directory="."):
    if record.get("hash_scheme") != TEXT_HASH_SCHEME:
        raise ValueError("Unsupported Q3 source hash scheme")
    current = snapshot(directory)
    if record["source_hashes"] != current["source_hashes"]:
        raise ValueError("Q3 numerical sources differ from this run")


def load_run(directory):
    import numpy as np
    directory = Path(directory)
    record = json.loads((directory/"run.json").read_text(encoding="utf-8"))
    if record.get("status") != "computed":
        raise ValueError("Incomplete Q3 run")
    verify_snapshot(record["source"])
    for name, digest in record["files"].items():
        verify_file(directory / name, digest)
    with np.load(directory/"fields.npz") as z:
        fields = {k:z[k] for k in z.files}
    return record, fields
