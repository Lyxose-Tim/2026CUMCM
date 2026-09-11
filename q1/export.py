"""Prepare all products from the same verified archive; use one rounding rule."""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path

import numpy as np

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
    payload = {"verification_file":str(directory/"verification.json"),"verification_sha256":sha256(directory/"verification.json"),"archive_manifest_file":str(directory/"archive"/"manifest.json"),"archive_manifest_sha256":sha256(directory/"archive"/"manifest.json"),"worksheets":worksheets}
    write_json(payload_path,payload)
    return data,g,m,v


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",default="results/q1")
    parser.add_argument("--payload",default=".scratch/q1_workbook_payload.json")
    args = parser.parse_args()
    prepare(args.directory,args.payload)
