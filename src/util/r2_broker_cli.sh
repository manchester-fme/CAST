#!/usr/bin/env bash
# Thin wrapper: get a presigned R2 URL from the r2-broker Lambda (via
# src/util/r2_broker_client.py, the single source of truth for the OIDC/STS/
# SigV4 exchange - this script does not reimplement any of that) and perform
# the actual HTTP operation against it with curl.
#
# Used by the workflow call sites that talk to storage directly in bash
# (.github/actions/s3-put-object, the oracle/SUT-binary/coverage-map fetches
# in commit-fuzzer.yml) instead of through S3StateManager/CoverageStateManager,
# so they can support AWS_STORAGE_PROVIDER=r2-broker too. Requires
# `permissions: id-token: write` on the calling job and R2_BROKER_FUNCTION_URL/
# R2_BROKER_ROLE_ARN to be set (see src/util/storage_backend.py).
#
# Usage:
#   r2_broker_cli.sh get    <namespace> <key>    <dest-file>
#   r2_broker_cli.sh put    <namespace> <key>    <src-file>
#   r2_broker_cli.sh head   <namespace> <key>                 # exit 0 if exists, 1 if not
#   r2_broker_cli.sh delete <namespace> <key>
#   r2_broker_cli.sh list   <namespace> <prefix> <dest-xml-file>  # raw ListObjectsV2 XML

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

op="${1:?operation required (get|put|head|delete|list)}"
# namespace may legitimately be empty - a read-only caller fetching the real
# unnamespaced canonical production data (e.g. the fuzzer's oracle binary)
# passes "" deliberately. Only require the argument to be present, not non-empty.
namespace="${2?namespace argument required (may be empty)}"
key="${3:?key/prefix required}"

presign() {
  local broker_op="$1"
  PYTHONPATH="$REPO_ROOT/src" python3 -m util.r2_broker_client "$broker_op" "$key" --namespace "$namespace"
}

case "$op" in
  get)
    dest="${4:?destination file required for get}"
    url="$(presign get_object)"
    curl -fsSL -o "$dest" "$url"
    ;;
  put)
    src="${4:?source file required for put}"
    url="$(presign put_object)"
    curl -fsSL -X PUT --data-binary "@$src" "$url"
    ;;
  head)
    url="$(presign head_object)"
    curl -fsSL -I -o /dev/null "$url"
    ;;
  delete)
    url="$(presign delete_object)"
    curl -fsSL -X DELETE "$url"
    ;;
  list)
    dest="${4:?destination file required for list}"
    url="$(presign list_objects_v2)"
    curl -fsSL -o "$dest" "$url"
    ;;
  *)
    echo "❌ Unknown operation: $op (expected get|put|head|delete|list)" >&2
    exit 1
    ;;
esac
