#! /bin/bash

#
# Resolves which object storage backend (Cloudflare R2 or AWS S3) this CI job
# should use, and exports a common set of env vars for the rest of the job.
#
# One unprefixed set of secrets feeds both backends:
#   BUCKET_NAME, ACCESS_KEY_ID, SECRET_ACCESS_KEY, and (R2 only) ACCOUNT_ID,
#   plus an optional REGION for AWS.
#
# On the way out, the bucket keeps the name BUCKET_NAME, while the credentials
# are emitted under the AWS_* names because those are the AWS SDK's interface:
# boto3 and the `aws` CLI look them up by those exact names regardless of which
# backend is actually behind them.
#
# Selected via the STORAGE_PROVIDER repo variable: "r2" (default) or "aws".
#
# Usage (from a workflow step): ./src/configure_storage.sh >> "$GITHUB_ENV"

set -euo pipefail

PROVIDER="${STORAGE_PROVIDER:-r2}"

: "${BUCKET_NAME:?BUCKET_NAME is required}"
: "${ACCESS_KEY_ID:?ACCESS_KEY_ID is required}"
: "${SECRET_ACCESS_KEY:?SECRET_ACCESS_KEY is required}"

echo "STORAGE_PROVIDER=${PROVIDER}"
echo "BUCKET_NAME=${BUCKET_NAME}"
echo "AWS_ACCESS_KEY_ID=${ACCESS_KEY_ID}"
echo "AWS_SECRET_ACCESS_KEY=${SECRET_ACCESS_KEY}"

if [ "$PROVIDER" = "r2" ]; then
  : "${ACCOUNT_ID:?ACCOUNT_ID is required when STORAGE_PROVIDER=r2}"
  echo "AWS_REGION=auto"
  echo "AWS_DEFAULT_REGION=auto"
  echo "AWS_ENDPOINT_URL_S3=https://${ACCOUNT_ID}.r2.cloudflarestorage.com"
elif [ "$PROVIDER" = "aws" ]; then
  echo "AWS_REGION=${REGION:-eu-north-1}"
  echo "AWS_DEFAULT_REGION=${REGION:-eu-north-1}"
else
  echo "Unknown STORAGE_PROVIDER '${PROVIDER}' (expected 'r2' or 'aws')" >&2
  exit 1
fi
