"""One verified numeric source for Table 6 and result4.xlsx."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np

from q2.archive import write_json
from q2.inputs import sha256
from q2.provenance import portable_artifact_sha256
from q3.solver import output_axis
from q4.validation import verified


def rounded(values):
    values = np.asarray(values, dtype=float)
    out = []
    for value in values.ravel():
        if np.isnan(value):
            out.append(np.nan)
        elif not np.isfinite(value):
            raise ValueError("Nonfinite output cannot be rounded")
        else:
            out.append(float(Decimal(str(float(value))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)))
    return np.asarray(out, dtype=float).reshape(values.shape)


def delivery_sources():
    paths = ["q4/export.py", "q4/check_export.py", "scripts/build_result4.mjs"]
    return {p: portable_artifact_sha256(p) for p in paths}


def json_rows(rows):
    result = []
    for row in rows:
        result.append([None if isinstance(value, float) and np.isnan(value) else value for value in row])
    return result


def prepare(data_root, directory="results/q4", payload=".scratch/q4/workbook_payload.json"):
    directory = Path(directory)
    verification, record, fields = verified(directory)
    template = Path(data_root) / "附件" / "附件3" / "result4.xlsx"
    if sha256(template) != record["identity"]["inputs"]["q4_template"]["sha256"]:
        raise ValueError("Changed result4 template")
    end = record["root"]["time_s"]
    t6 = output_axis(end, 21600)
    indices = np.array([np.argmin(abs(fields["time_s"] - t)) for t in t6])
    np.testing.assert_allclose(fields["time_s"][indices], t6, rtol=0, atol=1e-9)
    selected = [0, 5, 10, 15, 20, 21]
    table = np.c_[fields["time_s"][indices] / 3600, fields["moisture"][indices][:, selected]]
    np.savetxt(directory / "table6.csv", table, delimiter=",",
               header="time_h,r0_cm,r0.5_cm,r1_cm,r1.5_cm,r2_cm,surface",
               comments="", fmt="%.17g")
    header = "| 时间 / h | 0 cm | 0.5 cm | 1 cm | 1.5 cm | 2 cm | 表面 |\n|---:|---:|---:|---:|---:|---:|---:|\n"
    lines = []
    for row in rounded(table):
        cells = ["" if np.isnan(value) else f"{value:.4f}" for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    (directory / "table6.md").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    rows = np.c_[fields["time_s"][1:], rounded(fields["moisture"][1:])]
    content = {
        "rows": json_rows(rows.tolist()),
        "headers": [record["identity"]["inputs"]["q4_template"]["A1"]]
                   + record["identity"]["fixed_radius_m"]
                   + [record["identity"]["inputs"]["q4_template"]["surface_header"]],
        "template": str(template.resolve()),
        "template_sha256": sha256(template),
        "output": "results/result4.xlsx",
        "verification_file": str((directory / "verification.json").resolve()),
        "verification_sha256": sha256(directory / "verification.json"),
        "run_file": str((directory / "runs" / verification["formal_case"] / "run.json").resolve()),
        "run_sha256": sha256(directory / "runs" / verification["formal_case"] / "run.json"),
        "sources": delivery_sources(),
    }
    write_json(payload, content)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--directory", default="results/q4")
    parser.add_argument("--payload", default=".scratch/q4/workbook_payload.json")
    args = parser.parse_args()
    print(f"Prepared {prepare(args.data_root, args.directory, args.payload)} rows")

