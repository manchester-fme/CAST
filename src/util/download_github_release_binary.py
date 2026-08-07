#!/usr/bin/env python3
"""
Download a solver binary from that solver's latest GitHub release. Generic
replacement for a per-solver "download my oracle" script: which repo, which
release asset, and what to name the installed binary are all CLI args
(manifest-driven via coverage.oracle_fetch in <solver-dir>/manifest.json),
not hardcoded per-solver knowledge.

Usage: python3 download_github_release_binary.py --repo cvc5/cvc5 \\
    --asset-keywords linux,x86_64,static --binary-name cvc5 [output_dir]
"""

import argparse
import os
import sys
import subprocess
import tempfile
import shutil
import requests
from pathlib import Path


def install_unzip():
    """Install unzip if not available"""
    if shutil.which('unzip'):
        return

    print("📦 Installing unzip...")
    try:
        subprocess.run(['sudo', 'apt-get', 'update'], check=True, capture_output=True)
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 'unzip'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Cannot install unzip automatically. Please install unzip manually.")
        sys.exit(1)


def get_latest_release(repo: str, github_token=None):
    """Get the latest release from GitHub API"""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        'User-Agent': 'CAST/1.0'  # GitHub API requires User-Agent header
    }
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"❌ Failed to get latest release for {repo}: {e}")
        if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
            print("⚠️ 403 Forbidden - This might be a rate limit issue. Consider setting GITHUB_TOKEN environment variable.")
        sys.exit(1)


def find_matching_asset(assets, keywords):
    """Find the release asset whose download URL contains every keyword"""
    for asset in assets:
        url = asset['browser_download_url']
        if all(kw in url.lower() for kw in keywords):
            return url
    return None


def download_and_extract(asset_url, output_dir, binary_name, github_token=None):
    """Download and extract the release asset, installing binary_name into output_dir"""
    print(f"📥 Downloading: {asset_url}")

    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "release.zip")

        headers = {
            'User-Agent': 'CAST/1.0'  # GitHub API requires User-Agent header
        }
        if github_token:
            headers['Authorization'] = f'token {github_token}'
        try:
            response = requests.get(asset_url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except requests.RequestException as e:
            print(f"❌ Failed to download: {e}")
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
                print("⚠️ 403 Forbidden - This might be a rate limit issue. Consider setting GITHUB_TOKEN environment variable.")
            sys.exit(1)

        print("📦 Extracting...")
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        subprocess.run(['unzip', '-q', zip_path, '-d', extract_dir], check=True)

        for root, dirs, files in os.walk(extract_dir):
            if binary_name in files:
                src_bin = os.path.join(root, binary_name)
                if os.path.isfile(src_bin):
                    output_path = os.path.join(output_dir, binary_name)
                    shutil.copy2(src_bin, output_path)
                    os.chmod(output_path, 0o755)
                    print(f"✅ Installed to: {output_path}")
                    return output_path

        print(f"❌ {binary_name} binary not found in archive")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Download a solver binary from its latest GitHub release')
    parser.add_argument('--repo', required=True, help='GitHub repo to fetch the release from, e.g. cvc5/cvc5')
    parser.add_argument('--asset-keywords', required=True,
                         help='Comma-separated keywords the release asset URL must all contain, e.g. linux,x86_64,static')
    parser.add_argument('--binary-name', required=True, help='Name of the binary inside the archive, and the installed filename')
    parser.add_argument('output_dir', nargs='?', default=os.path.join(os.path.expanduser('~'), '.local', 'bin'),
                         help='Output directory (default: ~/.local/bin)')
    args = parser.parse_args()

    install_unzip()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    github_token = os.environ.get('GITHUB_TOKEN')
    keywords = [kw.strip().lower() for kw in args.asset_keywords.split(',') if kw.strip()]

    print(f"🔍 Finding latest release for {args.repo}...")
    release = get_latest_release(args.repo, github_token)
    tag = release['tag_name']
    print(f"📦 Latest release: {tag}")

    asset_url = find_matching_asset(release['assets'], keywords)
    if not asset_url:
        print(f"❌ No release asset matching keywords {keywords} found in {tag}")
        sys.exit(1)

    binary_path = download_and_extract(asset_url, str(output_dir), args.binary_name, github_token)

    result = subprocess.run([binary_path, '--version'], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print(result.stdout.strip())


if __name__ == "__main__":
    main()
