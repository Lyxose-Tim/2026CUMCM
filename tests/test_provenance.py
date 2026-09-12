from pathlib import Path
import subprocess

import pytest


def test_text_hash_accepts_only_line_ending_equivalence(tmp_path):
    from q1.provenance import artifact_sha256
    a,b=tmp_path/'a.py',tmp_path/'b.py'
    a.write_bytes(b'k = 0.36\nD = 7e-9\n')
    b.write_bytes(b'k = 0.36\rD = 7e-9\r')
    assert artifact_sha256(a)==artifact_sha256(b)
    b.write_bytes(b'k = 0.37\r\nD = 7e-9\r\n')
    assert artifact_sha256(a)!=artifact_sha256(b)
    x,y=tmp_path/'a.npz',tmp_path/'b.npz'
    x.write_bytes(b'\n'); y.write_bytes(b'\r\n')
    assert artifact_sha256(x)!=artifact_sha256(y)


def test_declared_text_requires_utf8_and_hash_record_is_versioned(tmp_path):
    from common.hashing import TEXT_HASH_SCHEME, file_record, verify_file
    path = tmp_path / "model.yaml"
    path.write_text("radius: 0.02\n", encoding="utf-8")
    record = file_record(path)
    assert record["hash_scheme"] == TEXT_HASH_SCHEME
    assert verify_file(path, record) == record
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="UTF-8"):
        file_record(path)


def test_metadata_migration_refuses_numerical_source_change(tmp_path):
    from common.hashing import LEGACY_TEXT_HASH_SCHEME, file_sha256
    from common.migrate_provenance import verify_legacy_sources
    source = tmp_path / "model.py"
    source.write_text("coefficient = 1.0\n", encoding="utf-8")
    record = {
        "source_hash_scheme": LEGACY_TEXT_HASH_SCHEME,
        "source_hashes": {"model.py": file_sha256(source, LEGACY_TEXT_HASH_SCHEME)},
    }
    assert verify_legacy_sources(record, tmp_path, ["model.py"], set()) == ["model.py"]
    source.write_text("coefficient = 1.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="migration refused"):
        verify_legacy_sources(record, tmp_path, ["model.py"], set())


@pytest.mark.parametrize('kind',['missing_executable','not_a_repository'])
def test_git_metadata_is_optional(monkeypatch,tmp_path,kind):
    from q1.provenance import git_commit
    def fail(*args,**kwargs):
        if kind=='missing_executable':
            raise FileNotFoundError('git')
        return subprocess.CompletedProcess(args[0],128,'','not a git repository')
    monkeypatch.setattr(subprocess,'run',fail)
    assert git_commit(tmp_path) is None


def test_git_metadata_does_not_borrow_an_ancestor_repository(monkeypatch,tmp_path):
    from q1.provenance import git_commit
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a[0],0,str(tmp_path.parent),' '))
    assert git_commit(tmp_path) is None


def test_source_guard_rejects_edits_but_accepts_lf_checkout(tmp_path):
    from q1.provenance import NUMERICAL_FILES, source_snapshot, verify_sources
    for name in NUMERICAL_FILES:
        target=tmp_path/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(Path(name).read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    snapshot=source_snapshot(tmp_path)
    for name in NUMERICAL_FILES:
        target=tmp_path/name
        target.write_bytes(target.read_bytes().replace(b'\r\n',b'\n'))
    match=verify_sources(snapshot,tmp_path)
    assert match['matches'] and match['raw_byte_differences']
    target=tmp_path/'q1/fvm.py'
    target.write_bytes(target.read_bytes()+b'\n# source changed after verification\n')
    with pytest.raises(ValueError,match='q1/fvm.py'):
        verify_sources(snapshot,tmp_path)
    del snapshot['source_hashes']['q1/archive.py']
    with pytest.raises(ValueError,match='scope'):
        verify_sources(snapshot,tmp_path)


def test_report_blocks_verified_artifacts_if_current_sources_changed(tmp_path):
    from q1.provenance import source_snapshot, artifact_sha256, HASH_SCHEME
    from q1.archive import write_json
    from q1.sensitivity_report import verified_runs
    snapshot=source_snapshot()
    snapshot['source_hashes']['q1/fvm.py']='0'*64
    write_json(tmp_path/'verification.json',{'status':'numerically_verified'})
    write_json(tmp_path/'manifest.json',{
        **snapshot,'status':'numerically_verified','artifact_hash_scheme':HASH_SCHEME,
        'verification_sha256':artifact_sha256(tmp_path/'verification.json'),'run_records':{}})
    with pytest.raises(ValueError,match='source'):
        verified_runs(tmp_path)
