#!/usr/bin/env python3
"""Fake solver that always answers 'unknown', simulating a broken/invalid
install for check_solver_installed()'s smoke test (see fake_solver_lib.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_solver_lib import run  # noqa: E402

if __name__ == "__main__":
    run("target", default="unknown")
