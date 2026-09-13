"""Migrate unchanged numerical evidence to current versioned metadata contracts."""
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
    verify_file,
)
from q1.provenance import NUMERICAL_FILES as Q1_NUMERICAL, artifact_sha256, source_snapshot as q1_snapshot
from q2.provenance import NUMERICAL_FILES as Q2_NUMERICAL, source_snapshot as q2_snapshot
from q3.provenance import NUMERICAL as Q3_NUMERICAL, snapshot as q3_snapshot
from q4.provenance import NUMERICAL as Q4_NUMERICAL, snapshot as q4_snapshot


Q1_EVIDENCE_ONLY = {"q1/provenance.py", "common/hashing.py"}
Q2_EVIDENCE_ONLY = {"q2/archive.py", "q2/provenance.py", "q2/run.py", "common/hashing.py"}
Q3_EVIDENCE_ONLY = {
    "q1/provenance.py", "q2/archive.py", "q2/provenance.py",
    "q3/run.py", "q3/provenance.py", "common/hashing.py",
}
Q4_EVIDENCE_ONLY = {
    "q4/inputs.py", "q4/provenance.py", "common/hashing.py", "configs/q4.json",
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


def migration_record(
    path: Path,
    old_raw: str,
    critical: list[str],
    from_scheme=LEGACY_TEXT_HASH_SCHEME,
    kind="metadata-only-hash-contract-migration",
    reason=None,
) -> dict:
    record = {
        "schema_version": 1,
        "kind": kind,
        "from_hash_scheme": from_scheme,
        "to_hash_scheme": TEXT_HASH_SCHEME,
        "old_record_raw_sha256": old_raw,
        "verified_unchanged_numerical_files": critical,
        "migration_source": file_record(Path(__file__)),
        "record": path.as_posix(),
    }
    if reason is not None:
        record["reason"] = reason
    return record


def append_migration(record: dict, migration: dict) -> None:
    previous = record.pop("metadata_migration", None)
    history = record.setdefault("metadata_migration_history", [])
    if previous is not None:
        history.append(previous)
    history.append(migration)


def verify_current_sources(record: dict, root: Path, files, evidence_only) -> list[str]:
    hashes = record.get("source_hashes", {})
    critical = [name for name in files if name not in evidence_only]
    changed = [
        name for name in critical
        if file_sha256(root / name, TEXT_HASH_SCHEME) != hashes.get(name)
    ]
    if changed:
        raise ValueError("Numerical source changed; migration refused: " + ", ".join(changed))
    return critical


def migrate_q2(root: Path) -> dict:
    path = root / "results/q2/archive/manifest.json"
    record = read_json(path)
    if record.get("source_hash_scheme") == TEXT_HASH_SCHEME:
        old_raw = raw_sha256(path)
        critical = verify_current_sources(record, root, Q2_NUMERICAL, Q2_EVIDENCE_ONLY)
        verification = root / "results/q2/verification.json"
        geometry = path.parent / "geometry.npz"
        verify_file(verification, record["verification_hash"])
        verify_file(geometry, record["geometry_hash"])
        for item in record["chunks"]:
            verify_file(path.parent / item["file"], item["hash"])
        current = q2_snapshot(root)
        if all(record.get(key) == value for key, value in current.items()):
            return {"status": "already-current", "path": path.as_posix()}
        record.update(current)
        append_migration(
            record,
            migration_record(path.relative_to(root), old_raw, critical, from_scheme=TEXT_HASH_SCHEME),
        )
        write_json(path, record)
        return {"status": "refreshed", "path": path.as_posix(), "sha256": raw_sha256(path)}
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
    append_migration(record, migration_record(path.relative_to(root), old_raw, critical))
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
        append_migration(record, migration_record(
            path.relative_to(root), old_raw, critical, from_scheme=source_scheme
        ))
        write_json(path, record)
        migrated += 1
    return {"status": "migrated", "records": migrated}


def migrate_q4(root: Path) -> dict:
    config = read_json(root / "configs/q4.json")
    observed_end_s = float(config["radius"]["observed_end_s"])
    paths = sorted((root / "results/q4/runs").glob("*/run.json"))
    paths += sorted((root / "results/q4/sensitivity/runs").glob("*/run.json"))
    if len(paths) != 13:
        raise ValueError(f"Expected 13 Q4 run records, found {len(paths)}")
    current_source = q4_snapshot(root)
    migrated = 0
    unchanged_artifacts = 0
    for path in paths:
        record = read_json(path)
        source = record.get("source", {})
        if source.get("hash_scheme") != TEXT_HASH_SCHEME:
            raise ValueError(f"Q4 record does not use the current hash scheme: {path}")
        critical = [name for name in Q4_NUMERICAL if name not in Q4_EVIDENCE_ONLY]
        changed = [
            name for name in critical
            if file_sha256(root / name, TEXT_HASH_SCHEME)
            != source.get("source_hashes", {}).get(name)
        ]
        if changed:
            raise ValueError("Q4 numerical source changed; migration refused: " + ", ".join(changed))
        artifact_records = record.get("files", {})
        if set(artifact_records) != {"fields.npz", "accepted_steps.csv"}:
            raise ValueError(f"Incomplete Q4 artifact set: {path}")
        before = {}
        for name, digest in artifact_records.items():
            artifact = path.parent / name
            verify_file(artifact, digest)
            before[name] = raw_sha256(artifact)
        radius = record["identity"]["inputs"]["q4_radius"]
        if (radius.get("sha256") != config["input_sha256"]["radius"]
                or int(radius.get("rows", 0)) != 145):
            raise ValueError(f"Q4 radius identity is not eligible for migration: {path}")
        if not radius.get("fixed") and float(radius["horizon_s"]) > observed_end_s:
            raise ValueError(f"Shrinking Q4 run exceeds the observed radius domain: {path}")
        old_raw = raw_sha256(path)
        previous_digest = source.get("source_digest")
        radius["observed_end_s"] = observed_end_s
        record["source"] = current_source
        migration = migration_record(
            path.relative_to(root),
            old_raw,
            critical,
            from_scheme=TEXT_HASH_SCHEME,
            kind="metadata-only-q4-evidence-contract-refresh",
            reason=(
                "Add separate radius observation metadata and strengthen archive loading; "
                "PDE operators, case parameters, solver settings, NPZ, and accepted steps are unchanged."
            ),
        )
        migration["previous_source_digest"] = previous_digest
        migration["refreshed_metadata_files"] = sorted(Q4_EVIDENCE_ONLY)
        migration["unchanged_artifact_raw_sha256"] = before
        append_migration(record, migration)
        write_json(path, record)
        for name, expected in before.items():
            if raw_sha256(path.parent / name) != expected:
                raise ValueError(f"Q4 artifact changed during metadata migration: {path.parent.name}/{name}")
            unchanged_artifacts += 1
        migrated += 1
    return {
        "status": "migrated",
        "records": migrated,
        "unchanged_artifacts": unchanged_artifacts,
        "source_digest": current_source["source_digest"],
        "code_commit": current_source["code_commit"],
    }


def migrate_q1_sensitivity(root: Path) -> dict:
    base = root / "results/q1_sensitivity"
    manifest_path = base / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("source_hash_scheme") == TEXT_HASH_SCHEME:
        current = q1_snapshot(root)
        if all(manifest.get(key) == value for key, value in current.items()):
            return {"status": "already-current", "path": manifest_path.as_posix()}
        old_manifest_raw = raw_sha256(manifest_path)
        critical = verify_current_sources(manifest, root, Q1_NUMERICAL, Q1_EVIDENCE_ONLY)
        verification = base / "verification.json"
        if artifact_sha256(verification) != manifest.get("verification_sha256"):
            raise ValueError("Q1 sensitivity verification binding failed")
        run_hashes = {}
        for path in sorted((base / "runs").glob("*/run.json")):
            expected = manifest.get("run_records", {}).get(path.parent.name)
            if artifact_sha256(path) != expected:
                raise ValueError(f"Q1 sensitivity run binding failed: {path.parent.name}")
            record = read_json(path)
            verify_current_sources(record, root, Q1_NUMERICAL, Q1_EVIDENCE_ONLY)
            for name, digest in record.get("files", {}).items():
                if artifact_sha256(path.parent / name) != digest:
                    raise ValueError(f"Q1 sensitivity artifact binding failed: {path.parent.name}/{name}")
            old_raw = raw_sha256(path)
            record.update(current)
            append_migration(
                record,
                migration_record(path.relative_to(root), old_raw, critical, from_scheme=TEXT_HASH_SCHEME),
            )
            write_json(path, record)
            run_hashes[path.parent.name] = artifact_sha256(path)
        manifest.update(current)
        manifest["run_records"] = run_hashes
        append_migration(
            manifest,
            migration_record(
                manifest_path.relative_to(root), old_manifest_raw, critical,
                from_scheme=TEXT_HASH_SCHEME,
            ),
        )
        write_json(manifest_path, manifest)
        return {"status": "refreshed", "records": len(run_hashes)}
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
        append_migration(record, migration_record(path.relative_to(root), old_raw, critical))
        write_json(path, record)
        run_hashes[path.parent.name] = artifact_sha256(path)
    verification = base / "verification.json"
    if legacy_artifact_sha256(verification) != manifest.get("verification_sha256"):
        raise ValueError("Q1 sensitivity legacy verification binding failed")
    manifest.update(source)
    manifest["artifact_hash_scheme"] = TEXT_HASH_SCHEME
    manifest["verification_sha256"] = artifact_sha256(verification)
    manifest["run_records"] = run_hashes
    append_migration(
        manifest,
        migration_record(manifest_path.relative_to(root), old_manifest_raw, critical),
    )
    write_json(manifest_path, manifest)
    return {"status": "migrated", "records": len(run_hashes)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--questions", nargs="+", choices=["q1_sensitivity", "q2", "q3", "q4"],
        default=["q1_sensitivity", "q2", "q3", "q4"],
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    operations = {
        "q1_sensitivity": migrate_q1_sensitivity,
        "q2": migrate_q2,
        "q3": migrate_q3,
        "q4": migrate_q4,
    }
    result = {name: operations[name](root) for name in args.questions}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
