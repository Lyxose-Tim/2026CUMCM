"""Reproducible Q4 shrinkage cases."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
from pathlib import Path

import numpy as np

from common.hashing import file_record
from q2.archive import write_json
from q2.inputs import read_config
from q4.inputs import read_inputs
from q4.model import ShrinkingRadialModel, material_grid, q4_parameters
from q4.provenance import load_run, snapshot
from q4.solver import (
    TRACE_COLUMNS,
    IntegrationFailure,
    StrictPostStateUnavailable,
    ThresholdNotReached,
    integrate_event,
)


def cases(config, include_refinement=True):
    all_cases = copy.deepcopy(config["cases"])
    if include_refinement:
        all_cases += copy.deepcopy(config.get("validation_cases", config.get("refinement_cases", [])))
    names = [case["name"] for case in all_cases]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate Q4 case name")
    if include_refinement and config["formal_case"] not in names:
        raise ValueError("formal_case is not configured")
    for case in all_cases:
        if case["properties"] not in {"appendix3", "appendix4"} or case["radius"] not in {"fixed", "shrink"}:
            raise ValueError(f"Invalid Q4 case: {case}")
        if case.get("method", "BDF") not in {"BDF", "Radau"}:
            raise ValueError(f"Invalid Q4 integration method: {case}")
    return all_cases


def event_settings(config):
    return config.get("event", config)


def save_solution(directory, solution, status, identity, source):
    arrays = {
        key: value for key, value in solution.items()
        if isinstance(value, np.ndarray) and key != "trace"
    }
    np.savez_compressed(directory / "fields.npz", **arrays)
    np.savetxt(
        directory / "accepted_steps.csv", solution["trace"], delimiter=",",
        header=",".join(TRACE_COLUMNS), comments="", fmt="%.17g",
    )
    record = {
        "status": status,
        "identity": identity,
        "source": source,
        "root": solution.get("root"),
        "terminal": solution["terminal"],
        "diagnostics": solution["diagnostics"],
        "files": {
            name: file_record(directory / name)
            for name in ["fields.npz", "accepted_steps.csv"]
        },
    }
    write_json(directory / "run.json", record)
    (directory / "failure.json").unlink(missing_ok=True)
    return record


def compute(data_root, directory, case, force=False, config_path="configs/q4.json"):
    directory = Path(directory) / "runs" / case["name"]
    config = read_config(config_path)
    inherited = read_config(config["q2_config"])
    horizon_s = float(case.get("horizon_s", config["default_horizon_s"]))
    env, radius, inputs = read_inputs(
        data_root,
        config,
        mode=case.get("environment_mode", config["environment_mode"]),
        fixed_radius=case["radius"] == "fixed",
        interpolation=case.get("interpolation", config["radius"]["interpolation"]),
        radius_offset_cm=case.get("radius_offset_cm", 0.0),
        horizon_s=horizon_s,
    )
    inputs["source_names"] = {k: v.replace("\\", "/") for k, v in inputs["source_names"].items()}
    settings = copy.deepcopy(inherited["solver"])
    tolerance_scale = float(case.get("tolerance_scale", 1.0))
    step_scale = float(case.get("max_step_scale", 1.0))
    for key in ["rtol", "atol_T", "atol_C"]:
        settings[key] *= tolerance_scale
    for key in ["max_step_observed", "max_step_extended"]:
        settings[key] *= step_scale
    settings["method"] = case.get("method", "BDF")
    parameters = q4_parameters(inherited["parameters"], config, case["properties"])
    fixed_radius_m = np.asarray(config["radius"]["fixed_output_radius_cm"], dtype=float) * 0.01
    identity = {
        "case": case,
        "inputs": inputs,
        "parameters": parameters,
        "settings": settings,
        "event": event_settings(config),
        "fixed_radius_m": fixed_radius_m.tolist(),
        "config_path": str(config_path).replace("\\", "/"),
    }
    if (directory / "run.json").exists() and not force:
        try:
            record, _ = load_run(directory)
        except ValueError:
            record = None
        if record is None:
            pass
        elif record["identity"] != identity:
            raise ValueError("Existing Q4 run configuration/input mismatch; use a new directory")
        elif record.get("status") == "computed":
            return case["name"], record["root"]["time_h"], "verified cache"
        else:
            return case["name"], record["status"], "verified typed-outcome cache"
    directory.mkdir(parents=True, exist_ok=True)
    source = snapshot()
    write_json(directory / "run.json", {"status": "running", "identity": identity, "source": source})
    try:
        grid = material_grid(case["N"], parameters["L"])
        solution = integrate_event(
            ShrinkingRadialModel(grid, parameters, env, radius),
            settings,
            event_settings(config),
            fixed_radius_m=fixed_radius_m,
        )
        save_solution(directory, solution, "computed", identity, source)
        return case["name"], solution["root"]["time_h"], solution["diagnostics"]["wall_seconds"]
    except (ThresholdNotReached, StrictPostStateUnavailable) as exc:
        status = exc.result["outcome"]
        save_solution(directory, exc.result, status, identity, source)
        return case["name"], status, exc.result["terminal"]["time_s"] / 3600
    except IntegrationFailure as exc:
        write_json(directory / "failure.json", {
            "type": type(exc).__name__, "error": str(exc), "identity": identity, "source": source,
        })
        raise RuntimeError(f"{case['name']}: {exc!r}") from exc
    except Exception as exc:
        write_json(directory / "failure.json", {"error": repr(exc), "identity": identity, "source": source})
        raise RuntimeError(f"{case['name']}: {exc!r}") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--directory", default="results/q4")
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected = cases(read_config("configs/q4.json"), include_refinement=bool(args.cases))
    if args.cases:
        selected = [case for case in selected if case["name"] in args.cases]
        if len(selected) != len(set(args.cases)):
            raise ValueError("Unknown Q4 case")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(compute, args.data_root, args.directory, case, args.force) for case in selected]
        for job in as_completed(jobs):
            print(json.dumps(job.result(), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
