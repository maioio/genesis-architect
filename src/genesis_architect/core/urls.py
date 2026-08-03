"""Host matching for URLs coming from outside the process.

Genesis classifies research results by where they came from, and that
classification feeds a confidence weight. A substring test like
``"reddit.com" in url`` is the wrong tool for the job: it also matches

    https://evil.example/reddit.com/thread
    https://reddit.com.attacker.example/x

so anyone who controls a URL in a search result can borrow the credibility of
a source Genesis trusts. Parse the host and compare it properly instead.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

__all__ = ["host_of", "host_matches"]

# A hostname is letters, digits, dots and hyphens. Anything else (spaces, for
# instance) means the input was not a URL at all. Without this, `urlparse`
# happily reports "not a url" as the host of "//not a url".
_VALID_HOST = re.compile(r"\A[a-z0-9.-]+\Z")


def host_of(url: str) -> str:
    """Return the lowercased hostname of ``url``, or "" if there isn't one.

    Never raises: these URLs arrive from search APIs and scraped pages, so
    malformed input is expected and must degrade to "no match".
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url if "//" in url else f"//{url}")
        host = (parsed.hostname or "").lower()
    except ValueError:
        # urlparse rejects things like an invalid IPv6 literal.
        return ""
    if not _VALID_HOST.match(host):
        return ""
    return host[4:] if host.startswith("www.") else host


def host_matches(url: str, *domains: str) -> bool:
    """True if ``url``'s host is one of ``domains``, or a subdomain of one.

    ``host_matches("https://old.reddit.com/r/x", "reddit.com")`` is True;
    ``host_matches("https://reddit.com.evil.test/x", "reddit.com")`` is not.
    """
    host = host_of(url)
    if not host:
        return False
    return any(
        host == d or host.endswith(f".{d}")
        for d in (d.lower().lstrip(".") for d in domains)
    )
