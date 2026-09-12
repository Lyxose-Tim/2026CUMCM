import numpy as np
import pytest

from q1.fvm import Grid
from q2.inputs import LongEnvironment
from q2.model import CoupledRadialModel
from q4.inputs import RadiusHistory
from q4.model import ShrinkingRadialModel, material_grid
from q4.solver import selected_physical


PARAMETERS = {
    "L": 0.25, "R": 0.02, "T0": 28.0, "C0": 2.55, "h": 25.0, "hm": 8e-7,
    "rho_intercept": 650.0, "rho_slope": 128.0, "cp_intercept": 1450.0,
    "cp_scale": 2736.0, "k_intercept": 0.21, "k_scale": 0.38,
    "D_prefactor": 0.0024, "D_moisture_exponent": 0.45,
    "D_temperature_exponent_K": 3850.0,
}


def environment():
    rows = np.c_[np.arange(241) * 60.0, np.full(241, 50.0), np.full(241, 0.05)]
    return LongEnvironment(rows, 14400.0)


def test_fixed_radius_q4_matches_q2_rhs():
    n = 12
    physical = Grid(n, PARAMETERS["R"], PARAMETERS["L"])
    material = material_grid(n, PARAMETERS["L"])
    env = environment()
    q2 = CoupledRadialModel(physical, PARAMETERS, env)
    q4 = ShrinkingRadialModel(material, PARAMETERS, env, RadiusHistory(np.array([[0.0, PARAMETERS["R"]], [14400.0, PARAMETERS["R"]]])))
    T = np.linspace(28.0, 49.0, n + 1)
    C = np.linspace(2.55, 0.5, n + 1)
    y = np.r_[T, C]
    np.testing.assert_allclose(q4.rhs(120.0, y), q2.rhs(120.0, y), rtol=2e-13, atol=1e-13)


def test_selected_physical_masks_outside_radius():
    grid = material_grid(4, 0.25)
    values = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    fixed = np.array([0.0, 0.005, 0.01, 0.015, 0.02])
    selected = selected_physical(grid, values, 0.012, fixed)
    assert selected[0] == pytest.approx(10.0)
    assert np.isfinite(selected[1])
    assert np.isnan(selected[3])
    assert np.isnan(selected[4])
    assert selected[-1] == pytest.approx(14.0)


def test_q4_jacobian_directional_derivative():
    n = 8
    grid = material_grid(n, 0.25)
    env = environment()
    radius = RadiusHistory(np.array([[0.0, 0.02], [14400.0, 0.018]]))
    model = ShrinkingRadialModel(grid, PARAMETERS, env, radius)
    y = np.r_[np.linspace(30.0, 45.0, n + 1), np.linspace(2.0, 0.7, n + 1)]
    direction = np.r_[np.linspace(-0.3, 0.2, n + 1), np.linspace(0.1, -0.05, n + 1)]
    eps = 1e-6
    finite = (model.rhs(500.0, y + eps * direction) - model.rhs(500.0, y - eps * direction)) / (2 * eps)
    analytic = model.jac(500.0, y) @ direction
    np.testing.assert_allclose(analytic, finite, rtol=2e-5, atol=2e-8)

