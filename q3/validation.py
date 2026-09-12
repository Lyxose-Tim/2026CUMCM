"""Event-specific numerical budgets, source checks, and regression evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from q2.archive import load_archive, write_json
from q2.inputs import read_config, sha256
from q2.provenance import portable_artifact_sha256, verify_sources
from q3.provenance import load_run
from q3.solver import output_axis, full_max
from q3.run import cases
from q3.refine import EXTRA_CASES


def validation_sources():
    paths = ["q3/validation.py", "q3/refine.py"] + sorted(str(p).replace("\\", "/") for p in Path("tests").glob("test_*.py"))
    return {p: portable_artifact_sha256(p) for p in paths}


def compare(a, b):
    times, ia, ib = np.intersect1d(a["time_s"], b["time_s"], return_indices=True)
    return {"common_times": len(times), "C": float(np.max(np.abs(a["moisture"][ia]-b["moisture"][ib]))),
            "T": float(np.max(np.abs(a["temperature_C"][ia]-b["temperature_C"][ib])))}


def check_run(record, fields, config):
    n = record["identity"]["case"]["N"] + 1
    root, diag = record["root"], record["diagnostics"]
    p = record["identity"]["parameters"]
    threshold = config["threshold"]
    if any(not np.isfinite(v).all() for v in fields.values()):
        raise ValueError("Nonfinite archived full-state or output data")
    np.testing.assert_array_equal(fields["time_s"], np.r_[0, output_axis(root["time_s"], 60)])
    np.testing.assert_array_equal(fields["initial_state"], np.r_[np.full(n,p["T0"]),np.full(n,p["C0"])])
    maxima = [full_max(y,n)[0] for y in fields["near_states"]]
    brackets = [full_max(y,n)[0] for y in fields["bracket_states"]]
    checks = {
        "finite_and_original_initial": True,
        "positive": bool(diag["minimum_moisture"] > 0),
        "temperature_envelope": diag["temperature_envelope_violation"] <= 1e-7,
        "water_balance": diag["max_relative_balance"] <= config["budgets"]["relative_balance"],
        "full_grid_strict_crossing": bool(maxima[0] > threshold and maxima[2] < threshold),
        "root_residual": abs(maxima[1]-threshold) < 1e-10,
        "bracket": bool(brackets[0] > threshold and brackets[2] <= threshold
                         and root["bracket_s"][1]-root["bracket_s"][0] <= config["bracket_width_s"]),
        "root_time_in_bracket": root["bracket_s"][0]-config["root_xtol_s"] <= root["time_s"]
                                <= root["bracket_s"][1]+config["root_xtol_s"],
        "max_nonincreasing": diag["max_Cmax_increase"] < 1e-8,
        "local_water_balance": diag["max_local_water_balance_absolute"] < 1e-15,
        "surface_gradient_finite": bool(np.isfinite(diag["max_surface_gradient_relative_residual"])),
        "event_slope_negative": root["slope_C_per_s"] < 0,
        "endpoint_matches_fields": bool(np.array_equal(fields["moisture"][-1],
                                           fields["near_states"][1,n:][np.arange(21)*(n-1)//20])),
    }
    if not all(checks.values()):
        raise ValueError(f"{record['identity']['case']['name']} failed checks: {checks}")
    return checks


def validate(directory="results/q3"):
    directory = Path(directory)
    config = read_config("configs/q3.json")
    write_json(directory/"verification.json", {"passed": False, "status": "running"})
    test = subprocess.run([sys.executable,"-m","pytest","-q","-p","no:cacheprovider"],
                          capture_output=True, text=True, encoding="utf-8")
    (directory/"unit_tests.txt").write_text(test.stdout+test.stderr, encoding="utf-8")
    if test.returncode:
        raise RuntimeError("Unit/regression tests failed")
    runs = {c["name"]: load_run(directory/"runs"/c["name"]) for c in cases(config)+EXTRA_CASES}
    checks = {name: check_run(*run, config) for name,run in runs.items()}
    spatial = []
    grids=config["grids"]+[40960]
    for a,b in zip(grids[:-1],grids[1:]):
        ra,fa=runs[f"base_N{a}"]; rb,fb=runs[f"base_N{b}"]
        spatial.append({"coarse_N":a,"fine_N":b,"time_difference_s":abs(ra["root"]["time_s"]-rb["root"]["time_s"]),
                        **compare(fa,fb)})
    temporal = []
    for a,b in [("base_N20480","tight_N20480"),("base_N10240","halfstep_N10240"),("base_N40960","tight_N40960")]:
        ra,fa=runs[a];rb,fb=runs[b]
        temporal.append({"a":a,"b":b,"time_difference_s":abs(ra["root"]["time_s"]-rb["root"]["time_s"]),
                         **compare(fa,fb)})
    budgets=config["budgets"]
    orders=[float(np.log2(a["time_difference_s"]/b["time_difference_s"])) for a,b in zip(spatial[:-1],spatial[1:])]
    # Observed asymptotic order is checked rather than silently assuming p=2.
    conservative_order=min(2.0,min(orders))
    spatial_estimate=spatial[-1]["time_difference_s"]/(2**conservative_order-1)
    if not (all(v["C"]<budgets["space_C"] for v in spatial)
            and all(1.8<p<2.2 for p in orders) and spatial_estimate<budgets["space_time_s"]
            and all(v["time_difference_s"]<budgets["temporal_time_s"] and v["C"]<budgets["temporal_C"] for v in temporal)):
        raise ValueError(f"Event convergence budget failed: {spatial}, {temporal}")
    formal_case="tight_N40960"
    formal, fields = runs[formal_case]
    q2, _, q2_manifest=load_archive("results/q2/archive")
    verify_sources(q2_manifest)
    # The archived Q2 formal grid is N=20480. A same-grid, same-settings
    # comparison isolates unchanged physics from deliberate Q3 mesh refinement.
    regression=compare(runs["tight_N20480"][1],q2)
    if regression["C"] >= budgets["q2_C"] or regression["T"] >= budgets["q2_T"]:
        raise ValueError(f"Q2 common-time regression failed: {regression}")
    n=formal["identity"]["case"]["N"]+1
    near_C=fields["near_states"][:,n:]
    near_Cmax=near_C.max(axis=1)
    temporal_estimate=max(x["time_difference_s"] for x in temporal)
    time_estimate=spatial_estimate+temporal_estimate+config["bracket_width_s"]
    slope=abs(formal["root"]["slope_C_per_s"])
    if config["strict_offset_s"] <= 10*time_estimate:
        raise ValueError("Strict state offset is not large relative to measured discretization change")
    trace=np.genfromtxt(directory/"runs"/formal_case/"accepted_steps.csv",delimiter=",",names=True)
    late=trace[trace["time_s"]>=21600]
    sensitivity=[]
    baseline=runs[f"base_N{config['sensitivity_grid']}"][0]["root"]["time_s"]
    for c in cases(config)[5:]:
        r=runs[c["name"]][0]
        t=r["root"]["time_s"]
        sensitivity.append({"case":c["name"],"N":c["N"],"time_h":t/3600,
                            "change_h":(t-baseline)/3600,"relative_change":t/baseline-1,
                            "environment":r["identity"]["inputs"]["environment_extension"]})
    result={"passed": True, "formal_case":formal_case,"checks":checks,
        "spatial":spatial,"temporal":temporal,"q2_regression":regression,
        "observed_orders":orders,"estimated_space_time_error_s":spatial_estimate,
        "initial_adjacent_difference_goal_passed":all(s["time_difference_s"]<budgets["space_time_s"] for s in spatial),
        "q2_archive_manifest_sha256":portable_artifact_sha256("results/q2/archive/manifest.json"),
        "estimated_numerical_time_change_s":time_estimate,
        "error_interpretation":"Richardson estimate using measured order + measured time change + root bracket; not a rigorous PDE bound",
        "slope_C_per_s":-slope,"C_error_1e_6_time_s":1e-6/slope,"rounding_5e_5_time_s":5e-5/slope,
        "near_Cmax":near_Cmax.tolist(),"near_argmax_radius_m":fields["radius_m"][near_C.argmax(axis=1)].tolist(),
        "argmax_radius_range_m":[float(trace["argmax_radius_m"].min()),float(trace["argmax_radius_m"].max())],
        "argmax_after_6h_range_m":[float(late["argmax_radius_m"].min()),float(late["argmax_radius_m"].max())],
        "max_radial_increase":float(trace["radial_increase"].max()),
        "sensitivity":sensitivity,
        "run_record_hashes":{k:portable_artifact_sha256(directory/"runs"/k/"run.json") for k in runs},
        "validation_sources":validation_sources(),"unit_tests_sha256":portable_artifact_sha256(directory/"unit_tests.txt")}
    write_json(directory/"verification.json",result)
    return result


def verified(directory="results/q3"):
    directory=Path(directory)
    v=json.loads((directory/"verification.json").read_text(encoding="utf-8"))
    if v.get("passed") is not True or v["validation_sources"] != validation_sources():
        raise ValueError("Current-source numerical verification missing/failed")
    expected={c["name"] for c in cases(read_config("configs/q3.json"))+EXTRA_CASES}
    if set(v["run_record_hashes"]) != expected:
        raise ValueError("Incomplete verification run set")
    for name,digest in v["run_record_hashes"].items():
        if portable_artifact_sha256(directory/"runs"/name/"run.json") != digest:
            raise ValueError("Changed run record")
        load_run(directory/"runs"/name)
    if portable_artifact_sha256(directory/"unit_tests.txt") != v["unit_tests_sha256"]:
        raise ValueError("Changed test evidence")
    record,fields=load_run(directory/"runs"/v["formal_case"])
    return v,record,fields


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",default="results/q3")
    args=parser.parse_args()
    v=validate(args.directory)
    print(json.dumps({k:v[k] for k in ["passed","spatial","temporal","q2_regression","estimated_numerical_time_change_s"]},indent=2))
