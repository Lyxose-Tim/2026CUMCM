"""Migrate unchanged Q1-Q3 numerical evidence to the versioned hash contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.hashing import (
    LEGACY_TEXT_HASH_SCHEME,
    RAW_HASH_SCHEME,
    TEXT_HASH_SCHEME,
    file_record,
    file_sha256,
    legacy_artifact_sha256,
    raw_sha256,
)
from q1.provenance import NUMERICAL_FILES as Q1_NUMERICAL, artifact_sha256, source_snapshot as q1_snapshot
from q2.provenance import NUMERICAL_FILES as Q2_NUMERICAL, source_snapshot as q2_snapshot
from q3.provenance import NUMERICAL as Q3_NUMERICAL, snapshot as q3_snapshot


Q1_EVIDENCE_ONLY = {"q1/provenance.py", "common/hashing.py"}
Q2_EVIDENCE_ONLY = {"q2/archive.py", "q2/provenance.py", "q2/run.py", "common/hashing.py"}
Q3_EVIDENCE_ONLY = {
    "q1/provenance.py", "q2/archive.py", "q2/provenance.py",
    "q3/run.py", "q3/provenance.py", "common/hashing.py",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_legacy_sources(record: dict, root: Path, files, evidence_only) -> list[str]:
    scheme = record.get("source_hash_scheme", record.get("hash_scheme"))
    if scheme != LEGACY_TEXT_HASH_SCHEME:
        raise ValueError(f"Expected legacy source scheme, found {scheme!r}")
    hashes = record.get("source_hashes", {})
    critical = [name for name in files if name not in evidence_only]
    missing = [name for name in critical if name not in hashes]
    if missing:
        raise ValueError("Legacy source scope incomplete: " + ", ".join(missing))
    changed = [
        name for name in critical
        if file_sha256(root / name, LEGACY_TEXT_HASH_SCHEME) != hashes[name]
    ]
    if changed:
        raise ValueError("Numerical source changed; migration refused: " + ", ".join(changed))
    return critical


def migration_record(path: Path, old_raw: str, critical: list[str], from_scheme=LEGACY_TEXT_HASH_SCHEME) -> dict:
    return {
        "schema_version": 1,
        "kind": "metadata-only-hash-contract-migration",
        "from_hash_scheme": from_scheme,
        "to_hash_scheme": TEXT_HASH_SCHEME,
        "old_record_raw_sha256": old_raw,
        "verified_unchanged_numerical_files": critical,
        "migration_source": file_record(Path(__file__)),
        "record": path.as_posix(),
    }


def migrate_q2(root: Path) -> dict:
    path = root / "results/q2/archive/manifest.json"
    record = read_json(path)
    if record.get("source_hash_scheme") == TEXT_HASH_SCHEME:
        return {"status": "already-current", "path": path.as_posix()}
    old_raw = raw_sha256(path)
    critical = verify_legacy_sources(record, root, Q2_NUMERICAL, Q2_EVIDENCE_ONLY)
    verification = root / "results/q2/verification.json"
    if raw_sha256(verification) != record.get("verification_sha256"):
        raise ValueError("Q2 legacy verification binding failed")
    geometry = path.parent / "geometry.npz"
    if raw_sha256(geometry) != record.get("geometry_sha256"):
        raise ValueError("Q2 legacy geometry binding failed")
    for item in record["chunks"]:
        artifact = path.parent / item["file"]
        if raw_sha256(artifact) != item.get("sha256"):
            raise ValueError(f"Q2 legacy chunk binding failed: {item['file']}")
        item["hash"] = file_record(artifact, RAW_HASH_SCHEME)
        item.pop("sha256", None)
    record.update(q2_snapshot(root))
    record["schema_version"] = 2
    record["verification_hash"] = file_record(verification)
    record["geometry_hash"] = file_record(geometry, RAW_HASH_SCHEME)
    record.pop("verification_sha256", None)
    record.pop("geometry_sha256", None)
    record["metadata_migration"] = migration_record(path.relative_to(root), old_raw, critical)
    write_json(path, record)
    return {"status": "migrated", "path": path.as_posix(), "sha256": raw_sha256(path)}


def migrate_q3(root: Path) -> dict:
    migrated = 0
    for path in sorted((root / "results/q3/runs").glob("*/run.json")):
        record = read_json(path)
        source = record.get("source", {})
        old_raw = raw_sha256(path)
        source_scheme = source.get("hash_scheme")
        if source_scheme == TEXT_HASH_SCHEME:
            critical = [name for name in Q3_NUMERICAL if name not in Q3_EVIDENCE_ONLY]
            changed = [
                name for name in critical
                if file_sha256(root / name, TEXT_HASH_SCHEME) != source.get("source_hashes", {}).get(name)
            ]
            if changed:
                raise ValueError("Numerical source changed; migration refused: " + ", ".join(changed))
            for name, digest in record.get("files", {}).items():
                from common.hashing import verify_file
                verify_file(path.parent / name, digest)
            if source == q3_snapshot(root):
                continue
        else:
            critical = verify_legacy_sources(source, root, Q3_NUMERICAL, Q3_EVIDENCE_ONLY)
            for name, digest in record.get("files", {}).items():
                artifact = path.parent / name
                if raw_sha256(artifact) != digest:
                    raise ValueError(f"Q3 legacy artifact binding failed: {path.parent.name}/{name}")
        record["source"] = q3_snapshot(root)
        if source_scheme != TEXT_HASH_SCHEME:
            record["files"] = {name: file_record(path.parent / name) for name in record.get("files", {})}
        previous = record.pop("metadata_migration", None)
        history = record.setdefault("metadata_migration_history", [])
        if previous is not None:
            history.append(previous)
        history.append(migration_record(
            path.relative_to(root), old_raw, critical, from_scheme=source_scheme
        ))
        write_json(path, record)
        migrated += 1
    return {"status": "migrated", "records": migrated}


def migrate_q1_sensitivity(root: Path) -> dict:
    base = root / "results/q1_sensitivity"
    manifest_path = base / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("source_hash_scheme") == TEXT_HASH_SCHEME:
        return {"status": "already-current", "path": manifest_path.as_posix()}
    old_manifest_raw = raw_sha256(manifest_path)
    critical = verify_legacy_sources(manifest, root, Q1_NUMERICAL, Q1_EVIDENCE_ONLY)
    source = q1_snapshot(root)
    run_hashes = {}
    for path in sorted((base / "runs").glob("*/run.json")):
        record = read_json(path)
        verify_legacy_sources(record, root, Q1_NUMERICAL, Q1_EVIDENCE_ONLY)
        for name, digest in record.get("files", {}).items():
            if legacy_artifact_sha256(path.parent / name) != digest:
                raise ValueError(f"Q1 sensitivity artifact binding failed: {path.parent.name}/{name}")
        old_raw = raw_sha256(path)
        record.update(source)
        record["artifact_hash_scheme"] = TEXT_HASH_SCHEME
        record["files"] = {name: artifact_sha256(path.parent / name) for name in record.get("files", {})}
        record["metadata_migration"] = migration_record(path.relative_to(root), old_raw, critical)
        write_json(path, record)
        run_hashes[path.parent.name] = artifact_sha256(path)
    verification = base / "verification.json"
    if legacy_artifact_sha256(verification) != manifest.get("verification_sha256"):
        raise ValueError("Q1 sensitivity legacy verification binding failed")
    manifest.update(source)
    manifest["artifact_hash_scheme"] = TEXT_HASH_SCHEME
    manifest["verification_sha256"] = artifact_sha256(verification)
    manifest["run_records"] = run_hashes
    manifest["metadata_migration"] = migration_record(
        manifest_path.relative_to(root), old_manifest_raw, critical
    )
    write_json(manifest_path, manifest)
    return {"status": "migrated", "records": len(run_hashes)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = {
        "q1_sensitivity": migrate_q1_sensitivity(root),
        "q2": migrate_q2(root),
        "q3": migrate_q3(root),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
