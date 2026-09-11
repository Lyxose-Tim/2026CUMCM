"""Portable, chunked float64 archive with hashes; no pickled solver objects."""
import json
from pathlib import Path

import numpy as np

from .inputs import sha256


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def save_archive(directory,sol,grid,metadata):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    chunks = []
    # Keep every file below GitHub's 100 MB per-file limit even at the allowed cap.
    for start in range(0,len(sol.times),300):
        end = min(start+300,len(sol.times))
        path = directory/f"field_{start:04d}_{end-1:04d}.npz"
        np.savez_compressed(path,time_s=sol.times[start:end],temperature_C=sol.temperature_C[start:end],moisture=sol.moisture[start:end])
        chunks.append({"file":path.name,"sha256":sha256(path),"first_time_s":float(sol.times[start]),"last_time_s":float(sol.times[end-1]),"bytes":path.stat().st_size})
    geometry = directory/"geometry.npz"
    np.savez_compressed(geometry,radius_m=grid.r,volume_m3=grid.volume,face_area_m2=grid.area,output_indices=grid.output_indices)
    record = {**metadata,"N":grid.N,"axis_order":["time_s","radius_m"],"dtype":"float64","chunks":chunks,"geometry_sha256":sha256(geometry)}
    write_json(directory/"manifest.json",record)
    return record


def load_archive(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    if sha256(directory/"geometry.npz") != manifest["geometry_sha256"]:
        raise ValueError("Archive geometry hash mismatch")
    with np.load(directory/"geometry.npz") as f:
        geometry = {k:f[k] for k in f.files}
    parts = {"time_s":[],"temperature_C":[],"moisture":[]}
    for item in manifest["chunks"]:
        path = directory/item["file"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Archive hash mismatch: {path.name}")
        with np.load(path) as f:
            for key in parts:
                parts[key].append(f[key])
    return {k:np.concatenate(v) for k,v in parts.items()},geometry,manifest
