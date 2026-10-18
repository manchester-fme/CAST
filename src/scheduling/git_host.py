#!/usr/bin/env python3
"""Host-specific API URLs, auth headers and response parsing for GitHub and GitLab"""

import os
from typing import List, Optional, Tuple
from urllib.parse import quote, urlparse

HOSTS = {'github.com': 'github', 'gitlab.com': 'gitlab'}
GITLAB_DATE_FIELDS = {'author': 'authored_date', 'committer': 'committed_date'}


def _split_repo_url(repo_url: str) -> Tuple[str, str]:
    if repo_url.startswith('git@'):
        hostname, _, path = repo_url[len('git@'):].partition(':')
    elif repo_url.startswith('https://'):
        parsed = urlparse(repo_url)
        hostname, path = parsed.hostname or '', parsed.path
    else:
        raise ValueError(f"Unsupported repository URL: {repo_url} "
                         f"(expected https://host/owner/repo or git@host:owner/repo)")
    return hostname.lower(), path.strip('/')


def detect_host(repo_url: str) -> str:
    hostname, _ = _split_repo_url(repo_url)
    if hostname not in HOSTS:
        raise ValueError(f"Unsupported git host '{hostname}' in {repo_url} "
                         f"(supported: {', '.join(sorted(HOSTS))})")
    return HOSTS[hostname]


def get_repo_path(repo_url: str) -> str:
    _, path = _split_repo_url(repo_url)
    path = path.removesuffix('.git')
    if '/' not in path:
        raise ValueError(f"No owner/repo path in {repo_url}")
    return path


def _api_base(repo_url: str) -> str:
    path = get_repo_path(repo_url)
    if detect_host(repo_url) == 'github':
        return f"https://api.github.com/repos/{path}"
    return f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}/repository"


def build_commits_url(repo_url: str) -> str:
    return f"{_api_base(repo_url)}/commits"


def build_commit_url(repo_url: str, ref: str) -> str:
    return f"{_api_base(repo_url)}/commits/{ref}"


def build_diff_url(repo_url: str, sha: str) -> str:
    """GitHub returns the changed files in the commit itself; GitLab has a separate diff endpoint."""
    commit_url = build_commit_url(repo_url, sha)
    if detect_host(repo_url) == 'github':
        return commit_url
    return f"{commit_url}/diff?per_page=100"


def resolve_token(host: str, cli_token: Optional[str]) -> Optional[str]:
    """GitHub uses the token passed in & GitLab reads GITLAB_TOKEN."""
    if host == 'gitlab':
        return os.environ.get('GITLAB_TOKEN')
    return cli_token


def build_headers(host: str, token: Optional[str]) -> dict:
    if host not in HOSTS.values():
        raise ValueError(f"Unknown host: {host}")
    token = resolve_token(host, token)
    if not token:
        return {}
    if host == 'github':
        return {'Authorization': f'token {token}'}
    return {'PRIVATE-TOKEN': token}


def parse_commit_list(host: str, response_json: list) -> List[str]:
    if host == 'github':
        return [commit['sha'] for commit in response_json]
    if host == 'gitlab':
        return [commit['id'] for commit in response_json]
    raise ValueError(f"Unknown host: {host}")


def parse_commit_date(host: str, response_json: dict, which: str) -> Optional[str]:
    """which is 'author' or 'committer'; returns the ISO 8601 string, or None if absent."""
    if host == 'github':
        return response_json.get('commit', {}).get(which, {}).get('date')
    if host == 'gitlab':
        return response_json.get(GITLAB_DATE_FIELDS[which])
    raise ValueError(f"Unknown host: {host}")


def parse_changed_files(host: str, response_json) -> List[str]:
    """response_json is the commit for GitHub and the diff list for GitLab."""
    if host == 'github':
        return [file_info.get('filename', '') for file_info in response_json.get('files', [])]
    if host == 'gitlab':
        return [diff.get('new_path', '') for diff in response_json]
    raise ValueError(f"Unknown host: {host}")


def check_response(response) -> None:
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} from {response.url}")
