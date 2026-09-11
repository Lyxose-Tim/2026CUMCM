import json
from pathlib import Path

import numpy as np
import pytest

from q1.fvm import Grid, RadialModel, diffusivity, harmonic

PARAMETERS = json.loads(Path("configs/q1.json").read_text())["parameters"]


@pytest.mark.parametrize("N", [20, 40, 160, 640])
def test_first_contract_shared_flux_conservation(N):
    g = Grid(N)
    rng = np.random.default_rng(129)
    u = rng.uniform(0.5, 2.5, N + 1)
    D, Dp = diffusivity(u)
    H, _, _ = harmonic(D, Dp)
    q = g.flux(u, H, 8e-7, 0.02)
    rate = g.divergence(q)
    residual = np.sum(g.volume * rate) + g.area[-1] * q[-1]
    scale = np.sum(np.abs(g.volume * rate)) + abs(g.area[-1] * q[-1])
    assert abs(residual) / scale <= 1e-12
    assert abs(g.volume.sum() / (np.pi * g.L * g.R**2) - 1) <= 1e-13


@pytest.mark.parametrize("N", [20, 40, 160, 640])
@pytest.mark.parametrize("a,b", [(0.36, 820 * 2600), (4.937655e-9, 1)])
def test_quadratic_cylinder_operator(N, a, b):
    g = Grid(N)
    u = (g.r / g.R)**2
    q = g.flux(u, a, boundary_flux=-2 * a / g.R)
    expected = 4 * a / (b * g.R**2)
    assert np.max(np.abs(g.divergence(q, b) / expected - 1)) <= 1e-10
    assert np.isclose(g.divergence(q, b)[0], 4 * a * (u[1] - u[0]) / (b * g.dr**2), rtol=1e-14)


def test_sparse_jacobian_against_independent_direction_difference():
    g = Grid(80)
    model = RadialModel(g, PARAMETERS, lambda t: (35.0, 0.025))
    y = np.r_[28 + 4 * (g.r/g.R)**2, 1 + (g.r/g.R)**2]
    rng = np.random.default_rng(59)
    v = rng.normal(size=y.size)
    Jv = model.jac(20, y) @ v
    n = g.N + 1
    errors = []
    for eps in [1e-3, 1e-4, 1e-5, 1e-6]:
        fd = (model.rhs(20, y + eps*v) - model.rhs(20, y - eps*v)) / (2*eps)
        errors.append([np.linalg.norm((fd-Jv)[sl], np.inf)/np.linalg.norm(Jv[sl], np.inf) for sl in [slice(0,n),slice(n,None)]])
    assert np.max(np.min(errors, axis=0)) < 1e-6
    J = model.jac(20, y)
    assert J[:n,n:].nnz == J[n:,:n].nnz == 0


def test_variable_D_manufactured_operator_orders():
    errors = []
    for N in [40, 80, 160]:
        g = Grid(N)
        C = 1 + (g.r/g.R)**2
        D, Dp = diffusivity(C)
        H, _, _ = harmonic(D, Dp)
        rate = g.divergence(g.flux(C, H, boundary_flux=-2*D[-1]/g.R))
        exact = 4*D/g.R**2 + 4*g.r**2*Dp/g.R**4
        err = abs(rate-exact)/(7e-9/g.R**2)
        errors.append([max(err[:-1]), err[-1], np.dot(g.volume,err)/g.volume.sum()])
    order = np.log2(np.asarray(errors[:-1])/np.asarray(errors[1:]))
    assert np.all((order[:,[0,2]] > 1.8) & (order[:,[0,2]] < 2.2))
    assert np.all((order[:,1] > 0.8) & (order[:,1] < 1.2))


def test_invalid_moisture_not_clipped():
    for value in [0, -1, np.nan]:
        with pytest.raises(ValueError):
            diffusivity(np.array([1., value]))
