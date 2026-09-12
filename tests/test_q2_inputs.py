import numpy as np

from q2.inputs import LongEnvironment


def observations():
    t = np.arange(0, 14401, 60, dtype=float)
    return np.c_[t, 28 + t / 1000, 0.02 + t / 1e6]


def test_long_environment_modes_and_bounds():
    values = observations()
    mean = LongEnvironment(values, 259200, "last_hour_mean", 10800)
    terminal = LongEnvironment(values, 259200, "terminal_hold", 10800)
    nominal = LongEnvironment(values, 259200, "nominal", 10800)
    expected = values[values[:, 0] >= 10800, 1:].mean(axis=0)
    assert np.allclose(mean(200000), expected)
    assert np.allclose(terminal(200000), values[-1, 1:])
    assert np.allclose(nominal(200000), [50.0, 0.05])
    loT, hiT, loC, hiC = mean.history_extrema(200000)
    assert loT == values[:, 1].min()
    assert hiT == max(values[:, 1].max(), expected[0])
    assert loC == values[:, 2].min()
    assert hiC == max(values[:, 2].max(), expected[1])


def test_observation_knots_are_reproduced_exactly():
    values = observations()
    environment = LongEnvironment(values, 259200)
    temperature, moisture = environment(values[:, 0])
    assert np.array_equal(temperature, values[:, 1])
    assert np.array_equal(moisture, values[:, 2])
