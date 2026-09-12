"""Event integration for the shrinking-radius fourth problem."""
from collections import deque
import time

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import BDF
from scipy.optimize import brentq

from q2.solver import evaluate_selected
from q3.solver import full_max, output_axis


TRACE_COLUMNS = [
    "time_s", "radius_m", "Cmax", "argmax_xi", "argmax_radius_m",
    "center_C", "mean_C", "surface_C", "Cmin", "Tmin_C", "Tmax_C",
    "radial_increase", "relative_balance",
]


def union_breaks(environment, radius, horizon_s):
    breaks = np.union1d(environment.breaks, radius.breaks)
    breaks = breaks[(breaks >= 0) & (breaks <= horizon_s)]
    if breaks[-1] != horizon_s:
        breaks = np.r_[breaks, horizon_s]
    return breaks


def locate(dense, left, right, n, threshold, xtol, width):
    def event(t):
        return full_max(dense(t), n)[0] - threshold
    if not (event(left) > 0 and event(right) <= 0):
        raise ValueError("A downward sign bracket is required")
    root = float(brentq(event, left, right, xtol=xtol, rtol=4 * np.finfo(float).eps))
    a, b = float(left), float(right)
    while b - a > width:
        middle = (a + b) / 2
        if event(middle) > 0:
            a = middle
        else:
            b = middle
    return root, [a, b], [event(a), event(b)]


def selected_physical(grid, values, radius_m, fixed_radius_m):
    xi = fixed_radius_m / radius_m
    result = np.full(len(fixed_radius_m) + 1, np.nan)
    valid = xi <= 1.0 + 1e-12
    clipped = np.clip(xi[valid], 0.0, 1.0)
    result[:len(fixed_radius_m)][valid] = np.interp(clipped, grid.r, values)
    result[-1] = values[-1]
    return result


