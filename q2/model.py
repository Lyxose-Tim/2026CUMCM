"""Conservative variable-property radial operator and sparse Jacobian."""
import numpy as np
from scipy.sparse import bmat, coo_matrix, diags

from q1.fvm import Grid, NonpositiveMoisture


def properties(temperature_C, moisture, parameters):
    T = np.asarray(temperature_C, dtype=float)
    C = np.asarray(moisture, dtype=float)
    if not np.all(np.isfinite(T)) or not np.all(np.isfinite(C)):
        raise ValueError("Nonfinite Q2 state")
    if np.any(C <= 0) or np.any(T <= -273.15):
        raise NonpositiveMoisture(C) if np.any(C <= 0) else ValueError("Nonpositive Kelvin temperature")
    rho = parameters["rho_intercept"] + parameters["rho_slope"] * C
    cp = parameters["cp_intercept"] + parameters["cp_scale"] * C / (C + 1.0)
    k = parameters["k_intercept"] + parameters["k_scale"] * C / (C + 1.0)
    kelvin = T + 273.15
    D = parameters["D_prefactor"] * np.exp(
        -parameters["D_moisture_exponent"] / C
        -parameters["D_temperature_exponent_K"] / kelvin
    )
    derivatives = {
        "rho_C": np.full_like(C, parameters["rho_slope"]),
        "cp_C": parameters["cp_scale"] / (C + 1.0) ** 2,
        "k_C": parameters["k_scale"] / (C + 1.0) ** 2,
        "D_C": D * parameters["D_moisture_exponent"] / C**2,
        "D_T": D * parameters["D_temperature_exponent_K"] / kelvin**2,
    }
    return rho, cp, k, D, derivatives


def harmonic(values, derivative_C, derivative_T):
    left, right = values[:-1], values[1:]
    denominator = left + right
    face = 2.0 * left * right / denominator
    left_factor = 2.0 * (right / denominator) ** 2
    right_factor = 2.0 * (left / denominator) ** 2
    return (
        face,
        left_factor * derivative_C[:-1],
        right_factor * derivative_C[1:],
        left_factor * derivative_T[:-1],
        right_factor * derivative_T[1:],
    )


def divergence_jacobian(grid, dq_left, dq_right, boundary_derivative=0.0):
    rows = np.r_[np.arange(grid.N), np.arange(1, grid.N + 1), grid.N]
    cols = np.r_[np.arange(grid.N), np.arange(1, grid.N + 1), grid.N]
    values = np.r_[
        -grid.area[1:-1] * dq_left / grid.volume[:-1],
        grid.area[1:-1] * dq_right / grid.volume[1:],
        -grid.area[-1] * boundary_derivative / grid.volume[-1],
    ]
    # Add the opposite endpoint contribution of each shared face.
    rows = np.r_[rows, np.arange(grid.N), np.arange(1, grid.N + 1)]
    cols = np.r_[cols, np.arange(1, grid.N + 1), np.arange(grid.N)]
    values = np.r_[
        values,
        -grid.area[1:-1] * dq_right / grid.volume[:-1],
        grid.area[1:-1] * dq_left / grid.volume[1:],
    ]
    return coo_matrix((values, (rows, cols)), shape=(grid.N + 1, grid.N + 1)).tocsc()


class CoupledRadialModel:
    def __init__(self, grid, parameters, environment):
        self.grid = grid
        self.p = parameters
        self.environment = environment

    def coefficients(self, T, C):
        rho, cp, k, D, derivatives = properties(T, C, self.p)
        zero = np.zeros_like(C)
        kface = harmonic(k, derivatives["k_C"], zero)
        Dface = harmonic(D, derivatives["D_C"], derivatives["D_T"])
        storage = rho * cp
        storage_C = derivatives["rho_C"] * cp + rho * derivatives["cp_C"]
        return storage, storage_C, kface, Dface

    def fluxes(self, t, y):
        n = self.grid.N + 1
        T, C = y[:n], y[n:]
        environment_T, environment_C = self.environment(t)
        _, _, kface, Dface = self.coefficients(T, C)
        qT = self.grid.flux(T, kface[0], self.p["h"], environment_T)
        qC = self.grid.flux(C, Dface[0], self.p["hm"], environment_C)
        return qT, qC

    def rhs(self, t, y):
        n = self.grid.N + 1
        T, C = y[:n], y[n:]
        storage, _, kface, Dface = self.coefficients(T, C)
        environment_T, environment_C = self.environment(t)
        qT = self.grid.flux(T, kface[0], self.p["h"], environment_T)
        qC = self.grid.flux(C, Dface[0], self.p["hm"], environment_C)
        return np.r_[self.grid.divergence(qT, storage), self.grid.divergence(qC)]

    def jac(self, t, y):
        grid = self.grid
        n = grid.N + 1
        T, C = y[:n], y[n:]
        storage, storage_C, kface, Dface = self.coefficients(T, C)
        dT = np.diff(T)
        dC = np.diff(C)

        heat_T = divergence_jacobian(
            grid, kface[0] / grid.dr, -kface[0] / grid.dr, self.p["h"]
        )
        heat_C = divergence_jacobian(
            grid, -kface[1] * dT / grid.dr, -kface[2] * dT / grid.dr
        )
        raw_heat = self.grid.divergence(
            self.grid.flux(T, kface[0], self.p["h"], self.environment(t)[0])
        )
        inverse_storage = diags(1.0 / storage, format="csc")
        heat_T = inverse_storage @ heat_T
        heat_C = inverse_storage @ heat_C - diags(raw_heat * storage_C / storage**2, format="csc")

        moisture_C = divergence_jacobian(
            grid,
            (Dface[0] - Dface[1] * dC) / grid.dr,
            -(Dface[0] + Dface[2] * dC) / grid.dr,
            self.p["hm"],
        )
        moisture_T = divergence_jacobian(
            grid, -Dface[3] * dC / grid.dr, -Dface[4] * dC / grid.dr
        )
        return bmat([[heat_T, heat_C], [moisture_T, moisture_C]], format="csc")


def q1_compatible_parameters(parameters):
    return {
        **parameters,
        "rho_intercept": 820.0,
        "rho_slope": 0.0,
        "cp_intercept": 2600.0,
        "cp_scale": 0.0,
        "k_intercept": 0.36,
        "k_scale": 0.0,
        "D_prefactor": 7e-9,
        "D_moisture_exponent": 0.89,
        "D_temperature_exponent_K": 0.0,
    }
