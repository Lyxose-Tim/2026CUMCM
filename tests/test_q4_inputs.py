import numpy as np
import pytest

from q4.inputs import RadiusHistory


def test_radius_history_linear_and_fixed():
    history = RadiusHistory(np.array([[0.0, 0.02], [10.0, 0.01]]))
    assert history(5.0) == pytest.approx(0.015)
    fixed = RadiusHistory(history.observations, fixed=True)
    assert fixed(np.array([0.0, 5.0, 10.0])).tolist() == [0.02, 0.02, 0.02]


def test_radius_history_rejects_growth():
    with pytest.raises(ValueError):
        RadiusHistory(np.array([[0.0, 0.02], [10.0, 0.021]]))

