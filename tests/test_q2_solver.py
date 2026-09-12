import numpy as np

from scipy.integrate import BDF, Radau

from q1.fvm import Grid
from q2.model import CoupledRadialModel
from q2.solver import evaluate_selected, integrate
from q2.validation import state_checks


PARAMETERS = {
    "L": 0.25, "R": 0.02, "T0": 28.0, "C0": 2.55, "h": 25.0, "hm": 8e-7,
    "rho_intercept": 650.0, "rho_slope": 128.0,
    "cp_intercept": 1450.0, "cp_scale": 2736.0,
    "k_intercept": 0.21, "k_scale": 0.38,
    "D_prefactor": 2.4e-3, "D_moisture_exponent": 0.45,
    "D_temperature_exponent_K": 3850.0,
}


class ConstantEnvironment:
    def __call__(self, t):
        query = np.asarray(t)
        return np.full_like(query, 28.0, dtype=float), np.full_like(query, 2.55, dtype=float)

    def history_extrema(self, t):
        return 28.0, 28.0, 2.55, 2.55


def test_selected_dense_matches_full_scipy_output():
    rhs = lambda t, y: -np.arange(1, 7) * y
    for solver_class in [BDF, Radau]:
        solver = solver_class(rhs, 0.0, np.arange(1, 7, dtype=float), 1.0, rtol=1e-9, atol=1e-12)
        solver.step()
        dense = solver.dense_output()
        query = np.linspace(dense.t_old, dense.t, 5)
        assert np.allclose(evaluate_selected(dense, query, [0, 3, 5]), dense(query)[[0, 3, 5]])


def test_short_equilibrium_integration_preserves_field():
    grid = Grid(20)
    model = CoupledRadialModel(grid, PARAMETERS, ConstantEnvironment())
    settings = {
        "method": "BDF", "rtol": 1e-8, "atol_T": 1e-10, "atol_C": 1e-12,
        "max_step_observed": 10.0, "max_step_extended": 10.0,
    }
    solution = integrate(model, settings, breaks=[0, 120], output_times=np.arange(121))
    assert np.max(np.abs(solution.temperature_C - 28.0)) < 1e-12
    assert np.max(np.abs(solution.moisture - 2.55)) < 1e-12
    assert solution.diagnostics["relative_moisture_balance"] < 1e-13
    checks = state_checks(solution, PARAMETERS, ConstantEnvironment())
    assert checks["surface_heat_robin_max_residual"] == 0.0
    assert checks["surface_moisture_robin_max_residual"] == 0.0
    assert checks["surface_heat_flux_sign_consistent"]
    assert checks["surface_moisture_flux_sign_consistent"]
