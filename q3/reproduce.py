"""Compare a separately computed N=5120 run with the delivered run."""
import argparse
from pathlib import Path
import numpy as np

from q2.archive import write_json
from q2.provenance import portable_artifact_sha256
from q3.provenance import load_run


def check(fresh,directory="results/q3"):
    fresh=Path(fresh)
    directory=Path(directory)
    original,of=load_run(directory/"runs/base_N5120")
    repeated,rf=load_run(fresh/"runs/base_N5120")
    if original["identity"] != repeated["identity"]:
        raise ValueError("Reproduction input/settings differ")
    np.testing.assert_array_equal(of["time_s"][:-1],rf["time_s"][:-1])
    changes={name:float(np.max(np.abs(of[name]-rf[name]))) for name in
             ["moisture","temperature_C","near_states","bracket_states","initial_state","summary"]}
    dt=abs(original["root"]["time_s"]-repeated["root"]["time_s"])
    passed=dt<0.02 and changes["moisture"]<2e-6 and changes["temperature_C"]<2e-7
    record={"passed":passed,"case":"base_N5120","fresh_integration":True,
            "time_difference_s":dt,"max_abs_changes":changes,
            "original_run_sha256":portable_artifact_sha256(directory/"runs/base_N5120/run.json"),
            "fresh_run_sha256":portable_artifact_sha256(fresh/"runs/base_N5120/run.json"),
            "fresh_record":repeated,"verification_source_sha256":portable_artifact_sha256("q3/reproduce.py"),
            "scope":"one new-process N=5120 integration from original uniform initial state; not every case rerun"}
    write_json(directory/"reproduction.json",record)
    if not passed:
        raise ValueError("Independent new-process repetition failed")
    return record


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--fresh",default=".scratch/q3-fresh")
    p.add_argument("--directory",default="results/q3")
    args=p.parse_args()
    print(check(args.fresh,args.directory)["max_abs_changes"])
