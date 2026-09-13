"""Prepare all products from the same verified archive; use one rounding rule."""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np

from common.hashing import file_record
from common.workbooks import write_dense_workbook
from .archive import load_archive,write_json
from .inputs import sha256

TABLE_TIMES = np.array([100,300,600,900,1200,1500,1800])


def rounded(value):
    return Decimal(str(float(value))).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)


def rounded_array(values):
    values = np.asarray(values)
    return np.array([float(rounded(v)) for v in values.ravel()]).reshape(values.shape)


def verified_source(directory):
    directory = Path(directory)
    if (directory/"failure.json").exists():
        raise ValueError("A later failed run blocks formal export; complete a successful run first")
    verification_path = directory/"verification.json"
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if not verification["numerical_passed"]:
        raise ValueError("Formal export requires all numerical validation gates to pass")
    data,geometry,manifest = load_archive(directory/"archive")
    if manifest["status"] != "numerically_verified" or manifest["verification_sha256"] != sha256(verification_path):
        raise ValueError("Archive validation provenance mismatch")
    if not np.array_equal(data["time_s"],np.arange(1801)):
        raise ValueError("Expected exact time axis 0:1:1800")
    return data,geometry,manifest,verification


def prepare(directory="results/q1",payload_path=".scratch/q1_workbook_payload.json"):
    directory = Path(directory)
    data,g,m,v = verified_source(directory)
    outputs = [data[k][:,g["output_indices"]] for k in ["temperature_C","moisture"]]
    worksheets = []
    tables = {}
    for name,key,values in zip(["温度","水分浓度"],["temperature","moisture"],outputs):
        matrix = [[m["inputs"]["template_A1"], *[j/10 for j in range(21)]]]
        matrix += [[t,*row.tolist()] for t,row in zip(range(1,1801),rounded_array(values[1:]))]
        worksheets.append({"name":name,"values":matrix})
        table = values[TABLE_TIMES][:,[0,5,10,15,20]]
        tables[key] = [[int(t),*[str(rounded(x)) for x in row]] for t,row in zip(TABLE_TIMES,table)]
        with (directory/f"table_{key}.csv").open("w",encoding="utf-8",newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["time_s","r_0_cm","r_0.5_cm","r_1_cm","r_1.5_cm","r_2_cm"])
            writer.writerows(tables[key])
    write_json(directory/"tables.json",tables)
    payload = {
        "verification_file": str(directory / "verification.json"),
        "verification_hash": file_record(directory / "verification.json"),
        "archive_manifest_file": str(directory / "archive" / "manifest.json"),
        "archive_manifest_hash": file_record(directory / "archive" / "manifest.json"),
        "worksheets": worksheets,
    }
    write_json(payload_path,payload)
    return data,g,m,v


def export_workbook(directory="results/q1", workbook="results/result1.xlsx", payload_path=".scratch/q1_workbook_payload.json"):
    data, geometry, manifest, _ = prepare(directory, payload_path)
    headers = [manifest["inputs"]["template_A1"], *[index / 10 for index in range(21)]]
    indices = geometry["output_indices"]
    sheets = [
        {
            "name": name,
            "header": headers,
            "times": data["time_s"][1:],
            "values": data[key][1:, indices],
        }
        for name, key in (("温度", "temperature_C"), ("水分浓度", "moisture"))
    ]
    write_dense_workbook(workbook, sheets, time_format="0")
    from .check_export import check
    return check(directory, workbook)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",default="results/q1")
    parser.add_argument("--payload",default=".scratch/q1_workbook_payload.json")
    parser.add_argument("--workbook",default="results/result1.xlsx")
    parser.add_argument("--prepare-only",action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        prepare(args.directory,args.payload)
    else:
        print(json.dumps(export_workbook(args.directory, args.workbook, args.payload), ensure_ascii=False))
