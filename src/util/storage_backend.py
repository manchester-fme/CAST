#!/usr/bin/env python3
"""
Shared storage backend selection for the fuzzing pipeline.

Both AWS S3 and Cloudflare R2 implement the S3 API, so a single boto3
client works for either — the only difference is the endpoint URL,
credentials, and region. This module picks the right combination based
on the CAST_STORAGE_PROVIDER environment variable so callers (s3_state.py,
coverage_state.py) don't need to know which backend is active.

Environment variables (all set by src/configure_storage.sh):
  CAST_STORAGE_PROVIDER            "r2" (default) or "aws"
  CAST_BUCKET_NAME                 bucket name, whichever backend is active
  CAST_ACCESS_KEY_ID / CAST_SECRET_ACCESS_KEY
                                    credentials for whichever backend is active
  CAST_REGION                      region ("auto" for R2)
  CAST_ENDPOINT_URL_S3             set for R2 only; absent means real AWS S3
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
    """Returns 'aws' or 'r2'. Defaults to 'aws' so existing setups keep working
    unchanged, and so AWS remains the fallback if R2 needs to be reverted."""
    provider = os.getenv('CAST_STORAGE_PROVIDER', 'r2').strip().lower()
    if provider not in ('aws', 'r2'):
        raise StorageConfigError(f"Unknown CAST_STORAGE_PROVIDER '{provider}', expected 'aws' or 'r2'")
    return provider


def get_bucket() -> str:
    bucket = os.getenv('CAST_BUCKET_NAME')
    if not bucket:
        raise StorageConfigError("CAST_BUCKET_NAME environment variable not set")
    return bucket


def build_client(region: str = None):
    """Builds a boto3 S3 client pointed at whichever backend is active.

    Credentials/region/endpoint are passed explicitly since they live under
    CAST_*-prefixed names rather than the AWS SDK's own env var names, so
    boto3 can't pick them up automatically.
    """
    kwargs = {
        'region_name': region or os.getenv('CAST_REGION', 'auto'),
        'aws_access_key_id': os.getenv('CAST_ACCESS_KEY_ID'),
        'aws_secret_access_key': os.getenv('CAST_SECRET_ACCESS_KEY'),
    }
    endpoint = os.getenv('CAST_ENDPOINT_URL_S3')
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
