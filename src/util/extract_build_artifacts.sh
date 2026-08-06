#!/bin/bash
# Extract a solver's build artifacts from artifacts.tar.gz (CAST-owned,
# solver-agnostic - see src/util/collect_build_artifacts.sh, its packing
# counterpart). Extracts:
# - All header files to build/ with preserved paths
# - The solver binary to <build_dir>/<binary_relpath>
# - compile_commands.json to build/
#
# Usage: ./extract_build_artifacts.sh <artifact_file> <build_dir> <binary_relpath> [extract_headers]
# Example: ./extract_build_artifacts.sh artifacts/artifacts.tar.gz cvc5/build bin/cvc5 true
#
# binary_relpath is the solver's build-relative binary path (manifest.json's
# fuzzer.target_binary_path with the leading "./build/" stripped, e.g.
# "bin/cvc5" for cvc5, "z3" for z3) - the archive itself always packs the
# binary at bin/<basename> regardless of solver (see collect_build_artifacts.sh).
#
# If extract_headers is "true" (default), extracts headers. If "false", only extracts binary.

set -e

ARTIFACT_FILE="${1}"
BUILD_DIR="${2}"
BINARY_RELPATH="${3}"
EXTRACT_HEADERS="${4:-true}"

if [ -z "$ARTIFACT_FILE" ]; then
    echo "Error: Artifact file not specified"
    exit 1
fi

if [ -z "$BUILD_DIR" ] || [ -z "$BINARY_RELPATH" ]; then
    echo "Error: build_dir and binary_relpath are required"
    exit 1
fi

if [ ! -f "$ARTIFACT_FILE" ]; then
    echo "Error: Artifact file not found: $ARTIFACT_FILE"
    exit 1
fi

BINARY_NAME=$(basename "$BINARY_RELPATH")

echo "📦 Extracting build artifacts from $ARTIFACT_FILE"
echo "   Build directory: $BUILD_DIR"
echo "   Binary: $BINARY_RELPATH"
echo "   Extract headers: $EXTRACT_HEADERS"

mkdir -p "$BUILD_DIR"

# Extract to temp location
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

echo "Extracting archive..."
tar -xzf "$ARTIFACT_FILE" -C "$TMP_DIR"

# Extract binary
if [ -f "$TMP_DIR/bin/$BINARY_NAME" ]; then
    mkdir -p "$BUILD_DIR/$(dirname "$BINARY_RELPATH")"
    cp "$TMP_DIR/bin/$BINARY_NAME" "$BUILD_DIR/$BINARY_RELPATH"
    chmod +x "$BUILD_DIR/$BINARY_RELPATH"
    echo "✓ Binary extracted to $BUILD_DIR/$BINARY_RELPATH"
else
    echo "⚠ Warning: Binary not found in artifacts"
fi

# Extract compile_commands.json
if [ -f "$TMP_DIR/compile_commands.json" ]; then
    cp "$TMP_DIR/compile_commands.json" "$BUILD_DIR/compile_commands.json"
    echo "✓ compile_commands.json extracted"
else
    echo "⚠ Warning: compile_commands.json not found in artifacts"
fi

# Extract headers if requested
if [ "$EXTRACT_HEADERS" = "true" ]; then
    if [ -d "$TMP_DIR/headers" ]; then
        # Move all header directories to build root (preserve structure)
        if [ -d "$TMP_DIR/headers/include" ]; then
            mv "$TMP_DIR/headers/include" "$BUILD_DIR/include"
            echo "✓ Headers extracted: include/"
        fi
        if [ -d "$TMP_DIR/headers/src" ]; then
            mv "$TMP_DIR/headers/src" "$BUILD_DIR/src"
            echo "✓ Headers extracted: src/"
        fi
        if [ -d "$TMP_DIR/headers/deps" ]; then
            mv "$TMP_DIR/headers/deps" "$BUILD_DIR/deps"
            echo "✓ Headers extracted: deps/"
        fi

        # Count headers
        HEADER_COUNT=$(find "$BUILD_DIR" -type f \( -name "*.h" -o -name "*.hpp" -o -name "*.hxx" \) 2>/dev/null | wc -l || echo "0")
        echo "  Total headers: $HEADER_COUNT"
    else
        echo "⚠ Warning: headers/ directory not found in artifacts"
    fi
fi

# Verify binary
if [ -f "$BUILD_DIR/$BINARY_RELPATH" ]; then
    "$BUILD_DIR/$BINARY_RELPATH" --version > /dev/null 2>&1 && echo "✓ Binary verified" || echo "⚠ Binary verification failed"
fi

echo "✅ Extraction complete!"
