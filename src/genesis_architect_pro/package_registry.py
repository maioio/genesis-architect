"""
Package registry adapters: PyPI, npm, crates.io, Maven Central, NuGet —
plus CVE validation via OSV.dev.
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
    ecosystem: str          # pypi | npm | crates | maven | nuget
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


def _signal_line(pkg: str, ecosystem: str, status: str, days: int, downloads: int,
                 downloads_label: str = "downloads/month") -> str:
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
            parts.append(f"{downloads // 1_000_000}M {downloads_label}")
        elif downloads >= 1_000:
            parts.append(f"{downloads // 1_000}k {downloads_label}")
        elif downloads < 1_000:
            parts.append(f"⚠ low adoption ({downloads} {downloads_label})")
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
        signal_line=_signal_line(package, "crates", status, days, downloads,
                                 downloads_label="downloads all-time"),
    )


# --- Maven Central ---

def query_maven(package: str) -> PackageSignal:
    """Query Maven Central search API. `package` is "groupId:artifactId"."""
    group, _, artifact = package.partition(":")
    if not artifact:
        return PackageSignal(package, "maven", "?", -1, -1, "unknown",
                             f"❓ {package} (maven) - expected groupId:artifactId")
    data = _fetch_json(
        "https://search.maven.org/solrsearch/select"
        f"?q=g:%22{group}%22+AND+a:%22{artifact}%22&rows=1&wt=json"
    )
    docs = (data or {}).get("response", {}).get("docs", [])
    if not docs:
        return PackageSignal(package, "maven", "?", -1, -1, "unknown",
                             f"❓ {package} (maven) - registry unavailable")
    doc = docs[0]
    latest = doc.get("latestVersion", "?")
    ts_ms = doc.get("timestamp")
    days = -1
    if isinstance(ts_ms, (int, float)):
        days = (datetime.now(UTC) - datetime.fromtimestamp(ts_ms / 1000, UTC)).days
    status = _status(days)
    return PackageSignal(
        name=package, ecosystem="maven", latest_version=latest,
        last_release_days=days, monthly_downloads=-1,
        status=status,
        signal_line=_signal_line(package, "maven", status, days, -1),
    )


# --- NuGet ---

def query_nuget(package: str) -> PackageSignal:
    """Query NuGet search API for package activity signal."""
    data = _fetch_json(
        f"https://azuresearch-usnc.nuget.org/query?q=packageid:{package}&take=1"
    )
    hits = (data or {}).get("data", [])
    if not hits:
        return PackageSignal(package, "nuget", "?", -1, -1, "unknown",
                             f"❓ {package} (nuget) - registry unavailable")
    hit = hits[0]
    latest = hit.get("version", "?")
    downloads = hit.get("totalDownloads", -1)
    # Release date comes from the registration index (search API has none)
    days = -1
    reg = _fetch_json(
        f"https://api.nuget.org/v3/registration5-semver1/{package.lower()}/index.json"
    )
    if reg:
        pages = reg.get("items", [])
        last_page = pages[-1] if pages else {}
        leaves = last_page.get("items", [])
        if not leaves and last_page.get("@id"):
            # Large packages: the index only references its pages — fetch the last one.
            page = _fetch_json(last_page["@id"])
            leaves = (page or {}).get("items", [])
        if leaves:
            published = (leaves[-1].get("catalogEntry") or {}).get("published", "")
            days = _days_since(published) if published else -1
    status = _status(days)
    return PackageSignal(
        name=package, ecosystem="nuget", latest_version=latest,
        last_release_days=days, monthly_downloads=downloads,
        status=status,
        signal_line=_signal_line(package, "nuget", status, days, downloads,
                                 downloads_label="downloads all-time"),
    )


# --- OSV.dev CVE validation ---

# PackageSignal.ecosystem -> OSV ecosystem name
_OSV_ECOSYSTEM = {
    "pypi": "PyPI",
    "npm": "npm",
    "crates": "crates.io",
    "maven": "Maven",
    "nuget": "NuGet",
}


@dataclass
class CVESignal:
    name: str
    ecosystem: str
    version: str            # "" = all versions of the package
    vuln_ids: list[str]     # OSV/CVE identifiers, e.g. ["CVE-2024-39689"]
    signal_line: str        # one-line display


def query_osv(package: str, ecosystem: str, version: str = "") -> CVESignal:
    """Query OSV.dev for known vulnerabilities. Free API, no key.

    Degrades gracefully: network/API failure returns an empty CVESignal with
    an 'unavailable' signal line — it never raises.
    """
    osv_eco = _OSV_ECOSYSTEM.get(ecosystem, ecosystem)
    query: dict = {"package": {"name": package, "ecosystem": osv_eco}}
    if version:
        query["version"] = version
    try:
        req = urllib.request.Request(
            "https://api.osv.dev/v1/query",
            data=json.dumps(query).encode(),
            headers={"User-Agent": "genesis-architect-registry/1.0",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:  # NOSONAR
            data = json.loads(resp.read())
    except Exception:
        return CVESignal(package, ecosystem, version, [],
                         f"❓ {package} - OSV unavailable")

    vulns = data.get("vulns", []) or []
    ids: list[str] = []
    for v in vulns:
        aliases = v.get("aliases", []) or []
        cve = next((a for a in aliases if a.startswith("CVE-")), None)
        ids.append(cve or v.get("id", "?"))
    ids = list(dict.fromkeys(ids))
    at = f"@{version}" if version else ""
    if ids:
        line = f"⚠ {package}{at} ({ecosystem}) - {len(ids)} known vulnerabilit" \
               f"{'y' if len(ids) == 1 else 'ies'}: {', '.join(ids[:5])}"
    else:
        line = f"✅ {package}{at} ({ecosystem}) - no known vulnerabilities (OSV)"
    return CVESignal(package, ecosystem, version, ids, line)


# --- Dispatcher ---

def query_package(package: str, ecosystem: str) -> PackageSignal:
    """
    Dispatch to the correct registry adapter.
    ecosystem: 'pypi' | 'npm' | 'crates' | 'maven' | 'nuget'
    """
    if ecosystem == "pypi":
        return query_pypi(package)
    if ecosystem == "npm":
        return query_npm(package)
    if ecosystem in ("crates", "crates.io"):
        return query_crates(package)
    if ecosystem in ("maven", "maven-central"):
        return query_maven(package)
    if ecosystem == "nuget":
        return query_nuget(package)
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
