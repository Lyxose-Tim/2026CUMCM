"""One verified numeric source for Table 5 and the template-based workbook."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np

from common.hashing import file_record
from common.workbooks import write_dense_workbook
from q2.archive import write_json
from q2.inputs import sha256
from q2.provenance import portable_artifact_sha256
from q3.validation import verified
from q3.solver import output_axis


def rounded(values):
    values=np.asarray(values,dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite output cannot be rounded")
    return np.array([float(Decimal(str(float(v))).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP))
                     for v in values.ravel()]).reshape(values.shape)


def delivery_sources():
    paths=[
        "q3/export.py", "q3/check_export.py", "common/workbooks.py",
        "scripts/hash_record.mjs", "scripts/build_result3.mjs",
    ]
    return {p:file_record(p) for p in paths}


def prepare(data_root,directory="results/q3",payload=".scratch/q3/workbook_payload.json"):
    directory=Path(directory)
    verification,record,fields=verified(directory)
    template=Path(data_root)/"附件"/"附件3"/"result3.xlsx"
    if sha256(template) != record["identity"]["inputs"]["q3_template"]["sha256"]:
        raise ValueError("Changed result3 template")
    end=record["root"]["time_s"]
    t5=output_axis(end,21600)
    idx=np.searchsorted(fields["time_s"],t5)
    np.testing.assert_array_equal(fields["time_s"][idx],t5)
    table=np.c_[t5/3600,fields["moisture"][idx][:,[0,5,10,15,20]]]
    np.savetxt(directory/"table5.csv",table,delimiter=",",header="time_h,r0_cm,r0.5_cm,r1_cm,r1.5_cm,r2_cm",
               comments="",fmt="%.17g")
    header="| 时间 / h | 0 cm | 0.5 cm | 1 cm | 1.5 cm | 2 cm |\n|---:|---:|---:|---:|---:|---:|\n"
    body="\n".join("| "+" | ".join(f"{v:.4f}" for v in row)+" |" for row in rounded(table))
    (directory/"table5.md").write_text(header+body+"\n",encoding="utf-8")
    rows=np.c_[fields["time_s"][1:],rounded(fields["moisture"][1:])]
    content={"rows":rows.tolist(),"template":str(template.resolve()),
             "template_hash":file_record(template),"output":"results/result3.xlsx",
             "verification_file":str((directory/"verification.json").resolve()),
             "verification_hash":file_record(directory/"verification.json"),
             "run_file":str((directory/"runs"/verification["formal_case"]/"run.json").resolve()),
             "run_hash":file_record(directory/"runs"/verification["formal_case"]/"run.json"),
             "sources":delivery_sources()}
    write_json(payload,content)
    return len(rows)


def export_workbook(data_root, directory="results/q3", workbook="results/result3.xlsx", payload=".scratch/q3/workbook_payload.json"):
    prepare(data_root, directory, payload)
    _, record, fields = verified(directory)
    header = [record["identity"]["inputs"]["q3_template"]["A1"], *[index / 10 for index in range(21)]]
    write_dense_workbook(
        workbook,
        [{
            "name": "Sheet1",
            "header": header,
            "times": fields["time_s"][1:],
            "values": fields["moisture"][1:],
        }],
    )
    from q3.check_export import check
    return check(directory, workbook)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",required=True)
    p.add_argument("--directory",default="results/q3")
    p.add_argument("--payload",default=".scratch/q3/workbook_payload.json")
    p.add_argument("--workbook",default="results/result3.xlsx")
    p.add_argument("--prepare-only",action="store_true")
    a=p.parse_args()
    if a.prepare_only:
        print(f"Prepared {prepare(a.data_root,a.directory,a.payload)} rows")
    else:
        print(json.dumps(export_workbook(a.data_root, a.directory, a.workbook, a.payload), ensure_ascii=False))
