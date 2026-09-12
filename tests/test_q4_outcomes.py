import numpy as np
import pytest
from scipy.sparse import diags

from q2.inputs import LongEnvironment
from q4.inputs import RadiusHistory
from q4.model import material_grid
from q4.solver import StrictPostStateUnavailable, ThresholdNotReached, integrate_event


class UniformDecayModel:
    def __init__(self, horizon_s):
        rows = np.c_[np.arange(241) * 60.0, np.full(241, 28.0), np.full(241, 0.01)]
        self.environment = LongEnvironment(rows, 14400.0)
        self.radius = RadiusHistory(
            np.array([[0.0, 0.02], [horizon_s, 0.02]]), fixed=True
        )
        self.grid = material_grid(4, 0.25)
        self.p = {"T0": 28.0, "C0": 1.0, "hm": 0.0}

    def rhs(self, _t, y):
        n = self.grid.N + 1
        return np.r_[np.zeros(n), -0.1 * y[n:]]

    def jac(self, _t, _y):
        n = self.grid.N + 1
        return diags(np.r_[np.zeros(n), np.full(n, -0.1)], format="csc")


SETTINGS = {
    "method": "BDF", "rtol": 1e-8, "atol_T": 1e-10, "atol_C": 1e-10,
    "max_step_observed": 0.05, "max_step_extended": 0.05,
}


def event_config(threshold, strict_offset_s=0.1):
    return {
        "threshold": threshold,
        "root_xtol_s": 1e-9,
        "bracket_width_s": 1e-7,
        "strict_offset_s": strict_offset_s,
    }


def test_threshold_not_reached_preserves_terminal_evidence():
    with pytest.raises(ThresholdNotReached) as caught:
        integrate_event(
            UniformDecayModel(1.0), SETTINGS, event_config(0.15),
            fixed_radius_m=np.array([0.0, 0.02]),
        )
    result = caught.value.result
    assert result["outcome"] == "threshold_not_reached"
    assert result["terminal"]["time_s"] == pytest.approx(1.0)
    assert result["terminal"]["g"] > 0
    assert result["terminal_state"].shape == (10,)
    assert result["trace"].shape[0] > 0


def test_root_without_strict_post_state_has_distinct_type():
    crossing = -np.log(0.9) / 0.1
    with pytest.raises(StrictPostStateUnavailable) as caught:
        integrate_event(
            UniformDecayModel(crossing + 0.02), SETTINGS,
            event_config(0.9, strict_offset_s=0.1),
            fixed_radius_m=np.array([0.0, 0.02]),
        )
    result = caught.value.result
    assert result["outcome"] == "root_found_post_state_unavailable"
    assert result["root"]["time_s"] == pytest.approx(crossing, abs=2e-6)
    assert result["near_states"].shape[0] == 0
