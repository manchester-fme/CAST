#!/bin/bash
# Run coverage analysis for a range of tests (CAST-owned, solver-agnostic
# wrapper). Delegates to <solver_dir>/coverage/coverage_mapper.py, which
# stays per-solver since test discovery/execution genuinely differs between
# solvers (e.g. cvc5's CTest introspection vs z3's SMT2 file walking).
#
# Usage: ./run_coverage_builder.sh <solver> <solver_dir> <start_index> <end_index>
# Example: ./run_coverage_builder.sh cvc5 cvc5/.cast 1 50

set -e

SOLVER="$1"
SOLVER_DIR="$2"
START_INDEX="$3"
END_INDEX="$4"

echo "Running coverage analysis for tests ${START_INDEX}-${END_INDEX}"

# Set test timeout environment variable (120 seconds = 2 minutes)
export TEST_TIMEOUT=120

# Change to build directory
cd "$SOLVER/build"

# Run coverage analysis
python3 "$GITHUB_WORKSPACE/$SOLVER_DIR/coverage/coverage_mapper.py" \
    --build-dir . \
    --start-index "${START_INDEX}" \
    --end-index "${END_INDEX}"

echo "Coverage analysis completed"
