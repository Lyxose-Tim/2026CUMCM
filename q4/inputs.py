"""Problem 4 input binding: environment, radius history, and result template."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

from q2.inputs import read_config, read_inputs as read_q2_inputs, sha256


@dataclass(frozen=True)
class RadiusHistory:
    observations: np.ndarray
    fixed: bool = False

    def __post_init__(self):
        values = np.asarray(self.observations, dtype=float)
        if values.ndim != 2 or values.shape[1] != 2 or not np.all(np.isfinite(values)):
            raise ValueError("Expected finite two-column radius observations")
        if values[0, 0] != 0 or np.any(np.diff(values[:, 0]) <= 0):
            raise ValueError("Radius time axis must start at 0 and be strictly increasing")
        if np.any(values[:, 1] <= 0) or np.any(np.diff(values[:, 1]) > 1e-12):
            raise ValueError("Radius observations must stay positive and nonincreasing")
        object.__setattr__(self, "observations", values.copy())

    def __call__(self, t):
        query = np.asarray(t, dtype=float)
        if np.any(~np.isfinite(query)) or np.any(query < 0) or np.any(query > self.observations[-1, 0]):
            raise ValueError("Radius query outside configured history")
        if self.fixed:
            return np.full_like(query, self.observations[0, 1], dtype=float)
        return np.interp(query, self.observations[:, 0], self.observations[:, 1])

    @property
    def breaks(self):
        return self.observations[:, 0]


def read_radius(path):
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        rows = list(workbook.active.values)
    finally:
        workbook.close()
    numeric = np.asarray([row[:2] for row in rows[1:] if row[0] is not None and row[1] is not None], dtype=float)
    if numeric.shape != (145, 2):
        raise ValueError("Expected 145 radius rows after the header")
    numeric[:, 1] *= 0.01
    return RadiusHistory(numeric)


def read_inputs(data_root, config, mode=None, fixed_radius=False):
    q2_config = read_config(config["q2_config"])
    environment, metadata = read_q2_inputs(data_root, q2_config, mode=mode)
    root = Path(data_root)
    paths = {
        "radius": root / "附件" / "附件2.xlsx",
        "template": root / "附件" / "附件3" / "result4.xlsx",
    }
    hashes = {key: sha256(path) for key, path in paths.items()}
    for key, expected in config["input_sha256"].items():
        if hashes[key] != expected:
            raise ValueError(f"Unreviewed Q4 {key} input hash: {hashes[key]}")
    radius = read_radius(paths["radius"])
    if fixed_radius:
        radius = RadiusHistory(radius.observations, fixed=True)
    template = load_workbook(paths["template"], data_only=True, read_only=True)
    try:
        if template.sheetnames != ["Sheet1"]:
            raise ValueError("Unexpected result4 template sheets")
        template_a1 = template.active["A1"].value
        template_surface = template.active["F1"].value
    finally:
        template.close()
    metadata["q4_radius"] = {
        "sha256": hashes["radius"],
        "source": str(paths["radius"].relative_to(root)),
        "rows": int(len(radius.observations)),
        "initial_radius_m": float(radius.observations[0, 1]),
        "final_radius_m": float(radius.observations[-1, 1]),
        "fixed": fixed_radius,
    }
    metadata["q4_template"] = {
        "sha256": hashes["template"],
        "source": str(paths["template"].relative_to(root)),
        "A1": template_a1,
        "surface_header": template_surface,
    }
    return environment, radius, metadata

