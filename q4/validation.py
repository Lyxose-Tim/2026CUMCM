"""Q4 numerical verification with separated space, time, method, and root evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q2.inputs import read_config
from q3.provenance import load_run as load_q3_run
from q3.solver import full_max, output_axis
from q4.provenance import load_run
from q4.run import cases


SUMMARY_INDEX = {
    "Cmax": 2,
    "argmax_radius_m": 4,
    "mean_C": 6,
}


def validation_sources():
    paths = ["q4/validation.py", "q4/export.py", "q4/check_export.py"]
    paths += sorted(str(path).replace("\\", "/") for path in Path("tests").glob("test_q4*.py"))
    return {path: file_record(path) for path in paths if Path(path).exists()}


def _comparison_indices(a, b, spacing_s, checkpoint_s):
    ta = np.asarray(a["time_s"], dtype=float)
    tb = np.asarray(b["time_s"], dtype=float)
    regular_a = ta[np.isclose(ta / spacing_s, np.rint(ta / spacing_s), rtol=0, atol=1e-10)]
    regular_b = tb[np.isclose(tb / spacing_s, np.rint(tb / spacing_s), rtol=0, atol=1e-10)]
    common = np.intersect1d(regular_a, regular_b)
    if checkpoint_s not in ta or checkpoint_s not in tb:
        raise ValueError(f"Configured intermediate checkpoint {checkpoint_s} s is absent")
    times = np.unique(np.r_[common, float(checkpoint_s)])
    ia = np.searchsorted(ta, times)
    ib = np.searchsorted(tb, times)
    if not np.array_equal(ta[ia], times) or not np.array_equal(tb[ib], times):
        raise ValueError("Q4 comparison time lookup is not exact")
    return times, ia, ib, common


def _field_difference(name, a, b, times, ia, ib):
    left = np.asarray(a[name])[ia]
    right = np.asarray(b[name])[ib]
    if left.shape[1] != 22 or right.shape[1] != 22:
        raise ValueError("Q4 comparisons require 21 fixed radii plus the dynamic surface")
    valid = np.isfinite(left) & np.isfinite(right)
    valid[:, -1] = True
    if not np.all(np.isfinite(left[:, -1])) or not np.all(np.isfinite(right[:, -1])):
        raise ValueError("Dynamic surface must be finite in both Q4 runs")
    difference = np.abs(left - right)
    masked = np.where(valid, difference, -np.inf)
    row, column = np.unravel_index(int(np.argmax(masked)), masked.shape)
    fixed = np.asarray(a["fixed_radius_m"], dtype=float)
    if len(fixed) != 21 or not np.array_equal(fixed, np.asarray(b["fixed_radius_m"], dtype=float)):
        raise ValueError("Q4 fixed output radii differ between compared runs")
    dynamic = bool(column == 21)
    if dynamic:
        radius_a = float(a["surface_radius_m"][ia[row]])
        radius_b = float(b["surface_radius_m"][ib[row]])
        label = "surface"
    else:
        radius_a = radius_b = float(fixed[column])
        label = f"fixed_{radius_a * 100:.1f}_cm"
    return {
        "max_abs": float(masked[row, column]),
        "time_s": float(times[row]),
        "column_index": int(column),
        "column": label,
        "dynamic_surface": dynamic,
        "radius_m_a": radius_a,
        "radius_m_b": radius_b,
        "valid_values_compared": int(valid.sum()),
    }


def _summary_difference(a, b, times, ia, ib, column):
    delta = np.abs(np.asarray(a["summary"])[ia, column] - np.asarray(b["summary"])[ib, column])
    index = int(np.argmax(delta))
    return {"max_abs": float(delta[index]), "time_s": float(times[index])}


def _checkpoint_field(name, a, b, index_a, index_b):
    left = np.asarray(a[name][index_a], dtype=float)
    right = np.asarray(b[name][index_b], dtype=float)
    if left.shape != (22,) or right.shape != (22,):
        raise ValueError("Q4 checkpoint fields require 21 fixed radii plus the dynamic surface")
    fixed = np.asarray(a["fixed_radius_m"], dtype=float)
    if len(fixed) != 21 or not np.array_equal(fixed, np.asarray(b["fixed_radius_m"], dtype=float)):
        raise ValueError("Q4 fixed output radii differ between compared runs")
    valid = np.isfinite(left) & np.isfinite(right)
    if not valid[-1]:
        raise ValueError("Dynamic surface must be finite in both Q4 checkpoint states")
    rows = []
    for column in np.flatnonzero(valid):
        dynamic = bool(column == 21)
        radius_a = float(a["surface_radius_m"][index_a]) if dynamic else float(fixed[column])
        radius_b = float(b["surface_radius_m"][index_b]) if dynamic else float(fixed[column])
        rows.append({
            "column_index": int(column),
            "column": "surface" if dynamic else f"fixed_{radius_a * 100:.1f}_cm",
            "dynamic_surface": dynamic,
            "radius_m_a": radius_a,
            "radius_m_b": radius_b,
            "value_a": float(left[column]),
            "value_b": float(right[column]),
            "abs_difference": float(abs(left[column] - right[column])),
        })
    return {
        "valid_columns": len(rows),
        "max_abs": max(row["abs_difference"] for row in rows),
        "columns": rows,
    }


def _checkpoint_difference(a, b, time_s, index_a, index_b, acquisition):
    return {
        "time_s": float(time_s),
        "state_acquisition": acquisition,
        "time_reconstruction_error_s": 0.0,
        "surface_radius_m_a": float(a["surface_radius_m"][index_a]),
        "surface_radius_m_b": float(b["surface_radius_m"][index_b]),
        "T": _checkpoint_field("temperature_C", a, b, index_a, index_b),
        "C": _checkpoint_field("moisture", a, b, index_a, index_b),
    }


def compare(a, b, *, spacing_s=60.0, intermediate_checkpoint_s=86400.0):
    """Compare every valid fixed radius and the separately sampled moving surface."""
    times, ia, ib, common = _comparison_indices(
        a, b, spacing_s, intermediate_checkpoint_s
    )
    checkpoint_index = int(np.flatnonzero(times == intermediate_checkpoint_s)[0])
    near_root_time = float(common[-1])
    near_root_index = int(np.flatnonzero(times == near_root_time)[0])
    common_coverage_end = min(float(np.max(a["time_s"])), float(np.max(b["time_s"])))
    if common_coverage_end - near_root_time > spacing_s + 1e-8:
        raise ValueError("Last common regular Q4 state is not adjacent to the common event horizon")
    result = {
        "regular_spacing_s": float(spacing_s),
        "common_regular_times": int(len(common)),
        "comparison_times": int(len(times)),
        "common_start_s": float(times[0]),
        "common_end_s": float(times[-1]),
        "intermediate_checkpoint_s": float(intermediate_checkpoint_s),
        "dynamic_surface_included": True,
        "T": _field_difference("temperature_C", a, b, times, ia, ib),
        "C": _field_difference("moisture", a, b, times, ia, ib),
    }
    for name, column in SUMMARY_INDEX.items():
        result[name] = _summary_difference(a, b, times, ia, ib, column)
    result["intermediate_checkpoint"] = _checkpoint_difference(
        a, b, intermediate_checkpoint_s, ia[checkpoint_index], ib[checkpoint_index],
        "exact_archived_regular_sample",
    )
    result["near_root_common"] = {
        **_checkpoint_difference(
            a, b, near_root_time, ia[near_root_index], ib[near_root_index],
            "exact_archived_regular_sample",
        ),
        "common_coverage_end_s": common_coverage_end,
        "gap_to_common_coverage_end_s": common_coverage_end - near_root_time,
    }
    return result


def compare_q3_fixed(q4_fields, q3_fields, *, spacing_s, intermediate_checkpoint_s):
    q4_view = {
        "time_s": q4_fields["time_s"],
        "temperature_C": q4_fields["temperature_C"][:, :21],
        "moisture": q4_fields["moisture"][:, :21],
    }
    ta = np.asarray(q4_view["time_s"])
    tb = np.asarray(q3_fields["time_s"])
    common = np.intersect1d(ta, tb)
    common = common[np.isclose(common / spacing_s, np.rint(common / spacing_s), rtol=0, atol=1e-10)]
    if intermediate_checkpoint_s not in common:
        raise ValueError("Q3 regression intermediate checkpoint is unavailable")
    ia, ib = np.searchsorted(ta, common), np.searchsorted(tb, common)
    return {
        "common_regular_times": int(len(common)),
        "intermediate_checkpoint_s": float(intermediate_checkpoint_s),
        "C": float(np.max(np.abs(q4_view["moisture"][ia] - q3_fields["moisture"][ib]))),
        "T": float(np.max(np.abs(q4_view["temperature_C"][ia] - q3_fields["temperature_C"][ib]))),
    }


def check_run(record, fields, config):
    if record["status"] != "computed":
        raise ValueError(f"Required event run has status {record['status']}")
    n = record["identity"]["case"]["N"] + 1
    root, diag = record["root"], record["diagnostics"]
    parameters = record["identity"]["parameters"]
    event = config["event"]
    threshold = event["threshold"]
    spacing = config["validation"]["regular_spacing_s"]
    np.testing.assert_array_equal(fields["time_s"], np.r_[0, output_axis(root["time_s"], spacing)])
    np.testing.assert_array_equal(
        fields["initial_state"],
        np.r_[np.full(n, parameters["T0"]), np.full(n, parameters["C0"])],
    )
    if fields["moisture"].shape[1] != 22 or fields["temperature_C"].shape[1] != 22:
        raise ValueError("Q4 output must contain 21 fixed radii plus the dynamic surface")
    maxima = [full_max(state, n)[0] for state in fields["near_states"]]
    brackets = [full_max(state, n)[0] for state in fields["bracket_states"]]
    fixed_radius = fields["fixed_radius_m"]
    surface_radius = fields["surface_radius_m"]
    mask = fixed_radius[None, :] <= surface_radius[:, None] + 1e-12
    checks = {
        "finite_surface": bool(np.isfinite(fields["moisture"][:, -1]).all()),
        "outside_mask_is_nan": bool(np.isnan(fields["moisture"][:, :21][~mask]).all()),
        "inside_mask_is_finite": bool(np.isfinite(fields["moisture"][:, :21][mask]).all()),
        "terminal_state_saved": bool(fields["terminal_state"].shape == (2 * n,)
                                     and np.isfinite(fields["terminal_state"]).all()),
        "positive": bool(diag["minimum_moisture"] > 0),
        "temperature_envelope": diag["temperature_envelope_violation"] <= 1e-7,
        "water_balance": diag["max_relative_balance"] <= config["budgets"]["relative_balance"],
        "full_grid_strict_crossing": bool(maxima[0] > threshold and maxima[2] < threshold),
        "root_residual": abs(maxima[1] - threshold) < 1e-10,
        "bracket": bool(brackets[0] > threshold and brackets[2] <= threshold
                         and root["bracket_s"][1] - root["bracket_s"][0] <= event["bracket_width_s"]),
        "max_nonincreasing": diag["max_Cmax_increase"] < 1e-8,
        "radius_nonincreasing": bool(np.all(np.diff(surface_radius) <= 1e-12)),
        "event_slope_negative": root["slope_C_per_s"] < 0,
        "terminal_strictly_below": record["terminal"]["g"] < 0,
    }
    if not all(checks.values()):
        raise ValueError(f"{record['identity']['case']['name']} failed checks: {checks}")
    return checks


def check_typed_outcome(record, fields):
    status = record["status"]
    if status not in {"threshold_not_reached", "root_found_post_state_unavailable"}:
        raise ValueError(f"Unexpected typed outcome: {status}")
    n = record["identity"]["case"]["N"] + 1
    state = np.asarray(fields["terminal_state"], dtype=float)
    trace = np.asarray(fields["trace"], dtype=float)
    if state.shape != (2 * n,) or not np.isfinite(state).all() or len(trace) == 0:
        raise ValueError("Typed Q4 outcome lacks terminal fields or accepted-step trace")
    if fields["time_s"][-1] != record["terminal"]["time_s"] or trace[-1, 0] != fields["time_s"][-1]:
        raise ValueError("Typed Q4 terminal output is not archived")
    terminal = record["terminal"]
    if not np.array_equal(trace[-1, :12], np.asarray(fields["summary"][-1], dtype=float)):
        raise ValueError("Typed Q4 terminal summary differs from the accepted-step trace")
    T, C = state[:n], state[n:]
    cmax, index = full_max(state, n)
    reconstructed = {
        "Cmax": cmax,
        "argmax_xi": float(fields["xi"][index]),
        "argmax_radius_m": float(terminal["radius_m"] * fields["xi"][index]),
        "center_C": float(C[0]),
        "mean_C": float(np.dot(fields["volume_xi"], C) / np.sum(fields["volume_xi"])),
        "surface_C": float(C[-1]),
        "Cmin": float(C.min()),
        "Tmin_C": float(T.min()),
        "Tmax_C": float(T.max()),
        "radial_increase": float(np.diff(C).max()),
    }
    for name, value in reconstructed.items():
        if not np.isclose(value, terminal[name], rtol=2e-13, atol=2e-14):
            raise ValueError(f"Typed Q4 terminal_state differs from terminal {name}")
    if fields["surface_radius_m"][-1] != terminal["radius_m"]:
        raise ValueError("Typed Q4 terminal radius differs from the archived output")
    if not np.isclose(fields["moisture"][-1, 0], C[0], rtol=0, atol=2e-14):
        raise ValueError("Typed Q4 terminal center output differs from terminal_state")
    if not np.isclose(fields["moisture"][-1, -1], C[-1], rtol=0, atol=2e-14):
        raise ValueError("Typed Q4 terminal surface output differs from terminal_state")
    if status == "threshold_not_reached" and record["terminal"]["g"] <= 0:
        raise ValueError("Threshold-not-reached record has a crossed terminal state")
    if status == "root_found_post_state_unavailable" and record.get("root") is None:
        raise ValueError("Post-state-unavailable record lacks its located root")
    return {"terminal_evidence_verified": True, "status": status}


def load_case(directory, name):
    return load_run(Path(directory) / "runs" / name)


def check_comparison_budget(comparisons, budgets, prefix):
    required = {
        "root_time_difference_s": budgets[f"{prefix}_time_s"],
        "C": budgets[f"{prefix}_C"],
        "T": budgets[f"{prefix}_T_C"],
    }
    failures, checked = [], []
    for item in comparisons:
        values = {
            "root_time_difference_s": float(item["root_time_difference_s"]),
            "C": float(item["field_difference"]["C"]["max_abs"]),
            "T": float(item["field_difference"]["T"]["max_abs"]),
        }
        item_checks = {}
        for key, budget in required.items():
            value = values[key]
            passed = bool(np.isfinite(value) and value <= budget)
            item_checks[key] = {"value": value, "budget": float(budget), "passed": passed}
            if not passed:
                failures.append(f"{item['a']}->{item['b']} {key}={value} exceeds {budget}")
        checked.append({"a": item["a"], "b": item["b"], "checks": item_checks})
    if failures:
        raise ValueError(f"Q4 {prefix} comparison exceeds configured budget: " + "; ".join(failures))
    return {"passed": True, "comparisons": checked}


def check_spatial_budget(spatial, budgets):
    return check_comparison_budget(spatial, budgets, "space")


def normalize_test_output(output):
    if not output:
        return ""
    lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(line.rstrip() for line in lines) + "\n"


def _pair_comparison(name_a, run_a, name_b, run_b, config):
    record_a, fields_a = run_a
    record_b, fields_b = run_b
    difference = compare(
        fields_a,
        fields_b,
        spacing_s=config["validation"]["regular_spacing_s"],
        intermediate_checkpoint_s=config["validation"]["intermediate_checkpoint_s"],
    )
    return {
        "a": name_a,
        "b": name_b,
        "root_time_difference_s": abs(record_a["root"]["time_s"] - record_b["root"]["time_s"]),
        "field_difference": difference,
    }


def factorial_interaction(runs):
    names = {
        "A": "A_appendix3_fixed_N5120",
        "B": "B_appendix3_shrink_N5120",
        "C": "C_appendix4_fixed_N5120",
        "D": "D_appendix4_shrink_N5120",
    }
    if any(runs[name][0]["status"] != "computed" for name in names.values()):
        return {"status": "censored", "reason": "All four event times are required for exact interaction"}
    values = {key: runs[name][0]["root"]["time_s"] for key, name in names.items()}
    return {
        "status": "complete",
        "event_time_s": values,
        "geometry_effect_appendix3_s": values["B"] - values["A"],
        "geometry_effect_appendix4_s": values["D"] - values["C"],
        "property_effect_fixed_s": values["C"] - values["A"],
        "property_effect_shrinking_s": values["D"] - values["B"],
        "interaction_s": values["D"] - values["C"] - values["B"] + values["A"],
    }


def validate(directory="results/q4"):
    directory = Path(directory)
    config = read_config("configs/q4.json")
    write_json(directory / "verification.json", {"passed": False, "status": "running"})
    configured_basetemp = os.environ.get("CUMCM_PYTEST_BASETEMP")
    base = Path(configured_basetemp) if configured_basetemp else Path(".scratch") / "pytest-validation"
    basetemp = base / f"q4-{os.getpid()}"
    basetemp.parent.mkdir(parents=True, exist_ok=True)
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp", basetemp, "-p", "no:cacheprovider"],
        capture_output=True,
    )
    output = normalize_test_output(
        test.stdout.decode("utf-8", errors="replace") + test.stderr.decode("utf-8", errors="replace")
    )
    (directory / "unit_tests.txt").write_text(output, encoding="utf-8")
    if test.returncode:
        raise RuntimeError("Unit/regression tests failed")

    configured = cases(config)
    runs = {case["name"]: load_case(directory, case["name"]) for case in configured}
    checks = {name: check_run(*run, config) for name, run in runs.items()}

    q3_record, q3_fields = load_q3_run("results/q3/runs/base_N5120")
    regression = compare_q3_fixed(
        runs["A_appendix3_fixed_N5120"][1],
        q3_fields,
        spacing_s=config["validation"]["regular_spacing_s"],
        intermediate_checkpoint_s=config["validation"]["intermediate_checkpoint_s"],
    )
    regression["root_time_difference_s"] = abs(
        runs["A_appendix3_fixed_N5120"][0]["root"]["time_s"] - q3_record["root"]["time_s"]
    )
    budgets = config["budgets"]
    if (
        regression["root_time_difference_s"] > budgets["regression_time_s"]
        or regression["C"] > budgets["regression_C"]
        or regression["T"] > budgets["regression_T_C"]
    ):
        raise ValueError(f"Q3 regression failed: {regression}")

    spatial_names = config["validation"]["spatial_group"]
    spatial = [
        _pair_comparison(a, runs[a], b, runs[b], config)
        for a, b in zip(spatial_names[:-1], spatial_names[1:])
    ]
    spatial_budget = check_comparison_budget(spatial, budgets, "space")
    temporal_names = config["validation"]["temporal_group"]
    temporal = [_pair_comparison(temporal_names[0], runs[temporal_names[0]],
                                 temporal_names[1], runs[temporal_names[1]], config)]
    temporal_budget = check_comparison_budget(temporal, budgets, "time")

    method_names = config["validation"]["method_group"]
    method = {
        "status": "computed",
        "comparison": _pair_comparison(
            method_names[0], runs[method_names[0]], method_names[1], runs[method_names[1]], config
        ),
    }

    main_names = [
        "A_appendix3_fixed_N5120", "B_appendix3_shrink_N5120",
        "C_appendix4_fixed_N5120", "D_appendix4_shrink_N5120",
    ]
    table = []
    for name in main_names:
        record, fields = runs[name]
        table.append({
            "case": name,
            "status": "event",
            "time_h": record["root"]["time_h"],
            "event_radius_cm": record["root"]["radius_m"] * 100,
            "surface_C_at_event": float(fields["moisture"][-1, -1]),
            "center_C_at_event": float(fields["moisture"][-1, 0]),
        })
    interaction = factorial_interaction(runs)
    if interaction["status"] != "complete":
        raise ValueError("A/B/C/D interaction remains censored")

    formal_case = config["formal_case"]
    formal = runs[formal_case][0]
    result = {
        "schema_version": 3,
        "passed": True,
        "status": "verified",
        "formal_case": formal_case,
        "checks": checks,
        "q3_regression": regression,
        "spatial": spatial,
        "spatial_budget": spatial_budget,
        "temporal": temporal,
        "temporal_budget": temporal_budget,
        "method": method,
        "root_resolution": {
            "configured_bracket_width_s": config["event"]["bracket_width_s"],
            "formal_bracket_width_s": formal["root"]["bracket_s"][1] - formal["root"]["bracket_s"][0],
            "formal_root_residual": formal["root"]["root_g"],
        },
        "uncertainty_layers": {
            "space": "same BDF settings across N=5120/10240/20480",
            "time": "same N=20480 and physical inputs; base versus tightened/half-step BDF",
            "method": "same N=5120 configured diagnostic grid; BDF versus Radau",
            "root": "bracket width and residual only",
            "not_combined": True,
        },
        "factorial_interaction": interaction,
        "table6_summary": table,
        "root": formal["root"],
        "validation_sources": validation_sources(),
        "unit_tests_hash": file_record(directory / "unit_tests.txt"),
        "run_record_hashes": {
            name: file_record(directory / "runs" / name / "run.json") for name in runs
        },
    }
    write_json(directory / "verification.json", result)
    return result


def verified(directory="results/q4"):
    directory = Path(directory)
    verification = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
    if (verification.get("schema_version") != 3 or verification.get("passed") is not True
            or verification["validation_sources"] != validation_sources()):
        raise ValueError("Current-source Q4 verification missing/failed")
    verify_file(directory / "unit_tests.txt", verification["unit_tests_hash"])
    config = read_config("configs/q4.json")
    if verification["formal_case"] != config["formal_case"]:
        raise ValueError("Verified Q4 formal_case differs from current config")
    expected = {case["name"] for case in cases(config)}
    if set(verification["run_record_hashes"]) != expected:
        raise ValueError("Incomplete Q4 verification run set")
    configured = {case["name"]: case for case in cases(config)}
    loaded = {}
    for name, digest in verification["run_record_hashes"].items():
        verify_file(directory / "runs" / name / "run.json", digest)
        record, fields = load_case(directory, name)
        if record["identity"]["case"] != configured[name]:
            raise ValueError(f"Verified Q4 case identity differs from current config: {name}")
        check_run(record, fields, config)
        loaded[name] = (record, fields)
    record, fields = loaded[verification["formal_case"]]
    return verification, record, fields


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="results/q4")
    args = parser.parse_args()
    value = validate(args.directory)
    print(json.dumps({
        "passed": value["passed"],
        "q3_regression": value["q3_regression"],
        "spatial": value["spatial"],
        "temporal": value["temporal"],
        "method": value["method"],
    }, indent=2))
