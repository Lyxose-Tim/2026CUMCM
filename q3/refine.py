"""Additional N=40960 cases after the initial three-grid event comparison."""
import argparse
from q3.run import compute
from q2.inputs import read_config

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-root",required=True)
    parser.add_argument("--directory",default="results/q3")
    args=parser.parse_args()
    # Sequential: a very fine full-state history can require several GB.
    for case in read_config("configs/q3.json")["refinement_cases"]:
        print(compute(args.data_root,args.directory,case),flush=True)
