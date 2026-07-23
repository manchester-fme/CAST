#!/usr/bin/env python3
"""Generate combined matrix of (commit, chunk) for coverage mapping"""

import os
import sys
import json
import boto3
import subprocess
from pathlib import Path
from botocore.exceptions import ClientError
from src.storage_backend import get_bucket, build_client

def main():
    solver = sys.argv[1]
    max_commits = None
    if len(sys.argv) > 2:
        try:
            max_commits = int(sys.argv[2])
        except ValueError:
            pass
    
    bucket = get_bucket()
    if not bucket:
        raise RuntimeError("BUCKET_NAME environment variable not set")
    
    s3_client = build_client()
    s3_key = f"evaluation/rq2/{solver}/selected-commits.json"
    
    # Read selected commits
    try:
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        selected_commits = json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise RuntimeError(f"Selected commits not found at {s3_key}. Run commit selection first.")
        raise
    
    if not selected_commits:
        raise RuntimeError("No commits selected")
    
    # Limit commits if specified
    if max_commits and max_commits > 0:
        selected_commits = selected_commits[:max_commits]
        print(f"📝 Limited to {len(selected_commits)} commits (max_commits={max_commits})", file=sys.stderr)
    
    # Download coverage binary for first commit to discover tests
    # (We assume all commits have similar test counts)
    first_commit = selected_commits[0]
    coverage_key = f"evaluation/rq2/{solver}/builds/coverage/{first_commit}.tar.gz"
    
    print(f"📥 Downloading coverage binary for test discovery...", file=sys.stderr)
    os.makedirs('artifacts', exist_ok=True)
    s3_client.download_file(bucket, coverage_key, 'artifacts/artifacts.tar.gz')
    
    # Extract binary
    solver_dir = solver
    build_dir = f"{solver_dir}/build"
    os.makedirs(build_dir, exist_ok=True)
    
    extract_script = f"src/{solver}/extract_build_artifacts.sh"
    result = subprocess.run(
        ['bash', extract_script, 'artifacts/artifacts.tar.gz', build_dir, 'true'],
        capture_output=True,
        text=True,
        check=True
    )
    print(result.stdout, file=sys.stderr)
    
    # Discover tests and generate chunks
    if solver == 'z3':
        # Clone z3test if needed
        if not os.path.exists('z3test'):
            subprocess.run(['git', 'clone', 'https://github.com/z3prover/z3test.git', 'z3test'], check=True)
        
        # Generate matrix
        result = subprocess.run(
            ['python3', 'src/z3/coverage/generate_matrix.py',
             '--z3test-dir', 'z3test',
             '--max-job-time', '300',
             '--buffer', '60',
             '--output', 'matrix.json'],
            capture_output=True,
            text=True,
            check=True
        )
    else:  # cvc5
        result = subprocess.run(
            ['python3', 'src/cvc5/coverage/generate_matrix.py',
             '--build-dir', build_dir,
             '--max-job-time', '300',
             '--buffer', '60',
             '--output', 'matrix.json'],
            capture_output=True,
            text=True,
            check=True
        )
    
    with open('matrix.json', 'r') as f:
        chunk_matrix = json.load(f)
    
    chunks = chunk_matrix['matrix']['include']
    print(f"📊 Discovered {chunk_matrix['total_tests']} tests, {len(chunks)} chunks", file=sys.stderr)
    
    # Generate combined matrix: (commit, chunk)
    combined_matrix = []
    for commit in selected_commits:
        for chunk in chunks:
            combined_matrix.append({
                'commit': commit,
                'chunk': chunk
            })
    
    output = {
        'include': combined_matrix,
        'total_commits': len(selected_commits),
        'total_chunks': len(chunks),
        'chunks_per_commit': len(chunks)
    }
    
    print(json.dumps(output, separators=(',', ':')))
    print(f"Generated combined matrix: {len(combined_matrix)} jobs ({len(selected_commits)} commits × {len(chunks)} chunks)", file=sys.stderr)

if __name__ == '__main__':
    main()

