"""Q4 reproduction entrypoint."""
import argparse
import subprocess
import sys
from pathlib import Path

from common.hashing import file_record
from q2.archive import write_json


def run(cmd):
    result = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    commands = [
        [sys.executable, "-m", "q4.run", "--data-root", args.data_root, "--workers", str(args.workers)],
        [sys.executable, "-m", "q4.run", "--data-root", args.data_root,
         "--cases", "main_appendix4_shrink_N10240", "space_appendix4_shrink_N20480",
         "main_appendix4_shrink_N20480", "method_appendix4_shrink_N5120_Radau",
         "--workers", str(args.workers)],
        [sys.executable, "-m", "q4.sensitivity", "--data-root", args.data_root,
         "--workers", str(args.workers)],
        [sys.executable, "-m", "q4.validation"],
        [sys.executable, "-m", "q4.export", "--data-root", args.data_root],
        [sys.executable, "-m", "q4.figures"],
        [sys.executable, "-m", "q4.reports"],
    ]
    log = []
    for command in commands:
        log.append({"command": command, "output": run(command)})
    path = Path("results/q4/reproduction.json")
    write_json(path, {"commands": log, "result4_hash": file_record("results/result4.xlsx")})
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
