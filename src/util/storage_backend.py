#!/usr/bin/env python3
"""
Shared storage backend selection for the fuzzing pipeline.

Both AWS S3 and Cloudflare R2 implement the S3 API, so a single boto3
client works for either — the only difference is the endpoint URL,
credentials, and region. This module picks the right combination based
on the AWS_STORAGE_PROVIDER environment variable so callers (s3_state.py,
coverage_state.py) don't need to know which backend is active.

A third provider, "r2-broker", covers callers (e.g. a fork's own Actions
run) that have no static credential at all: it returns a boto3-client-shaped
shim (BrokerS3Client, see src/util/r2_broker_client.py) that exchanges the
job's GitHub OIDC token for R2 presigned URLs via CAST's broker Lambda
(infra/r2-broker/). Object data still flows straight to/from R2 - AWS is
only used to verify identity and hand back a signed URL.

Environment variables (all set by src/configure_storage.sh, except the
r2-broker ones which the calling workflow sets directly since they aren't
secrets):
  AWS_STORAGE_PROVIDER            "r2" (default), "aws", or "r2-broker"
  AWS_BUCKET_NAME                 bucket name (aws/r2 only)
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
                                    credentials (aws/r2 only)
  AWS_REGION                      region ("auto" for R2)
  AWS_ENDPOINT_URL_S3             set for R2 only; absent means real AWS S3
  R2_BROKER_FUNCTION_URL           broker Lambda Function URL (r2-broker only)
  R2_BROKER_ROLE_ARN               IAM role to assume via OIDC (r2-broker only)
  R2_BROKER_REGION                  AWS region the Lambda lives in (r2-broker only)
"""

import os
import sys

try:
    import boto3
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3", file=sys.stderr)
    sys.exit(1)


class StorageConfigError(Exception):
    pass


def get_provider() -> str:
    """Returns 'aws', 'r2', or 'r2-broker'. Defaults to 'aws' so existing
    setups keep working unchanged, and so AWS remains the fallback if R2
    needs to be reverted."""
    provider = os.getenv('AWS_STORAGE_PROVIDER', 'r2').strip().lower()
    if provider not in ('aws', 'r2', 'r2-broker'):
        raise StorageConfigError(f"Unknown AWS_STORAGE_PROVIDER '{provider}', expected 'aws', 'r2', or 'r2-broker'")
    return provider


def get_bucket() -> str:
    if get_provider() == 'r2-broker':
        # The bucket lives entirely on the broker Lambda's side - the caller
        # never needs to know its name. S3StateManager/CoverageStateManager
        # still thread a "bucket" string through (BrokerS3Client ignores it),
        # so return a fixed, obviously-not-a-real-bucket placeholder.
        return 'r2-broker'
    bucket = os.getenv('AWS_BUCKET_NAME')
    if not bucket:
        raise StorageConfigError("AWS_BUCKET_NAME environment variable not set")
    return bucket


def build_client(region: str = None, namespace: str = None):
    """Builds an S3-client-shaped object pointed at whichever backend is
    active. For 'r2-broker', namespace identifies the caller to the broker
    (see BrokerS3Client) and is what the Lambda scopes *writes* to - it's
    optional here because reads are unrestricted (e.g. get_state_manager()
    with no namespace, used to read the real unnamespaced oracle production
    build, is a legitimate read-only case). A caller with no namespace can
    never successfully write anything, since no real key will ever match an
    empty/placeholder prefix - that's enforced by the Lambda, not here."""
    if get_provider() == 'r2-broker':
        from util.r2_broker_client import BrokerS3Client

        function_url = os.getenv('R2_BROKER_FUNCTION_URL')
        role_arn = os.getenv('R2_BROKER_ROLE_ARN')
        if not function_url or not role_arn:
            raise StorageConfigError(
                'R2_BROKER_FUNCTION_URL/R2_BROKER_ROLE_ARN must be set to use the r2-broker storage provider'
            )
        return BrokerS3Client(
            function_url=function_url,
            role_arn=role_arn,
            region=region or os.getenv('R2_BROKER_REGION', 'us-east-1'),
            namespace=namespace,
        )

    kwargs = {
        'region_name': region or os.getenv('AWS_REGION', 'auto'),
        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
    }
    endpoint = os.getenv('AWS_ENDPOINT_URL_S3')
    if endpoint:
        kwargs['endpoint_url'] = endpoint
    return boto3.client('s3', **kwargs)


if __name__ == '__main__':
    # Small CLI for sanity-checking which backend is active, e.g. in CI logs.
    try:
        provider = get_provider()
        bucket = get_bucket()
        print(f"provider={provider} bucket={bucket}")
    except StorageConfigError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
