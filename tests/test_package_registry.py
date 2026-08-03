"""Tests for package_registry.py — offline (all network calls mocked)."""
from __future__ import annotations

from unittest.mock import patch


from genesis_architect.pro.package_registry import (
    PackageSignal,
    _days_since,
    _signal_line,
    _status,
    query_crates,
    query_maven,
    query_npm,
    query_nuget,
    query_osv,
    query_package,
    query_pypi,
    score_packages,
)


# ---------------------------------------------------------------------------
# _days_since
# ---------------------------------------------------------------------------

class TestDaysSince:
    def test_iso_date_returns_non_negative(self):
        # A date from the past should give ≥ 0 days
        result = _days_since("2020-01-01T00:00:00")
        assert result > 0

    def test_future_date_returns_negative_or_zero(self):
        # Far future date → 0 or negative (datetime subtraction)
        result = _days_since("2099-01-01T00:00:00")
        assert result <= 0

    def test_malformed_string_returns_minus_one(self):
        assert _days_since("not-a-date") == -1

    def test_empty_string_returns_minus_one(self):
        assert _days_since("") == -1

    def test_z_suffix_handled(self):
        result = _days_since("2020-06-15T12:00:00Z")
        assert result > 0

    def test_recent_date_active_range(self):
        # A date 10 days ago should give ~10
        from datetime import datetime, timedelta, timezone
        d = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result = _days_since(d)
        assert 8 <= result <= 12   # allow ±2 for clock drift


# ---------------------------------------------------------------------------
# _status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_negative_is_unknown(self):
        assert _status(-1) == "unknown"

    def test_zero_is_active(self):
        assert _status(0) == "active"

    def test_180_is_active(self):
        assert _status(180) == "active"

    def test_181_is_slow(self):
        assert _status(181) == "slow"

    def test_365_is_slow(self):
        assert _status(365) == "slow"

    def test_366_is_stale(self):
        assert _status(366) == "stale"

    def test_1000_is_stale(self):
        assert _status(1000) == "stale"


# ---------------------------------------------------------------------------
# _signal_line
# ---------------------------------------------------------------------------

class TestSignalLine:
    def test_active_contains_package_name(self):
        line = _signal_line("requests", "pypi", "active", 10, -1)
        assert "requests" in line
        assert "pypi" in line

    def test_stale_shows_months(self):
        line = _signal_line("oldpkg", "npm", "stale", 400, -1)
        assert "months" in line

    def test_unknown_shows_unknown_text(self):
        line = _signal_line("mypkg", "crates", "unknown", -1, -1)
        assert "unknown" in line

    def test_million_downloads_formatted(self):
        line = _signal_line("react", "npm", "active", 10, 5_000_000)
        assert "M downloads" in line or "5" in line

    def test_thousands_formatted(self):
        line = _signal_line("mypkg", "pypi", "active", 5, 50_000)
        assert "k downloads" in line or "50" in line

    def test_low_adoption_flagged(self):
        line = _signal_line("obscure", "npm", "active", 5, 42)
        assert "low adoption" in line or "42" in line

    def test_active_emoji_present(self):
        line = _signal_line("pkg", "pypi", "active", 30, -1)
        assert "✅" in line


# ---------------------------------------------------------------------------
# query_pypi (mocked)
# ---------------------------------------------------------------------------

_PYPI_FIXTURE = {
    "info": {"version": "2.28.0"},
    "releases": {
        "2.28.0": [{"upload_time": "2023-05-01T12:00:00"}]
    }
}

class TestQueryPypi:
    def test_returns_package_signal(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=_PYPI_FIXTURE):
            sig = query_pypi("requests")
        assert isinstance(sig, PackageSignal)
        assert sig.name == "requests"
        assert sig.ecosystem == "pypi"
        assert sig.latest_version == "2.28.0"

    def test_status_is_string(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=_PYPI_FIXTURE):
            sig = query_pypi("requests")
        assert sig.status in ("active", "slow", "stale", "unknown")

    def test_signal_line_is_nonempty(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=_PYPI_FIXTURE):
            sig = query_pypi("requests")
        assert len(sig.signal_line) > 0

    def test_registry_unavailable_returns_unknown(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=None):
            sig = query_pypi("requests")
        assert sig.status == "unknown"
        assert sig.latest_version == "?"

    def test_no_releases_gives_minus_one_days(self):
        data = {"info": {"version": "1.0.0"}, "releases": {"1.0.0": []}}
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=data):
            sig = query_pypi("mypkg")
        assert sig.last_release_days == -1


