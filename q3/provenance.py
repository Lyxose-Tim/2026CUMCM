"""Portable input/code/data identity, valid in a source ZIP as well as Git."""
import json
from pathlib import Path
import platform
import importlib.metadata

from q1.provenance import source_digest
from q2.provenance import portable_artifact_sha256, git_commit
from q2.inputs import sha256


NUMERICAL = ["q1/fvm.py", "q2/model.py", "q2/inputs.py", "q2/solver.py",
             "q2/archive.py", "q1/provenance.py", "q2/provenance.py",
             "q3/__init__.py", "q3/solver.py", "q3/run.py", "q3/provenance.py",
             "configs/q2.json", "configs/q3.json", "requirements.lock.txt"]


def snapshot():
    hashes = {p: portable_artifact_sha256(p) for p in NUMERICAL}
    return {"hash_scheme": "sha256-text-lf-v1", "source_hashes": hashes,
            "source_digest": source_digest(hashes), "code_commit": git_commit(),
            "python": platform.python_version(),
            "packages": {p: importlib.metadata.version(p) for p in ["numpy", "scipy", "openpyxl"]}}


def verify_snapshot(record):
    current = snapshot()
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
        if sha256(directory/name) != digest:
            raise ValueError(f"Q3 artifact mismatch: {name}")
    with np.load(directory/"fields.npz") as z:
        fields = {k:z[k] for k in z.files}
    return record, fields
