"""Fresh-process reintegration of a selected checked sensitivity scenario."""
import argparse
import importlib.metadata
from pathlib import Path

from .archive import write_json
from .inputs import read_inputs
from .sensitivity import run_job, load_series
from .sensitivity_metrics import compare, within_budget
from .sensitivity_report import verified_runs
from .provenance import source_snapshot, artifact_sha256, HASH_SCHEME, git_commit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--directory",default="results/q1_sensitivity")
    parser.add_argument("--run",default="D_prefactor_minus20_N20480_BDF_base")
    parser.add_argument("--output",default="results/q1_sensitivity/reproduction")
    args=parser.parse_args()
    root,out=Path(args.directory),Path(args.output)
    # No existing cache may satisfy a reintegration request.
    if out.exists():
        raise ValueError("Reproduction destination must be new; choose another --output")
    m,v,records=verified_runs(root)
    original=records[args.run]
    env,inputs=read_inputs(args.data_root,m["configuration"])
    job={"key":args.run,"case":original["case"],"N":original["N"],"settings":original["settings"],
         "inputs":inputs,"observations":env.observations.tolist(),"source":source_snapshot(),
         "dependencies":{name:importlib.metadata.version(name) for name in m["dependencies"]},"directory":str(out)}
    _,new=run_job(job)
    a=load_series(root/"runs"/args.run/"series.npz")
    b=load_series(out/"series.npz")
    difference=compare(a,b)
    passed=new["passed"] and within_budget(difference,m["configuration"]["budgets"],"time")
    record={"passed":passed,"artifact_hash_scheme":HASH_SCHEME,"source_digest":new["source_digest"],"code_commit":git_commit(),"reintegrated_run":args.run,"cache_used":False,
            "comparison":difference,"new_run_record":(out/"run.json").as_posix(),"new_run_sha256":artifact_sha256(out/"run.json"),
            "original_run_sha256":m["run_records"][args.run],"accepted_steps":new["diagnostics"]["accepted_steps"],
            "command":["python","-m","q1.sensitivity_reproduce","--data-root","<path-to-A题>","--directory",args.directory,
                       "--run",args.run,"--output",args.output]}
    write_json(root/"reproduction.json",record)
    if not passed:
        raise RuntimeError("Fresh sensitivity reintegration failed comparison")
    print(f"Fresh reintegration passed: {difference}")


if __name__=="__main__":
    main()
