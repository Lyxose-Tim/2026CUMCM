"""Stepwise implicit event solve; no changes to the inherited physical model."""
from collections import deque
import time

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import BDF
from scipy.optimize import brentq

from q2.solver import evaluate_selected


TRACE_COLUMNS = [
    "time_s", "Cmax", "argmax_radius_m", "center_C", "mean_C", "surface_C",
    "Cmin", "Tmin_C", "Tmax_C", "radial_increase", "relative_balance",
]


def full_max(state, n):
    state = np.asarray(state)
    if state.shape != (2 * n,) or not np.all(np.isfinite(state)):
        raise ValueError("Invalid full state")
    if np.min(state[n:]) <= 0:
        raise ValueError("Nonpositive moisture; no clipping is permitted")
    # The grid includes r=0 and r=R. Shape-preserving spatial reconstruction
    # (even quadratic on the first cell, linear elsewhere) has no larger extrema.
    index = int(np.argmax(state[n:]))
    return float(state[n + index]), index


def output_axis(end_s, spacing):
    if not np.isfinite(end_s) or end_s <= 0 or spacing <= 0:
        raise ValueError("Positive finite endpoint and spacing required")
    regular = np.arange(1, int(np.floor(end_s / spacing)) + 1, dtype=float) * spacing
    # Do not replace a close but distinct endpoint with a rounded timestamp.
    return regular if len(regular) and regular[-1] == end_s else np.r_[regular, end_s]


def locate(dense, left, right, n, threshold, xtol, width):
    def event(t):
        return full_max(dense(t), n)[0] - threshold
    if not (event(left) > 0 and event(right) <= 0):
        raise ValueError("A downward sign bracket is required")
    root = float(brentq(event, left, right, xtol=xtol, rtol=4*np.finfo(float).eps))
    a, b = float(left), float(right)
    while b - a > width:
        middle = (a + b) / 2
        if event(middle) > 0:
            a = middle
        else:
            b = middle
    return root, [a, b], [event(a), event(b)]


