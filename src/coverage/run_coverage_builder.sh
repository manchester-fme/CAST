#!/bin/bash
# Run coverage analysis for a range of tests. Thin wrapper around CAST's
# shared, solver-agnostic src/coverage/coverage_mapper.py - all solver-
# specific behavior comes from <solver_dir>/manifest.json's
# list_tests_command/run_test_command, not from this script or any
# per-solver code (there is none: solver_dir only needs manifest.json +
# build.sh).
#
# Usage: ./run_coverage_builder.sh <solver> <solver_dir> <start_index> <end_index>
# Example: ./run_coverage_builder.sh cvc5 cvc5/.cast 1 50

set -e

SOLVER="$1"
SOLVER_DIR="$2"
START_INDEX="$3"
END_INDEX="$4"

echo "Running coverage analysis for tests ${START_INDEX}-${END_INDEX}"

# Set test timeout environment variable (120 seconds = 2 minutes) - read by
# some solvers' own build/test tooling (e.g. cvc5's CTest TIMEOUT property,
# set at configure time in build.sh); harmless no-op for solvers that don't.
export TEST_TIMEOUT=120

# Run from $GITHUB_WORKSPACE (repo root, our default cwd here) - the
# manifest's list_tests_command/run_test_command are written expecting that
# cwd and cd into $SOLVER/build themselves where needed (e.g. cvc5's ctest
# commands), since z3's needs the z3test checkout as a repo-root sibling.
python3 "$GITHUB_WORKSPACE/src/coverage/coverage_mapper.py" \
    --solver "$SOLVER" \
    --solver-dir "$SOLVER_DIR" \
    --start-index "${START_INDEX}" \
    --end-index "${END_INDEX}"

echo "Coverage analysis completed"
