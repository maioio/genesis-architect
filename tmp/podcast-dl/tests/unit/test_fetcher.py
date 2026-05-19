"""Tests for core/fetcher.py."""

import sys
from pathlib import Path
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from podcast_dl.core.fetcher import fetch_feed

MINIMAL_RSS = """\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Podcast</title>
    <item>
      <title>Episode 1</title>
      <enclosure url="https://example.com/ep1.mp3" type="audio/mpeg" length="1024"/>
    </item>
  </channel>
</rss>
"""


def _mock_resp(text, status=200):
    r = mock.Mock()
    r.text = text
    r.status_code = status
    r.raise_for_status = mock.Mock()
    return r


class TestFetchFeed:
    def test_returns_entries(self):
        with mock.patch("podcast_dl.core.fetcher.requests.get", return_value=_mock_resp(MINIMAL_RSS)):
            feed = fetch_feed("https://example.com/feed.rss")
        assert len(feed.entries) == 1

    def test_feedparser_receives_text_not_url(self):
        with mock.patch("podcast_dl.core.fetcher.requests.get", return_value=_mock_resp(MINIMAL_RSS)):
            with mock.patch("podcast_dl.core.fetcher.feedparser.parse") as mock_parse:
                mock_parse.return_value = mock.Mock(
                    entries=[mock.Mock()], feed=mock.Mock(), bozo=False
                )
                fetch_feed("https://example.com/feed.rss")
            arg = mock_parse.call_args[0][0]
            assert isinstance(arg, str)

    def test_network_error_propagates(self):
        import requests as req
        with mock.patch("podcast_dl.core.fetcher.requests.get",
                        side_effect=req.ConnectionError("refused")):
            with pytest.raises(req.ConnectionError):
                fetch_feed("https://example.com/feed.rss")

    def test_bozo_empty_entries_raises(self):
        bozo = mock.Mock(bozo=True, bozo_exception=Exception("bad xml"),
                         entries=[], feed=mock.Mock())
        with mock.patch("podcast_dl.core.fetcher.requests.get", return_value=_mock_resp("")):
            with mock.patch("podcast_dl.core.fetcher.feedparser.parse", return_value=bozo):
                with pytest.raises(ValueError, match="parse error"):
                    fetch_feed("https://example.com/feed.rss")

    def test_timeout_forwarded(self):
        with mock.patch("podcast_dl.core.fetcher.requests.get", return_value=_mock_resp(MINIMAL_RSS)) as mg:
            fetch_feed("https://example.com/feed.rss", timeout=5)
        assert mg.call_args[1]["timeout"] == 5
