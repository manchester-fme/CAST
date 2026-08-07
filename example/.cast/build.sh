#!/bin/bash
# YOUR_SOLVER build script.
#
# CAST calls this with:
#   build.sh                       -> production build
#   build.sh --static              -> static production binary (used for fuzzing)
#   build.sh --coverage            -> debug build with coverage instrumentation
#   build.sh --static --coverage   -> both
#
# It must leave a runnable binary at the path declared in cast.yml's
# binary_path input and manifest.json's fuzzer.target_binary_path.

set -e

ENABLE_COVERAGE=false
ENABLE_STATIC=false
for arg in "$@"; do
    case "$arg" in
        --coverage) ENABLE_COVERAGE=true ;;
        --static) ENABLE_STATIC=true ;;
    esac
done

# 1. Install build dependencies.
# sudo apt-get update && sudo apt-get install -y YOUR_BUILD_DEPS

# 2. Clone your solver if it isn't already checked out.
SOLVER_DIR="YOUR_SOLVER"
if [ ! -d "$SOLVER_DIR" ]; then
    git clone "https://github.com/YOUR_ORG/YOUR_SOLVER.git" "$SOLVER_DIR"
fi
cd "$SOLVER_DIR"

# 3. If coverage is requested, install whatever coverage tooling your
#    build needs (fastcov is required - CAST's coverage engine parses its
#    output) and set any env vars your build system expects.
# if [ "$ENABLE_COVERAGE" = "true" ]; then
#     pip3 install fastcov psutil
# fi

# 4. Configure and build, branching on $ENABLE_COVERAGE/$ENABLE_STATIC
#    however your build system needs it, e.g.:
# if [ "$ENABLE_COVERAGE" = "true" ]; then
#     ./configure.sh debug --coverage
# elif [ "$ENABLE_STATIC" = "true" ]; then
#     ./configure.sh production --static
# else
#     ./configure.sh production
# fi
# cd build && make -j"$(nproc)"

echo "✅ Build complete"
