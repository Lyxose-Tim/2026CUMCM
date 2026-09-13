import json

import numpy as np
import pytest

from q4.check_export import assert_headers
from q4.export import workbook_headers
from q4.validation import check_spatial_budget, compare, normalize_test_output


def record():
    return {
        "identity": {
            "inputs": {"q4_template": {"A1": "时间(s)", "surface_header": "药材表面"}},
            "fixed_radius_m": [i * 0.001 for i in range(21)],
        }
    }


def test_q4_workbook_headers_use_centimeters():
    headers = workbook_headers(record())
    assert headers[1:22] == pytest.approx([i * 0.1 for i in range(21)])
    assert headers[22] == "药材表面"


def test_q4_meter_radius_headers_are_rejected():
    bad = ["时间(s)"] + [i * 0.001 for i in range(21)] + ["药材表面"]
    with pytest.raises(ValueError, match="centimeters"):
        assert_headers(bad, record())


def test_q4_wrong_surface_header_is_rejected():
    bad = workbook_headers(record())
    bad[-1] = "2 cm"
    with pytest.raises(ValueError, match="surface header"):
        assert_headers(bad, record())


def test_q4_default_spatial_budget_passes():
    spatial = [{
        "a": "N10240", "b": "N20480", "root_time_difference_s": 0.0755,
        "field_difference": {"C": {"max_abs": 1.8e-6}, "T": {"max_abs": 2e-4}},
    }]
    result = check_spatial_budget(spatial, {
        "space_time_s": 0.4, "space_C": 2e-5, "space_T_C": 5e-3,
    })
    assert result["passed"] is True


def test_q4_test_output_normalization_strips_trailing_whitespace():
    assert normalize_test_output("ok   \r\nnext\t\r\n\r\n") == "ok\nnext\n"


@pytest.mark.parametrize("key,value", [("root_time_difference_s", 0.5), ("C", 3e-5), ("C", np.inf)])
def test_q4_spatial_budget_overrun_fails(key, value):
    spatial = [{
        "a": "N10240", "b": "N20480", "root_time_difference_s": 0.0755,
        "field_difference": {"C": {"max_abs": 1.8e-6}, "T": {"max_abs": 2e-4}},
    }]
    if key in {"C", "T"}:
        spatial[0]["field_difference"][key]["max_abs"] = value
    else:
        spatial[0][key] = value
    with pytest.raises(ValueError, match="space comparison"):
        check_spatial_budget(spatial, {
            "space_time_s": 0.4, "space_C": 2e-5, "space_T_C": 5e-3,
        })


def test_q4_compare_includes_dynamic_surface_and_near_root_checkpoint():
    times = np.array([0.0, 60.0, 120.0])
    fixed = np.arange(21) * 0.001
    base = np.tile(np.linspace(2.0, 1.0, 22), (3, 1))
    summary = np.zeros((3, 12))
    summary[:, 0] = times
    summary[:, 2] = [2.0, 1.9, 1.8]
    summary[:, 4] = 0.01
    summary[:, 6] = [1.5, 1.4, 1.3]
    a = {
        "time_s": times, "temperature_C": base + 30, "moisture": base,
        "summary": summary, "fixed_radius_m": fixed,
        "surface_radius_m": np.array([0.02, 0.019, 0.018]),
    }
    b = {key: np.array(value, copy=True) for key, value in a.items()}
    b["moisture"][1, -1] += 0.25
    result = compare(a, b, spacing_s=60, intermediate_checkpoint_s=60)
    assert result["dynamic_surface_included"] is True
    assert result["C"]["dynamic_surface"] is True
    assert result["C"]["time_s"] == 60
    assert result["intermediate_checkpoint_s"] == 60
    assert result["near_root_common"]["time_s"] == 120
    assert result["near_root_common"]["state_acquisition"] == "exact_archived_regular_sample"
    assert result["near_root_common"]["time_reconstruction_error_s"] == 0
    assert result["near_root_common"]["C"]["valid_columns"] == 22


def test_q4_failed_export_blocks_reports(tmp_path):
    from q4.reports import require_export

    (tmp_path / "export_verification.json").write_text(json.dumps({"passed": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="failed"):
        require_export(tmp_path, tmp_path / "missing.xlsx")


def test_q4_missing_export_blocks_reports(tmp_path):
    from q4.reports import require_export

    with pytest.raises(FileNotFoundError):
        require_export(tmp_path, tmp_path / "missing.xlsx")


def test_q4_changed_workbook_blocks_reports(tmp_path):
    from q2.inputs import sha256
    from q4.reports import require_export

    workbook = tmp_path / "result4.xlsx"
    workbook.write_bytes(b"current workbook")
    (tmp_path / "table6.csv").write_text("time_h,surface\n0,2.55\n", encoding="utf-8")
    (tmp_path / "verification.json").write_text("{}", encoding="utf-8")
    (tmp_path / "export_verification.json").write_text(
        json.dumps({
            "passed": True,
            "workbook_sha256": "not-current",
            "verification_sha256": sha256(tmp_path / "verification.json"),
            "delivery_sources": {},
            "table6_sha256": sha256(tmp_path / "table6.csv"),
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different workbook"):
        require_export(tmp_path, workbook)


def test_q4_stale_export_evidence_blocks_reports(tmp_path):
    from q2.inputs import sha256
    from q4.reports import require_export

    workbook = tmp_path / "result4.xlsx"
    workbook.write_bytes(b"current workbook")
    (tmp_path / "table6.csv").write_text("time_h,surface\n0,2.55\n", encoding="utf-8")
    (tmp_path / "verification.json").write_text("{}", encoding="utf-8")
    (tmp_path / "export_verification.json").write_text(
        json.dumps({
            "passed": True,
            "workbook_sha256": sha256(workbook),
            "verification_sha256": "old",
            "delivery_sources": {},
            "table6_sha256": sha256(tmp_path / "table6.csv"),
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stale"):
        require_export(tmp_path, workbook)
