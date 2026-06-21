"""
Package registry adapters: PyPI, npm, crates.io.
All APIs are public, require no key, and degrade gracefully on failure.

Used by Ecosystem Velocity Scoring in Phase 2.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class PackageSignal:
    name: str
    ecosystem: str          # pypi | npm | crates
    latest_version: str
    last_release_days: int  # days since last release (-1 = unknown)
    monthly_downloads: int  # -1 = unknown
    status: str             # active | slow | stale | unknown
    signal_line: str        # one-line display for Phase 5


def _fetch_json(url: str, timeout: int = 8) -> dict | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "genesis-architect-registry/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # NOSONAR
            return json.loads(resp.read())
    except Exception:
        return None


def _days_since(iso_date: str) -> int:
    """Parse ISO 8601 date and return days since then. -1 on parse failure."""
    try:
        clean = iso_date[:19].replace("Z", "").replace(" ", "T")
        dt = datetime.fromisoformat(clean).replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt).days
    except Exception:
        return -1


def _status(days: int) -> str:
    if days < 0:
        return "unknown"
    if days <= 180:
        return "active"
    if days <= 365:
        return "slow"
    return "stale"


def _signal_line(pkg: str, ecosystem: str, status: str, days: int, downloads: int) -> str:
    icon = {"active": "✅", "slow": "⚠", "stale": "⚠", "unknown": "❓"}[status]
    parts = [f"{icon} {pkg} ({ecosystem})"]
    if status == "active":
        parts.append("actively maintained")
    elif status in ("slow", "stale"):
        months = days // 30
        parts.append(f"no release in {months} months")
    else:
        parts.append("release date unknown")
    if downloads >= 0:
        if downloads >= 1_000_000:
            parts.append(f"{downloads // 1_000_000}M downloads/month")
        elif downloads >= 1_000:
            parts.append(f"{downloads // 1_000}k downloads/month")
        elif downloads < 1_000:
            parts.append(f"⚠ low adoption ({downloads}/month)")
    return " - ".join(parts)


# --- PyPI ---

def query_pypi(package: str) -> PackageSignal:
    """Query PyPI JSON API for package activity signal."""
    data = _fetch_json(f"https://pypi.org/pypi/{package}/json")
    if not data:
        return PackageSignal(package, "pypi", "?", -1, -1, "unknown",
                             f"❓ {package} (pypi) - registry unavailable")

    info = data.get("info", {})
    latest = info.get("version", "?")

    # Find most recent release date across all files of latest version
    releases = data.get("releases", {}).get(latest, [])
    upload_dates = [f.get("upload_time", "") for f in releases if f.get("upload_time")]
    days = _days_since(max(upload_dates)) if upload_dates else -1
    status = _status(days)

    return PackageSignal(
        name=package, ecosystem="pypi", latest_version=latest,
        last_release_days=days, monthly_downloads=-1,
        status=status,
        signal_line=_signal_line(package, "pypi", status, days, -1),
    )


# --- npm ---

def query_npm(package: str) -> PackageSignal:
    """Query npm registry + downloads API for package activity signal."""
    meta = _fetch_json(f"https://registry.npmjs.org/{package}")
    if not meta:
        return PackageSignal(package, "npm", "?", -1, -1, "unknown",
                             f"❓ {package} (npm) - registry unavailable")

    latest = (meta.get("dist-tags") or {}).get("latest", "?")
    time_map = meta.get("time", {})
    modified = time_map.get("modified") or time_map.get(latest, "")
    days = _days_since(modified) if modified else -1
    status = _status(days)

    # Download stats (separate endpoint)
    dl_data = _fetch_json(f"https://api.npmjs.org/downloads/point/last-month/{package}")
    monthly = dl_data.get("downloads", -1) if dl_data else -1

    return PackageSignal(
        name=package, ecosystem="npm", latest_version=latest,
        last_release_days=days, monthly_downloads=monthly,
        status=status,
        signal_line=_signal_line(package, "npm", status, days, monthly),
    )


# --- crates.io ---

def query_crates(package: str) -> PackageSignal:
    """Query crates.io API for crate activity signal. Rust projects only."""
    data = _fetch_json(f"https://crates.io/api/v1/crates/{package}")
    if not data:
        return PackageSignal(package, "crates", "?", -1, -1, "unknown",
                             f"❓ {package} (crates.io) - registry unavailable")

    crate = data.get("crate", {})
    latest = crate.get("newest_version", "?")
    updated = crate.get("updated_at", "")
    days = _days_since(updated) if updated else -1
    status = _status(days)
    downloads = crate.get("downloads", -1)

    return PackageSignal(
        name=package, ecosystem="crates", latest_version=latest,
        last_release_days=days, monthly_downloads=downloads,
        status=status,
        signal_line=_signal_line(package, "crates", status, days, downloads),
    )


# --- Dispatcher ---

def query_package(package: str, ecosystem: str) -> PackageSignal:
    """
    Dispatch to the correct registry adapter.
    ecosystem: 'pypi' | 'npm' | 'crates'
    """
    if ecosystem == "pypi":
        return query_pypi(package)
    if ecosystem == "npm":
        return query_npm(package)
    if ecosystem in ("crates", "crates.io"):
        return query_crates(package)
    return PackageSignal(package, ecosystem, "?", -1, -1, "unknown",
                         f"❓ {package} - unsupported ecosystem: {ecosystem}")


def score_packages(packages: list[tuple[str, str]]) -> list[PackageSignal]:
    """
    Query multiple packages and return signals sorted: stale first, then slow, then active.
    packages: list of (name, ecosystem) tuples.
    """
    results = [query_package(name, eco) for name, eco in packages]
    order = {"stale": 0, "slow": 1, "unknown": 2, "active": 3}
    results.sort(key=lambda s: order.get(s.status, 2))
    return results
