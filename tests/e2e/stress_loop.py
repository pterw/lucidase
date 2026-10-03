"""Stress loop (not a test; no test_ prefix, so pytest never collects it).

Starts one CPU-burner process per core, runs the given e2e files repeatedly
and prints the failure rate. Stdlib only. Always kills the burners.

    python tests/e2e/stress_loop.py --runs 6 --budget 270 [pytest args or files]
"""

from __future__ import annotations

import argparse
import multiprocessing
import subprocess
import sys
import time

DEFAULT_FILES = [
    "tests/e2e/test_inheritance.py",
    "tests/e2e/test_ui_honesty.py",
    "tests/e2e/test_web_adversarial.py",
]


def _burn() -> None:
    while True:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=6)
    ap.add_argument("--budget", type=float, default=270.0, help="seconds, hard stop")
    ap.add_argument("--burners", type=int, default=multiprocessing.cpu_count())
    ap.add_argument("files", nargs="*", default=DEFAULT_FILES)
    args = ap.parse_args()

    burners = [multiprocessing.Process(target=_burn, daemon=True) for _ in range(args.burners)]
    for b in burners:
        b.start()
    start = time.monotonic()
    done = failed = 0
    try:
        for i in range(args.runs):
            if time.monotonic() - start > args.budget:
                print("budget exhausted", flush=True)
                break
            left = max(30.0, args.budget - (time.monotonic() - start))
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args.files],
                    capture_output=True, text=True, timeout=left,
                )
                code, tail = r.returncode, (r.stdout.strip().splitlines() or [""])[-1]
                fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
            except subprocess.TimeoutExpired:
                print(f"run {i + 1}: cut off by the time budget (not counted)", flush=True)
                break
            done += 1
            failed += code != 0
            print(f"run {i + 1}: exit={code} {tail}", flush=True)
            for ln in fails:
                print("   ", ln[:200], flush=True)
    finally:
        for b in burners:
            b.kill()
            b.join()
    print(f"RESULT runs={done} failed_runs={failed} burners={args.burners}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
