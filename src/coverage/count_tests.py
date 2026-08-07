#!/usr/bin/env python3
"""
Generic test-counting utility, shared by every solver. Reuses
coverage_mapper's list_tests/load_manifest so the count always matches what
coverage-mapper.yml itself would discover and slice into jobs.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coverage_mapper import list_tests, load_manifest


def count_tests(solver: str, solver_dir: Path) -> Dict:
    """
    Count a solver's tests via its manifest's list_tests_command.

    Args:
        solver: Solver name (e.g. cvc5, z3) - also the checkout dir name
        solver_dir: Directory containing manifest.json for this solver

    Returns:
        Dictionary with test_count, commit_hash, and solver_version
    """
    manifest = load_manifest(solver_dir)
    tests = list_tests(manifest)

    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=Path(solver),
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to get {solver} commit hash: {e}", file=sys.stderr)
        commit_hash = "unknown"

    return {
        'test_count': len(tests),
        'commit_hash': commit_hash,
        'solver_version': 'main'
    }


def main():
    parser = argparse.ArgumentParser(
        description='Count tests for any manifest-driven solver',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 src/coverage/count_tests.py --solver cvc5 --solver-dir cvc5/.cast --output test-count.json
  python3 src/coverage/count_tests.py --solver z3 --solver-dir src/solvers/z3 --output test-count.json
        """
    )

    parser.add_argument('--solver', required=True, help='Solver name (e.g. cvc5, z3)')
    parser.add_argument('--solver-dir', required=True, type=Path,
                         help='Directory containing manifest.json for this solver')
    parser.add_argument('--output', type=Path, help='Output JSON file path (prints to stdout if not specified)')

    args = parser.parse_args()

    print(f"Counting {args.solver} tests...", file=sys.stderr)
    result = count_tests(args.solver, args.solver_dir)
    print(f"✅ Found {result['test_count']} tests at commit {result['commit_hash'][:8]}", file=sys.stderr)

    output_json = json.dumps(result, indent=2)

    if args.output:
        args.output.write_text(output_json)
        print(f"✅ Results written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == '__main__':
    sys.exit(main())
