"""Fresh-process final solve; compare all internal nodes at every saved second."""
import argparse
import json
from pathlib import Path

import numpy as np

from .archive import write_json
from .export import verified_source
from .fvm import Grid,RadialModel
from .inputs import read_inputs
from .solver import integrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--directory",default="results/q1")
    args = parser.parse_args()
    data,g,m,v = verified_source(args.directory)
    env,inputs = read_inputs(args.data_root,m["configuration"])
    if inputs["sha256"] != m["inputs"]["sha256"]:
        raise ValueError("Reproduction input version differs")
    grid = Grid(m["N"],m["configuration"]["parameters"]["R"],m["configuration"]["parameters"]["L"])
    sol = integrate(RadialModel(grid,m["configuration"]["parameters"],env),m["solver"]["settings"],check_envelope=True)
    errors = {}
    for key,actual in [("temperature_C",sol.temperature_C),("moisture",sol.moisture)]:
        # Chunk the comparison to bound additional memory at the largest mesh.
        errors[key] = max(float(np.max(abs(actual[start:start+100]-data[key][start:start+100]))) for start in range(0,1801,100))
    passed = errors["temperature_C"] <= m["configuration"]["budgets"]["time_T"] and errors["moisture"] <= m["configuration"]["budgets"]["time_C"]
    result = {"passed":passed,"N":grid.N,"times_compared":1801,"radii_compared":grid.N+1,"full_internal_grid_max_abs":errors,"input_sha256":inputs["sha256"],"solver":sol.diagnostics,"command":"python -m q1.reproduce --data-root <path-to-A题>"}
    write_json(Path(args.directory)/"reproduction.json",result)
    print(json.dumps(result),flush=True)
    if not passed:
        raise RuntimeError("Reproduction failed")


if __name__ == "__main__":
    main()
