"""Q1 response functionals: ratio-scale quantities, never Celsius percentages."""
import numpy as np


METRICS = ("center_rise_K", "surface_rise_K", "center_moisture", "surface_moisture", "mean_loss")
UNITS = ("K", "K", "kg/kg", "kg/kg", "kg/kg")


def endpoints(data, parameters):
    if data["time_s"][-1] != 1800:
        raise ValueError("Q1 sensitivity functionals require t=1800 s")
    T, C = data["temperature_C"][-1], data["moisture"][-1]
    return dict(zip(METRICS, map(float, (T[0]-parameters["T0"], T[-1]-parameters["T0"],
                                        C[0], C[-1], parameters["C0"]-data["mean_moisture"][-1]))))


def elasticity(qminus, q0, qplus, delta, resolution):
    """Resolution is an explicit physical/numerical scale, not a denominator epsilon."""
    if delta <= 0 or resolution <= 0 or not np.all(np.isfinite([qminus,q0,qplus,delta,resolution])):
        raise ValueError("Finite values and positive delta/resolution required")
    resolved = max(abs(qplus-q0),abs(qminus-q0)) > 2*resolution
    if abs(q0) <= resolution:
        return {"central":None,"plus":None,"minus":None,"response_resolved":resolved,
                "status":"baseline_below_resolution"}
    return {"central":(qplus-qminus)/(2*delta*q0),"plus":(qplus-q0)/(delta*q0),
            "minus":(q0-qminus)/(delta*q0),"response_resolved":resolved,
            "status":"resolved" if resolved else "response_below_global_budget"}


def compare(a, b):
    """Every formal radius and second (t=0 excluded), plus volume means."""
    if not np.array_equal(a["time_s"],b["time_s"]):
        raise ValueError("Time axes differ")
    if not np.array_equal(a["radius_m"],b["radius_m"]):
        raise ValueError("Formal radius axes differ")
    mask = a["time_s"] >= 1
    times = a["time_s"][mask]
    early = times <= 60
    result = {}
    for name,key,mean_key in (("T","temperature_C","mean_temperature_C"),("C","moisture","mean_moisture")):
        err = abs(a[key][mask]-b[key][mask])
        i,j = np.unravel_index(err.argmax(),err.shape)
        result[name] = {"max_abs":float(err[i,j]),"time_s":float(times[i]),
                        "radius_cm":float(100*a["radius_m"][j]),
                        "early_surface_max":float(err[early,-1].max()),
                        "mean_max_abs":float(abs(a[mean_key][mask]-b[mean_key][mask]).max())}
    return result


def within_budget(comparison, budgets, kind):
    return all(comparison[x][key] <= budgets[f"{kind}_{x}"] for x in ("T","C")
               for key in ("max_abs","mean_max_abs"))
