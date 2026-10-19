#!/usr/bin/env python3
"""Detect if a commit has source code changes"""

import os
import sys
import subprocess
from typing import Iterable, List, Optional
import argparse

try:
    import git
except ImportError:
    print("Error: GitPython is required. Install with: pip install GitPython", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, src_dir)

from scheduling import git_host

DEFAULT_SOURCE_EXTENSIONS = {'.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.hxx', '.hh'}


def has_source_extension(filename: str, extensions: Optional[Iterable[str]] = None) -> bool:
    return git_host.matches_extension(filename, extensions or DEFAULT_SOURCE_EXTENSIONS)


def detect_source_changes_git(repo_path: str, commit_hash: str, extensions: Optional[Iterable[str]] = None) -> tuple[bool, List[str]]:
    try:
        repo = git.Repo(repo_path)
        commit = repo.commit(commit_hash)
        parents = commit.parents
        parent_hash = parents[0].hexsha if parents else None
        diff = commit.diff(parent_hash if parent_hash else git.NULL_TREE)
        
        source_files = []
        for item in diff:
            for path in [item.a_path, item.b_path]:
                if path and has_source_extension(path, extensions) and path not in source_files:
                    source_files.append(path)
        return len(source_files) > 0, source_files
    except git.exc.BadName:
        raise ValueError(f"Invalid commit hash: {commit_hash}")
    except Exception as e:
        raise RuntimeError(f"Error detecting source changes: {e}")


def detect_source_changes_api(repo_url: str, commit_hash: str, token: Optional[str] = None,
                              extensions: Optional[Iterable[str]] = None) -> tuple[bool, List[str]]:
    if requests is None:
        raise RuntimeError("requests library required. Install with: pip install requests")
    
    host = git_host.detect_host(repo_url)
    api_url = git_host.build_diff_url(repo_url, commit_hash)
    headers = git_host.build_headers(host, token)
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        
        source_files = []
        for filename in git_host.parse_changed_files(host, response.json()):
            if has_source_extension(filename, extensions) and filename not in source_files:
                source_files.append(filename)
        return len(source_files) > 0, source_files
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise ValueError(f"Commit not found: {commit_hash}")
        elif e.response.status_code == 403:
            raise RuntimeError(f"{host} API denied access (403), possibly a rate limit. Use an API token.")
        raise RuntimeError(f"{host} API error: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")


def detect_source_changes(repo_path_or_url: str, commit_hash: str, token: Optional[str] = None,
                          extensions: Optional[Iterable[str]] = None) -> tuple[bool, List[str]]:
    if '://' in repo_path_or_url or repo_path_or_url.startswith('git@'):
        return detect_source_changes_api(repo_path_or_url, commit_hash, token, extensions)
    return detect_source_changes_git(repo_path_or_url, commit_hash, extensions)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Detect source changes in a commit')
    parser.add_argument('repo', help='Local repository path, or a GitHub or GitLab URL')
    parser.add_argument('commit', help='Commit hash')
    parser.add_argument('--token', help='GitHub token (GitLab reads GITLAB_TOKEN)', default=os.getenv('GITHUB_TOKEN'))
    parser.add_argument('--extensions', default=None, help="Comma-separated source file extensions, e.g. '.ml,.mli' (default: C/C++)")
    parser.add_argument('--list-files', action='store_true', help='List changed source files')
    
    args = parser.parse_args()
    
    try:
        extensions = git_host.normalise_extensions(args.extensions)
        has_source, source_files = detect_source_changes(args.repo, args.commit, args.token, extensions)
        
        if args.list_files:
            print('\n'.join(source_files) if source_files else '', end='')
        else:
            print(f"✅ Commit {args.commit} has source changes ({len(source_files)} files)" if has_source 
                  else f"❌ Commit {args.commit} has no source changes")
            sys.exit(0 if has_source else 1)
    except (ValueError, RuntimeError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
