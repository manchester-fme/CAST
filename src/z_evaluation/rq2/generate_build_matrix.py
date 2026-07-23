#!/usr/bin/env python3
"""Generate build matrix from selected commits in S3"""

import os
import sys
import json
import boto3
from botocore.exceptions import ClientError
from src.storage_backend import get_bucket, build_client

def main():
    solver = sys.argv[1]
    bucket = get_bucket()
    if not bucket:
        raise RuntimeError("BUCKET_NAME environment variable not set")
    
    s3_client = build_client()
    s3_key = f"evaluation/rq2/{solver}/selected-commits.json"
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        selected_commits = json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise RuntimeError(f"Selected commits not found at {s3_key}. Run commit selection first.")
        raise
    
    if not selected_commits:
        raise RuntimeError("No commits selected")
    
    # Generate matrix with commit hashes
    matrix = {
        'include': [{'commit': commit} for commit in selected_commits]
    }
    
    # Output compact JSON for GitHub Actions
    print(json.dumps(matrix, separators=(',', ':')))
    print(f"Generated matrix with {len(selected_commits)} commits", file=sys.stderr)

if __name__ == '__main__':
    main()

