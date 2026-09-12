"""Prepare Q2 tables and chunked Artifact Tool payload from verified results."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .archive import load_archive, write_json
from .inputs import sha256
from .provenance import delivery_snapshot, verify_sources


TABLE_TIMES = np.arange(1800, 10801, 1800, dtype=int)
TABLE_RADIUS_INDICES = np.array([0, 5, 10, 15, 20])


def rounded_array(values):
    values = np.asarray(values, dtype=float)
    if np.any(values < 0):
        raise ValueError("Formal Q2 outputs are expected to be nonnegative")
    return np.floor(values * 10000.0 + 0.5) / 10000.0


def verified_source(directory="results/q2"):
    directory = Path(directory)
    if (directory / "failure.json").exists():
        raise ValueError("A later failed Q2 run blocks formal export")
    verification_path = directory / "verification.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if not verification["numerical_passed"]:
        raise ValueError("Formal Q2 export requires all numerical gates")
    data, geometry, manifest = load_archive(directory / "archive")
    verify_sources(manifest)
    if manifest["status"] != "numerically_verified" or manifest["verification_sha256"] != sha256(verification_path):
        raise ValueError("Q2 archive validation provenance mismatch")
    if not np.array_equal(data["time_s"], np.arange(259201, dtype=float)):
        raise ValueError("Expected exact Q2 time axis 0:1:259200")
    if data["temperature_C"].shape != (259201, 21) or data["moisture"].shape != (259201, 21):
        raise ValueError("Unexpected Q2 formal output shape")
    return data, geometry, manifest, verification


def prepare(directory="results/q2", payload_path=".scratch/q2_workbook/payload.json", chunk_rows=21600):
    directory = Path(directory)
    data, geometry, manifest, verification = verified_source(directory)
    payload_path = Path(payload_path)
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    tables = {}
    chunks = []
    for sheet_name, key, values in (
        ("温度", "temperature", data["temperature_C"]),
        ("水分浓度", "moisture", data["moisture"]),
    ):
        table = values[TABLE_TIMES][:, TABLE_RADIUS_INDICES]
        rows = [[int(t), *[f"{value:.4f}" for value in row]] for t, row in zip(TABLE_TIMES, rounded_array(table))]
        tables[key] = rows
        with (directory / f"table_{key}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time_s", "r_0_cm", "r_0.5_cm", "r_1_cm", "r_1.5_cm", "r_2_cm"])
            writer.writerows(rows)
        for start in range(1, len(data["time_s"]), chunk_rows):
            end = min(start + chunk_rows, len(data["time_s"]))
            matrix = np.c_[data["time_s"][start:end], rounded_array(values[start:end])].tolist()
            path = payload_path.parent / f"{key}_{start:06d}_{end - 1:06d}.json"
            path.write_text(json.dumps(matrix, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            chunks.append({
                "sheet": sheet_name, "first_excel_row": start + 1, "rows": end - start,
                "file": str(path), "sha256": sha256(path),
            })
    write_json(directory / "tables.json", tables)
    payload = {
        "verification_file": str(directory / "verification.json"),
        "verification_sha256": sha256(directory / "verification.json"),
        "archive_manifest_file": str(directory / "archive" / "manifest.json"),
        "archive_manifest_sha256": sha256(directory / "archive" / "manifest.json"),
        "template_A1": manifest["inputs"]["template_A1"],
        "delivery_source": delivery_snapshot(),
        "chunks": chunks,
    }
    write_json(payload_path, payload)
    return data, geometry, manifest, verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="results/q2")
    parser.add_argument("--payload", default=".scratch/q2_workbook/payload.json")
    parser.add_argument("--node", default="node")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    prepare(args.directory, args.payload)
    if not args.prepare_only:
        subprocess.run([args.node, "scripts/build_result2.mjs", "--payload", args.payload, "--preview-only"], check=True)
        subprocess.run([sys.executable, "scripts/build_result2_stream.py", "--payload", args.payload], check=True)
        from .check_export import check
        check(args.directory, "results/result2.xlsx")
