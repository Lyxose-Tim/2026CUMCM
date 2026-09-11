import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import j0

from q1.fvm import Grid, RadialModel
from q1.inputs import Environment, read_config
from q1.reference import bessel_series
from q1.solver import integrate

CONFIG = read_config()
P = CONFIG["parameters"]
SETTINGS = CONFIG["solver"]


def test_equilibrium_preserved():
    g = Grid(40)
    m = RadialModel(g,P,lambda t: (28.,2.55))
    sol = integrate(m, SETTINGS, breaks=[0,60,120],output_times=[0,1,60,61,120])
    assert abs(sol.temperature_C-28).max() <= 1e-9
    assert abs(sol.moisture-2.55).max() <= 1e-11


def test_closed_moisture_conserves_mass_and_dissipates_variance():
    g = Grid(80)
    m = RadialModel(g,{**P,"hm":0},lambda t: (28.,0.02))
    y = np.r_[np.full(g.N+1,28.),1+0.1*np.cos(np.pi*g.r/g.R)]
    sol = integrate(m,SETTINGS,initial=y,breaks=[0,600],output_times=np.arange(0,601,10))
    mean = sol.moisture @ g.volume/g.volume.sum()
    var = ((sol.moisture-mean[:,None])**2) @ g.volume/g.volume.sum()
    assert max(abs(mean/mean[0]-1)) <= 1e-10
    assert max(np.diff(var)) <= 1e-14


def test_bessel_projection_coefficients():
    _, info = bessel_series(np.linspace(0,1,21),np.array([1,60]),P["k"]/(P["rho"]*P["cp"]*P["R"]**2),P["h"]*P["R"]/P["k"])
    for mu,A in zip(info["first_roots"],info["first_coefficients"]):
        projection = quad(lambda x:x*j0(mu*x),0,1)[0]/quad(lambda x:x*j0(mu*x)**2,0,1)[0]
        assert abs(projection-A) < 1e-12


def test_simplified_full_series_before_real_environment():
    g = Grid(5120)
    D0 = P["D_prefactor"]*np.exp(-P["D_exponent"]/P["C0"])
    m = RadialModel(g,P,lambda t: (38.,0.02),constant_D=D0)
    times = np.array([1,2,5,10,30,60,100,300,600,1800],float)
    sol = integrate(m,SETTINGS,breaks=[0,1800],output_times=times)
    T,C = sol.output(g)
    for actual,ue,u0,a,b,beta,tol in [(T,38.,28.,P["k"],P["rho"]*P["cp"],P["h"],0.0008),(C,0.02,2.55,D0,1,P["hm"],0.000008)]:
        ref,_ = bessel_series(g.r[g.output_indices]/g.R,times,a/(b*g.R**2),beta*g.R/a)
        error = max(abs(actual-(ue+(u0-ue)*ref)).ravel())
        # Fine-grid startup benchmark uses the approved spatial budgets.
        assert error < tol


def test_environment_interpolation_and_extrapolation_rejection():
    times = np.arange(0,1801,60)
    a = np.c_[times,28+times/180,0.02+times/1e5]
    env = Environment(a)
    assert np.allclose(env(times)[0],a[:,1])
    assert env(30)[0] == pytest.approx((a[0,1]+a[1,1])/2)
    for t in [-1e-12,1800.000001,np.nan]:
        with pytest.raises(ValueError):
            env(t)
