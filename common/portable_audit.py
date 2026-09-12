"""Read-only delivery audit that does not require Git metadata."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import sys
from typing import Callable
import xml.etree.ElementTree as ET

from common.hashing import file_record, verify_file
from q2.archive import write_json


def _report_manifest(question: str, generator: str) -> dict:
    directory = Path("results") / question
    manifest_path = directory / "report_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError(f"Versioned {question} report manifest is required")
    verify_file(generator, manifest["generator"])
    for name, digest in manifest["reports"].items():
        verify_file(Path("reports") / name, digest)
    verify_file(directory / "verification.json", manifest["verification"])
    verify_file(directory / "export_verification.json", manifest["export_verification"])
    verify_file(directory / "figure_manifest.json", manifest["figure_manifest"])
    if question == "q4":
        verify_file(directory / "sensitivity" / "summary.json", manifest["sensitivity_summary"])
    return {"reports": len(manifest["reports"]), "schema_version": manifest["schema_version"]}


def _q1_workbook() -> dict:
    evidence = json.loads(Path("results/q1/export_verification.json").read_text(encoding="utf-8"))
    if evidence.get("passed") is not True or evidence.get("numeric_result_cells_checked") != 75600:
        raise ValueError("Q1 workbook evidence is incomplete")
    verify_file("results/result1.xlsx", evidence["workbook_hash"])
    return {
        "workbook": evidence["workbook_hash"],
        "numeric_result_cells_checked": evidence["numeric_result_cells_checked"],
    }


def _q2() -> dict:
    from q2.export import verified_source
    from q2.reports import validated_export, validated_figures

    data, _, manifest, verification = verified_source("results/q2")
    if data["temperature_C"].shape != (259201, 21) or data["moisture"].shape != (259201, 21):
        raise ValueError("Unexpected Q2 archive shape")
    export = validated_export("results/q2", "results/result2.xlsx")
    figures = validated_figures("results/q2")
    reports = _report_manifest("q2", "q2/reports.py")
    return {
        "N": manifest["N"],
        "numerical_passed": bool(verification["numerical_passed"]),
        "workbook": export["workbook_hash"],
        "figure_count": len(figures["pdf"]),
        **reports,
    }


def _q3() -> dict:
    from q3.reports import require_export, require_figures
    from q3.validation import verified

    verification, record, _ = verified("results/q3")
    export = require_export("results/q3", "results/result3.xlsx")
    figures = require_figures(Path("results/q3"))
    reports = _report_manifest("q3", "q3/reports.py")
    return {
        "formal_case": verification["formal_case"],
        "event_time_h": record["root"]["time_h"],
        "workbook": export["workbook_hash"],
        "figure_count": len(figures["pdf"]),
        **reports,
    }


def _q4() -> dict:
    from q4.reports import require_export, require_figures, require_sensitivity
    from q4.validation import verified

    verification, record, _ = verified("results/q4")
    export = require_export("results/q4", "results/result4.xlsx")
    figures = require_figures(Path("results/q4"))
    sensitivity = require_sensitivity(Path("results/q4"))
    reports = _report_manifest("q4", "q4/reports.py")
    return {
        "formal_case": verification["formal_case"],
        "event_time_h": record["root"]["time_h"],
        "workbook": export["workbook_hash"],
        "figure_count": len(figures["pdf"]),
        "sensitivity_scenarios": len(sensitivity["scenarios"]),
        **reports,
    }


def _paper_figures() -> dict:
    manifest_path = Path("results/paper_figure_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2 or len(manifest.get("pdf", {})) != 6:
        raise ValueError("Six versioned paper figures are required")
    verify_file("paper_figures.py", manifest["generator"])
    drawio = Path("figures/paper/fig01_model_roadmap.drawio")
    drawio_record = verify_file(drawio, manifest["drawio_source"])
    if ET.parse(drawio).getroot().tag != "mxfile":
        raise ValueError("Invalid DrawIO source root")
    evidence_paths = {
        "q2_figure_manifest": Path("results/q2/figure_manifest.json"),
        "q3_verification": Path("results/q3/verification.json"),
        "q4_verification": Path("results/q4/verification.json"),
        "q4_sensitivity": Path("results/q4/sensitivity/summary.json"),
    }
    for name, path in evidence_paths.items():
        verify_file(path, manifest["evidence"][name])
    for name, digest in manifest["csv"].items():
        verify_file(Path("results/paper_figure_data") / name, digest)
    for name, digest in manifest["pdf"].items():
        verify_file(Path("figures/paper") / name, digest)
    return {
        "figure_count": len(manifest["pdf"]),
        "csv_count": len(manifest["csv"]),
        "drawio": drawio_record,
    }


def audit(section_checks: dict[str, Callable[[], dict]] | None = None) -> dict:
    checks = section_checks or {
        "q1_workbook": _q1_workbook,
        "q2": _q2,
        "q3": _q3,
        "q4": _q4,
        "paper_figures": _paper_figures,
    }
    sections = {}
    for name, check in checks.items():
        sections[name] = check()
    return {
        "passed": True,
        "git_required": False,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "sections": sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", default="results/portable_audit.json")
    args = parser.parse_args()
    result = audit()
    if args.write:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
