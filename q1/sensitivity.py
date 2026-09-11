"""Reproducible OAT scenarios with immutable baseline and extreme-case audits."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import traceback

import numpy as np

from .archive import write_json
from .fvm import Grid, RadialModel
from .inputs import read_config, read_inputs, sha256, Environment
from .solver import integrate, DIAGNOSTIC_COLUMNS
from .validation import balance_check, boundary_check
from .sensitivity_metrics import compare, within_budget, endpoints, elasticity, METRICS, UNITS


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def scenarios(config, design):
    p = config["parameters"]
    result = [{"id":"baseline","parameter":None,"relative_change":0.,"parameters":p.copy()}]
    for key in design["parameters"]:
        if key not in ("h","hm","D_prefactor"):
            raise ValueError(f"Parameter outside approved Q1 OAT scope: {key}")
        for delta in design["relative_changes"]:
            if delta not in (-0.2,-0.1,0.1,0.2):
                raise ValueError("Only approved +/-10% and +/-20% scenarios supported")
            name = f"{key}_{'plus' if delta>0 else 'minus'}{round(abs(delta)*100)}"
            result.append({"id":name,"parameter":key,"relative_change":delta,
                           "parameters":{**p,key:p[key]*(1+delta)}})
    if len(result)!=13 or len({c["id"] for c in result})!=13:
        raise ValueError("Expected baseline and twelve distinct OAT scenarios")
    return result


def protected_files():
    paths = [Path("results/result1.xlsx")]
    for folder in ("results/q1","figures/q1"):
        paths.extend(p for p in Path(folder).rglob("*") if p.is_file())
    return {p.as_posix():sha256(p) for p in sorted(paths)}


def load_series(path):
    with np.load(path,allow_pickle=False) as f:
        return {k:f[k] for k in f.files}


def historical_baseline(directory="results/q1/archive"):
    """Read verified chunks one at a time: never round Excel values for comparisons."""
    root = Path(directory)
    m = read_config(root/"manifest.json")
    if m["status"] != "numerically_verified" or sha256(root/"geometry.npz") != m["geometry_sha256"]:
        raise ValueError("Baseline archive is unverified or damaged")
    with np.load(root/"geometry.npz") as g:
        weights, idx, r = g["volume_m3"],g["output_indices"],g["radius_m"]
    pieces = {k:[] for k in ("time_s","temperature_C","moisture","mean_temperature_C","mean_moisture")}
    for item in m["chunks"]:
        path = root/item["file"]
        if sha256(path) != item["sha256"]:
            raise ValueError("Baseline chunk hash mismatch")
        with np.load(path) as f:
            pieces["time_s"].append(f["time_s"])
            for key,mean_key in (("temperature_C","mean_temperature_C"),("moisture","mean_moisture")):
                u = f[key]
                pieces[key].append(u[:,idx])
                pieces[mean_key].append(u@weights/weights.sum())
    return {**{k:np.concatenate(v) for k,v in pieces.items()},"radius_m":r[idx]}


def run_job(job):
    root = Path(job["directory"])
    root.mkdir(parents=True,exist_ok=True)
    fingerprint = digest({k:v for k,v in job.items() if k!="directory"})
    record_path = root/"run.json"
    if record_path.exists():
        record = read_config(record_path)
        if record["fingerprint"]!=fingerprint:
            raise ValueError(f"Stale cached run {root}; use a new output directory")
        if not all(sha256(root/name)==expected for name,expected in record["files"].items()):
            raise ValueError(f"Corrupt cached run {root}")
        return job["key"],record
    try:
        case = job["case"]
        p = case["parameters"]
        grid = Grid(job["N"],p["R"],p["L"])
        env = Environment(job["observations"])
        sol = integrate(RadialModel(grid,p,env),job["settings"],check_envelope=True,audit=True)
        T,C = sol.output(grid)
        np.savez_compressed(root/"series.npz",time_s=sol.times,radius_m=grid.r[grid.output_indices],
                            temperature_C=T,moisture=C,
                            mean_temperature_C=sol.temperature_C@grid.volume/grid.volume.sum(),
                            mean_moisture=sol.moisture@grid.volume/grid.volume.sum(),
                            final_radius_m=grid.r,final_temperature_C=sol.temperature_C[-1],
                            final_moisture=sol.moisture[-1],volume_m3=grid.volume)
        balance,rows = balance_check(sol,grid,p)
        boundary = boundary_check(sol,grid,p,env)
        np.savetxt(root/"balance.csv",rows,delimiter=",",comments="",
                   header="time_s,heat_balance,moisture_balance,heat_quadrature_difference,moisture_quadrature_difference")
        np.savetxt(root/"accepted_steps.csv",sol.accepted,delimiter=",",comments="",header=",".join(DIAGNOSTIC_COLUMNS))
        record = {"fingerprint":fingerprint,"case":case,"N":job["N"],"settings":job["settings"],
                  "inputs":job["inputs"],"source_hashes":job["source_hashes"],"diagnostics":sol.diagnostics,
                  "balance":balance,"boundary":boundary,"accepted_and_output_envelopes_passed":True,
                  "passed":all(r["passed"] for r in (*balance.values(),*boundary.values())),
                  "files":{f:sha256(root/f) for f in ("series.npz","balance.csv","accepted_steps.csv")}}
        write_json(record_path,record)
        return job["key"],record
    except Exception as exc:
        write_json(root/"failure.json",{"fingerprint":fingerprint,"error":str(exc),"traceback":traceback.format_exc()})
        raise


def validate_results(root, config, design, cases, records):
    def series(key):
        return load_series(root/"runs"/key/"series.npz")
    N = design["production_N"]
    b = config["budgets"]
    key = lambda case,n=N,method="BDF",level="base": f"{case}_N{n}_{method}_{level}"
    baseline = series(key("baseline"))
    same_baseline = compare(historical_baseline(),baseline)
    numeric = {}
    for case in cases:
        if abs(case["relative_change"]) != 0.2:
            continue
        name = case["id"]
        outputs = [series(key(name,n)) for n in design["extreme_grids"]]
        pairs = [compare(u,v) for u,v in zip(outputs[:-1],outputs[1:])]
        decreasing = all(pairs[1][s]["max_abs"] < pairs[0][s]["max_abs"] for s in ("T","C"))
        orders = {s:float(np.log2(pairs[0][s]["max_abs"]/pairs[1][s]["max_abs"])) for s in ("T","C")}
        time = compare(outputs[-1],series(key(name,level="tight")))
        check = {"space_pairs":pairs,"observed_order":orders,"time":time,
                 "passed":decreasing and all(within_budget(d,b,"space") for d in pairs) and within_budget(time,b,"time")}
        if name in design["radau_cases"]:
            radau = compare(series(key(name,level="tight")),series(key(name,method="Radau",level="tight")))
            check.update(radau=radau,passed=check["passed"] and within_budget(radau,b,"time"))
        numeric[name] = check
    q0 = endpoints(baseline,config["parameters"])
    responses = []
    for case in cases:
        data = series(key(case["id"]))
        cmp = compare(baseline,data)
        q = endpoints(data,case["parameters"])
        unaffected = "C" if case["parameter"]=="h" else "T"
        decoupled = cmp[unaffected]["max_abs"]<=b[f"time_{unaffected}"]
        responses.append({"id":case["id"],"parameter":case["parameter"],"relative_change":case["relative_change"],
                          "endpoint":q,"endpoint_difference":{m:q[m]-q0[m] for m in METRICS},
                          "field_difference":cmp,"unaffected_field":unaffected,"decoupling_passed":decoupled})
    elasticities = []
    by_id = {r["id"]:r for r in responses}
    for param in design["parameters"]:
        for delta in (0.1,0.2):
            minus,plus = [by_id[f"{param}_{sign}{round(delta*100)}"]["endpoint"] for sign in ("minus","plus")]
            for metric,unit in zip(METRICS,UNITS):
                resolution = 0.001 if unit=="K" else 1e-5
                elasticities.append({"parameter":param,"delta":delta,"metric":metric,"unit":unit,
                                     "baseline":q0[metric],"minus_value":minus[metric],"plus_value":plus[metric],
                                     "global_resolution":resolution,
                                     **elasticity(minus[metric],q0[metric],plus[metric],delta,resolution)})
    passed = (all(r["passed"] for r in records.values()) and all(r["passed"] for r in numeric.values())
              and all(r["decoupling_passed"] for r in responses) and within_budget(same_baseline,b,"time"))
    return {"status":"numerically_verified" if passed else "diagnostic_only","budgets":b,
            "baseline_reproduction":same_baseline,"extreme_checks":numeric,"responses":responses,"elasticities":elasticities}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--directory",default="results/q1_sensitivity")
    parser.add_argument("--workers",type=int,default=2)
    args = parser.parse_args(argv)
    if args.workers not in (1,2):
        raise ValueError("Use one or two workers to bound memory usage")
    root = Path(args.directory)
    if root.resolve()==Path("results").resolve() or any(root.resolve().is_relative_to(Path(p).resolve()) for p in ("results/q1","figures/q1")):
        raise ValueError("Refuse to overwrite baseline output directories")
    root.mkdir(parents=True,exist_ok=True)
    config,design = read_config(),read_config("configs/q1_sensitivity.json")
    env,metadata = read_inputs(args.data_root,config)
    protected = protected_files()
    snapshot = root/"protected_baseline.json"
    if snapshot.exists() and read_config(snapshot)!=protected:
        raise ValueError("Protected baseline changed since experiment start")
    write_json(snapshot,protected)
    source = [Path(f"q1/{s}.py") for s in ("inputs","fvm","solver","validation","reference","sensitivity","sensitivity_metrics")]
    source += [Path(p) for p in ("configs/q1.json","configs/q1_sensitivity.json","requirements.lock.txt")]
    source_hashes = {p.as_posix():sha256(p) for p in source}
    cases = scenarios(config,design)
    settings = config["solver"]
    tight = {**settings,**{k:settings[k]*design["time_refinement_factor"] for k in ("rtol","atol_T","atol_C")},
             "max_step":settings["max_step"]/2}
    jobs = []
    for case in cases:
        specs = [(design["production_N"],settings,"base")]
        if abs(case["relative_change"])==0.2:
            specs += [(n,settings,"base") for n in design["extreme_grids"][:-1]]
            specs += [(design["production_N"],tight,"tight")]
        if case["id"] in design["radau_cases"]:
            specs += [(design["production_N"],{**tight,"method":"Radau"},"tight")]
        for n,s,level in specs:
            key = f"{case['id']}_N{n}_{s['method']}_{level}"
            jobs.append({"key":key,"case":case,"N":n,"settings":s,"inputs":metadata,"observations":env.observations.tolist(),
                         "source_hashes":source_hashes,"directory":str(root/"runs"/key)})
    command = ["python","-m","q1.sensitivity","--data-root","<path-to-A题>","--directory",args.directory,"--workers",str(args.workers)]
    manifest = {"status":"running","configuration":config,"design":design,"source_hashes":source_hashes,"inputs":metadata,
                "code_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                "python":platform.python_version(),"platform":platform.platform(),"command":command,
                "dependencies":{name:importlib.metadata.version(name) for name in ("numpy","scipy","matplotlib","pytest")},
                "thread_environment":{name:os.environ.get(name) for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")},
                "axis_order":["time_s","formal_radius_m"],"dtype":"float64","runs":len(jobs)}
    write_json(root/"manifest.json",manifest)
    records = {}
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_job,j) for j in jobs]
            for done in as_completed(futures):
                key,record = done.result()
                records[key] = record
                print(f"[{len(records)}/{len(jobs)}] {key}: {'PASS' if record['passed'] else 'FAIL'} ({record['diagnostics']['seconds']:.1f}s)",flush=True)
        result = validate_results(root,config,design,cases,records)
        result["protected_baseline_unchanged"] = protected_files()==protected
        # Re-read originals as well: changes during the run are not silently accepted.
        _,end_metadata = read_inputs(args.data_root,config)
        result["source_inputs_unchanged"] = end_metadata==metadata
        if not result["protected_baseline_unchanged"] or not result["source_inputs_unchanged"]:
            result["status"] = "diagnostic_only"
        write_json(root/"verification.json",result)
        manifest.update(status=result["status"],verification_sha256=sha256(root/"verification.json"),
                        run_records={key:sha256(root/"runs"/key/"run.json") for key in sorted(records)})
        write_json(root/"manifest.json",manifest)
        if result["status"]!="numerically_verified":
            raise RuntimeError("Sensitivity acceptance failed; see verification.json")
    except Exception as exc:
        manifest["status"]="diagnostic_only"
        write_json(root/"manifest.json",manifest)
        write_json(root/"failure.json",{"error":str(exc),"traceback":traceback.format_exc()})
        raise
    print("Sensitivity numerical verification passed; reporting is a separate step.",flush=True)


if __name__ == "__main__":
    main()
