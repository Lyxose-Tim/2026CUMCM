"""Q4 numerical verification and Q3 fixed-domain regression."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

from q2.archive import write_json
from q2.inputs import read_config
from q2.provenance import portable_artifact_sha256
from q3.provenance import load_run as load_q3_run
from q3.solver import full_max, output_axis
from q4.provenance import load_run
from q4.run import cases


def validation_sources():
    paths = ["q4/validation.py", "q4/export.py", "q4/check_export.py"]
    paths += sorted(str(p).replace("\\", "/") for p in Path("tests").glob("test_q4*.py"))
    return {p: portable_artifact_sha256(p) for p in paths if Path(p).exists()}


def compare(a, b):
    times, ia, ib = np.intersect1d(a["time_s"], b["time_s"], return_indices=True)
    return {
        "common_times": int(len(times)),
        "C": float(np.nanmax(np.abs(a["moisture"][ia, :21] - b["moisture"][ib, :21]))),
        "T": float(np.nanmax(np.abs(a["temperature_C"][ia, :21] - b["temperature_C"][ib, :21]))),
    }


def check_run(record, fields, config):
    n = record["identity"]["case"]["N"] + 1
    root, diag = record["root"], record["diagnostics"]
    p = record["identity"]["parameters"]
    threshold = config["threshold"]
    np.testing.assert_array_equal(fields["time_s"], np.r_[0, output_axis(root["time_s"], 60)])
    np.testing.assert_array_equal(fields["initial_state"], np.r_[np.full(n, p["T0"]), np.full(n, p["C0"])])
    if fields["moisture"].shape[1] != 22 or fields["temperature_C"].shape[1] != 22:
        raise ValueError("Q4 output must contain 21 fixed radii plus the dynamic surface")
    maxima = [full_max(y, n)[0] for y in fields["near_states"]]
    brackets = [full_max(y, n)[0] for y in fields["bracket_states"]]
    fixed_radius = fields["fixed_radius_m"]
    surface_radius = fields["surface_radius_m"]
    mask = fixed_radius[None, :] <= surface_radius[:, None] + 1e-12
    checks = {
        "finite_surface": bool(np.isfinite(fields["moisture"][:, -1]).all()),
        "outside_mask_is_nan": bool(np.isnan(fields["moisture"][:, :21][~mask]).all()),
        "inside_mask_is_finite": bool(np.isfinite(fields["moisture"][:, :21][mask]).all()),
        "positive": bool(diag["minimum_moisture"] > 0),
        "temperature_envelope": diag["temperature_envelope_violation"] <= 1e-7,
        "water_balance": diag["max_relative_balance"] <= config["budgets"]["relative_balance"],
        "full_grid_strict_crossing": bool(maxima[0] > threshold and maxima[2] < threshold),
        "root_residual": abs(maxima[1] - threshold) < 1e-10,
        "bracket": bool(brackets[0] > threshold and brackets[2] <= threshold
                         and root["bracket_s"][1] - root["bracket_s"][0] <= config["bracket_width_s"]),
        "max_nonincreasing": diag["max_Cmax_increase"] < 1e-8,
        "radius_nonincreasing": bool(np.all(np.diff(surface_radius) <= 1e-12)),
        "event_slope_negative": root["slope_C_per_s"] < 0,
    }
    if not all(checks.values()):
        raise ValueError(f"{record['identity']['case']['name']} failed checks: {checks}")
    return checks


def load_case(directory, name):
    run_dir = directory / "runs" / name
    try:
        return load_run(run_dir)
    except ValueError:
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        if record.get("status") != "no_event":
            raise
        return record, None


def validate(directory="results/q4"):
    directory = Path(directory)
    config = read_config("configs/q4.json")
    write_json(directory / "verification.json", {"passed": False, "status": "running"})
    basetemp = str(Path(tempfile.gettempdir()) / "pytest-q4")
    test = subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", basetemp,
                           "-p", "no:cacheprovider"],
                          capture_output=True)
    output = test.stdout.decode("utf-8", errors="replace") + test.stderr.decode("utf-8", errors="replace")
    (directory / "unit_tests.txt").write_text(output, encoding="utf-8")
    if test.returncode:
        raise RuntimeError("Unit/regression tests failed")
    runs = {case["name"]: load_case(directory, case["name"]) for case in cases(config)}
    checks = {name: check_run(*run, config) for name, run in runs.items() if run[1] is not None}
    q3_record, q3_fields = load_q3_run("results/q3/runs/base_N5120")
    regression = compare(runs["A_appendix3_fixed_N5120"][1], q3_fields)
    if (abs(runs["A_appendix3_fixed_N5120"][0]["root"]["time_s"] - q3_record["root"]["time_s"])
            > config["budgets"]["regression_time_s"] or regression["C"] > config["budgets"]["regression_C"]):
        raise ValueError(f"Q3 regression failed: {regression}")
    spatial = []
    names = ["D_appendix4_shrink_N5120", "main_appendix4_shrink_N10240", "main_appendix4_shrink_N20480"]
    for a, b in zip(names[:-1], names[1:]):
        ra, fa = runs[a]
        rb, fb = runs[b]
        spatial.append({"a": a, "b": b, "time_difference_s": abs(ra["root"]["time_s"] - rb["root"]["time_s"]),
                        **compare(fa, fb)})
    formal_case = config["formal_case"]
    formal, fields = runs[formal_case]
    table = []
    for name in ["A_appendix3_fixed_N5120", "B_appendix3_shrink_N5120",
                 "C_appendix4_fixed_N5120", "D_appendix4_shrink_N5120", formal_case]:
        record, f = runs[name]
        if f is None:
            table.append({
                "case": name, "status": "no_event_by_horizon", "time_h": None,
                "horizon_h": record["horizon_h"], "event_radius_cm": None,
                "surface_C_at_event": None, "center_C_at_event": None,
            })
        else:
            table.append({
                "case": name, "status": "event",
                "time_h": record["root"]["time_h"],
                "event_radius_cm": record["root"]["radius_m"] * 100,
                "surface_C_at_event": float(f["moisture"][-1, -1]),
                "center_C_at_event": float(f["moisture"][-1, 0]),
            })
    result = {
        "passed": True, "formal_case": formal_case, "checks": checks,
        "q3_regression": regression, "spatial": spatial, "table6_summary": table,
        "estimated_numerical_time_change_s": spatial[-1]["time_difference_s"] + config["bracket_width_s"],
        "root": formal["root"],
        "validation_sources": validation_sources(),
        "unit_tests_sha256": portable_artifact_sha256(directory / "unit_tests.txt"),
        "run_record_hashes": {k: portable_artifact_sha256(directory / "runs" / k / "run.json") for k in runs},
    }
    write_json(directory / "verification.json", result)
    return result


def verified(directory="results/q4"):
    directory = Path(directory)
    v = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
    if v.get("passed") is not True or v["validation_sources"] != validation_sources():
        raise ValueError("Current-source Q4 verification missing/failed")
    config = read_config("configs/q4.json")
    if v["formal_case"] != config["formal_case"]:
        raise ValueError("Verified Q4 formal_case differs from current config")
    expected = {case["name"] for case in cases(config)}
    if set(v["run_record_hashes"]) != expected:
        raise ValueError("Incomplete Q4 verification run set")
    for name, digest in v["run_record_hashes"].items():
        if portable_artifact_sha256(directory / "runs" / name / "run.json") != digest:
            raise ValueError("Changed Q4 run record")
        load_case(directory, name)
    record, fields = load_run(directory / "runs" / v["formal_case"])
    return v, record, fields


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="results/q4")
    args = parser.parse_args()
    v = validate(args.directory)
    print(json.dumps({k: v[k] for k in ["passed", "q3_regression", "spatial", "estimated_numerical_time_change_s"]}, indent=2))
