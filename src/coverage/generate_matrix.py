#!/usr/bin/env python3
"""
Generate the dynamic coverage-mapping job matrix for any solver. Test
discovery is the manifest's list_tests_command (see coverage_mapper.py,
which owns list_tests/load_manifest - reused here so there's exactly one
place that knows how to run it); job-count math is
coverage_mapper_utils.calculate_jobs, tuned per-solver via the manifest's
target_jobs/avg_test_time_seconds. Nothing here branches on which solver is
being mapped.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coverage_mapper import list_tests, load_manifest
from coverage_mapper_utils import calculate_jobs


def generate_matrix(solver: str, solver_dir, max_job_time_minutes: int = 360, buffer_minutes: int = 60):
    manifest = load_manifest(solver_dir)
    tests = list_tests(manifest)

    if not tests:
        print("❌ No tests found", file=sys.stderr)
        return {'matrix': {'include': []}, 'total_tests': 0, 'total_jobs': 0}

    total_tests = len(tests)

    total_jobs, tests_per_job = calculate_jobs(
        total_tests,
        target_jobs=manifest['target_jobs'],
        max_job_time_minutes=max_job_time_minutes,
        buffer_minutes=buffer_minutes,
        avg_test_time_seconds=manifest['avg_test_time_seconds'],
    )

    print(f"Total jobs: {total_jobs}, Tests per job: {tests_per_job}", file=sys.stderr)

    matrix_entries = []
    for job_id in range(1, total_jobs + 1):
        start_index = (job_id - 1) * tests_per_job + 1
        end_index = min(job_id * tests_per_job, total_tests)
        matrix_entries.append({
            'job_name': f'{solver}-job{job_id}',
            'start_index': start_index,
            'end_index': end_index
        })

    return {
        'matrix': {'include': matrix_entries},
        'total_tests': total_tests,
        'total_jobs': total_jobs,
        'tests_per_job': tests_per_job
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate the dynamic coverage-mapping job matrix for a solver')
    parser.add_argument('--solver', required=True, help='Solver name (e.g. cvc5, z3)')
    parser.add_argument('--solver-dir', required=True, type=Path,
                         help='Directory containing manifest.json for this solver')
    parser.add_argument('--max-job-time', type=int, default=360, help='Maximum time per job in minutes')
    parser.add_argument('--buffer', type=int, default=60, help='Buffer time for setup/teardown in minutes')
    parser.add_argument('--output', default='matrix.json', help='Output JSON file')

    args = parser.parse_args()

    result = generate_matrix(
        solver=args.solver,
        solver_dir=args.solver_dir,
        max_job_time_minutes=args.max_job_time,
        buffer_minutes=args.buffer,
    )

    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"✅ Matrix written to {args.output}")
    print(f"Total tests: {result['total_tests']}, Total jobs: {result['total_jobs']}")
