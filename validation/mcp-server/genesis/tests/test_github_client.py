# Tests from PITFALLS.md Pitfall 3 - HTTP errors return isError, don't crash
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import patch, MagicMock
import urllib.error
from github_client import fetch_json

def make_http_error(code, reason="Error", headers=None):
    err = urllib.error.HTTPError(url="http://x", code=code, msg=reason, hdrs=headers or {}, fp=None)
    return err

def test_403_returns_rate_limit_message():
    with patch("github_client.urllib.request.urlopen", side_effect=make_http_error(403)):
        result = fetch_json("http://fake")
    assert result["isError"] is True
    assert "rate limit" in result["error"].lower()
    assert "GITHUB_TOKEN" in result["error"]

def test_429_returns_retry_after():
    headers = MagicMock()
    headers.get = lambda k, d="60": "30" if k == "Retry-After" else d
    with patch("github_client.urllib.request.urlopen", side_effect=make_http_error(429, headers=headers)):
        result = fetch_json("http://fake")
    assert result["isError"] is True
    assert "30" in result["error"]

def test_404_returns_not_found():
    with patch("github_client.urllib.request.urlopen", side_effect=make_http_error(404)):
        result = fetch_json("http://fake")
    assert result["isError"] is True
    assert "Not found" in result["error"]

def test_network_error_returns_is_error():
    with patch("github_client.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = fetch_json("http://fake")
    assert result["isError"] is True
    assert "Network error" in result["error"]

def test_successful_response_parsed():
    mock_response = MagicMock()
    mock_response.read.return_value = b'[{"number": 1, "title": "test"}]'
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("github_client.urllib.request.urlopen", return_value=mock_response):
        result = fetch_json("http://fake")
    assert isinstance(result, list)
    assert result[0]["number"] == 1
