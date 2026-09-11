from types import SimpleNamespace

import numpy as np

from q1.fvm import Grid
from q2.archive import load_archive, save_archive


def test_chunked_archive_round_trip_includes_final_internal_state(tmp_path):
    grid = Grid(20)
    times = np.arange(5, dtype=float)
    temperature = np.arange(105, dtype=float).reshape(5, 21)
    moisture = 1.0 + temperature / 1000
    final_state = np.r_[temperature[-1], moisture[-1]]
    solution = SimpleNamespace(
        times=times, temperature_C=temperature, moisture=moisture,
        final_state=final_state,
    )
    save_archive(tmp_path, solution, grid, {"status": "test"}, chunk_rows=2)
    data, geometry, manifest = load_archive(tmp_path)
    assert np.array_equal(data["time_s"], times)
    assert np.array_equal(data["temperature_C"], temperature)
    assert np.array_equal(data["moisture"], moisture)
    assert np.array_equal(geometry["final_temperature_C"], temperature[-1])
    assert np.array_equal(geometry["final_moisture"], moisture[-1])
    assert len(manifest["chunks"]) == 3
