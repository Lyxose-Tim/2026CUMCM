import json

import numpy as np
import pytest

import q2.check_export as check_export
import q2.provenance as provenance
import q2.reports as reports


def test_chunk_rejects_missing_value_even_when_same_block_has_large_error():
    expected = np.zeros((2, 21))
    rows = [
        [1, None, *([0.0] * 20)],
        [2, 0.0, 12345.6789, *([0.0] * 19)],
    ]
    with pytest.raises(ValueError, match="Missing or nonfinite"):
        check_export.compare_chunk(rows, [1, 2], expected, "temperature")


def test_chunk_rejects_nonfinite_difference():
    rows = np.c_[np.arange(1, 3), np.zeros((2, 21))]
    expected = np.zeros((2, 21))
    expected[0, 0] = np.inf
    with pytest.raises(ValueError, match="source value"):
        check_export.compare_chunk(rows, [1, 2], expected, "temperature")


def test_failed_readback_overwrites_previous_success(tmp_path, monkeypatch):
    directory = tmp_path / "results" / "q2"
    directory.mkdir(parents=True)
    workbook_path = tmp_path / "result2.xlsx"
    workbook_path.write_bytes(b"invalid-test-workbook")
    (directory / "export_verification.json").write_text('{"passed":true}\n', encoding="utf-8")
    zero = np.broadcast_to(np.zeros((1, 21)), (259201, 21))
    data = {"temperature_C": zero, "moisture": zero}
    manifest = {"inputs": {"template_A1": "time"}}

    class FakeSheet:
        max_row = 259201
        max_column = 22

        def iter_rows(self, values_only=True):
            yield ("time", *[index / 10 for index in range(21)])
            for time_s in range(1, 21601):
                row = [time_s, *([0.0] * 21)]
                if time_s == 1:
                    row[1] = None
                elif time_s == 2:
                    row[2] = 12345.6789
                yield tuple(row)

    class FakeBook:
        sheetnames = ["温度", "水分浓度"]

        def __getitem__(self, name):
            return FakeSheet()

        def close(self):
            pass

    monkeypatch.setattr(check_export, "verified_source", lambda directory: (data, {}, manifest, {}))
    monkeypatch.setattr(check_export, "load_workbook", lambda *args, **kwargs: FakeBook())
    with pytest.raises(ValueError, match="Missing or nonfinite"):
        check_export.check(directory, workbook_path)
    record = json.loads((directory / "export_verification.json").read_text(encoding="utf-8"))
    assert record["passed"] is False
    assert record["error_type"] == "ValueError"


def test_reports_reject_failed_verification_and_remove_stale_outputs(tmp_path, monkeypatch):
    directory = tmp_path / "results" / "q2"
    output = tmp_path / "reports"
    directory.mkdir(parents=True)
    output.mkdir()
    (directory / "export_verification.json").write_text(
        json.dumps({"passed": False, "max_absolute_readback_difference": 123.0}), encoding="utf-8"
    )
    for name in ("Q2_RESULTS_REPORT.md", "Q2_VERIFY_REPORT.md"):
        (output / name).write_text("stale success", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["reports.py", "--directory", str(directory), "--reports", str(output)]
    )
    with pytest.raises(ValueError, match="did not pass"):
        reports.main()
    assert not list(output.glob("Q2_*_REPORT.md"))


def test_reports_reject_verification_bound_to_other_workbook(tmp_path):
    directory = tmp_path / "results" / "q2"
    directory.mkdir(parents=True)
    workbook = tmp_path / "result2.xlsx"
    workbook.write_bytes(b"current workbook")
    (directory / "export_verification.json").write_text(json.dumps({
        "passed": True,
        "numeric_result_cells_checked": 10886400,
        "max_absolute_readback_difference": 0.0,
        "workbook_sha256": "0" * 64,
        "workbook_bytes": workbook.stat().st_size,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="stale for the current workbook"):
        reports.validated_export(directory, workbook)


def test_javascript_delivery_hash_accepts_line_endings_but_rejects_code_change(tmp_path, monkeypatch):
    script = tmp_path / "scripts" / "build_result2.mjs"
    script.parent.mkdir()
    monkeypatch.setattr(provenance, "DELIVERY_FILES", ("scripts/build_result2.mjs",))
    script.write_bytes(b"const chunkRows = 21600;\nexport { chunkRows };\n")
    lf = provenance.delivery_snapshot(tmp_path)
    script.write_bytes(b"const chunkRows = 21600;\r\nexport { chunkRows };\r\n")
    crlf = provenance.delivery_snapshot(tmp_path)
    assert crlf["source_digest"] == lf["source_digest"]
    assert crlf["source_hashes"] == lf["source_hashes"]
    assert crlf["source_raw_hashes"] != lf["source_raw_hashes"]
    script.write_bytes(b"const chunkRows = 10800;\r\nexport { chunkRows };\r\n")
    changed = provenance.delivery_snapshot(tmp_path)
    assert changed["source_digest"] != lf["source_digest"]
    assert changed["source_hashes"] != lf["source_hashes"]
