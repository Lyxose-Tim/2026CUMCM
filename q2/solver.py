"""Segmented implicit integration with selected-node dense output."""
from dataclasses import dataclass
import time

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import BDF, Radau

from q1.fvm import NonpositiveMoisture


DIAGNOSTIC_COLUMNS = [
    "time_s", "step_s", "temperature_min_C", "temperature_max_C",
    "moisture_min", "moisture_max", "surface_temperature_C",
    "surface_moisture", "mean_temperature_C", "mean_moisture",
    "surface_heat_flux", "surface_moisture_flux", "cumulative_moisture_flux",
]


@dataclass
class Solution:
    times: np.ndarray
    temperature_C: np.ndarray
    moisture: np.ndarray
    accepted: np.ndarray
    final_state: np.ndarray
    diagnostics: dict


def evaluate_selected(dense, query, indices):
    """Evaluate SciPy's pinned BDF/Radau polynomial only at selected states."""
    t = np.asarray(query, dtype=float)
    indices = np.asarray(indices, dtype=int)
    if dense.__class__.__name__ == "BdfDenseOutput":
        if t.ndim == 0:
            p = np.cumprod((t - dense.t_shift) / dense.denom)
        else:
            p = np.cumprod(
                (t[None, :] - dense.t_shift[:, None]) / dense.denom[:, None], axis=0
            )
        y = np.dot(dense.D[1:, indices].T, p)
        return y + (dense.D[0, indices] if y.ndim == 1 else dense.D[0, indices, None])
    if dense.__class__.__name__ == "RadauDenseOutput":
        x = (t - dense.t_old) / dense.h
        if t.ndim == 0:
            p = np.cumprod(np.tile(x, dense.order + 1))
        else:
            p = np.cumprod(np.tile(x, (dense.order + 1, 1)), axis=0)
        y = np.dot(dense.Q[indices], p)
        return y + (dense.y_old[indices] if y.ndim == 1 else dense.y_old[indices, None])
    return dense(t)[indices]


