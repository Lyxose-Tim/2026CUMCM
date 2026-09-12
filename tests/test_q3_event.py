import numpy as np
import pytest

from q3.solver import full_max, locate, output_axis


def test_off_center_maximum_controls_event():
    # The surface and center are already dry; an interior node remains wet.
    def dense(t):
        return np.r_[np.full(4, 50.0), [0.1, 0.3-0.01*t, 0.11, 0.06]]
    root, bracket, signs = locate(dense, 0, 20, 4, 0.15, 1e-6, 1e-5)
    assert root == pytest.approx(15, abs=1e-6)
    assert full_max(dense(root), 4)[1] == 1
    assert bracket[1]-bracket[0] <= 1e-5
    assert signs[0] > 0 and signs[1] <= 0


def test_maximum_can_switch_nodes_without_changing_rule():
    def dense(t):
        return np.r_[np.full(3, 50.0), [0.3-0.01*t, 0.25-0.005*t, 0.06]]
    assert full_max(dense(0), 3)[1] == 0
    root, _, _ = locate(dense, 0, 21, 3, 0.15, 1e-6, 1e-5)
    assert root == pytest.approx(20, abs=1e-6)
    assert full_max(dense(root), 3)[1] == 1


@pytest.mark.parametrize("bad", [np.nan, np.inf, 0.0, -0.1])
def test_invalid_state_is_never_an_event(bad):
    with pytest.raises(ValueError):
        full_max(np.array([50, 50, 0.2, bad]), 2)


def test_output_endpoints_exact_and_deduplicated():
    np.testing.assert_array_equal(output_axis(120, 60), [60, 120])
    endpoint = np.nextafter(120.0, np.inf)
    assert output_axis(endpoint, 60)[-1] == endpoint
    assert len(output_axis(endpoint, 60)) == 3
    np.testing.assert_array_equal(output_axis(125.3, 60), [60, 120, 125.3])


def test_upward_crossing_is_rejected():
    with pytest.raises(ValueError, match="downward"):
        locate(lambda t: np.array([50., 0.1+0.01*t]), 0, 10, 1, 0.15, 1e-6, 1e-5)
