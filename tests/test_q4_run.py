import pytest

from q2.inputs import read_config
from q4.run import cases


def test_q4_configured_cases_are_unique_and_include_formal():
    config = read_config("configs/q4.json")
    names = [case["name"] for case in cases(config)]
    assert len(names) == len(set(names))
    assert config["formal_case"] in names


def test_q4_unknown_case_property_rejected():
    config = read_config("configs/q4.json")
    config["cases"] = [{"name": "bad", "N": 4, "properties": "x", "radius": "fixed"}]
    with pytest.raises(ValueError):
        cases(config)