# ---------------------------------------------------------------------------
# query_npm (mocked)
# ---------------------------------------------------------------------------

_NPM_META_FIXTURE = {
    "dist-tags": {"latest": "18.2.0"},
    "time": {"modified": "2023-06-01T10:00:00Z", "18.2.0": "2023-06-01T10:00:00Z"},
}
_NPM_DL_FIXTURE = {"downloads": 3_000_000}

class TestQueryNpm:
    def test_returns_package_signal(self):
        def fake_fetch(url, **kw):
            if "downloads" in url:
                return _NPM_DL_FIXTURE
            return _NPM_META_FIXTURE
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   side_effect=fake_fetch):
            sig = query_npm("react")
        assert isinstance(sig, PackageSignal)
        assert sig.name == "react"
        assert sig.ecosystem == "npm"

    def test_downloads_populated(self):
        def fake_fetch(url, **kw):
            return _NPM_DL_FIXTURE if "downloads" in url else _NPM_META_FIXTURE
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   side_effect=fake_fetch):
            sig = query_npm("react")
        assert sig.monthly_downloads == 3_000_000

    def test_registry_unavailable(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=None):
            sig = query_npm("react")
        assert sig.status == "unknown"


# ---------------------------------------------------------------------------
# query_crates (mocked)
# ---------------------------------------------------------------------------

_CRATES_FIXTURE = {
    "crate": {
        "newest_version": "1.0.188",
        "updated_at": "2023-07-01T00:00:00Z",
        "downloads": 50_000_000,
    }
}

class TestQueryCrates:
    def test_returns_package_signal(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=_CRATES_FIXTURE):
            sig = query_crates("serde")
        assert isinstance(sig, PackageSignal)
        assert sig.ecosystem == "crates"
        assert sig.latest_version == "1.0.188"

    def test_registry_unavailable(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=None):
            sig = query_crates("serde")
        assert sig.status == "unknown"


# ---------------------------------------------------------------------------
# query_package dispatcher
# ---------------------------------------------------------------------------

class TestQueryPackage:
    def test_dispatches_to_pypi(self):
        with patch("genesis_architect.pro.package_registry.query_pypi") as mock:
            mock.return_value = PackageSignal("p", "pypi", "1", 10, -1, "active", "line")
            query_package("requests", "pypi")
        mock.assert_called_once_with("requests")

    def test_dispatches_to_npm(self):
        with patch("genesis_architect.pro.package_registry.query_npm") as mock:
            mock.return_value = PackageSignal("p", "npm", "1", 10, -1, "active", "line")
            query_package("react", "npm")
        mock.assert_called_once_with("react")

    def test_dispatches_to_crates(self):
        with patch("genesis_architect.pro.package_registry.query_crates") as mock:
            mock.return_value = PackageSignal("p", "crates", "1", 10, -1, "active", "line")
            query_package("serde", "crates")
        mock.assert_called_once_with("serde")

    def test_crates_io_alias(self):
        with patch("genesis_architect.pro.package_registry.query_crates") as mock:
            mock.return_value = PackageSignal("p", "crates", "1", 10, -1, "active", "line")
            query_package("serde", "crates.io")
        mock.assert_called_once()

    def test_dispatches_to_maven(self):
        with patch("genesis_architect.pro.package_registry.query_maven") as mock:
            mock.return_value = PackageSignal("p", "maven", "1", 10, -1, "active", "line")
            query_package("com.google.guava:guava", "maven")
        mock.assert_called_once_with("com.google.guava:guava")

    def test_dispatches_to_nuget(self):
        with patch("genesis_architect.pro.package_registry.query_nuget") as mock:
            mock.return_value = PackageSignal("p", "nuget", "1", 10, -1, "active", "line")
            query_package("Newtonsoft.Json", "nuget")
        mock.assert_called_once_with("Newtonsoft.Json")

    def test_unsupported_ecosystem_returns_unknown(self):
        sig = query_package("something", "homebrew")
        assert sig.status == "unknown"
        assert "unsupported" in sig.signal_line


# ---------------------------------------------------------------------------
# query_maven / query_nuget
# ---------------------------------------------------------------------------

