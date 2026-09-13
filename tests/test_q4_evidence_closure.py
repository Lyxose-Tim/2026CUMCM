import csv
import json
from pathlib import Path

import numpy as np
import pytest

from common.hashing import file_record
from common.portable_audit import audit
from q2.inputs import read_config
import q4.figures as q4_figures
import q4.reports as q4_reports
import q4.sensitivity as q4_sensitivity
import q4.validation as q4_validation


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_missing_radau_is_rejected_by_all_public_q4_entrypoints(tmp_path, monkeypatch):
    config = read_config("configs/q4.json")
    configured = {case["name"]: case for case in q4_validation.cases(config)}
    method_name = config["validation"]["method_group"][1]
    root = tmp_path / "q4"
    (root / "runs").mkdir(parents=True)
    for name in configured:
        if name != method_name:
            (root / "runs" / name).mkdir()
    (root / "unit_tests.txt").write_text("synthetic\n", encoding="utf-8")
    write_json(root / "verification.json", {
        "schema_version": 3,
        "passed": True,
        "formal_case": config["formal_case"],
        "validation_sources": {},
        "unit_tests_hash": {},
        "run_record_hashes": {name: {} for name in configured},
    })

    monkeypatch.setattr(q4_validation, "validation_sources", lambda: {})
    monkeypatch.setattr(q4_validation, "verify_file", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(q4_validation, "check_run", lambda *_args, **_kwargs: {"passed": True})

    def load_case(directory, name):
        if not (Path(directory) / "runs" / name).is_dir():
            raise FileNotFoundError(name)
        return {"identity": {"case": configured[name]}}, {}

    monkeypatch.setattr(q4_validation, "load_case", load_case)

    def strict_verifier(*_args, **_kwargs):
        return q4_validation.verified(root)

    with pytest.raises(FileNotFoundError, match=method_name):
        q4_validation.verified(root)
    with pytest.raises(FileNotFoundError, match=method_name):
        audit({"q4": strict_verifier})
    monkeypatch.setattr(q4_reports, "verified", strict_verifier)
    monkeypatch.setattr(q4_reports, "REPORT_DIR", tmp_path / "reports")
    with pytest.raises(FileNotFoundError, match=method_name):
        q4_reports.write_reports(root)
    monkeypatch.setattr(q4_figures, "verified", strict_verifier)
    with pytest.raises(FileNotFoundError, match=method_name):
        q4_figures.make(root, tmp_path / "figures")


def sensitivity_fixture(tmp_path):
    main_config = read_config("configs/q4.json")
    sensitivity_config = read_config("configs/q4_sensitivity.json")
    configured = q4_sensitivity.scenario_cases(main_config, sensitivity_config)
    q4_root = tmp_path / "q4"
    root = q4_root / "sensitivity"
    rows = []
    runs = {}
    for case in configured:
        scenario = case["scenario"]
        run_directory = root / "runs" / case["name"]
        run_directory.mkdir(parents=True)
        write_json(run_directory / "run.json", {
            "status": "computed",
            "identity": {"case": case},
            "root": {"time_s": 1.0},
        })
        np.savez(run_directory / "fields.npz", sentinel=np.array([1.0]))
        rows.append({"scenario": scenario, "case_name": case["name"], "event_time_s": "1"})
        runs[scenario] = {
            "case_name": case["name"],
            "directory": f"runs/{case['name']}",
            "run_record": file_record(run_directory / "run.json"),
        }
    csv_path = root / "summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["scenario", "case_name", "event_time_s"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": 2,
        "passed": True,
        "base_case": sensitivity_config["base_case"],
        "configuration_hash": file_record("configs/q4_sensitivity.json"),
        "generator_hash": file_record("q4/sensitivity.py"),
        "summary_csv_hash": file_record(csv_path),
        "scenarios": rows,
        "runs": runs,
    }
    write_json(root / "summary.json", summary)
    return q4_root, configured


def install_minimal_sensitivity_loader(monkeypatch):
    def load_run(directory):
        directory = Path(directory)
        try:
            with np.load(directory / "fields.npz") as archive:
                fields = {name: archive[name] for name in archive.files}
        except (OSError, ValueError) as exc:
            raise ValueError("Unreadable sensitivity fields") from exc
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        return record, fields

    monkeypatch.setattr(q4_sensitivity, "load_run", load_run)


def assert_sensitivity_rejected_everywhere(q4_root, tmp_path, monkeypatch, match):
    with pytest.raises(ValueError, match=match):
        q4_sensitivity.verified_summary(q4_root / "sensitivity")
    with pytest.raises(ValueError, match=match):
        audit({"q4": lambda: q4_reports.require_sensitivity(q4_root)})

    monkeypatch.setattr(q4_reports, "verified", lambda *_args, **_kwargs: ({}, {}, {}))
    monkeypatch.setattr(q4_reports, "require_export", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(q4_reports, "require_figures", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(q4_reports, "REPORT_DIR", tmp_path / "reports")
    with pytest.raises(ValueError, match=match):
        q4_reports.write_reports(q4_root)

    monkeypatch.setattr(q4_figures, "verified", lambda *_args, **_kwargs: ({}, {}, {}))
    with pytest.raises(ValueError, match=match):
        q4_figures.make(q4_root, tmp_path / "figures")


def test_corrupt_sensitivity_npz_is_rejected_everywhere(tmp_path, monkeypatch):
    q4_root, configured = sensitivity_fixture(tmp_path)
    install_minimal_sensitivity_loader(monkeypatch)
    pchip = next(case for case in configured if case["scenario"] == "pchip")
    (q4_root / "sensitivity" / "runs" / pchip["name"] / "fields.npz").write_bytes(b"not-an-npz")
    assert_sensitivity_rejected_everywhere(
        q4_root, tmp_path, monkeypatch, "Unreadable sensitivity fields"
    )


def test_corrupt_sensitivity_summary_csv_is_rejected_everywhere(tmp_path, monkeypatch):
    q4_root, _ = sensitivity_fixture(tmp_path)
    (q4_root / "sensitivity" / "summary.csv").write_text("corrupt\n", encoding="utf-8")
    assert_sensitivity_rejected_everywhere(q4_root, tmp_path, monkeypatch, "hash mismatch")