def integrate(model, settings, *, breaks, output_times, initial=None, check_envelope=True):
    started = time.perf_counter()
    grid, parameters = model.grid, model.p
    n = grid.N + 1
    breaks = np.asarray(breaks, dtype=float)
    times = np.asarray(output_times, dtype=float)
    if (
        np.any(np.diff(breaks) <= 0) or np.any(np.diff(times) <= 0)
        or times[0] < breaks[0] or times[-1] > breaks[-1]
    ):
        raise ValueError("Strictly increasing breaks and output times are required")
    state = (
        np.r_[np.full(n, parameters["T0"]), np.full(n, parameters["C0"])]
        if initial is None else np.asarray(initial, dtype=float).copy()
    )
    if state.shape != (2 * n,) or np.any(state[n:] <= 0) or not np.all(np.isfinite(state)):
        raise ValueError("Invalid initial Q2 state")
    output_indices = grid.output_indices
    state_indices = np.r_[output_indices, n + output_indices]
    temperature = np.empty((len(times), 21), dtype=float)
    moisture = np.empty((len(times), 21), dtype=float)
    position = 0
    if times[0] == breaks[0]:
        temperature[0] = state[output_indices]
        moisture[0] = state[n + output_indices]
        position = 1

    solver_class = {"BDF": BDF, "Radau": Radau}[settings["method"]]
    atol = np.r_[np.full(n, settings["atol_T"]), np.full(n, settings["atol_C"])]
    initial_bounds = (state[:n].min(), state[:n].max(), state[n:].min(), state[n:].max())
    accepted = []
    failures = []
    counts = {"nfev": 0, "njev": 0, "nlu": 0}
    cumulative_moisture_flux = 0.0
    quadrature_difference = 0.0
    quadratures = [leggauss(4), leggauss(8)]

    def envelope(t):
        loT, hiT, loC, hiC = model.environment.history_extrema(t)
        return (
            min(initial_bounds[0], float(loT)), max(initial_bounds[1], float(hiT)),
            min(initial_bounds[2], float(loC)), max(initial_bounds[3], float(hiC)),
        )

    def integrate_surface_flux(dense, left, right):
        estimates = []
        for nodes, weights in quadratures:
            query = (left + right) / 2 + (right - left) / 2 * nodes
            values = evaluate_selected(dense, query, [2 * n - 1])[0]
            exterior = model.environment(query)[1]
            flux = parameters["hm"] * (values - exterior)
            estimates.append((right - left) / 2 * float(np.dot(flux, weights)))
        return estimates[1], abs(estimates[1] - estimates[0])

    for a, b in zip(breaks[:-1], breaks[1:]):
        segment_initial = state.copy()
        segment_position = position
        segment_cumulative = cumulative_moisture_flux
        segment_quadrature = quadrature_difference
        max_step = settings["max_step_observed"] if a < 14400 else settings["max_step_extended"]
        for attempt in range(3):
            state = segment_initial.copy()
            position = segment_position
            cumulative_moisture_flux = segment_cumulative
            quadrature_difference = segment_quadrature
            rows = []
            solver = None
            last_rhs = {"time": float(a)}

            def rhs(t, y):
                last_rhs["time"] = float(t)
                return model.rhs(t, y)

            try:
                solver = solver_class(
                    rhs, a, state, b, jac=model.jac, rtol=settings["rtol"], atol=atol,
                    max_step=max_step / (10**attempt),
                    first_step=None if attempt == 0 else min(1e-4 / (10**(attempt - 1)), b - a),
                )
                while solver.status == "running":
                    left = solver.t
                    message = solver.step()
                    if solver.status == "failed":
                        raise RuntimeError(f"{settings['method']} failed: {message}")
                    right, state = solver.t, solver.y
                    T, C = state[:n], state[n:]
                    if np.any(C <= 0) or not np.all(np.isfinite(state)):
                        raise RuntimeError("Illegal accepted Q2 state")
                    if check_envelope:
                        loT, hiT, loC, hiC = envelope(right)
                        if (
                            T.min() < loT - 1e-7 or T.max() > hiT + 1e-7
                            or C.min() < loC - 1e-9 or C.max() > hiC + 1e-9
                        ):
                            raise RuntimeError(f"Accepted-state envelope failed at {right}")
                    dense = solver.dense_output()
                    flux_increment, quad_difference = integrate_surface_flux(dense, left, right)
                    cumulative_moisture_flux += flux_increment
                    quadrature_difference += quad_difference
                    qT, qC = model.fluxes(right, state)
                    rows.append([
                        right, right - left, T.min(), T.max(), C.min(), C.max(), T[-1], C[-1],
                        np.dot(grid.volume, T) / grid.volume.sum(),
                        np.dot(grid.volume, C) / grid.volume.sum(),
                        qT[-1], qC[-1], cumulative_moisture_flux,
                    ])
                    end = np.searchsorted(times, right, side="right")
                    if end > position:
                        selected = evaluate_selected(dense, times[position:end], state_indices)
                        temperature[position:end] = selected[:21].T
                        moisture[position:end] = selected[21:].T
                        position = end
                accepted.extend(rows)
                for key in counts:
                    counts[key] += getattr(solver, key)
                break
            except NonpositiveMoisture as exc:
                failures.append({
                    "segment_start": float(a), "attempt": attempt + 1,
                    "trial_time": last_rhs["time"], "node": exc.node, "value": exc.value,
                })
                if attempt == 2:
                    raise RuntimeError(f"Three nonpositive trial failures: {failures}") from exc
    if position != len(times):
        raise RuntimeError("Incomplete Q2 output time coverage")
    if np.any(moisture <= 0) or not np.all(np.isfinite(temperature)) or not np.all(np.isfinite(moisture)):
        raise RuntimeError("Invalid selected-node Q2 output")
    initial_content = parameters["C0"] * grid.volume.sum()
    final_content = np.dot(grid.volume, state[n:])
    moisture_balance = final_content - initial_content + grid.area[-1] * cumulative_moisture_flux
    diagnostics = {
        **counts,
        "method": settings["method"], "settings": settings,
        "seconds": time.perf_counter() - started, "accepted_steps": len(accepted),
        "trial_failures": failures,
        "moisture_balance": float(moisture_balance),
        "relative_moisture_balance": float(abs(moisture_balance) / initial_content),
        "surface_flux_quadrature_difference": float(quadrature_difference),
    }
    return Solution(times, temperature, moisture, np.asarray(accepted), state.copy(), diagnostics)