class TestQueryMaven:
    def test_parses_search_response(self):
        payload = {"response": {"docs": [{"latestVersion": "33.0.0",
                                          "timestamp": 1700000000000}]}}
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=payload):
            sig = query_maven("com.google.guava:guava")
        assert sig.ecosystem == "maven"
        assert sig.latest_version == "33.0.0"
        assert sig.last_release_days > 0

    def test_bad_coordinates_return_unknown(self):
        sig = query_maven("guava-without-group")
        assert sig.status == "unknown"
        assert "groupId:artifactId" in sig.signal_line

    def test_registry_unavailable(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=None):
            sig = query_maven("com.google.guava:guava")
        assert sig.status == "unknown"


class TestQueryNuget:
    def test_parses_search_and_registration(self):
        search = {"data": [{"version": "13.0.3", "totalDownloads": 5_000_000_000}]}
        reg = {"items": [{"items": [{"catalogEntry": {"published": "2024-01-01T00:00:00Z"}}]}]}
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   side_effect=[search, reg]):
            sig = query_nuget("Newtonsoft.Json")
        assert sig.ecosystem == "nuget"
        assert sig.latest_version == "13.0.3"
        assert sig.monthly_downloads == 5_000_000_000
        assert sig.last_release_days > 0

    def test_follows_page_reference_when_index_has_no_leaves(self):
        search = {"data": [{"version": "4.0.0", "totalDownloads": 10}]}
        index = {"items": [{"@id": "https://api.nuget.org/page/2"}]}
        page = {"items": [{"catalogEntry": {"published": "2024-01-01T00:00:00Z"}}]}
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   side_effect=[search, index, page]):
            sig = query_nuget("Serilog")
        assert sig.last_release_days > 0

    def test_registry_unavailable(self):
        with patch("genesis_architect.pro.package_registry._fetch_json",
                   return_value=None):
            sig = query_nuget("Newtonsoft.Json")
        assert sig.status == "unknown"


# ---------------------------------------------------------------------------
# query_osv (CVE validation)
# ---------------------------------------------------------------------------

class TestQueryOSV:
    def _osv_response(self, payload):
        import io
        import json as _json

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _Resp(_json.dumps(payload).encode())

    def test_prefers_cve_alias_over_osv_id(self):
        payload = {"vulns": [{"id": "GHSA-xxxx", "aliases": ["CVE-2024-26130"]}]}
        with patch("urllib.request.urlopen", return_value=self._osv_response(payload)):
            sig = query_osv("cryptography", "pypi", "42.0.2")
        assert sig.vuln_ids == ["CVE-2024-26130"]
        assert "CVE-2024-26130" in sig.signal_line

    def test_no_vulns_gives_clean_line(self):
        with patch("urllib.request.urlopen", return_value=self._osv_response({})):
            sig = query_osv("requests", "pypi", "9.9.9")
        assert sig.vuln_ids == []
        assert "no known vulnerabilities" in sig.signal_line

    def test_network_failure_degrades_gracefully(self):
        with patch("urllib.request.urlopen", side_effect=OSError("boom")):
            sig = query_osv("requests", "pypi")
        assert sig.vuln_ids == []
        assert "unavailable" in sig.signal_line

    def test_ecosystem_mapping(self):
        captured = {}

        def fake_urlopen(req, timeout=0):
            import json as _json
            captured.update(_json.loads(req.data))
            return self._osv_response({})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            query_osv("serde", "crates")
        assert captured["package"]["ecosystem"] == "crates.io"


# ---------------------------------------------------------------------------
# score_packages
# ---------------------------------------------------------------------------

class TestScorePackages:
    def _make_sig(self, name, status):
        return PackageSignal(name, "pypi", "1", 10, -1, status, f"{status} line")

    def test_stale_sorted_first(self):
        stale = self._make_sig("stale_pkg", "stale")
        active = self._make_sig("active_pkg", "active")
        slow = self._make_sig("slow_pkg", "slow")
        with patch("genesis_architect.pro.package_registry.query_package",
                   side_effect=[stale, active, slow]):
            results = score_packages([("stale_pkg", "pypi"),
                                      ("active_pkg", "pypi"),
                                      ("slow_pkg", "pypi")])
        assert results[0].status == "stale"
        assert results[-1].status == "active"

    def test_returns_all_signals(self):
        sig = self._make_sig("pkg", "active")
        with patch("genesis_architect.pro.package_registry.query_package",
                   return_value=sig):
            results = score_packages([("pkg", "pypi"), ("pkg2", "npm")])
        assert len(results) == 2

    def test_empty_list_returns_empty(self):
        assert score_packages([]) == []
