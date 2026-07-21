#!/usr/bin/env python3
"""
Shared storage backend selection for the fuzzing pipeline.

Both AWS S3 and Cloudflare R2 implement the S3 API, so a single boto3
client works for either — the only difference is the endpoint URL,
credentials, and region. This module picks the right combination based
on the STORAGE_PROVIDER environment variable so callers (s3_state.py,
coverage_state.py) don't need to know which backend is active.

Environment variables:
  STORAGE_PROVIDER      "aws" (default) or "r2"

  AWS (used when STORAGE_PROVIDER=aws, the default / fallback backend):
    AWS_S3_BUCKET
    AWS_REGION           (default: eu-north-1)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY  (or any boto3-supported
                                                 credential source)

  Cloudflare R2 (used when STORAGE_PROVIDER=r2):
    R2_ACCOUNT_ID         Cloudflare account ID (used to build the endpoint URL)
    R2_BUCKET
    R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY    R2 API token credentials
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
    provider = os.getenv('STORAGE_PROVIDER', 'aws').strip().lower()
    if provider not in ('aws', 'r2'):
        raise StorageConfigError(f"Unknown STORAGE_PROVIDER '{provider}', expected 'aws' or 'r2'")
    return provider


def get_bucket() -> str:
    provider = get_provider()
    if provider == 'r2':
        bucket = os.getenv('R2_BUCKET')
        if not bucket:
            raise StorageConfigError("R2_BUCKET environment variable not set")
        return bucket
    bucket = os.getenv('AWS_S3_BUCKET')
    if not bucket:
        raise StorageConfigError("AWS_S3_BUCKET environment variable not set")
    return bucket


def build_client(region: str = None):
    """Builds a boto3 S3 client pointed at whichever backend is active."""
    provider = get_provider()

    if provider == 'r2':
        account_id = os.getenv('R2_ACCOUNT_ID')
        access_key = os.getenv('R2_ACCESS_KEY_ID')
        secret_key = os.getenv('R2_SECRET_ACCESS_KEY')
        if not account_id:
            raise StorageConfigError("R2_ACCOUNT_ID environment variable not set")
        if not access_key or not secret_key:
            raise StorageConfigError("R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY environment variables not set")
        return boto3.client(
            's3',
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='auto',
        )

    # AWS (default / fallback)
    resolved_region = region or os.getenv('AWS_REGION', 'eu-north-1')
    return boto3.client('s3', region_name=resolved_region)


if __name__ == '__main__':
    # Small CLI for sanity-checking which backend is active, e.g. in CI logs.
    try:
        provider = get_provider()
        bucket = get_bucket()
        print(f"provider={provider} bucket={bucket}")
    except StorageConfigError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
