#!/usr/bin/env python3
"""Build a local commit-fuzzer matrix without AWS/S3 state.

This script discovers tests from the solver-specific local corpus and splits
them into matrix jobs for the commit-fuzzer workflows.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import List, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def check_has_unsupported_commands(test_file: Path) -> bool:
    """Return True if a Z3 SMT2 test uses commands unsupported by CVC5."""
    try:
        content = test_file.read_text()
    except Exception:
        return False
    return bool(re.search(r"\(check-sat-using\b", content, re.IGNORECASE))


def discover_z3_tests(z3test_dir: str) -> List[str]:
    from scripts.z3.coverage.coverage_mapper import CoverageMapper

    z3test_path = Path(z3test_dir)
    mapper = CoverageMapper(z3test_dir=str(z3test_path))
    tests = [name for _, name in mapper.get_smt2_tests()]

    filtered: List[str] = []
    skip_tests = {"regressions/smt2/5731.smt2"}
    for test_name in tests:
        if test_name in skip_tests:
            continue
        test_file = z3test_path / test_name
        if test_file.exists() and check_has_unsupported_commands(test_file):
            continue
        filtered.append(test_name)
    return filtered


def discover_cvc5_tests(build_dir: str) -> List[str]:
    from scripts.cvc5.coverage.coverage_mapper import CoverageMapper

    mapper = CoverageMapper(build_dir=build_dir)
    return [name for _, name in mapper.get_ctest_tests()]


def maybe_limit_tests(tests: Sequence[str], limit_tests: int | None) -> List[str]:
    if limit_tests is None:
        return list(tests)
    if limit_tests < 1:
        raise ValueError("--limit-tests must be a positive integer")
    return list(tests[:limit_tests])


def build_jobs(
    tests: Sequence[str],
    tests_per_job: int | None,
    max_jobs: int | None,
    solver: str,
) -> tuple[list[dict], int]:
    total_tests = len(tests)
    if total_tests == 0:
        return [], 0

    if tests_per_job is not None and tests_per_job < 1:
        raise ValueError("--tests-per-job must be a positive integer")
    if max_jobs is not None and max_jobs < 1:
        raise ValueError("--max-jobs must be a positive integer")

    if tests_per_job is None:
        if max_jobs is None:
            tests_per_job = 1
        else:
            tests_per_job = max(1, math.ceil(total_tests / max_jobs))
    elif max_jobs is not None:
        calculated_jobs = math.ceil(total_tests / tests_per_job)
        if calculated_jobs > max_jobs:
            tests_per_job = max(1, math.ceil(total_tests / max_jobs))

    jobs: list[dict] = []
    for job_index in range(0, total_tests, tests_per_job):
        job_id = len(jobs) + 1
        job_tests = list(tests[job_index:job_index + tests_per_job])
        jobs.append(
            {
                "job_id": job_id,
                "job_name": f"{solver}-job-{job_id}",
                "tests": job_tests,
            }
        )

    return jobs, tests_per_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local commit-fuzzer matrix")
    parser.add_argument("solver", choices=["z3", "cvc5"], help="Solver name")
    parser.add_argument("--z3test-dir", default="z3test", help="Path to the z3test repository")
    parser.add_argument("--build-dir", default="build", help="Path to the solver build directory")
    parser.add_argument("--limit-tests", type=int, default=None, help="Cap the discovered test count")
    parser.add_argument("--tests-per-job", type=int, default=None, help="Number of tests per job")
    parser.add_argument("--max-jobs", type=int, default=None, help="Maximum number of jobs")
    parser.add_argument("--output", default="matrix.json", help="Output JSON file")
    args = parser.parse_args()

    if args.solver == "z3":
        tests = discover_z3_tests(args.z3test_dir)
    else:
        tests = discover_cvc5_tests(args.build_dir)

    tests = maybe_limit_tests(tests, args.limit_tests)
    jobs, tests_per_job = build_jobs(tests, args.tests_per_job, args.max_jobs, args.solver)

    matrix_data = {
        "matrix": {"include": jobs},
        "total_tests": len(tests),
        "total_jobs": len(jobs),
        "tests_per_job": tests_per_job,
        "solver": args.solver,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(matrix_data, f, indent=2)

    print(f"✅ Matrix written to {args.output}")
    print(f"Solver: {args.solver}")
    print(f"Total tests: {len(tests)}")
    print(f"Total jobs: {len(jobs)}")
    print(f"Tests per job: {tests_per_job}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
