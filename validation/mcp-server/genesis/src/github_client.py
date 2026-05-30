# Architecture note: all HTTP behind fetch_json - never urlopen outside this module
# Avoids: Pitfall 3 - unhandled 403/429 crashes entire MCP server

import urllib.request
import urllib.error
import json
import os

_TOKEN = os.environ.get("GITHUB_TOKEN")

def _headers():
    h = {"Accept": "application/vnd.github+json"}
    if _TOKEN:
        h["Authorization"] = f"Bearer {_TOKEN}"
    return h

def fetch_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"isError": True, "error": "GitHub rate limit exceeded. Set GITHUB_TOKEN env var for 5000 req/hour."}
        if e.code == 429:
            retry_after = e.headers.get("Retry-After", "60")
            return {"isError": True, "error": f"GitHub rate limit (429). Retry after {retry_after}s."}
        if e.code == 404:
            return {"isError": True, "error": f"Not found: {url}"}
        return {"isError": True, "error": f"GitHub API error {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"isError": True, "error": f"Network error: {e.reason}"}
