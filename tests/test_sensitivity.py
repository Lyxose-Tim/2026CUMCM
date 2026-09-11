from types import SimpleNamespace

import numpy as np
import pytest

from q1.fvm import Grid, RadialModel
from q1.inputs import Environment, read_config
from q1.solver import integrate
from q1.validation import boundary_check
from q1.sensitivity import scenarios
from q1.sensitivity_metrics import elasticity, endpoints, compare
from q1.sensitivity_report import verified_runs
from q1.archive import write_json


CFG = read_config()
P = CFG["parameters"]


def test_history_extrema_use_past_knots_and_current_interpolation_only():
    a = np.c_[np.arange(0,1801,60),np.full(31,28.),np.full(31,.02)]
    a[1,1:]=[50,.04]
    a[2,1:]=[20,.01]
    a[10,1:]=[100,.1]  # Future maximum must not leak into early bounds.
    env = Environment(a)
    assert env.history_extrema(30)==pytest.approx((28,39,.02,.03))
    assert env.history_extrema(90)==pytest.approx((28,50,.02,.04))
    assert env.history_extrema(120)==pytest.approx((20,50,.01,.04))
    vector = env.history_extrema([0,30,90,120])
    for i,t in enumerate((0,30,90,120)):
        assert [v[i] for v in vector]==pytest.approx(env.history_extrema(t))
    for t in (-1,1800.1,np.nan):
        with pytest.raises(ValueError):
            env.history_extrema(t)


def test_cooling_environment_allows_material_above_instantaneous_temperature():
    a = np.c_[np.arange(0,1801,60),np.full(31,28.),np.full(31,2.55)]
    a[1,1]=55.
    env = Environment(a)
    grid = Grid(40)
    sol = integrate(RadialModel(grid,P,env),CFG["solver"],breaks=[0,60,120,180,240],
                    output_times=[0,60,120,180,240],check_envelope=True)
    assert sol.temperature_C[2,-1] > env(120)[0]+.1
    assert sol.temperature_C.max() < 55
    assert sol.temperature_C.min() >= 28-1e-9
    assert np.max(abs(sol.moisture-2.55)) < 1e-11


def test_boundary_audit_uses_modified_diffusivity():
    grid = Grid(80)
    p = {**P,"D_prefactor":1.2*P["D_prefactor"]}
    # A quadratic has an exact second-order backward derivative at R.
    Cs=1.5
    D=p["D_prefactor"]*np.exp(-p["D_exponent"]/Cs)
    Ce=Cs+2*D/(p["hm"]*grid.R)
    C=Cs-1+(grid.r/grid.R)**2
    sol = SimpleNamespace(times=np.array([1.,60,100,1800]),
                          moisture=np.tile(C,(4,1)),temperature_C=np.full((4,81),28.))
    check = boundary_check(sol,grid,p,lambda t:(np.full_like(t,28.),np.full_like(t,Ce)))
    assert check["C"]["early"] < 1e-11
    wrong = boundary_check(sol,grid,P,lambda t:(np.full_like(t,28.),np.full_like(t,Ce)))
    assert wrong["C"]["early"] > .01


def test_oat_changes_exactly_one_parameter_and_preserves_original():
    cases = scenarios(CFG,read_config("configs/q1_sensitivity.json"))
    assert len(cases)==13
    assert cases[0]["parameters"]==P
    for case in cases[1:]:
        changed = [k for k in P if case["parameters"][k]!=P[k]]
        assert changed==[case["parameter"]]
        assert case["parameters"][changed[0]]==pytest.approx(P[changed[0]]*(1+case["relative_change"]))


def test_elasticity_linear_and_quadratic_responses():
    # Q(p)=3p -> unit elasticity. Q(p)=p^2 -> central 2, distinct one-sided slopes.
    linear = elasticity(2.4,3,3.6,.2,1e-5)
    assert [linear[k] for k in ("central","plus","minus")]==pytest.approx([1,1,1])
    quadratic = elasticity(.8**2,1,1.2**2,.2,1e-5)
    assert [quadratic[k] for k in ("central","plus","minus")]==pytest.approx([2,2.2,1.8])
    assert elasticity(-1e-9,0,1e-9,.1,1e-5)["central"] is None
    assert not elasticity(1-1e-8,1,1+1e-8,.1,1e-5)["response_resolved"]


def test_endpoint_metrics_are_temperature_offset_invariant_and_volume_loss():
    data={"time_s":np.array([1800.]),"temperature_C":np.array([[33.,37.]]),
          "moisture":np.array([[2.5,1.5]]),"mean_moisture":np.array([2.3])}
    original = endpoints(data,P)
    shifted = endpoints({**data,"temperature_C":data["temperature_C"]+273.15},{**P,"T0":P["T0"]+273.15})
    assert original==pytest.approx(shifted)
    assert original["mean_loss"]==pytest.approx(.25)


def test_comparison_covers_early_surface_and_all_seconds():
    shape=(1801,21)
    a={"time_s":np.arange(1801.),"radius_m":np.linspace(0,.02,21),
       "temperature_C":np.zeros(shape),"moisture":np.ones(shape),
       "mean_temperature_C":np.zeros(1801),"mean_moisture":np.ones(1801)}
    b={k:v.copy() for k,v in a.items()}
    b["moisture"][1,-1]+=.123
    b["temperature_C"][117,7]+=.24
    report=compare(a,b)
    assert report["C"]["time_s"]==1
    assert report["C"]["early_surface_max"]==pytest.approx(.123)
    assert report["T"]["time_s"]==117
    assert report["T"]["radius_cm"]==pytest.approx(.7)


def test_sensitivity_report_rejects_incomplete_or_modified_verification(tmp_path):
    write_json(tmp_path/"manifest.json",{"status":"running"})
    with pytest.raises(ValueError,match="Unverified"):
        verified_runs(tmp_path)
    write_json(tmp_path/"verification.json",{"status":"numerically_verified"})
    write_json(tmp_path/"manifest.json",{"status":"numerically_verified","verification_sha256":"incorrect"})
    with pytest.raises(ValueError,match="stale"):
        verified_runs(tmp_path)
