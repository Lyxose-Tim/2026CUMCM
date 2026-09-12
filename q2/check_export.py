"""Stream-read result2.xlsx and compare every result cell with verified sources."""
import argparse
import json
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

from .archive import write_json
from .export import rounded_array, verified_source
from .inputs import sha256
from .provenance import delivery_snapshot


def check(directory="results/q2", workbook="results/result2.xlsx"):
    directory, workbook = Path(directory), Path(workbook)
    data, _, manifest, _ = verified_source(directory)
    book = load_workbook(workbook, read_only=True, data_only=True)
    max_difference = 0.0
    checked = 0
    try:
        if book.sheetnames != ["温度", "水分浓度"]:
            raise ValueError("Unexpected result2 sheet names")
        for sheet_name, key in (("温度", "temperature_C"), ("水分浓度", "moisture")):
            sheet = book[sheet_name]
            if sheet.max_row != 259201 or sheet.max_column != 22:
                raise ValueError(f"Unexpected {sheet_name} dimensions")
            rows = sheet.iter_rows(values_only=True)
            header = next(rows)
            if header != (manifest["inputs"]["template_A1"], *[j / 10 for j in range(21)]):
                raise ValueError(f"Unexpected {sheet_name} header")
            for start in range(1, 259201, 21600):
                end = min(start + 21600, 259201)
                actual = np.asarray([next(rows) for _ in range(end - start)], dtype=float)
                if not np.array_equal(actual[:, 0], np.arange(start, end)):
                    raise ValueError(f"Broken time axis in {sheet_name}")
                expected = rounded_array(data[key][start:end])
                difference = float(np.max(np.abs(actual[:, 1:] - expected)))
                max_difference = max(max_difference, difference)
                checked += expected.size
            if next(rows, None) is not None:
                raise ValueError(f"Unexpected extra rows in {sheet_name}")
    finally:
        book.close()
    result = {
        "passed": max_difference == 0.0 and checked == 10886400,
        "workbook_sha256": sha256(workbook),
        "workbook_bytes": workbook.stat().st_size,
        "numeric_result_cells_checked": checked,
        "max_absolute_readback_difference": max_difference,
        "sheets": ["温度", "水分浓度"],
        "rows_per_sheet": 259201,
        "columns_per_sheet": 22,
        "delivery_source": delivery_snapshot(),
        "writer": "openpyxl write-only streaming; Artifact Tool format blueprint rendered separately",
    }
    write_json(directory / "export_verification.json", result)
    if not result["passed"]:
        raise ValueError("Q2 workbook readback failed")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="results/q2")
    parser.add_argument("--workbook", default="results/result2.xlsx")
    args = parser.parse_args()
    print(json.dumps(check(args.directory, args.workbook), ensure_ascii=False))
