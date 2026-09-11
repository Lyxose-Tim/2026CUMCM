"""Independent Q2 comparison metrics and physical checks."""
import numpy as np

from q1.archive import load_archive as load_q1_archive


def difference(coarse, fine, times):
    result = {}
    radius = np.arange(21, dtype=float) / 10
    for name, a, b in (
        ("T", coarse.temperature_C, fine.temperature_C),
        ("C", coarse.moisture, fine.moisture),
    ):
        delta = np.abs(a - b)
        index = np.unravel_index(np.argmax(delta), delta.shape)
        early = times <= 60
        result[name] = {
            "max_abs": float(delta[index]),
            "time_s": float(times[index[0]]),
            "radius_cm": float(radius[index[1]]),
            "early_surface_max": float(delta[early, -1].max()),
            "at_72h_max": float(delta[-1].max()),
        }
    return result


def q1_comparison(q2_solution, q1_directory="results/q1/archive"):
    q1, geometry, _ = load_q1_archive(q1_directory)
    q1_T = q1["temperature_C"][:, geometry["output_indices"]]
    q1_C = q1["moisture"][:, geometry["output_indices"]]
    records = {}
    for name, q1_values, q2_values in (
        ("T", q1_T, q2_solution.temperature_C[:1801]),
        ("C", q1_C, q2_solution.moisture[:1801]),
    ):
        delta = np.abs(q2_values - q1_values)
        index = np.unravel_index(np.argmax(delta), delta.shape)
        records[name] = {
            "max_abs": float(delta[index]),
            "time_s": int(index[0]),
            "radius_cm": index[1] / 10,
            "q1": float(q1_values[index]),
            "q2": float(q2_values[index]),
        }
    return records


def state_checks(solution, parameters, environment=None):
    result = {
        "finite": bool(np.isfinite(solution.temperature_C).all() and np.isfinite(solution.moisture).all()),
        "positive_moisture": bool(np.all(solution.moisture > 0)),
        "temperature_min_C": float(solution.temperature_C.min()),
        "temperature_max_C": float(solution.temperature_C.max()),
        "moisture_min": float(solution.moisture.min()),
        "moisture_max": float(solution.moisture.max()),
        "initial_temperature_exact": bool(np.array_equal(solution.temperature_C[0], np.full(21, parameters["T0"]))),
        "initial_moisture_exact": bool(np.array_equal(solution.moisture[0], np.full(21, parameters["C0"]))),
        "time_axis_exact": bool(np.array_equal(solution.times, np.arange(len(solution.times), dtype=float))),
        "outward_heat_flux_nonpositive_fraction": float(np.mean(solution.accepted[:, 10] <= 1e-12)),
        "outward_moisture_flux_nonnegative_fraction": float(np.mean(solution.accepted[:, 11] >= -1e-14)),
    }
    if environment is not None:
        exterior_T, exterior_C = environment(solution.accepted[:, 0])
        expected_T = parameters["h"] * (solution.accepted[:, 6] - exterior_T)
        expected_C = parameters["hm"] * (solution.accepted[:, 7] - exterior_C)
        result.update({
            "surface_heat_robin_max_residual": float(np.max(np.abs(solution.accepted[:, 10] - expected_T))),
            "surface_moisture_robin_max_residual": float(np.max(np.abs(solution.accepted[:, 11] - expected_C))),
            "surface_heat_flux_sign_consistent": bool(np.all(solution.accepted[:, 10] * (solution.accepted[:, 6] - exterior_T) >= -1e-13)),
            "surface_moisture_flux_sign_consistent": bool(np.all(solution.accepted[:, 11] * (solution.accepted[:, 7] - exterior_C) >= -1e-18)),
        })
    return result
