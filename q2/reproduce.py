"""Reproduce Q2 numerical results, workbook, figures, and reports in order."""
import argparse
from pathlib import Path
import subprocess
import sys


def run(command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    run([sys.executable, "-m", "q2.run", "--data-root", args.data_root])
    run([sys.executable, "-m", "q2.export", "--node", args.node])
    run([sys.executable, "-m", "q2.figures"])
    run([sys.executable, "-m", "q2.reports"])


if __name__ == "__main__":
    main()
