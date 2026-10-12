"""Unit tests for git_host.py."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import git_host


class GitHostTests(unittest.TestCase):
    def test_detect_host_github(self):
        self.assertEqual(git_host.detect_host('https://github.com/owner/repo.git'), 'github')
        self.assertEqual(git_host.detect_host('git@github.com:owner/repo.git'), 'github')

    def test_detect_host_gitlab(self):
        self.assertEqual(git_host.detect_host('https://gitlab.com/owner/repo.git'), 'gitlab')
        self.assertEqual(git_host.detect_host('git@gitlab.com:owner/repo.git'), 'gitlab')

    def test_detect_host_unsupported_raises(self):
        with self.assertRaises(ValueError):
            git_host.detect_host('https://bitbucket.org/owner/repo.git')

    def test_get_repo_path_strips_git_suffix(self):
        self.assertEqual(git_host.get_repo_path('https://github.com/owner/repo.git'), 'owner/repo')

    def test_get_repo_path_keeps_dot_git_inside_name(self):
        # str.replace('.git', '') would turn this into 'owner/repohub'
        self.assertEqual(git_host.get_repo_path('https://github.com/owner/repo.github.git'), 'owner/repo.github')

    def test_build_commits_url_github(self):
        self.assertEqual(git_host.build_commits_url('https://github.com/owner/repo.git'),
                         'https://api.github.com/repos/owner/repo/commits')

    def test_build_commits_url_gitlab_encodes_slash(self):
        self.assertEqual(git_host.build_commits_url('https://gitlab.com/owner/repo.git'),
                         'https://gitlab.com/api/v4/projects/owner%2Frepo/repository/commits')

    def test_build_headers_github(self):
        self.assertEqual(git_host.build_headers('github', 'X'), {'Authorization': 'token X'})

    def test_build_headers_gitlab(self):
        self.assertEqual(git_host.build_headers('gitlab', 'X'), {'PRIVATE-TOKEN': 'X'})

    def test_build_headers_empty_token(self):
        self.assertEqual(git_host.build_headers('github', ''), {})
        self.assertEqual(git_host.build_headers('gitlab', ''), {})

    def test_parse_commit_list_github(self):
        self.assertEqual(git_host.parse_commit_list('github', [{'sha': 'a'}, {'sha': 'b'}]), ['a', 'b'])

    def test_parse_commit_list_gitlab(self):
        self.assertEqual(git_host.parse_commit_list('gitlab', [{'id': 'a'}, {'id': 'b'}]), ['a', 'b'])

    def test_parse_changed_files_github(self):
        commit = {'files': [{'filename': 'src/x.cpp'}]}
        self.assertEqual(git_host.parse_changed_files('github', commit), ['src/x.cpp'])

    def test_parse_changed_files_gitlab(self):
        diff = [{'old_path': 'src/x.ml', 'new_path': 'src/x.ml'}]
        self.assertEqual(git_host.parse_changed_files('gitlab', diff), ['src/x.ml'])

    def test_check_response_passes_on_200(self):
        git_host.check_response(mock.Mock(status_code=200, url='https://example.com/commits'))

    def test_check_response_raises_on_non_200(self):
        response = mock.Mock(status_code=404, url='https://example.com/commits')
        with self.assertRaises(RuntimeError) as ctx:
            git_host.check_response(response)
        self.assertIn('404', str(ctx.exception))
        self.assertIn('https://example.com/commits', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
