"""
HTTP + feed parsing layer. HTTP is always handled by requests; feedparser
receives pre-fetched text, never a URL.

# Architecture note: requests-first pattern (inspired by kissgyorgy/simple-podcast-dl)
# Avoids: PITFALLS.md #1 (feedparser hangs with no timeout)
#         PITFALLS.md #2 (silent network errors in feedparser 6.x)
#         PITFALLS.md #3 (wrong Content-Type rejects valid feeds)
"""

import logging
from typing import Any

import feedparser
import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10


def fetch_feed(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """
    Fetch and parse an RSS feed. Returns a feedparser result dict.

    Raises:
        requests.RequestException: on network failure.
        ValueError: if the response body cannot be parsed as a feed.
    """
    log.debug("Fetching feed: %s", url)
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "podcast-dl/0.1"})
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)

    if feed.bozo and not feed.entries:
        raise ValueError(
            f"Feed parse error for {url!r}: {feed.get('bozo_exception', 'unknown')}"
        )

    if not feed.entries and not feed.feed:
        raise ValueError(f"No entries or feed metadata found at {url!r}")

    log.info("Fetched %d entries from %s", len(feed.entries), url)
    return feed
