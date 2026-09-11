"""Node control volumes. A single outward face flux is shared by its neighbours."""
from dataclasses import dataclass

import numpy as np
from scipy.sparse import diags, block_diag


@dataclass(frozen=True)
class Grid:
    N: int
    R: float = 0.02
    L: float = 0.25

    def __post_init__(self):
        if not isinstance(self.N, int) or self.N < 2 or self.R <= 0 or self.L <= 0:
            raise ValueError("N >= 2, R > 0, L > 0 required")
        r = np.linspace(0.0, self.R, self.N + 1)
        faces = np.r_[0.0, (r[:-1] + r[1:]) / 2.0, self.R]
        object.__setattr__(self, "r", r)
        object.__setattr__(self, "dr", self.R / self.N)
        object.__setattr__(self, "faces", faces)
        object.__setattr__(self, "area", 2 * np.pi * self.L * faces)
        # Difference of squares factored to avoid cancellation in thin outer cells.
        object.__setattr__(self, "volume", np.pi * self.L * np.diff(faces) * (faces[1:] + faces[:-1]))

    @property
    def output_indices(self):
        if self.N % 20:
            raise ValueError("Formal output requires N to be a multiple of 20")
        return np.arange(21) * (self.N // 20)

    def flux(self, u, a_face, beta=0.0, exterior=0.0, boundary_flux=None):
        """q[0]=0; q[-1] is outward Robin or an explicit verification flux."""
        u = np.asarray(u, dtype=float)
        if u.shape != (self.N + 1,) or not np.all(np.isfinite(u)):
            raise ValueError("Invalid nodal state")
        q = np.empty(self.N + 2)
        q[0] = 0.0
        q[1:-1] = -np.asarray(a_face) * np.diff(u) / self.dr
        q[-1] = beta * (u[-1] - exterior) if boundary_flux is None else boundary_flux
        return q

    def divergence(self, q, b=1.0):
        if np.shape(q) != (self.N + 2,) or np.any(np.asarray(b) <= 0):
            raise ValueError("Invalid face flux or storage coefficient")
        return -np.diff(self.area * q) / (b * self.volume)

    def jacobian(self, dq_left, dq_right, beta, b):
        """dq_left/right = derivative of each internal outward flux wrt endpoints."""
        face_A = self.area[1:-1]
        storage = b * self.volume
        diagonal = np.zeros(self.N + 1)
        diagonal[:-1] -= face_A * dq_left / storage[:-1]
        diagonal[1:] += face_A * dq_right / storage[1:]
        diagonal[-1] -= self.area[-1] * beta / storage[-1]
        lower = face_A * dq_left / storage[1:]
        upper = -face_A * dq_right / storage[:-1]
        return diags([lower, diagonal, upper], [-1, 0, 1], format="csc")


class NonpositiveMoisture(ValueError):
    def __init__(self, C):
        self.node = int(np.argmin(C))
        self.value = float(C[self.node])
        super().__init__(f"Nonpositive trial moisture at node {self.node}: {self.value}")


def diffusivity(C, prefactor=7e-9, exponent=0.89):
    C = np.asarray(C, dtype=float)
    if not np.all(np.isfinite(C)):
        raise ValueError("Nonfinite moisture")
    if np.any(C <= 0):
        raise NonpositiveMoisture(C)
    D = prefactor * np.exp(-exponent / C)
    if np.any(D <= 0):
        raise FloatingPointError("Diffusivity underflow; no substitute property is allowed")
    return D, exponent * D / C**2


def harmonic(D, Dprime):
    left, right = D[:-1], D[1:]
    denom = left + right
    H = 2 * left * right / denom
    dleft = 2 * (right / denom)**2 * Dprime[:-1]
    dright = 2 * (left / denom)**2 * Dprime[1:]
    return H, dleft, dright


class RadialModel:
    def __init__(self, grid, parameters, environment, constant_D=None):
        self.grid, self.p, self.environment = grid, parameters, environment
        self.constant_D = constant_D
        k, b, h = parameters["k"], parameters["rho"] * parameters["cp"], parameters["h"]
        self.heat_jac = grid.jacobian(np.full(grid.N, k / grid.dr), np.full(grid.N, -k / grid.dr), h, b)

    def moisture_faces(self, C):
        D, Dp = diffusivity(C, self.p["D_prefactor"], self.p["D_exponent"])
        if self.constant_D is not None:
            D = np.full_like(C, self.constant_D)
            Dp = np.zeros_like(C)
        return harmonic(D, Dp)

    def fluxes(self, t, y):
        n, g, p = self.grid.N + 1, self.grid, self.p
        T, C = y[:n], y[n:]
        Te, Ce = self.environment(t)
        H, _, _ = self.moisture_faces(C)
        return g.flux(T, p["k"], p["h"], Te), g.flux(C, H, p["hm"], Ce)

    def rhs(self, t, y):
        qT, qC = self.fluxes(t, y)
        return np.r_[self.grid.divergence(qT, self.p["rho"] * self.p["cp"]), self.grid.divergence(qC)]

    def jac(self, t, y):
        g = self.grid
        C = y[g.N + 1:]
        H, HL, HR = self.moisture_faces(C)
        delta = np.diff(C)
        left, right = (H - HL * delta) / g.dr, -(H + HR * delta) / g.dr
        water_jac = g.jacobian(left, right, self.p["hm"], 1.0)
        return block_diag((self.heat_jac, water_jac), format="csc")
