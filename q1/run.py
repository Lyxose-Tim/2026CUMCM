"""python -m q1.run --data-root path/to/A题. Export remains behind validation."""
import argparse
import gc
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np

from .archive import save_archive,write_json
from .fvm import Grid,RadialModel
from .inputs import read_inputs,read_config,sha256
from .solver import integrate,DIAGNOSTIC_COLUMNS
from .validation import difference,boundary_check,balance_check,analytic_check,spatial_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--config",default="configs/q1.json")
    parser.add_argument("--output",default="results/q1")
    args = parser.parse_args()
    cfg = read_config(args.config)
    env,inputs = read_inputs(args.data_root,cfg)
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    checks = subprocess.run([sys.executable,"-m","pytest","-q"],capture_output=True,text=True)
    (out/"unit_tests.txt").write_text(checks.stdout+checks.stderr,encoding="utf-8")
    if checks.returncode:
        raise RuntimeError("Independent startup tests failed; see unit_tests.txt")
    print(checks.stdout.strip(),flush=True)
    p,settings = cfg["parameters"],cfg["solver"]
    previous = None
    previous_errors = None
    streak = 0
    history = []
    all_output = {}
    for N in cfg["grids"]:
        print(f"Spatial run N={N}",flush=True)
        grid = Grid(N,p["R"],p["L"])
        sol = integrate(RadialModel(grid,p,env),settings,check_envelope=True)
        samples = tuple(a.copy() for a in sol.output(grid))
        all_output[f"T_{N}"] = samples[0]
        all_output[f"C_{N}"] = samples[1]
        record = {"N":N,"solver":sol.diagnostics,"boundary":boundary_check(sol,grid,p,env)}
        if previous is not None:
            delta = difference(previous,samples,sol.times)
            record["difference"] = delta
            ok = all(delta[name]["max_abs"]<=cfg["budgets"][f"space_{name}"] for name in ["T","C"])
            decreasing = previous_errors is None or all(delta[name]["max_abs"]<previous_errors[name] for name in ["T","C"])
            streak = streak+1 if ok and decreasing else 0
            if previous_errors is not None:
                record["observed_order"] = {name:float(np.log2(previous_errors[name]/delta[name]["max_abs"])) for name in ["T","C"]}
            previous_errors = {name:delta[name]["max_abs"] for name in ["T","C"]}
            print(json.dumps({"N":N,"difference":delta,"consecutive_within_budget":streak}),flush=True)
        history.append(record)
        write_json(out/"convergence.json",history)
        np.savez_compressed(out/"grid_outputs.npz",time_s=sol.times,radius_cm=np.linspace(0,2,21),**all_output)
        previous = samples
        if streak >= 2:
            break
        del sol
        gc.collect()
    space_passed = streak >= 2
    print(f"Spatial gate: {space_passed}; N={N}. Continuing independent final diagnostics.",flush=True)
    tight = {**settings,"rtol":settings["rtol"]/10,"atol_T":settings["atol_T"]/10,"atol_C":settings["atol_C"]/10,"max_step":settings["max_step"]/2}
    # The stricter BDF solution is archived, avoiding the looser solution in reporting.
    final = integrate(RadialModel(grid,p,env),tight,check_envelope=True,audit=True)
    final_samples = final.output(grid)
    tolerance_difference = difference(previous,final_samples,final.times)
    print("Strict BDF comparison: "+json.dumps(tolerance_difference),flush=True)
    radau_settings = {**tight,"method":"Radau"}
    radau = integrate(RadialModel(grid,p,env),radau_settings,check_envelope=True)
    radau_difference = difference(final_samples,radau.output(grid),final.times)
    radau_diag = radau.diagnostics
    del radau
    gc.collect()
    time_passed = all(d[name]["max_abs"]<=cfg["budgets"][f"time_{name}"] for d in [tolerance_difference,radau_difference] for name in ["T","C"])
    print("Radau comparison: "+json.dumps(radau_difference),flush=True)
    analytic,analytic_data = analytic_check(grid,p,tight)
    balance,balance_data = balance_check(final,grid,p)
    boundary = boundary_check(final,grid,p,env)
    numerical_passed = space_passed and time_passed and all(r["passed"] for test in [analytic,balance,boundary] for r in test.values())
    verification = {"numerical_passed":numerical_passed,"space_passed":space_passed,"consecutive_within_budget":streak,"max_grid":cfg["grids"][-1],"N":N,"time_passed":time_passed,"tolerance_difference":tolerance_difference,"radau_difference":radau_difference,"radau_diagnostics":radau_diag,"analytic":analytic,"balance":balance,"boundary":boundary,"manufactured_operator":spatial_metrics(),"accepted_envelope_passed":True,"output_envelope_passed":True,"export_passed":False,"cross_review":"pending"}
    write_json(out/"verification.json",verification)
    np.savetxt(out/"balance.csv",balance_data,delimiter=",",header="time_s,heat_balance,moisture_balance,heat_quadrature_check,moisture_quadrature_check",comments="")
    np.savetxt(out/"accepted_steps.csv",final.accepted,delimiter=",",header=",".join(DIAGNOSTIC_COLUMNS),comments="")
    for name,data in zip(["T","C"],analytic_data):
        np.savetxt(out/f"bessel_{name}.csv",data,delimiter=",",header="time_s,radius_cm,numerical,series,absolute_error",comments="")
    source_hashes = {str(path).replace("\\","/"):sha256(path) for folder in ["q1","tests","configs"] for path in sorted(Path(folder).rglob("*")) if path.is_file() and "__pycache__" not in str(path)}
    metadata = {"status":"numerically_verified" if numerical_passed else "diagnostic_only", "inputs":inputs,"configuration":cfg,"solver":final.diagnostics,"python":platform.python_version(),"platform":platform.platform(),"dependencies":{name:importlib.metadata.version(name) for name in ["numpy","scipy","matplotlib","openpyxl","pytest"]},"code_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"source_hashes":source_hashes,"command":["python","-m","q1.run","--data-root","<path-to-A题>","--config",args.config],"verification_sha256":sha256(out/"verification.json")}
    save_archive(out/"archive",final,grid,metadata)
    np.savetxt(out/"environment.csv",env.observations,delimiter=",",header="time_s,temperature_C,equivalent_moisture",comments="")
    print(json.dumps({"numerical_passed":numerical_passed,"archive_status":metadata["status"],"N":N}),flush=True)
    if not numerical_passed:
        print("Formal Excel/table export blocked by validation. Diagnostics retained.",flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
