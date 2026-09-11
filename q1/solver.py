"""Segmented implicit integration with accepted-step and independent flux audits."""
from dataclasses import dataclass
import time

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.integrate import BDF, Radau

from .fvm import NonpositiveMoisture


DIAGNOSTIC_COLUMNS = ["time_s", "step_s", "temperature_min_C", "temperature_max_C", "moisture_min", "moisture_max", "surface_temperature_C", "surface_moisture", "mean_temperature_C", "mean_moisture"]


@dataclass
class Solution:
    times: np.ndarray
    temperature_C: np.ndarray
    moisture: np.ndarray
    accepted: np.ndarray
    boundary_integrals: np.ndarray
    integration_check: np.ndarray
    diagnostics: dict

    def output(self, grid):
        idx = grid.output_indices
        return self.temperature_C[:, idx], self.moisture[:, idx]


def integrate(model, settings, *, breaks=None, output_times=None, initial=None,
              check_envelope=False, audit=False):
    """Every segment starts from its exact predecessor endpoint; no state clipping.

    The flux audit integrates dense output independently of the ODE RHS. Splits
    include every accepted step, measurement knot and requested output time.
    Gauss 4/8 disagreement triggers subdivision; no auxiliary balance ODE is used.
    """
    started = time.perf_counter()
    g, p = model.grid, model.p
    n = g.N + 1
    breaks = np.arange(0.,1801.,60.) if breaks is None else np.asarray(breaks, dtype=float)
    times = np.arange(1801, dtype=float) if output_times is None else np.asarray(output_times,dtype=float)
    if np.any(np.diff(times) <= 0) or times[0] < breaks[0] or times[-1] > breaks[-1]:
        raise ValueError("Output times must increase within integration interval")
    state = np.r_[np.full(n,p["T0"]),np.full(n,p["C0"])] if initial is None else np.array(initial,dtype=float)
    field = np.empty((len(times),2*n))
    cumulative_out = np.zeros((len(times),2))
    quad_check_out = np.zeros((len(times),2))
    accepted = []
    failures = []
    total_counts = dict(nfev=0,njev=0,nlu=0)
    cumulative = np.zeros(2)
    quad_difference = np.zeros(2)
    position = 0
    if times[0] == breaks[0]:
        field[0] = state
        position = 1
    atol = np.r_[np.full(n,settings["atol_T"]),np.full(n,settings["atol_C"])]
    solver_cls = {"BDF":BDF,"Radau":Radau}[settings["method"]]
    quadratures = [leggauss(4), leggauss(8)]

    def flux_integral(dense, a, b, depth=0):
        estimates = []
        for nodes, weights in quadratures:
            tt = (a+b)/2 + (b-a)/2*nodes
            values = dense(tt)
            env_T, env_C = model.environment(tt)
            qs = np.array([p["h"]*(values[n-1]-env_T),p["hm"]*(values[-1]-env_C)])
            estimates.append((b-a)/2*(qs @ weights))
        difference = abs(estimates[1]-estimates[0])
        # Scale relative to a typical whole-run integral; absolute safeguard at zero flux.
        scale = np.array([p["h"]*14*1800, p["hm"]*p["C0"]*1800])
        if np.any(difference > 1e-12*scale) and depth < 8:
            l, dl = flux_integral(dense,a,(a+b)/2,depth+1)
            r, dr = flux_integral(dense,(a+b)/2,b,depth+1)
            return l+r, dl+dr
        if np.any(difference > 1e-12*scale):
            raise RuntimeError("Independent boundary quadrature failed to converge")
        return estimates[1], difference

    for a,b in zip(breaks[:-1],breaks[1:]):
        initial_segment = state.copy()
        initial_position = position
        initial_integral, initial_difference = cumulative.copy(), quad_difference.copy()
        for attempt in range(3):
            position = initial_position
            cumulative, quad_difference = initial_integral.copy(), initial_difference.copy()
            segment_rows = []
            last_rhs = {"t":float(a)}
            solver = None

            def rhs(t,y):
                last_rhs["t"] = float(t)
                return model.rhs(t,y)

            try:
                solver = solver_cls(rhs, a, initial_segment.copy(), b, jac=model.jac,
                                    rtol=settings["rtol"], atol=atol,
                                    max_step=settings["max_step"]/(10**attempt),
                                    first_step=None if attempt == 0 else min(1e-4/(10**(attempt-1)),b-a))
                while solver.status == "running":
                    left = solver.t
                    message = solver.step()
                    if solver.status == "failed":
                        raise RuntimeError(f"{settings['method']} failed: {message}")
                    right, y = solver.t, solver.y
                    T, C = y[:n], y[n:]
                    if np.any(C <= 0) or not np.all(np.isfinite(y)):
                        raise RuntimeError("Illegal accepted state")
                    if check_envelope:
                        upper_T = max(p["T0"], float(model.environment(right)[0]))
                        if T.min() < p["T0"]-1e-7 or T.max() > upper_T+1e-7 or C.min() < 0.01963-1e-9 or C.max() > p["C0"]+1e-9:
                            raise RuntimeError(f"Accepted-state envelope failed at t={right}")
                    segment_rows.append([right,right-left,T.min(),T.max(),C.min(),C.max(),T[-1],C[-1],np.dot(g.volume,T)/g.volume.sum(),np.dot(g.volume,C)/g.volume.sum()])
                    dense = solver.dense_output()
                    cursor = left
                    while position < len(times) and times[position] <= right:
                        t = times[position]
                        field[position] = dense(t)
                        if audit:
                            val, diff = flux_integral(dense,cursor,t)
                            cumulative += val
                            quad_difference += diff
                            cursor = t
                            cumulative_out[position] = cumulative
                            quad_check_out[position] = quad_difference
                        position += 1
                    if audit and cursor < right:
                        val,diff = flux_integral(dense,cursor,right)
                        cumulative += val
                        quad_difference += diff
                state = solver.y.copy()
                accepted.extend(segment_rows)
                for key in total_counts:
                    total_counts[key] += getattr(solver,key)
                break
            except NonpositiveMoisture as exc:
                failures.append({"segment_start":float(a),"attempt":attempt+1,"trial_time":last_rhs["t"],"node":exc.node,"value":exc.value,"current_step":None if solver is None else float(solver.h_abs)})
                if attempt == 2:
                    raise RuntimeError(f"Three nonpositive trial failures: {failures}") from exc
    if position != len(times):
        raise RuntimeError("Incomplete output time coverage")
    if np.any(field[:,n:] <= 0) or not np.all(np.isfinite(field)):
        raise RuntimeError("Invalid dense output")
    if check_envelope:
        upper = np.maximum(p["T0"], model.environment(times)[0])
        if np.any(field[:,:n] < p["T0"]-1e-7) or np.any(field[:,:n] > upper[:,None]+1e-7) or np.any(field[:,n:] > p["C0"]+1e-9) or np.any(field[:,n:] < 0.01963-1e-9):
            raise RuntimeError("Output envelope failed")
    diag = {**total_counts,"method":settings["method"],"settings":settings,"seconds":time.perf_counter()-started,"trial_failures":failures,"accepted_steps":len(accepted),"audited":audit}
    return Solution(times,field[:,:n],field[:,n:],np.asarray(accepted),cumulative_out,quad_check_out,diag)
