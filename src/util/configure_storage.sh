#! /bin/bash

#
# Resolves which object storage backend this CI job should use, and exports
# a common set of env vars for the rest of the job.
#
# Two static-credential backends share one set of secrets:
#   AWS_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and (R2 only)
#   AWS_ACCOUNT_ID, plus an optional AWS_REGION for AWS.
#
# A third, credential-free backend ("r2-broker", see src/infra/r2-broker/ and
# src/util/r2_broker_client.py) needs no secrets at all - just a public
# Lambda Function URL and IAM role ARN (neither sensitive; the role's trust
# policy is what actually gates access), exchanged at runtime for a scoped,
# short-lived R2 presigned URL using the job's own GitHub OIDC token.
#
# Selected via the AWS_STORAGE_PROVIDER repo variable ("r2", "aws", or
# "r2-broker") when set. When unset, it's auto-detected: CAST's own runs
# have AWS_ACCESS_KEY_ID as a repo secret, so they resolve to "r2"
# (preserving today's default); a caller with no static credential at all
# (any fork - secrets: inherit only forwards secrets the *caller* actually
# has, never CAST's) can't produce that variable, so it falls back to
# "r2-broker" with no configuration needed on the caller's side.
#
# Usage (from a workflow step): ./src/util/configure_storage.sh >> "$GITHUB_ENV"

set -euo pipefail

PROVIDER="${AWS_STORAGE_PROVIDER:-}"
if [ -z "$PROVIDER" ]; then
  if [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    PROVIDER="r2"
  else
    PROVIDER="r2-broker"
  fi
fi

echo "AWS_STORAGE_PROVIDER=${PROVIDER}"

if [ "$PROVIDER" = "r2-broker" ]; then
  : "${R2_BROKER_FUNCTION_URL:?R2_BROKER_FUNCTION_URL is required when AWS_STORAGE_PROVIDER=r2-broker}"
  : "${R2_BROKER_ROLE_ARN:?R2_BROKER_ROLE_ARN is required when AWS_STORAGE_PROVIDER=r2-broker}"
  echo "R2_BROKER_FUNCTION_URL=${R2_BROKER_FUNCTION_URL}"
  echo "R2_BROKER_ROLE_ARN=${R2_BROKER_ROLE_ARN}"
  echo "R2_BROKER_REGION=${R2_BROKER_REGION:-us-east-1}"
  exit 0
fi

: "${AWS_BUCKET_NAME:?AWS_BUCKET_NAME is required}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is required}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is required}"

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
  echo "Unknown AWS_STORAGE_PROVIDER '${PROVIDER}' (expected 'r2', 'aws', or 'r2-broker')" >&2
  exit 1
fi