def integrate_event(model, settings, event_cfg, *, fixed_radius_m):
    started = time.perf_counter()
    grid, p, env, radius = model.grid, model.p, model.environment, model.radius
    n = grid.N + 1
    threshold = event_cfg["threshold"]
    if max(env.observations[:, 2].max(), env.extension[1]) >= threshold:
        raise ValueError("First-crossing monotonicity requires environment below threshold")
    state = np.r_[np.full(n, p["T0"]), np.full(n, p["C0"])]
    initial = state.copy()
    initial_content = p["C0"] * grid.volume.sum()
    previous_max = p["C0"]
    atol = np.r_[np.full(n, settings["atol_T"]), np.full(n, settings["atol_C"])]
    quadrature = [leggauss(4), leggauss(8)]
    integrated_flux = 0.0
    quad_error = 0.0
    max_balance = 0.0
    max_increase = 0.0
    minimum_moisture = p["C0"]
    temperature_envelope_violation = 0.0
    traces, output_times, output_T, output_C, output_radius, output_summary = [], [], [], [], [], []
    history = deque()
    root = None
    root_record = None
    root_states = None
    near_states = None
    counts = dict(nfev=0, njev=0, nlu=0)

    def summarize(t, y, balance=np.nan):
        cmax, index = full_max(y, n)
        T, C = y[:n], y[n:]
        R = float(radius(t))
        return [float(t), R, cmax, grid.r[index], R * grid.r[index], C[0],
                np.dot(grid.volume, C) / grid.volume.sum(), C[-1],
                C.min(), T.min(), T.max(), np.diff(C).max(), balance]

    def append_output(t, y):
        R = float(radius(t))
        output_times.append(float(t))
        output_radius.append(R)
        output_T.append(selected_physical(grid, y[:n], R, fixed_radius_m))
        output_C.append(selected_physical(grid, y[n:], R, fixed_radius_m))
        output_summary.append(summarize(t, y)[:-1])

    append_output(0.0, state)
    next_output = 60.0

    def evaluate_history(t):
        for a, b, dense in history:
            if a <= t <= b:
                return dense(t)
        raise RuntimeError("Full-state event history coverage missing")

    breaks = union_breaks(env, radius, radius.observations[-1, 0])
    done = False
    for a, b in zip(breaks[:-1], breaks[1:]):
        max_step = settings["max_step_observed"] if a < 14400 else settings["max_step_extended"]
        solver = BDF(model.rhs, float(a), state, float(b), jac=model.jac,
                     rtol=settings["rtol"], atol=atol, max_step=max_step,
                     first_step=min(1e-4, b - a) if a == 0 else None)
        while solver.status == "running":
            left = solver.t
            message = solver.step()
            if solver.status == "failed":
                raise RuntimeError(f"BDF integration failed: {message}")
            right, state = solver.t, solver.y
            dense = solver.dense_output()
            history.append((left, right, dense))
            while history and history[0][1] < right - 1200:
                history.popleft()
            for query, y in (((left + right) / 2, dense((left + right) / 2)), (right, state)):
                current_max, _ = full_max(y, n)
                max_increase = max(max_increase, current_max - previous_max)
                previous_max = current_max
                minimum_moisture = min(minimum_moisture, float(y[n:].min()))
                loT, hiT, _, _ = env.history_extrema(query)
                violation = max(min(p["T0"], float(loT)) - y[:n].min(),
                                y[:n].max() - max(p["T0"], float(hiT)))
                temperature_envelope_violation = max(temperature_envelope_violation, float(violation))
                if violation > 1e-7 or current_max > p["C0"] + 1e-8:
                    raise RuntimeError("Historical state envelope failed")

            flux_estimates = []
            for nodes, weights in quadrature:
                queries = (left + right) / 2 + (right - left) / 2 * nodes
                surface_C = evaluate_selected(dense, queries, [2 * n - 1])[0]
                Rq = radius(queries)
                flux = p["hm"] * (surface_C - env(queries)[1]) / Rq
                flux_estimates.append((right - left) / 2 * float(np.dot(weights, flux)))
            integrated_flux += flux_estimates[1]
            quad_error += abs(flux_estimates[1] - flux_estimates[0])
            balance = (np.dot(grid.volume, state[n:]) - initial_content +
                       grid.area[-1] * integrated_flux) / initial_content
            max_balance = max(max_balance, abs(float(balance)))
            traces.append(summarize(right, state, balance))

            if root is None:
                gl = full_max(dense(left), n)[0] - threshold
                gr = full_max(state, n)[0] - threshold
                if gl > 0 and gr <= 0:
                    root, bracket, signs = locate(dense, left, right, n, threshold,
                                                 event_cfg["root_xtol_s"], event_cfg["bracket_width_s"])
                    root_record = {"time_s": root, "time_h": root / 3600,
                                   "radius_m": float(radius(root)),
                                   "accepted_bracket_s": [left, right], "bracket_s": bracket,
                                   "bracket_g": signs, "root_g": full_max(dense(root), n)[0] - threshold}
                    root_states = np.array([dense(bracket[0]), dense(root), dense(bracket[1])])
                elif gl <= 0:
                    raise RuntimeError("Missed the first downward crossing")

            limit = right if root is None else min(root, right)
            while next_output <= limit:
                append_output(next_output, dense(next_output))
                next_output += 60

            if root is not None and right >= root + event_cfg["strict_offset_s"]:
                delta = event_cfg["strict_offset_s"]
                near_times = np.array([root - delta, root, root + delta])
                near_states = np.array([evaluate_history(t) for t in near_times])
                near_summary = np.array([summarize(t, y) for t, y in zip(near_times, near_states)])
                if not (near_summary[0, 2] > threshold and near_summary[2, 2] < threshold):
                    raise RuntimeError("Strict pre/post state test failed")
                if output_times[-1] != root:
                    append_output(root, near_states[1])
                root_record["near_summary"] = near_summary[:, :-1].tolist()
                root_record["slope_C_per_s"] = float((near_summary[2, 2] - near_summary[0, 2]) / (2 * delta))
                done = True
                break
        for key in counts:
            counts[key] += getattr(solver, key)
        if done:
            break
    if not done:
        raise RuntimeError("No complete drying event by the available radius horizon")
    return {
        "time_s": np.array(output_times), "surface_radius_m": np.array(output_radius),
        "temperature_C": np.array(output_T), "moisture": np.array(output_C),
        "summary": np.array(output_summary), "trace": np.array(traces),
        "xi": grid.r, "volume_xi": grid.volume, "fixed_radius_m": np.array(fixed_radius_m),
        "initial_state": initial, "bracket_states": root_states, "near_states": near_states,
        "root": root_record,
        "diagnostics": {**counts, "wall_seconds": time.perf_counter() - started,
            "initial_step_s": 1e-4, "accepted_steps": len(traces),
            "max_relative_balance": max_balance,
            "flux_quadrature_difference": quad_error, "minimum_moisture": minimum_moisture,
            "temperature_envelope_violation": temperature_envelope_violation,
            "max_Cmax_increase": max_increase},
    }
