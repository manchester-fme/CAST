#! /bin/bash

#
# Resolves which object storage backend (Cloudflare R2 or AWS S3) this CI job
# should use, and exports a common set of env vars for the rest of the job.
#
# One set of secrets feeds both backends:
#   AWS_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and (R2 only)
#   AWS_ACCOUNT_ID, plus an optional AWS_REGION for AWS.
#
# All outputs are exported under AWS_*-prefixed names only.
#
# Selected via the AWS_STORAGE_PROVIDER repo variable: "r2" (default) or "aws".
#
# Usage (from a workflow step): ./src/configure_storage.sh >> "$GITHUB_ENV"

set -euo pipefail

PROVIDER="${AWS_STORAGE_PROVIDER:-r2}"

: "${AWS_BUCKET_NAME:?AWS_BUCKET_NAME is required}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required}"

echo "AWS_STORAGE_PROVIDER=${PROVIDER}"
echo "AWS_BUCKET_NAME=${AWS_BUCKET_NAME}"
echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"

if [ "$PROVIDER" = "r2" ]; then
  : "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID is required when AWS_STORAGE_PROVIDER=r2}"
  echo "AWS_REGION=auto"
  echo "AWS_DEFAULT_REGION=auto"
  echo "AWS_ENDPOINT_URL_S3=https://${AWS_ACCOUNT_ID}.r2.cloudflarestorage.com"
elif [ "$PROVIDER" = "aws" ]; then
  echo "AWS_REGION=${AWS_REGION:-eu-north-1}"
  echo "AWS_DEFAULT_REGION=${AWS_REGION:-eu-north-1}"
else
  echo "Unknown AWS_STORAGE_PROVIDER '${PROVIDER}' (expected 'r2' or 'aws')" >&2
  exit 1
fi
