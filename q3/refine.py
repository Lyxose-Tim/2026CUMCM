"""Additional N=40960 cases after the initial three-grid event comparison."""
import argparse
from q3.run import compute

EXTRA_CASES = [
    {"name": "base_N40960", "N": 40960},
    {"name": "tight_N40960", "N": 40960, "tight": True, "half_step": True},
]

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--directory",default="results/q3")
    args=parser.parse_args()
    # Sequential: a very fine full-state history can require several GB.
    for case in EXTRA_CASES:
        print(compute(args.data_root,args.directory,case),flush=True)
