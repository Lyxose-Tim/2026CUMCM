"""Run one-factor Q4 structural scenarios without treating them as confidence intervals."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import csv
import json
from pathlib import Path

import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q2.inputs import read_config
from q4.provenance import load_run
from q4.run import cases, compute
from q4.validation import compare


ALLOWED_OVERRIDES = {"interpolation", "radius_offset_cm", "environment_mode"}


def scenario_cases(main_config, sensitivity_config):
    configured = {case["name"]: case for case in cases(main_config)}
    base_name = sensitivity_config["base_case"]
    if base_name not in configured:
        raise ValueError("Unknown Q4 sensitivity base case")
    base = configured[base_name]
    result = []
    for scenario in sensitivity_config["scenarios"]:
        unknown = set(scenario) - ALLOWED_OVERRIDES - {"name"}
        if unknown:
            raise ValueError(f"Unsupported sensitivity override: {sorted(unknown)}")
        case = copy.deepcopy(base)
        case.update({key: value for key, value in scenario.items() if key != "name"})
        case["name"] = f"sensitivity_{scenario['name']}_N{base['N']}"
        case["scenario"] = scenario["name"]
        result.append(case)
    names = [case["name"] for case in result]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate Q4 sensitivity scenario")
    half_increment = main_config["radius"]["record_half_increment_cm"]
    offsets = sorted(case.get("radius_offset_cm", 0.0) for case in result if "radius_offset_cm" in case)
    if offsets and offsets != [-half_increment, half_increment]:
        raise ValueError("Radius precision scenarios must use the configured half display increment")
    return result


def summarize(directory, main_config, sensitivity_config):
    directory = Path(directory)
    configured = scenario_cases(main_config, sensitivity_config)
    runs = {case["scenario"]: load_run(directory / "runs" / case["name"]) for case in configured}
    if any(record[0]["status"] != "computed" for record in runs.values()):
        raise ValueError("Every structural scenario must reach the full-domain event")
    baseline_record, baseline_fields = runs["linear"]
    checkpoint = main_config["validation"]["intermediate_checkpoint_s"]
    spacing = main_config["validation"]["regular_spacing_s"]
    rows = []
    comparisons = {}
    for scenario, (record, fields) in runs.items():
        difference = compare(
            baseline_fields, fields, spacing_s=spacing,
            intermediate_checkpoint_s=checkpoint,
        )
        event_delta = record["root"]["time_s"] - baseline_record["root"]["time_s"]
        rows.append({
            "scenario": scenario,
            "case_name": record["identity"]["case"]["name"],
            "event_time_s": record["root"]["time_s"],
            "event_time_h": record["root"]["time_h"],
            "event_delta_vs_linear_s": event_delta,
            "max_temperature_difference_C": difference["T"]["max_abs"],
            "max_moisture_difference": difference["C"]["max_abs"],
            "environment_mode": record["identity"]["case"]["environment_mode"],
            "radius_interpolation": record["identity"]["case"]["interpolation"],
            "radius_offset_cm": record["identity"]["case"].get("radius_offset_cm", 0.0),
        })
        comparisons[scenario] = difference
    by_name = {row["scenario"]: row for row in rows}
    radius_times = [by_name[name]["event_time_s"] for name in ("radius_lower", "radius_upper")]
    result = {
        "schema_version": 2,
        "passed": True,
        "uncertainty_type": "deterministic structural scenario range; not a confidence interval",
        "base_case": sensitivity_config["base_case"],
        "baseline_event_time_s": baseline_record["root"]["time_s"],
        "pchip_minus_linear_s": by_name["pchip"]["event_delta_vs_linear_s"],
        "terminal_hold_minus_last_hour_mean_s": by_name["environment_terminal_hold"]["event_delta_vs_linear_s"],
        "radius_record_scenario_range_s": [min(radius_times), max(radius_times)],
        "radius_record_scenario_width_s": max(radius_times) - min(radius_times),
        "scenarios": rows,
        "field_comparisons": comparisons,
        "configuration_hash": file_record("configs/q4_sensitivity.json"),
        "generator_hash": file_record("q4/sensitivity.py"),
        "runs": {
            scenario: {
                "case_name": record[0]["identity"]["case"]["name"],
                "directory": f"runs/{record[0]['identity']['case']['name']}",
                "run_record": file_record(
                    directory / "runs" / record[0]["identity"]["case"]["name"] / "run.json"
                ),
            }
            for scenario, record in runs.items()
        },
    }
    write_json(directory / "summary.json", result)
    with (directory / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result["summary_csv_hash"] = file_record(directory / "summary.csv")
    write_json(directory / "summary.json", result)
    return result


def verified_summary(
    directory="results/q4/sensitivity",
    main_config_path="configs/q4.json",
    sensitivity_config_path="configs/q4_sensitivity.json",
):
    root = Path(directory)
    main_config = read_config(main_config_path)
    sensitivity_config = read_config(sensitivity_config_path)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if summary.get("schema_version") != 2 or summary.get("passed") is not True:
        raise ValueError("Versioned Q4 structural sensitivity evidence is required")
    verify_file(sensitivity_config_path, summary["configuration_hash"])
    verify_file("q4/sensitivity.py", summary["generator_hash"])
    verify_file(root / "summary.csv", summary["summary_csv_hash"])

    configured = {case["scenario"]: case for case in scenario_cases(main_config, sensitivity_config)}
    if summary.get("base_case") != sensitivity_config["base_case"]:
        raise ValueError("Q4 sensitivity base case differs from current config")
    if set(summary.get("runs", {})) != set(configured):
        raise ValueError("Incomplete Q4 sensitivity run manifest")
    rows = {row["scenario"]: row for row in summary.get("scenarios", [])}
    if set(rows) != set(configured):
        raise ValueError("Incomplete Q4 sensitivity scenario summary")
    with (root / "summary.csv").open("r", encoding="utf-8", newline="") as stream:
        csv_rows = {row["scenario"]: row for row in csv.DictReader(stream)}
    if set(csv_rows) != set(configured):
        raise ValueError("Incomplete Q4 sensitivity summary CSV")

    for scenario, expected_case in configured.items():
        entry = summary["runs"][scenario]
        expected_name = expected_case["name"]
        expected_directory = f"runs/{expected_name}"
        if entry.get("case_name") != expected_name or entry.get("directory") != expected_directory:
            raise ValueError(f"Q4 sensitivity identity mismatch for {scenario}")
        run_directory = root / expected_directory
        verify_file(run_directory / "run.json", entry["run_record"])
        record, _ = load_run(run_directory)
        if record["identity"]["case"] != expected_case or record.get("status") != "computed":
            raise ValueError(f"Q4 sensitivity run configuration mismatch for {scenario}")
        row = rows[scenario]
        csv_row = csv_rows[scenario]
        if row.get("case_name") != expected_name or csv_row.get("case_name") != expected_name:
            raise ValueError(f"Q4 sensitivity summary identity mismatch for {scenario}")
        event_time = float(record["root"]["time_s"])
        if not np.isclose(float(row["event_time_s"]), event_time, rtol=0, atol=1e-9):
            raise ValueError(f"Q4 sensitivity JSON event time mismatch for {scenario}")
        if not np.isclose(float(csv_row["event_time_s"]), event_time, rtol=0, atol=1e-9):
            raise ValueError(f"Q4 sensitivity CSV event time mismatch for {scenario}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--config", default="configs/q4_sensitivity.json")
    parser.add_argument("--directory")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main_config = read_config("configs/q4.json")
    sensitivity_config = read_config(args.config)
    directory = args.directory or sensitivity_config["output_directory"]
    selected = scenario_cases(main_config, sensitivity_config)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [
            pool.submit(compute, args.data_root, directory, case, args.force)
            for case in selected
        ]
        for job in as_completed(jobs):
            print(json.dumps(job.result(), ensure_ascii=False), flush=True)
    result = summarize(directory, main_config, sensitivity_config)
    print(json.dumps({
        "passed": result["passed"],
        "pchip_minus_linear_s": result["pchip_minus_linear_s"],
        "radius_record_scenario_width_s": result["radius_record_scenario_width_s"],
        "terminal_hold_minus_last_hour_mean_s": result["terminal_hold_minus_last_hour_mean_s"],
    }, indent=2))


if __name__ == "__main__":
    main()
