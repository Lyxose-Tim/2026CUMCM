"""Versioned, cross-platform file hashing for numerical evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


RAW_HASH_SCHEME = "sha256-raw-v1"
TEXT_HASH_SCHEME = "sha256-text-lf-v2"
LEGACY_TEXT_HASH_SCHEME = "sha256-text-lf-v1"

TEXT_SUFFIXES = frozenset({
    ".py", ".json", ".csv", ".md", ".txt",
    ".js", ".mjs", ".cjs", ".yaml", ".yml", ".toml",
})


def raw_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_text_bytes(path: str | Path) -> bytes:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Declared UTF-8 text cannot be decoded: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def hash_scheme_for(path: str | Path) -> str:
    return TEXT_HASH_SCHEME if Path(path).suffix.lower() in TEXT_SUFFIXES else RAW_HASH_SCHEME


def file_sha256(path: str | Path, scheme: str | None = None) -> str:
    selected = scheme or hash_scheme_for(path)
    if selected == RAW_HASH_SCHEME:
        return raw_sha256(path)
    if selected == TEXT_HASH_SCHEME:
        return hashlib.sha256(_normalized_text_bytes(path)).hexdigest()
    if selected == LEGACY_TEXT_HASH_SCHEME:
        return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    raise ValueError(f"Unsupported hash scheme: {selected}")


def file_record(path: str | Path, scheme: str | None = None) -> dict[str, str]:
    selected = scheme or hash_scheme_for(path)
    return {"hash_scheme": selected, "sha256": file_sha256(path, selected)}


def legacy_artifact_sha256(path: str | Path) -> str:
    scheme = LEGACY_TEXT_HASH_SCHEME if Path(path).suffix.lower() in TEXT_SUFFIXES else RAW_HASH_SCHEME
    return file_sha256(path, scheme)


def verify_file(path: str | Path, record: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(record, Mapping):
        raise ValueError(f"Unversioned file digest for {path}")
    scheme = record.get("hash_scheme")
    expected = record.get("sha256")
    if not isinstance(scheme, str) or not isinstance(expected, str):
        raise ValueError(f"Incomplete file digest record for {path}")
    actual = file_sha256(path, scheme)
    if actual != expected:
        raise ValueError(f"Artifact hash mismatch: {path}")
    return {"hash_scheme": scheme, "sha256": actual}


def digest_mapping(hashes: Mapping[str, str]) -> str:
    payload = json.dumps(hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_mapping(paths: Mapping[str, str | Path]) -> dict[str, dict[str, str]]:
    return {name: file_record(path) for name, path in paths.items()}


def verify_mapping(root: str | Path, records: Mapping[str, Mapping[str, str]]) -> None:
    root = Path(root)
    for name, record in records.items():
        verify_file(root / name, record)
