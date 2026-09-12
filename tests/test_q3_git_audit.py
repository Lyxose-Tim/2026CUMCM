"""Exercise Git audit binding through real commits, including the audit commit."""
import json
import subprocess

import pytest

from q3.git_audit import AUDIT_PATH, checkout_identity, verify_git_binding


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def commit(root, message):
    git(root, "add", ".")
    git(root, "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid",
        "commit", "-m", message)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "中文路径"
    root.mkdir()
    git(root, "init")
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    commit(root, "source")
    return root


def test_audit_commit_and_fresh_clone_pass_without_stale_head(repository, tmp_path):
    identity = checkout_identity(repository)
    record = {"audited_content_commit": identity["code_commit"], "git_tree": identity["git_tree"]}
    audit_file = repository / AUDIT_PATH
    audit_file.parent.mkdir(parents=True)
    audit_file.write_text(json.dumps(record), encoding="utf-8")
    commit(repository, "audit record")
    current = verify_git_binding(record, repository)
    assert current["code_commit"] != identity["code_commit"]
    assert current["code_commit"] == git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    clone = tmp_path / "fresh-clone"
    git(tmp_path, "clone", "--quiet", str(repository), str(clone))
    assert verify_git_binding(record, clone) == current


def test_changed_committed_content_rejects_stale_audit(repository):
    identity = checkout_identity(repository)
    record = {"audited_content_commit": identity["code_commit"], "git_tree": identity["git_tree"]}
    # Even a file outside the Q3 artifact list changes the committed tree.
    (repository / "README.md").write_text("changed delivery\n", encoding="utf-8")
    commit(repository, "changed content")
    with pytest.raises(ValueError, match="committed tree"):
        verify_git_binding(record, repository)


@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked"])
def test_uncommitted_content_cannot_be_bound_to_head(repository, state):
    name = "new.py" if state == "untracked" else "source.py"
    (repository / name).write_text("value = 2\n", encoding="utf-8")
    if state == "staged":
        git(repository, "add", name)
    with pytest.raises(ValueError, match="Uncommitted"):
        checkout_identity(repository)


def test_source_zip_explicitly_skips_git_binding(tmp_path):
    record = {"audited_content_commit": None, "git_tree": {"sha256": "archive-origin"}}
    assert verify_git_binding(record, tmp_path) is None


def test_git_checkout_cannot_fall_back_to_zip_on_git_failure(repository, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "")
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    with pytest.raises(ValueError, match="Cannot read Git"):
        checkout_identity(repository)


def test_legacy_commit_record_is_rejected(repository):
    with pytest.raises(ValueError, match="Legacy"):
        verify_git_binding({"code_commit": "old"}, repository)


def test_git_checkout_rejects_missing_git_binding(repository):
    with pytest.raises(ValueError, match="tree origin"):
        verify_git_binding({"git_tree": None}, repository)
