import numpy as np
import pytest
from openpyxl import Workbook

from q4.inputs import RadiusHistory, read_radius


def test_radius_history_linear_and_fixed():
    history = RadiusHistory(np.array([[0.0, 0.02], [10.0, 0.01]]))
    assert history(5.0) == pytest.approx(0.015)
    fixed = RadiusHistory(history.observations, fixed=True)
    assert fixed(np.array([0.0, 5.0, 10.0])).tolist() == [0.02, 0.02, 0.02]


def test_fixed_radius_can_extend_without_extrapolating_attachment_history():
    fixed = RadiusHistory(
        np.array([[0.0, 0.02], [10.0, 0.01]]), fixed=True, horizon_s=20.0
    )
    assert fixed(20.0) == pytest.approx(0.02)
    assert fixed.breaks.tolist() == [0.0, 10.0, 20.0]
    with pytest.raises(ValueError, match="extrapolated"):
        RadiusHistory(np.array([[0.0, 0.02], [10.0, 0.01]]), horizon_s=20.0)


def test_pchip_radius_hits_observations_and_stays_monotone():
    observations = np.array([
        [0.0, 0.0200], [10.0, 0.0187], [20.0, 0.0180], [30.0, 0.0161]
    ])
    history = RadiusHistory(observations, interpolation="pchip")
    np.testing.assert_allclose(history(observations[:, 0]), observations[:, 1], rtol=0, atol=1e-15)
    dense = history(np.linspace(0.0, 30.0, 1001))
    assert np.all(dense > 0)
    assert np.all(np.diff(dense) <= 1e-12)


def test_radius_history_rejects_growth():
    with pytest.raises(ValueError):
        RadiusHistory(np.array([[0.0, 0.02], [10.0, 0.021]]))


def test_radius_attachment_endpoint_is_checked_independently(tmp_path):
    path = tmp_path / "radius.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["时间", "半径"])
    for index in range(145):
        sheet.append([index * 1800, 2.0 - index * 0.005])
    workbook.save(path)
    history = read_radius(path, 259200)
    assert history.observations[-1, 0] == 259200
    with pytest.raises(ValueError, match="observation endpoint"):
        read_radius(path, 14400)

