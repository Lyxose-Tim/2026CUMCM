"""Chunked archive for the formal 21-radius Q2 output."""
import json
from pathlib import Path

import numpy as np

from .inputs import sha256


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_archive(directory, solution, grid, metadata, chunk_rows=21600):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    chunks = []
    for start in range(0, len(solution.times), chunk_rows):
        end = min(start + chunk_rows, len(solution.times))
        path = directory / f"series_{start:06d}_{end - 1:06d}.npz"
        np.savez_compressed(
            path,
            time_s=solution.times[start:end],
            temperature_C=solution.temperature_C[start:end],
            moisture=solution.moisture[start:end],
        )
        chunks.append({
            "file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size,
            "first_time_s": float(solution.times[start]), "last_time_s": float(solution.times[end - 1]),
        })
    geometry = directory / "geometry.npz"
    np.savez_compressed(
        geometry,
        internal_radius_m=grid.r,
        volume_m3=grid.volume,
        face_area_m2=grid.area,
        output_indices=grid.output_indices,
        output_radius_cm=np.arange(21, dtype=float) / 10,
        final_temperature_C=solution.final_state[:grid.N + 1],
        final_moisture=solution.final_state[grid.N + 1:],
    )
    manifest = {
        **metadata,
        "N": grid.N,
        "axis_order": ["time_s", "radius_cm"],
        "dtype": "float64",
        "formal_radius_cm": [j / 10 for j in range(21)],
        "chunks": chunks,
        "geometry_sha256": sha256(geometry),
    }
    write_json(directory / "manifest.json", manifest)
    return manifest


def load_archive(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    geometry_path = directory / "geometry.npz"
    if sha256(geometry_path) != manifest["geometry_sha256"]:
        raise ValueError("Q2 archive geometry hash mismatch")
    with np.load(geometry_path) as source:
        geometry = {key: source[key] for key in source.files}
    pieces = {"time_s": [], "temperature_C": [], "moisture": []}
    for item in manifest["chunks"]:
        path = directory / item["file"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Q2 archive hash mismatch: {path.name}")
        with np.load(path) as source:
            for key in pieces:
                pieces[key].append(source[key])
    return {key: np.concatenate(value) for key, value in pieces.items()}, geometry, manifest
