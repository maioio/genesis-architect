"""Tests for GitHub rate limit handling and fork analyzer ranking."""
import sys
import urllib.error
import unittest.mock as mock
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from genesis_architect.core.github import (
    search_repos, fetch_issues, GitHubRateLimitError, _get
)
from genesis_architect.core import fork_analyzer


def _make_http_error(code: int, remaining: str = "0"):
    headers = mock.MagicMock()
    headers.get = lambda k, d="": remaining if k == "X-RateLimit-Remaining" else d
    err = urllib.error.HTTPError(url="", code=code, msg="", hdrs=headers, fp=None)
    return err


# ---------------------------------------------------------------------------
# github._get rate limit detection
# ---------------------------------------------------------------------------

class TestGitHubRateLimit:
    def test_403_with_remaining_zero_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=_make_http_error(403, "0")):
            with pytest.raises(GitHubRateLimitError) as exc:
                _get("https://api.github.com/test")
        assert "GITHUB_TOKEN" in str(exc.value)

    def test_429_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=_make_http_error(429)):
            with pytest.raises(GitHubRateLimitError):
                _get("https://api.github.com/test")

    def test_search_repos_propagates_rate_limit(self):
        with mock.patch("genesis_architect.core.github._get",
                        side_effect=GitHubRateLimitError("rate limit")):
            with pytest.raises(GitHubRateLimitError):
                search_repos("podcast downloader")

    def test_fetch_issues_propagates_rate_limit(self):
        with mock.patch("genesis_architect.core.github._get",
                        side_effect=GitHubRateLimitError("rate limit")):
            with pytest.raises(GitHubRateLimitError):
                fetch_issues("user/repo")

    def test_rate_limit_message_contains_instructions(self):
        with mock.patch("urllib.request.urlopen", side_effect=_make_http_error(403, "0")):
            with pytest.raises(GitHubRateLimitError) as exc:
                _get("https://api.github.com/test")
        msg = str(exc.value)
        assert "genesis config set GITHUB_TOKEN" in msg
        assert "github.com/settings/tokens" in msg


# ---------------------------------------------------------------------------
# fork_analyzer ranking - merged PRs not stars
# ---------------------------------------------------------------------------

class TestForkAnalyzerRanking:
    def _mock_forks(self):
        return [
            {"full_name": "user/fork-a", "html_url": "https://github.com/user/fork-a",
             "pushed_at": "2024-01-01", "stargazers_count": 500},
            {"full_name": "user/fork-b", "html_url": "https://github.com/user/fork-b",
             "pushed_at": "2024-01-02", "stargazers_count": 10},
            {"full_name": "user/fork-c", "html_url": "https://github.com/user/fork-c",
             "pushed_at": "2024-01-03", "stargazers_count": 1},
        ]

    def test_ranks_by_merged_prs_not_stars(self):
        # fork-a has 500 stars but 1 merged PR
        # fork-b has 10 stars but 5 merged PRs  -> should be ranked first
        # fork-c has 1 star but 3 merged PRs    -> should be ranked second
        pr_counts = {"user/fork-a": 1, "user/fork-b": 5, "user/fork-c": 3}

        with mock.patch("genesis_architect.core.fork_analyzer._get",
                        return_value=self._mock_forks()):
            with mock.patch("genesis_architect.core.fork_analyzer._recent_merged_pr_count",
                            side_effect=lambda repo, token, **kw: pr_counts.get(repo, 0)):
                result = fork_analyzer.top_active_forks("original/repo", limit=3)

        assert result[0]["name"] == "user/fork-b"
        assert result[1]["name"] == "user/fork-c"
        assert result[2]["name"] == "user/fork-a"

    def test_excludes_forks_with_zero_activity(self):
        pr_counts = {"user/fork-a": 0, "user/fork-b": 0, "user/fork-c": 2}

        with mock.patch("genesis_architect.core.fork_analyzer._get",
                        return_value=self._mock_forks()):
            with mock.patch("genesis_architect.core.fork_analyzer._recent_merged_pr_count",
                            side_effect=lambda repo, token, **kw: pr_counts.get(repo, 0)):
                result = fork_analyzer.top_active_forks("original/repo", limit=3)

        assert len(result) == 1
        assert result[0]["name"] == "user/fork-c"

    def test_limit_respected(self):
        pr_counts = {"user/fork-a": 3, "user/fork-b": 5, "user/fork-c": 2}

        with mock.patch("genesis_architect.core.fork_analyzer._get",
                        return_value=self._mock_forks()):
            with mock.patch("genesis_architect.core.fork_analyzer._recent_merged_pr_count",
                            side_effect=lambda repo, token, **kw: pr_counts.get(repo, 0)):
                result = fork_analyzer.top_active_forks("original/repo", limit=2)

        assert len(result) == 2

    def test_rate_limit_propagates_from_fork_analyzer(self):
        with mock.patch("genesis_architect.core.fork_analyzer._get",
                        side_effect=GitHubRateLimitError("rate limit")):
            with pytest.raises(GitHubRateLimitError):
                fork_analyzer.top_active_forks("original/repo")
