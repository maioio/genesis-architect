"""Tests for host matching.

These pin down the behaviour CodeQL flagged as
py/incomplete-url-substring-sanitization: a substring test like
`"reddit.com" in url` lets an attacker-controlled URL borrow the credibility
of a trusted source, because Genesis maps the source label to a confidence
weight.
"""

import pytest

from genesis_architect.core.urls import host_matches, host_of


class TestHostOf:
    @pytest.mark.parametrize("url,expected", [
        ("https://reddit.com/r/python", "reddit.com"),
        ("https://www.reddit.com/r/python", "reddit.com"),   # www stripped
        ("http://OLD.Reddit.COM/r/x", "old.reddit.com"),     # lowercased
        ("https://reddit.com:8443/r/x", "reddit.com"),       # port dropped
        ("reddit.com/r/x", "reddit.com"),                    # scheme optional
        ("", ""),
        ("not a url", ""),
        ("https://", ""),
    ])
    def test_host_extraction(self, url, expected):
        assert host_of(url) == expected

    def test_never_raises_on_malformed_input(self):
        # These arrive from search APIs and scraped pages; garbage is expected.
        for bad in ["http://[oops", "://", "%%%", "http://a b c"]:
            host_of(bad)  # must not raise


class TestHostMatches:
    @pytest.mark.parametrize("url", [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python",
        "https://old.reddit.com/r/python",   # subdomain counts
    ])
    def test_genuine_hosts_match(self, url):
        assert host_matches(url, "reddit.com")

    @pytest.mark.parametrize("url", [
        "https://evil.test/reddit.com/thread",      # domain in the path
        "https://reddit.com.attacker.test/thread",  # domain as a prefix
        "https://notreddit.com/thread",             # suffix without a dot
        "https://myreddit.com/thread",
        "",
    ])
    def test_spoofed_hosts_do_not_match(self, url):
        assert not host_matches(url, "reddit.com")

    def test_multiple_domains(self):
        assert host_matches("https://youtu.be/abc", "youtube.com", "youtu.be")
        assert not host_matches("https://vimeo.com/1", "youtube.com", "youtu.be")


class TestCallSitesAreHardened:
    """The two places the substring bug actually lived."""

    def test_pitfall_ranker_rejects_spoofed_source(self):
        from genesis_architect.pro.pitfall_ranker import from_exa_result
        genuine = from_exa_result({"url": "https://www.reddit.com/r/x"})
        assert genuine.source == "reddit"
        spoofed = from_exa_result({"url": "https://evil.test/reddit.com/x"})
        assert spoofed.source == "exa_blog"
        # and the spoof must not inherit reddit's confidence weight
        assert spoofed.confidence != genuine.confidence

    def test_video_research_rejects_spoofed_platform(self):
        from genesis_architect.pro.video_research import _detect_platform
        assert _detect_platform("https://youtu.be/abc") == "youtube"
        assert _detect_platform("https://www.youtube.com/watch?v=1") == "youtube"
        assert _detect_platform("https://evil.test/youtube.com/x") == "unknown"
        assert _detect_platform("https://youtube.com.evil.test/x") == "unknown"
