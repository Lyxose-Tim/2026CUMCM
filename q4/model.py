"""Variable-property radial drying model on the shrinking material coordinate."""
import numpy as np
from scipy.sparse import bmat, diags

from q1.fvm import Grid
from q2.model import divergence_jacobian, harmonic, properties


class ShrinkingRadialModel:
    def __init__(self, grid, parameters, environment, radius):
        if abs(grid.R - 1.0) > 1e-15:
            raise ValueError("Q4 grid must be built on xi in [0, 1]")
        self.grid = grid
        self.p = parameters
        self.environment = environment
        self.radius = radius

    def coefficients(self, T, C):
        rho, cp, k, D, derivatives = properties(T, C, self.p)
        zero = np.zeros_like(C)
        kface = harmonic(k, derivatives["k_C"], zero)
        Dface = harmonic(D, derivatives["D_C"], derivatives["D_T"])
        storage = rho * cp
        storage_C = derivatives["rho_C"] * cp + rho * derivatives["cp_C"]
        return storage, storage_C, kface, Dface

    def scale(self, t):
        R = float(self.radius(t))
        if R <= 0:
            raise ValueError("Nonpositive material radius")
        return R, 1.0 / R**2

    def fluxes(self, t, y):
        n = self.grid.N + 1
        T, C = y[:n], y[n:]
        environment_T, environment_C = self.environment(t)
        storage, _, kface, Dface = self.coefficients(T, C)
        R, _ = self.scale(t)
        qT = self.grid.flux(T, kface[0], self.p["h"] * R, environment_T)
        qC = self.grid.flux(C, Dface[0], self.p["hm"] * R, environment_C)
        return qT, qC, storage

    def rhs(self, t, y):
        n = self.grid.N + 1
        qT, qC, storage = self.fluxes(t, y)
        _, scale = self.scale(t)
        return np.r_[scale * self.grid.divergence(qT, storage), scale * self.grid.divergence(qC)]

    def jac(self, t, y):
        grid = self.grid
        n = grid.N + 1
        T, C = y[:n], y[n:]
        storage, storage_C, kface, Dface = self.coefficients(T, C)
        dT = np.diff(T)
        dC = np.diff(C)
        R, scale = self.scale(t)

        heat_T = divergence_jacobian(
            grid, kface[0] / grid.dr, -kface[0] / grid.dr, self.p["h"] * R
        )
        heat_C = divergence_jacobian(
            grid, -kface[1] * dT / grid.dr, -kface[2] * dT / grid.dr
        )
        raw_heat = scale * self.grid.divergence(
            self.grid.flux(T, kface[0], self.p["h"] * R, self.environment(t)[0])
        )
        inverse_storage = diags(scale / storage, format="csc")
        heat_T = inverse_storage @ heat_T
        heat_C = inverse_storage @ heat_C - diags(raw_heat * storage_C / storage**2, format="csc")

        moisture_C = divergence_jacobian(
            grid,
            (Dface[0] - Dface[1] * dC) / grid.dr,
            -(Dface[0] + Dface[2] * dC) / grid.dr,
            self.p["hm"] * R,
        )
        moisture_T = divergence_jacobian(
            grid, -Dface[3] * dC / grid.dr, -Dface[4] * dC / grid.dr
        )
        moisture_C = scale * moisture_C
        moisture_T = scale * moisture_T
        return bmat([[heat_T, heat_C], [moisture_T, moisture_C]], format="csc")


def material_grid(N, length_m):
    return Grid(N, 1.0, length_m)


def q4_parameters(q2_parameters, q4_config, appendix="appendix4"):
    parameters = dict(q2_parameters)
    if appendix == "appendix4":
        parameters.update(q4_config["appendix4_parameters"])
    elif appendix != "appendix3":
        raise ValueError("Unknown Q4 property set")
    return parameters

