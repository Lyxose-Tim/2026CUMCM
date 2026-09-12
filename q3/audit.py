"""Final source/artifact audit, including actual visual QA and report binding."""
import argparse
import json
from pathlib import Path

from q2.archive import write_json
from q2.provenance import portable_artifact_sha256
from q3.validation import verified
from q3.reports import require_export
from q3.git_audit import checkout_identity, verify_git_binding


def artifact_hashes():
    paths=list(Path("q3").glob("*.py"))+list(Path("tests").glob("test_q3*.py"))
    paths += [Path(p) for p in ["scripts/build_result3.mjs","configs/q3.json","Q3_REPRODUCE.md",
                               "results/result3.xlsx"]]
    paths += list(Path("reports").glob("Q3_*.md"))
    paths += [p for p in Path("results/q3").rglob("*") if p.is_file() and p.name!="audit.json"]
    paths += list(Path("figures/q3").glob("*.pdf"))
    return {str(p).replace("\\","/"):portable_artifact_sha256(p) for p in sorted(paths)}


def audit(write=False):
    if write:
        current=checkout_identity()
    else:
        recorded=json.loads(Path("results/q3/audit.json").read_text(encoding="utf-8"))
        current=verify_git_binding(recorded)
    v,r,f=verified()
    e=require_export()
    qa=json.loads(Path("results/q3/visual_qa.json").read_text(encoding="utf-8"))
    if qa.get("passed") is not True:
        raise ValueError("Visual QA is incomplete")
    if qa["workbook_sha256"] != e["workbook_sha256"]:
        raise ValueError("Visual QA is for a different workbook")
    figure_manifest=json.loads(Path("results/q3/figure_manifest.json").read_text(encoding="utf-8"))
    if qa["pdf"] != figure_manifest["pdf"]:
        raise ValueError("Visual QA is for different figures")
    for name,digest in figure_manifest["pdf"].items():
        if portable_artifact_sha256(Path("figures/q3")/name)!=digest:
            raise ValueError("Changed figure")
    reproduction=json.loads(Path("results/q3/reproduction.json").read_text(encoding="utf-8"))
    if reproduction.get("passed") is not True:
        raise ValueError("New-process reproduction failed")
    if reproduction["verification_source_sha256"] != portable_artifact_sha256("q3/reproduce.py"):
        raise ValueError("Changed reproduction checker")
    if reproduction["original_run_sha256"] != portable_artifact_sha256("results/q3/runs/base_N5120/run.json"):
        raise ValueError("Reproduction does not bind the current baseline")
    hashes=artifact_hashes()
    if not write:
        if recorded.get("passed") is not True or recorded["artifacts"] != hashes:
            raise ValueError("Source or delivered artifact changed after audit")
    record={"schema_version":2,"passed":True,
            "audited_content_commit":current["code_commit"] if current else None,
            "git_tree":current["git_tree"] if current else None,
            "formal_case":v["formal_case"],
            "time_h":r["root"]["time_h"],"artifacts":hashes,
            "scope":"numerical, tests, workbook, figures, reports, reproduction and visual QA; not independent peer approval"}
    if write:
        write_json("results/q3/audit.json",record)
    print(f"Q3 audit passed: {len(hashes)} source/artifact files; {r['root']['time_h']:.10f} h")
    print(f"Current HEAD: {current['code_commit']}" if current else
          "Source ZIP: Git binding skipped; portable source/artifact hashes verified")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--write",action="store_true")
    audit(parser.parse_args().write)
