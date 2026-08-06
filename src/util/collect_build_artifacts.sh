#!/bin/bash
# Collect a solver's build artifacts for libclang parsing (CAST-owned,
# solver-agnostic - see src/util/extract_build_artifacts.sh, its unpacking
# counterpart). Collects:
# - All header files (.h, .hpp, .hxx) from build directory with preserved paths
# - The solver binary, normalized to bin/<basename> in the archive regardless
#   of where it actually lives in the build dir (e.g. cvc5: build/bin/cvc5,
#   z3: build/z3 - both end up packed as bin/cvc5 / bin/z3)
# - compile_commands.json
#
# Usage: ./collect_build_artifacts.sh <build_dir> <output_dir> <binary_relpath>
# Example: ./collect_build_artifacts.sh cvc5/build artifacts bin/cvc5
#
# binary_relpath is the solver's build-relative binary path (manifest.json's
# fuzzer.target_binary_path with the leading "./build/" stripped).

set -e

BUILD_DIR="${1}"
OUTPUT_DIR="${2}"
BINARY_RELPATH="${3}"

if [ -z "$BUILD_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$BINARY_RELPATH" ]; then
    echo "Error: build_dir, output_dir, and binary_relpath are all required"
    exit 1
fi

if [ ! -d "$BUILD_DIR" ]; then
    echo "Error: Build directory not found: $BUILD_DIR"
    exit 1
fi

BINARY_NAME=$(basename "$BINARY_RELPATH")

echo "📦 Collecting build artifacts from $BUILD_DIR"
echo "   Output directory: $OUTPUT_DIR"
echo "   Binary: $BINARY_RELPATH"

# Create output directory structure
mkdir -p "$OUTPUT_DIR/headers"
mkdir -p "$OUTPUT_DIR/bin"

# Collect all header files with preserved directory structure
echo "🔍 Collecting header files..."

# Collect headers from include/
if [ -d "$BUILD_DIR/include" ]; then
    find "$BUILD_DIR/include" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) | while read -r header; do
        rel_path="${header#$BUILD_DIR/}"
        target_path="$OUTPUT_DIR/headers/$rel_path"
        mkdir -p "$(dirname "$target_path")"
        cp "$header" "$target_path"
    done
    INCLUDE_COUNT=$(find "$BUILD_DIR/include" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | wc -l)
    echo "   ✓ Collected $INCLUDE_COUNT headers from include/"
fi

# Collect headers from src/
if [ -d "$BUILD_DIR/src" ]; then
    find "$BUILD_DIR/src" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) | while read -r header; do
        rel_path="${header#$BUILD_DIR/}"
        target_path="$OUTPUT_DIR/headers/$rel_path"
        mkdir -p "$(dirname "$target_path")"
        cp "$header" "$target_path"
    done
    SRC_COUNT=$(find "$BUILD_DIR/src" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | wc -l)
    echo "   ✓ Collected $SRC_COUNT headers from src/"
fi

# Collect headers from deps/include/ (present for some solvers, e.g. cvc5)
if [ -d "$BUILD_DIR/deps/include" ]; then
    find "$BUILD_DIR/deps/include" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) | while read -r header; do
        rel_path="${header#$BUILD_DIR/}"
        target_path="$OUTPUT_DIR/headers/$rel_path"
        mkdir -p "$(dirname "$target_path")"
        cp "$header" "$target_path"
    done
    DEPS_INCLUDE_COUNT=$(find "$BUILD_DIR/deps/include" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | wc -l)
    echo "   ✓ Collected $DEPS_INCLUDE_COUNT headers from deps/include/"
fi

# Collect headers from deps/src/ (present for some solvers, e.g. cvc5)
if [ -d "$BUILD_DIR/deps/src" ]; then
    find "$BUILD_DIR/deps/src" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) | while read -r header; do
        rel_path="${header#$BUILD_DIR/}"
        target_path="$OUTPUT_DIR/headers/$rel_path"
        mkdir -p "$(dirname "$target_path")"
        cp "$header" "$target_path"
    done
    DEPS_SRC_COUNT=$(find "$BUILD_DIR/deps/src" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | wc -l)
    echo "   ✓ Collected $DEPS_SRC_COUNT headers from deps/src/"
fi

# Count total headers
TOTAL_HEADERS=$(find "$OUTPUT_DIR/headers" -type f 2>/dev/null | wc -l || echo "0")
echo "   Total headers collected: $TOTAL_HEADERS"

# Copy binary (always normalized to bin/<name> in the archive)
if [ -f "$BUILD_DIR/$BINARY_RELPATH" ]; then
    cp "$BUILD_DIR/$BINARY_RELPATH" "$OUTPUT_DIR/bin/$BINARY_NAME"
    chmod +x "$OUTPUT_DIR/bin/$BINARY_NAME"
    BINARY_SIZE=$(du -h "$OUTPUT_DIR/bin/$BINARY_NAME" | cut -f1)
    echo "   ✓ Binary copied ($BINARY_SIZE)"
else
    echo "   ⚠ Warning: Binary not found at $BUILD_DIR/$BINARY_RELPATH"
fi

# Copy compile_commands.json
if [ -f "$BUILD_DIR/compile_commands.json" ]; then
    cp "$BUILD_DIR/compile_commands.json" "$OUTPUT_DIR/compile_commands.json"
    echo "   ✓ compile_commands.json copied"
else
    echo "   ⚠ Warning: compile_commands.json not found at $BUILD_DIR/compile_commands.json"
fi

# Create summary
echo ""
echo "✅ Artifact collection complete!"
echo "   Headers: $OUTPUT_DIR/headers/"
echo "   Binary: $OUTPUT_DIR/bin/$BINARY_NAME"
echo "   Compile commands: $OUTPUT_DIR/compile_commands.json"
echo ""
echo "📊 Summary:"
echo "   Total header files: $TOTAL_HEADERS"
if [ -f "$OUTPUT_DIR/bin/$BINARY_NAME" ]; then
    echo "   Binary: ✓"
else
    echo "   Binary: ✗"
fi
if [ -f "$OUTPUT_DIR/compile_commands.json" ]; then
    echo "   compile_commands.json: ✓"
else
    echo "   compile_commands.json: ✗"
fi
