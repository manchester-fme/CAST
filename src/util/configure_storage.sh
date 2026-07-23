#! /bin/bash

#
# Resolves which object storage backend (Cloudflare R2 or AWS S3) this CI job
# should use, and exports a common set of env vars for the rest of the job.
#
# One set of secrets feeds both backends:
#   CAST_BUCKET_NAME, CAST_ACCESS_KEY_ID, CAST_SECRET_ACCESS_KEY, and (R2 only)
#   CAST_ACCOUNT_ID, plus an optional CAST_REGION for AWS.
#
# All outputs are exported under CAST_*-prefixed names only.
#
# Selected via the CAST_STORAGE_PROVIDER repo variable: "r2" (default) or "aws".
#
# Usage (from a workflow step): ./src/configure_storage.sh >> "$GITHUB_ENV"

set -euo pipefail

PROVIDER="${CAST_STORAGE_PROVIDER:-r2}"

: "${CAST_BUCKET_NAME:?CAST_BUCKET_NAME is required}"
: "${CAST_ACCESS_KEY_ID:?CAST_ACCESS_KEY_ID is required}"
: "${CAST_SECRET_ACCESS_KEY:?CAST_SECRET_ACCESS_KEY is required}"

echo "CAST_STORAGE_PROVIDER=${PROVIDER}"
echo "CAST_BUCKET_NAME=${CAST_BUCKET_NAME}"
echo "CAST_ACCESS_KEY_ID=${CAST_ACCESS_KEY_ID}"
echo "CAST_SECRET_ACCESS_KEY=${CAST_SECRET_ACCESS_KEY}"

if [ "$PROVIDER" = "r2" ]; then
  : "${CAST_ACCOUNT_ID:?CAST_ACCOUNT_ID is required when CAST_STORAGE_PROVIDER=r2}"
  echo "CAST_REGION=auto"
  echo "CAST_DEFAULT_REGION=auto"
  echo "CAST_ENDPOINT_URL_S3=https://${CAST_ACCOUNT_ID}.r2.cloudflarestorage.com"
elif [ "$PROVIDER" = "aws" ]; then
  echo "CAST_REGION=${CAST_REGION:-eu-north-1}"
  echo "CAST_DEFAULT_REGION=${CAST_REGION:-eu-north-1}"
else
  echo "Unknown CAST_STORAGE_PROVIDER '${PROVIDER}' (expected 'r2' or 'aws')" >&2
  exit 1
fi
