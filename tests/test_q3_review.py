"""Regression cases for the PR #7 provenance and configuration review."""
import copy
import subprocess
import sys

import pytest

from q2.inputs import read_config
from q2.provenance import git_commit
from q3.run import cases


def test_final_config_selects_configured_refinement_case():
    config = read_config("configs/q3.json")
    assert config["formal_case"] == "tight_N40960"
    configured = {case["name"]: case for case in cases(config)}
    assert configured[config["formal_case"]]["N"] == config["grids"][-1]
    assert set(c["name"] for c in config["refinement_cases"]) <= configured.keys()
    assert len(configured) == len(cases(config)) == 13


def test_refinement_case_comes_from_config():
    config = read_config("configs/q3.json")
    config = copy.deepcopy(config)
    config["formal_case"] = "review_tight"
    config["refinement_cases"][-1]["name"] = "review_tight"
    config["temporal_comparisons"][-1][-1] = "review_tight"
    assert "review_tight" in {case["name"] for case in cases(config)}


def test_unknown_formal_case_is_rejected():
    config = read_config("configs/q3.json")
    config["formal_case"] = "missing"
    with pytest.raises(ValueError, match="formal_case"):
        cases(config)


def test_git_failure_with_non_ascii_stderr_is_quiet(tmp_path, monkeypatch, capfd):
    (tmp_path / ".git").mkdir()
    real_run = subprocess.run

    def failed_git(command, **kwargs):
        return real_run([sys.executable, "-c",
                         "import sys; sys.stderr.buffer.write(bytes([0xe6, 0xb5, 0x8b])); sys.exit(128)"],
                        **kwargs)

    monkeypatch.setattr("q2.provenance.subprocess.run", failed_git)
    assert git_commit(tmp_path) is None
    captured = capfd.readouterr()
    assert captured.out == captured.err == ""
