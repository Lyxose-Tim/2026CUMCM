import numpy as np
import pytest

from q1.fvm import Grid
from q2.model import CoupledRadialModel, properties, q1_compatible_parameters


PARAMETERS = {
    "L": 0.25, "R": 0.02, "T0": 28.0, "C0": 2.55, "h": 25.0, "hm": 8e-7,
    "rho_intercept": 650.0, "rho_slope": 128.0,
    "cp_intercept": 1450.0, "cp_scale": 2736.0,
    "k_intercept": 0.21, "k_scale": 0.38,
    "D_prefactor": 2.4e-3, "D_moisture_exponent": 0.45,
    "D_temperature_exponent_K": 3850.0,
}


class ConstantEnvironment:
    def __init__(self, T=28.0, C=2.55):
        self.value = (T, C)

    def __call__(self, t):
        query = np.asarray(t)
        return np.full_like(query, self.value[0], dtype=float), np.full_like(query, self.value[1], dtype=float)

    def history_extrema(self, t):
        return (*self.value[:1], *self.value[:1], *self.value[1:], *self.value[1:])


def test_appendix3_properties_and_derivatives():
    T = np.array([28.0, 50.0])
    C = np.array([2.55, 0.15])
    rho, cp, k, D, derivative = properties(T, C, PARAMETERS)
    assert rho[0] == pytest.approx(650 + 128 * 2.55)
    assert cp[0] == pytest.approx(1450 + 2736 * 2.55 / 3.55)
    assert k[1] == pytest.approx(0.21 + 0.38 * 0.15 / 1.15)
    expected_D = 2.4e-3 * np.exp(-0.45 / C) * np.exp(-3850 / (T + 273.15))
    assert np.allclose(D, expected_D)
    step = 1e-6
    assert np.allclose(
        derivative["D_T"],
        (properties(T + step, C, PARAMETERS)[3] - properties(T - step, C, PARAMETERS)[3]) / (2 * step),
        rtol=2e-7,
    )
    assert np.allclose(
        derivative["D_C"],
        (properties(T, C + step, PARAMETERS)[3] - properties(T, C - step, PARAMETERS)[3]) / (2 * step),
        rtol=2e-7,
    )
    plus = properties(T, C + step, PARAMETERS)
    minus = properties(T, C - step, PARAMETERS)
    assert np.allclose(derivative["rho_C"], (plus[0] - minus[0]) / (2 * step), rtol=2e-7)
    assert np.allclose(derivative["cp_C"], (plus[1] - minus[1]) / (2 * step), rtol=2e-7)
    assert np.allclose(derivative["k_C"], (plus[2] - minus[2]) / (2 * step), rtol=2e-7)


def test_full_sparse_jacobian_directional_difference():
    grid = Grid(12)
    env = ConstantEnvironment(46.0, 0.04)
    model = CoupledRadialModel(grid, PARAMETERS, env)
    radius = grid.r / grid.R
    state = np.r_[28 + 8 * radius**2, 2.55 - 0.4 * radius**2]
    direction = np.random.default_rng(20260911).normal(size=state.size)
    direction /= np.linalg.norm(direction)
    step = 2e-6
    finite = (model.rhs(123.0, state + step * direction) - model.rhs(123.0, state - step * direction)) / (2 * step)
    analytic = model.jac(123.0, state) @ direction
    assert np.max(np.abs(finite - analytic)) < 3e-7


def test_equilibrium_rhs_is_zero():
    grid = Grid(20)
    model = CoupledRadialModel(grid, PARAMETERS, ConstantEnvironment())
    state = np.r_[np.full(21, 28.0), np.full(21, 2.55)]
    assert np.max(np.abs(model.rhs(0.0, state))) < 1e-14


def test_shared_flux_conserves_each_control_volume_sum_and_center_is_symmetric():
    grid = Grid(20)
    model = CoupledRadialModel(grid, PARAMETERS, ConstantEnvironment(50.0, 0.05))
    radius = grid.r / grid.R
    state = np.r_[28.0 + radius, 2.55 - 0.2 * radius]
    rhs = model.rhs(30.0, state)
    qT, qC = model.fluxes(30.0, state)
    storage = properties(state[:21], state[21:], PARAMETERS)[0] * properties(
        state[:21], state[21:], PARAMETERS
    )[1]
    assert qT[0] == 0.0 and qC[0] == 0.0
    heat_cell_residual = grid.volume * storage * rhs[:21] + np.diff(grid.area * qT)
    moisture_cell_residual = grid.volume * rhs[21:] + np.diff(grid.area * qC)
    assert np.max(np.abs(heat_cell_residual)) < 1e-14
    assert np.max(np.abs(moisture_cell_residual)) < 1e-14
    assert np.dot(grid.volume * storage, rhs[:21]) == pytest.approx(-grid.area[-1] * qT[-1])
    assert np.dot(grid.volume, rhs[21:]) == pytest.approx(-grid.area[-1] * qC[-1])
    assert qT[-1] < 0.0
    assert qC[-1] > 0.0


def test_q1_compatible_mode_removes_temperature_diffusivity_dependence():
    p = q1_compatible_parameters(PARAMETERS)
    _, _, _, D1, derivatives1 = properties(np.array([20.0]), np.array([1.5]), p)
    _, _, _, D2, derivatives2 = properties(np.array([80.0]), np.array([1.5]), p)
    assert D1 == pytest.approx(D2)
    assert derivatives1["D_T"][0] == 0
    assert derivatives2["D_T"][0] == 0
