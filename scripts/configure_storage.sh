#! /bin/bash

#
# Resolves which object storage backend (AWS S3 or Cloudflare R2) this CI job
# should use, and exports a common set of env vars for the rest of the job.
#
# Downstream steps (raw `aws s3` CLI calls and the Python scripts under
# scripts/) only ever need to look at AWS_S3_BUCKET / AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY / AWS_REGION / AWS_ENDPOINT_URL_S3 — they don't need
# to know which real backend is behind those names.
#
# Selected via the STORAGE_PROVIDER repo variable: "r2" or "aws".
# Defaults to "aws" so it keeps working unchanged, and so AWS is always the
# fallback if R2 needs to be reverted.
#
# Usage (from a workflow step): ./scripts/configure_storage.sh >> "$GITHUB_ENV"
# Required env vars going in: STORAGE_PROVIDER (optional), and either the
# AWS_* or R2_* secrets, both of which may be present at once.

set -euo pipefail

PROVIDER="${STORAGE_PROVIDER:-aws}"

if [ "$PROVIDER" = "r2" ]; then
  : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required when STORAGE_PROVIDER=r2}"
  : "${R2_BUCKET:?R2_BUCKET is required when STORAGE_PROVIDER=r2}"
  : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required when STORAGE_PROVIDER=r2}"
  : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required when STORAGE_PROVIDER=r2}"

  echo "STORAGE_PROVIDER=r2"
  echo "AWS_S3_BUCKET=${R2_BUCKET}"
  echo "AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}"
  echo "AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}"
  echo "AWS_REGION=auto"
  echo "AWS_DEFAULT_REGION=auto"
  # Recognized by AWS CLI v2 (>=2.13) and boto3 for endpoint override.
  echo "AWS_ENDPOINT_URL_S3=https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
  echo "::notice::Storage backend: Cloudflare R2 (bucket: ${R2_BUCKET})"
else
  : "${AWS_S3_BUCKET:?AWS_S3_BUCKET is required when STORAGE_PROVIDER=aws}"
  : "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required when STORAGE_PROVIDER=aws}"
  : "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required when STORAGE_PROVIDER=aws}"

  echo "STORAGE_PROVIDER=aws"
  echo "AWS_S3_BUCKET=${AWS_S3_BUCKET}"
  echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
  echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
  echo "AWS_REGION=${AWS_REGION:-eu-north-1}"
  echo "AWS_DEFAULT_REGION=${AWS_REGION:-eu-north-1}"
  echo "::notice::Storage backend: AWS S3 (bucket: ${AWS_S3_BUCKET})"
fi
