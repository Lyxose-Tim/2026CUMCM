"""Run the gated 72-hour Q2 calculation and create its verified archive."""
import argparse
import gc
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np

from common.hashing import file_record
from q1.fvm import Grid

from .archive import save_archive, write_json
from .inputs import read_config, read_inputs, sha256
from .model import CoupledRadialModel, q1_compatible_parameters
from .provenance import source_snapshot
from .solver import DIAGNOSTIC_COLUMNS, integrate
from .validation import difference, q1_comparison, state_checks


def tight_settings(settings):
    return {
        **settings,
        "rtol": settings["rtol"] / 10,
        "atol_T": settings["atol_T"] / 10,
        "atol_C": settings["atol_C"] / 10,
        "max_step_observed": settings["max_step_observed"] / 2,
        "max_step_extended": settings["max_step_extended"] / 2,
    }


def within_budget(record, budgets, prefix):
    return all(record[name]["max_abs"] <= budgets[f"{prefix}_{name}"] for name in ("T", "C"))


def csv(path, data, header):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, data, delimiter=",", header=header, comments="")


def run_scenario(data_root, config, mode, grid, settings, output_times):
    environment, metadata = read_inputs(data_root, config, mode=mode)
    solution = integrate(
        CoupledRadialModel(grid, config["parameters"], environment),
        settings,
        breaks=environment.breaks,
        output_times=output_times,
    )
    return solution, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--config", default="configs/q2.json")
    parser.add_argument("--output", default="results/q2")
    args = parser.parse_args()

    config = read_config(args.config)
    parameters = config["parameters"]
    settings = config["solver"]
    budgets = config["budgets"]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "failure.json").unlink(missing_ok=True)

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True
    )
    (output / "unit_tests.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    if tests.returncode:
        raise RuntimeError("Startup tests failed; formal Q2 output is blocked")
    print(tests.stdout.strip(), flush=True)

    environment, inputs = read_inputs(args.data_root, config)
    times = np.arange(config["horizon_s"] + 1, dtype=float)
    previous = None
    previous_errors = None
    streak = 0
    convergence = []
    final_grid = None
    for N in config["grids"]:
        print(f"Q2 spatial run N={N}", flush=True)
        grid = Grid(N, parameters["R"], parameters["L"])
        solution = integrate(
            CoupledRadialModel(grid, parameters, environment), settings,
            breaks=environment.breaks, output_times=times,
        )
        record = {"N": N, "solver": solution.diagnostics}
        if previous is not None:
            delta = difference(previous, solution, times)
            errors = {name: delta[name]["max_abs"] for name in ("T", "C")}
            decreasing = previous_errors is None or all(
                errors[name] < previous_errors[name] for name in ("T", "C")
            )
            passed = within_budget(delta, budgets, "space")
            streak = streak + 1 if passed and decreasing else 0
            record.update({
                "difference": delta,
                "within_budget": passed,
                "strictly_decreasing": decreasing,
                "consecutive_within_budget": streak,
            })
            if previous_errors is not None:
                record["observed_order"] = {
                    name: float(np.log2(previous_errors[name] / errors[name]))
                    for name in ("T", "C")
                }
            previous_errors = errors
            print(json.dumps(record["difference"]), flush=True)
        convergence.append(record)
        write_json(output / "convergence.json", convergence)
        if previous is not None:
            del previous
        previous = solution
        final_grid = grid
        if streak >= 2:
            break
        gc.collect()

    space_passed = streak >= 2
    if not space_passed:
        raise RuntimeError(f"Spatial convergence gate failed through N={final_grid.N}")

    strict = tight_settings(settings)
    print(f"Q2 strict BDF N={final_grid.N}", flush=True)
    final = integrate(
        CoupledRadialModel(final_grid, parameters, environment), strict,
        breaks=environment.breaks, output_times=times,
    )
    tolerance_difference = difference(previous, final, times)
    del previous
    gc.collect()

    radau_settings = {**strict, "method": "Radau"}
    print(f"Q2 Radau cross-check N={final_grid.N}", flush=True)
    radau = integrate(
        CoupledRadialModel(final_grid, parameters, environment), radau_settings,
        breaks=environment.breaks, output_times=times,
    )
    radau_difference = difference(final, radau, times)
    radau_diagnostics = radau.diagnostics
    del radau
    gc.collect()
    time_passed = within_budget(tolerance_difference, budgets, "time") and within_budget(
        radau_difference, budgets, "time"
    )

    q1_data, _, q1_manifest = __import__("q1.archive", fromlist=["load_archive"]).load_archive(
        "results/q1/archive"
    )
    q1_N = int(q1_manifest["N"])
    q1_grid = Grid(q1_N, parameters["R"], parameters["L"])
    q1_times = np.arange(1801, dtype=float)
    q1_breaks = environment.observations[environment.observations[:, 0] <= 1800, 0]
    q1_solution = integrate(
        CoupledRadialModel(q1_grid, q1_compatible_parameters(parameters), environment),
        strict, breaks=q1_breaks, output_times=q1_times,
    )
    q1_delta = q1_comparison(q1_solution)
    q1_passed = q1_delta["T"]["max_abs"] <= budgets["time_T"] and q1_delta["C"]["max_abs"] <= budgets["time_C"]
    del q1_data, q1_solution

    checks = state_checks(final, parameters, environment)
    balance_passed = final.diagnostics["relative_moisture_balance"] <= 1e-8
    flux_passed = (
        checks["surface_heat_robin_max_residual"] <= 1e-12
        and checks["surface_moisture_robin_max_residual"] <= 1e-18
        and checks["surface_heat_flux_sign_consistent"]
        and checks["surface_moisture_flux_sign_consistent"]
    )
    state_passed = all(checks[key] for key in (
        "finite", "positive_moisture", "initial_temperature_exact",
        "initial_moisture_exact", "time_axis_exact",
    ))
    numerical_passed = all((space_passed, time_passed, balance_passed, flux_passed, state_passed, q1_passed))
    verification = {
        "numerical_passed": numerical_passed,
        "space_passed": space_passed,
        "consecutive_within_budget": streak,
        "N": final_grid.N,
        "time_passed": time_passed,
        "tolerance_difference": tolerance_difference,
        "radau_difference": radau_difference,
        "radau_diagnostics": radau_diagnostics,
        "state_checks": checks,
        "moisture_balance_passed": balance_passed,
        "surface_flux_boundary_passed": flux_passed,
        "q1_compatible_passed": q1_passed,
        "q1_compatible_difference": q1_delta,
        "accepted_envelope_passed": True,
        "export_passed": False,
    }
    write_json(output / "verification.json", verification)
    csv(output / "accepted_steps.csv", final.accepted, ",".join(DIAGNOSTIC_COLUMNS))
    csv(output / "environment.csv", environment.observations, "time_s,temperature_C,equivalent_moisture")

    if not numerical_passed:
        raise RuntimeError("One or more Q2 numerical gates failed")

    snapshot = source_snapshot()
    metadata = {
        "status": "numerically_verified",
        "inputs": inputs,
        "configuration": config,
        "solver": final.diagnostics,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "matplotlib", "openpyxl", "pytest")
        },
        **snapshot,
        "command": ["python", "-m", "q2.run", "--data-root", "<A-problem-directory>"],
        "verification_hash": file_record(output / "verification.json"),
    }
    save_archive(output / "archive", final, final_grid, metadata)

    scenario_times = np.unique(np.r_[np.arange(0, config["horizon_s"] + 1, 3600), config["horizon_s"]]).astype(float)
    scenario_records = []
    scenario_arrays = {"time_s": scenario_times}
    for mode in config["environment"]["scenario_extensions"]:
        print(f"Q2 environment scenario={mode}", flush=True)
        scenario, scenario_inputs = run_scenario(
            args.data_root, config, mode, final_grid, strict, scenario_times
        )
        scenario_arrays[f"{mode}_temperature_C"] = scenario.temperature_C
        scenario_arrays[f"{mode}_moisture"] = scenario.moisture
        scenario_records.append({
            "mode": mode,
            "extension": scenario_inputs["environment_extension"],
            "solver": scenario.diagnostics,
            "endpoint": {
                "center_temperature_C": float(scenario.temperature_C[-1, 0]),
                "surface_temperature_C": float(scenario.temperature_C[-1, -1]),
                "center_moisture": float(scenario.moisture[-1, 0]),
                "surface_moisture": float(scenario.moisture[-1, -1]),
            },
        })
        del scenario
        gc.collect()
    np.savez_compressed(output / "environment_scenarios.npz", **scenario_arrays)
    write_json(output / "environment_scenarios.json", scenario_records)
    print(json.dumps({"numerical_passed": True, "N": final_grid.N}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        destination = sys.argv[sys.argv.index("--output") + 1] if "--output" in sys.argv else "results/q2"
        write_json(Path(destination) / "failure.json", {
            "type": type(exc).__name__, "message": str(exc), "export_allowed": False,
        })
        raise
