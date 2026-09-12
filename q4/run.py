"""Reproducible Q4 shrinkage cases."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
from pathlib import Path

import numpy as np

from q2.archive import write_json
from q2.inputs import read_config, sha256
from q4.inputs import read_inputs
from q4.model import ShrinkingRadialModel, material_grid, q4_parameters
from q4.provenance import load_run, snapshot
from q4.solver import TRACE_COLUMNS, integrate_event


def cases(config, include_refinement=True):
    all_cases = copy.deepcopy(config["cases"])
    if include_refinement:
        all_cases += copy.deepcopy(config["refinement_cases"])
    names = [case["name"] for case in all_cases]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate Q4 case name")
    if include_refinement and config["formal_case"] not in names:
        raise ValueError("formal_case is not configured")
    for case in all_cases:
        if case["properties"] not in {"appendix3", "appendix4"} or case["radius"] not in {"fixed", "shrink"}:
            raise ValueError(f"Invalid Q4 case: {case}")
    return all_cases


def compute(data_root, directory, case, force=False):
    directory = Path(directory) / "runs" / case["name"]
    config = read_config("configs/q4.json")
    inherited = read_config(config["q2_config"])
    env, radius, inputs = read_inputs(data_root, config, fixed_radius=case["radius"] == "fixed")
    inputs["source_names"] = {k: v.replace("\\", "/") for k, v in inputs["source_names"].items()}
    settings = copy.deepcopy(inherited["solver"])
    if case.get("tight"):
        for key in ["rtol", "atol_T", "atol_C"]:
            settings[key] *= 0.1
    if case.get("half_step"):
        for key in ["max_step_observed", "max_step_extended"]:
            settings[key] *= 0.5
    parameters = q4_parameters(inherited["parameters"], config, case["properties"])
    fixed_radius_m = np.asarray(config["radius"]["fixed_output_radius_cm"], dtype=float) * 0.01
    identity = {"case": case, "inputs": inputs, "parameters": parameters,
                "settings": settings, "event": config, "fixed_radius_m": fixed_radius_m.tolist()}
    if (directory / "run.json").exists() and not force:
        try:
            record, _ = load_run(directory)
        except ValueError:
            record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
            if record.get("status") != "no_event":
                record = None
        if record is None:
            pass
        elif record["identity"] != identity:
            raise ValueError("Existing Q4 run configuration/input mismatch; use a new directory")
        elif record.get("status") == "no_event":
            return case["name"], f">{record['horizon_h']}", "verified no-event cache"
        else:
            return case["name"], record["root"]["time_h"], "verified cache"
    directory.mkdir(parents=True, exist_ok=True)
    source = snapshot()
    write_json(directory / "run.json", {"status": "running", "identity": identity, "source": source})
    try:
        grid = material_grid(case["N"], parameters["L"])
        solution = integrate_event(
            ShrinkingRadialModel(grid, parameters, env, radius),
            settings,
            config,
            fixed_radius_m=fixed_radius_m,
        )
        np.savez_compressed(directory / "fields.npz", **{
            key: value for key, value in solution.items()
            if isinstance(value, np.ndarray) and key != "trace"
        })
        np.savetxt(directory / "accepted_steps.csv", solution["trace"], delimiter=",",
                   header=",".join(TRACE_COLUMNS), comments="", fmt="%.17g")
        write_json(directory / "run.json", {
            "status": "computed", "identity": identity, "source": source,
            "root": solution["root"], "diagnostics": solution["diagnostics"],
            "files": {p: sha256(directory / p) for p in ["fields.npz", "accepted_steps.csv"]},
        })
        return case["name"], solution["root"]["time_h"], solution["diagnostics"]["wall_seconds"]
    except Exception as exc:
        if case.get("allow_no_event") and "No complete drying event" in str(exc):
            write_json(directory / "run.json", {
                "status": "no_event", "identity": identity, "source": source,
                "horizon_s": radius.observations[-1, 0],
                "horizon_h": radius.observations[-1, 0] / 3600,
                "reason": "No full-domain threshold crossing within the observed radius horizon",
            })
            return case["name"], f">{radius.observations[-1, 0] / 3600}", "no event"
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
