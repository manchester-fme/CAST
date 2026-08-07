#!/usr/bin/env python3
"""
Generic coverage mapper shared by every solver, CAST-maintained or
fork-hosted. Test discovery and single-test execution are opaque,
manifest-declared shell commands (coverage.list_tests_command /
run_test_command in <solver-dir>/manifest.json) - this script has no
per-solver knowledge and never branches on which solver it's mapping.
Coverage extraction itself (fastcov parsing, demangling, memory
bookkeeping) is genuinely solver-independent and lives in
coverage_mapper_utils.py.

Usage:
    python3 coverage_mapper.py --solver cvc5 --solver-dir cvc5/.cast \\
        --start-index 1 --end-index 50
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coverage_mapper_utils import (
    check_memory_limit,
    cleanup_memory,
    extract_coverage_data,
    get_memory_usage_mb,
    reset_coverage_counters,
    write_intermediate_mapping,
)

MAX_MEMORY_MB = 10000  # 10GB limit
MEMORY_CHECK_INTERVAL = 50  # Check every 50 tests


def load_manifest(solver_dir: Path) -> Dict:
    return json.loads((solver_dir / 'manifest.json').read_text())['coverage']


def list_tests(manifest: Dict) -> List[str]:
    """Run the manifest's list_tests_command. Each line of stdout is one
    test identifier, in stable order - that order is what start/end-index
    slicing is relative to."""
    result = subprocess.run(manifest['list_tests_command'], shell=True,
                             capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running list_tests_command: {result.stderr}")
        sys.stdout.flush()
        return []
    tests = [line for line in result.stdout.splitlines() if line.strip()]
    print(f"Found {len(tests)} tests")
    sys.stdout.flush()
    return tests


def run_test(manifest: Dict, test_name: str) -> bool:
    """Run the manifest's run_test_command for one test, with {test}
    substituted (shell-quoted). Exit 0 means the test passed and coverage
    should be attributed to it."""
    command = manifest['run_test_command'].replace('{test}', shlex.quote(test_name))
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
    return result.returncode == 0


def process_tests(manifest: Dict, build_dir: Path, tests: List[str]) -> str:
    """Process tests sequentially with streaming to disk to avoid memory issues"""
    demangle_cache: Dict[str, str] = {}
    temp_file = build_dir / "coverage_temp.json"
    function_to_tests: Dict[str, List[str]] = {}

    print(f"🚀 Processing {len(tests)} tests")
    print(f"💾 Memory limit: {MAX_MEMORY_MB}MB")
    sys.stdout.flush()

    for i, test_name in enumerate(tests, 1):
        print(f"Test {i}/{len(tests)}: {test_name}")
        sys.stdout.flush()

        if i % MEMORY_CHECK_INTERVAL == 0:
            if not check_memory_limit(MAX_MEMORY_MB):
                print(f"🛑 Stopping at test {i} due to memory limit")
                sys.stdout.flush()
                break
            cleanup_memory(demangle_cache)
            print(f"💾 Memory usage: {get_memory_usage_mb():.1f}MB")
            sys.stdout.flush()

        for gcda in build_dir.rglob("*.gcda"):
            gcda.unlink()
        reset_coverage_counters(build_dir)

        start_time = time.time()
        passed = run_test(manifest, test_name)
        execution_time = round(time.time() - start_time, 2)

        if not passed:
            print(f"❌ {test_name} - {execution_time}s")
            sys.stdout.flush()
            continue

        coverage_data = extract_coverage_data(build_dir, test_name, demangle_cache)
        if coverage_data:
            print(f"✅ {test_name} - {len(coverage_data['functions'])} functions - {execution_time}s")
            for func in coverage_data['functions']:
                function_to_tests.setdefault(func, []).append(test_name)
        else:
            print(f"❌ {test_name} - {execution_time}s")
        sys.stdout.flush()

        cleanup_memory(demangle_cache)

        if i % 100 == 0:
            write_intermediate_mapping(function_to_tests, temp_file)

    write_intermediate_mapping(function_to_tests, temp_file)
    return str(temp_file)


def run(manifest: Dict, build_dir: Path, start_index: Optional[int], end_index: Optional[int]):
    print("🔍 Discovering tests...")
    sys.stdout.flush()
    tests = list_tests(manifest)

    if not tests:
        print("❌ No tests found")
        sys.stdout.flush()
        return

    if start_index is not None and end_index is not None:
        start_idx = max(0, start_index - 1)
        end_idx = min(len(tests), end_index)
        tests = tests[start_idx:end_idx]
        print(f"🔍 Selected tests {start_index}-{end_index}: {len(tests)} tests")
        sys.stdout.flush()

    temp_file = process_tests(manifest, build_dir, tests)

    if not temp_file or not Path(temp_file).exists():
        print("❌ No coverage data generated")
        sys.stdout.flush()
        return

    output_name = (f"coverage_mapping_{start_index}_{end_index}.json"
                    if start_index is not None else "coverage_mapping.json")
    # Written inside build_dir (not cwd) - coverage-mapper.yml's "Upload
    # coverage mapping" step picks it up at $SOLVER/build/<output_name>.
    output_file = build_dir / output_name
    Path(temp_file).rename(output_file)

    with open(output_file, 'r') as f:
        coverage_mapping = json.load(f)

    print(f"📄 Coverage mapping saved to {output_file}")
    print(f"📊 Total functions: {len(coverage_mapping)}")
    print(f"📊 Total tests: {len(tests)}")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description='Generic manifest-driven coverage mapper')
    parser.add_argument('--solver', required=True, help='Solver name (e.g. cvc5, z3) - its build dir is <solver>/build')
    parser.add_argument('--solver-dir', required=True, type=Path, help='Directory containing manifest.json for this solver')
    parser.add_argument('--start-index', type=int, help='Start index for test range (1-based, inclusive)')
    parser.add_argument('--end-index', type=int, help='End index for test range (1-based, inclusive)')

    args = parser.parse_args()

    manifest = load_manifest(args.solver_dir)
    build_dir = Path(args.solver) / 'build'

    run(manifest, build_dir, args.start_index, args.end_index)


if __name__ == "__main__":
    main()