def integrate_event(model, settings, event_cfg):
    started = time.perf_counter()
    grid, p, env = model.grid, model.p, model.environment
    n = grid.N + 1
    threshold = event_cfg["threshold"]
    if max(env.observations[:, 2].max(), env.extension[1]) >= threshold:
        raise ValueError("First-crossing monotonicity requires environment below threshold")
    state = np.r_[np.full(n, p["T0"]), np.full(n, p["C0"])]
    if full_max(state, n)[0] <= threshold:
        raise ValueError("This problem requires a wet initial state")
    initial = state.copy()
    initial_content = p["C0"] * grid.volume.sum()
    atol = np.r_[np.full(n, settings["atol_T"]), np.full(n, settings["atol_C"])]
    quadrature = [leggauss(4), leggauss(8)]
    integrated_flux = 0.0
    quad_error = 0.0
    max_balance = 0.0
    max_increase = 0.0
    largest_boundary_relative_residual = 0.0
    largest_local_balance = 0.0
    temperature_envelope_violation = 0.0
    minimum_moisture = p["C0"]
    traces, output_times, output_T, output_C, output_summary = [], [0.0], [], [], []
    history = deque()
    root = None
    root_record = None
    root_states = None
    near_states = None
    previous_max = p["C0"]
    counts = dict(nfev=0, njev=0, nlu=0)

    def summarize(t, y, balance=np.nan):
        cmax, index = full_max(y, n)
        T, C = y[:n], y[n:]
        return [float(t), cmax, grid.r[index], C[0], np.dot(grid.volume, C)/grid.volume.sum(),
                C[-1], C.min(), T.min(), T.max(), np.diff(C).max(), balance]

    output_T.append(state[:n][grid.output_indices])
    output_C.append(state[n:][grid.output_indices])
    output_summary.append(summarize(0, state, 0)[:-1])
    next_output = 60.0

    def evaluate_history(t):
        for a, b, dense in history:
            if a <= t <= b:
                return dense(t)
        raise RuntimeError("Full-state event history coverage missing")

    done = False
    for a, b in zip(env.breaks[:-1], env.breaks[1:]):
        max_step = settings["max_step_observed"] if a < 14400 else settings["max_step_extended"]
        solver = BDF(model.rhs, float(a), state, float(b), jac=model.jac,
                     rtol=settings["rtol"], atol=atol, max_step=max_step,
                     first_step=min(1e-4, b-a) if a == 0 else None)
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
            # Check full state at every accepted endpoint AND midpoint, not 21 radii.
            mid = (left + right)/2
            for query, y in ((mid, dense(mid)), (right, state)):
                current_max, _ = full_max(y, n)
                max_increase = max(max_increase, current_max - previous_max)
                previous_max = current_max
                minimum_moisture = min(minimum_moisture, float(y[n:].min()))
                loT, hiT, _, _ = env.history_extrema(query)
                violation = max(min(p["T0"], float(loT))-y[:n].min(),
                                y[:n].max()-max(p["T0"], float(hiT)))
                temperature_envelope_violation = max(temperature_envelope_violation, float(violation))
                if violation > 1e-7 or current_max > p["C0"] + 1e-8:
                    raise RuntimeError("Historical state envelope failed")

            flux_estimates = []
            for nodes, weights in quadrature:
                queries = (left+right)/2 + (right-left)/2*nodes
                surface_C = evaluate_selected(dense, queries, [2*n-1])[0]
                flux = p["hm"] * (surface_C - env(queries)[1])
                flux_estimates.append((right-left)/2 * float(np.dot(weights, flux)))
            integrated_flux += flux_estimates[1]
            quad_error += abs(flux_estimates[1]-flux_estimates[0])
            balance = (np.dot(grid.volume, state[n:]) - initial_content +
                       grid.area[-1]*integrated_flux)/initial_content
            max_balance = max(max_balance, abs(float(balance)))
            traces.append(summarize(right, state, balance))

            if root is None:
                gl = full_max(dense(left), n)[0] - threshold
                gr = full_max(state, n)[0] - threshold
                if gl > 0 and gr <= 0:
                    root, bracket, signs = locate(dense, left, right, n, threshold,
                                                 event_cfg["root_xtol_s"], event_cfg["bracket_width_s"])
                    root_record = {"time_s": root, "time_h": root/3600,
                                   "accepted_bracket_s": [left, right], "bracket_s": bracket,
                                   "bracket_g": signs, "root_g": full_max(dense(root), n)[0]-threshold}
                    root_states = np.array([dense(bracket[0]), dense(root), dense(bracket[1])])
                elif gl <= 0:
                    raise RuntimeError("Missed the first downward crossing")

            limit = right if root is None else min(root, right)
            while next_output <= limit:
                y = dense(next_output)
                output_times.append(next_output)
                output_T.append(y[:n][grid.output_indices])
                output_C.append(y[n:][grid.output_indices])
                output_summary.append(summarize(next_output, y)[:-1])
                # Boundary derivative is independently reconstructed by 2nd order
                # backward differences; this is not the algebraic Robin flux itself.
                qT, qC = model.fluxes(next_output, y)
                rhs = model.rhs(next_output, y)
                local = np.max(np.abs(grid.volume*rhs[n:] + np.diff(grid.area*qC)))
                largest_local_balance = max(largest_local_balance, float(local))
                if next_output >= 60:
                    from q2.model import properties
                    _, _, _, D, _ = properties(y[:n], y[n:], p)
                    grad = (3*y[-1]-4*y[-2]+y[-3])/(2*grid.dr)
                    residual = abs(-D[-1]*grad-qC[-1])/max(abs(qC[-1]), 1e-30)
                    largest_boundary_relative_residual = max(largest_boundary_relative_residual, float(residual))
                next_output += 60

            if root is not None and right >= root + event_cfg["strict_offset_s"]:
                delta = event_cfg["strict_offset_s"]
                near_times = np.array([root-delta, root, root+delta])
                near_states = np.array([evaluate_history(t) for t in near_times])
                near_summary = np.array([summarize(t, y) for t,y in zip(near_times,near_states)])
                if not (near_summary[0, 1] > threshold and near_summary[2, 1] < threshold):
                    raise RuntimeError("Strict pre/post state test failed")
                if output_times[-1] != root:
                    output_times.append(root)
                    output_T.append(near_states[1,:n][grid.output_indices])
                    output_C.append(near_states[1,n:][grid.output_indices])
                    output_summary.append(near_summary[1, :-1])
                root_record["near_summary"] = near_summary[:, :-1].tolist()
                root_record["slope_C_per_s"] = float((near_summary[2,1]-near_summary[0,1])/(2*delta))
                done = True
                break
        for key in counts:
            counts[key] += getattr(solver, key)
        if done:
            break
    if not done:
        raise RuntimeError(f"No complete drying event by {env.horizon_s/3600} h; inspect model before extending")
    return {
        "time_s": np.array(output_times), "temperature_C": np.array(output_T),
        "moisture": np.array(output_C), "summary": np.array(output_summary),
        "trace": np.array(traces), "radius_m": grid.r, "volume_m3": grid.volume,
        "initial_state": initial, "bracket_states": root_states, "near_states": near_states,
        "root": root_record,
        "diagnostics": {**counts, "wall_seconds": time.perf_counter()-started,
            "initial_step_s": 1e-4,
            "accepted_steps": len(traces), "max_relative_balance": max_balance,
            "flux_quadrature_difference": quad_error, "minimum_moisture": minimum_moisture,
            "temperature_envelope_violation": temperature_envelope_violation,
            "max_Cmax_increase": max_increase,
            "max_surface_gradient_relative_residual": largest_boundary_relative_residual,
            "max_local_water_balance_absolute": largest_local_balance},
    }
