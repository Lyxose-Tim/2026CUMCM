import pytest

from q2.inputs import read_config
from q4.run import cases
from q4.sensitivity import scenario_cases


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


def test_q4_validation_groups_change_one_numerical_setting_at_a_time():
    config = read_config("configs/q4.json")
    configured = {case["name"]: case for case in cases(config)}
    spatial = [configured[name] for name in config["validation"]["spatial_group"]]
    for left, right in zip(spatial[:-1], spatial[1:]):
        differing = {key for key in left | right if left.get(key) != right.get(key)}
        assert differing <= {"name", "N"}
    temporal = [configured[name] for name in config["validation"]["temporal_group"]]
    differing = {key for key in temporal[0] | temporal[1] if temporal[0].get(key) != temporal[1].get(key)}
    assert differing <= {"name", "tolerance_scale", "max_step_scale"}


def test_q4_sensitivity_radius_offsets_match_record_precision():
    main = read_config("configs/q4.json")
    sensitivity = read_config("configs/q4_sensitivity.json")
    configured = scenario_cases(main, sensitivity)
    offsets = sorted(case["radius_offset_cm"] for case in configured if "radius_offset_cm" in case)
    assert offsets == [-0.0005, 0.0005]

