"""Tests for first_run - the no-setup customer readiness surface.

Encodes the packaging promise (Constitution 13): license is the only required
step; everything else is optional and never blocks; status checks never install
or phone home; offline reporting is honest.
"""

import pytest

from genesis_architect_pro.first_run import (
    Check, Readiness, CUSTOMER_FLOW, OPTIONAL_DEPS,
    LOCAL_CAPABILITIES, NETWORK_CAPABILITIES,
    check_readiness, doctor_report, offline_capability_report,
    ensure_optional_dep,
)


@pytest.fixture
def no_license(monkeypatch):
    monkeypatch.delenv("GENESIS_PRO_LICENSE", raising=False)
    # also neutralize a license file if is_licensed reads one
    monkeypatch.setattr("genesis_architect_pro.license.is_licensed",
                        lambda: False)


@pytest.fixture
def licensed(monkeypatch):
    monkeypatch.setattr("genesis_architect_pro.license.is_licensed",
                        lambda: True)


class TestReadinessModel:
    def test_required_gap_blocks_ready(self):
        r = Readiness(licensed=False, pro_installed=True, checks=[
            Check("license", ok=False, required=True),
            Check("ffmpeg", ok=False, required=False),
        ])
        assert r.ready_to_work is False
        assert [c.name for c in r.missing_required()] == ["license"]
        assert [c.name for c in r.optional_gaps()] == ["ffmpeg"]

    def test_only_optional_gaps_is_ready(self):
        r = Readiness(licensed=True, pro_installed=True, checks=[
            Check("license", ok=True, required=True),
            Check("ffmpeg", ok=False, required=False),
        ])
        assert r.ready_to_work is True

    def test_check_status_strings(self):
        assert Check("x", True, True).status() == "ready"
        assert Check("x", False, True).status() == "MISSING"
        assert Check("x", False, False).status() == "optional"


class TestCheckReadiness:
    def test_license_required(self, no_license):
        r = check_readiness()
        lic = next(c for c in r.checks if c.name == "license")
        assert lic.required is True and lic.ok is False
        assert r.ready_to_work is False  # no license -> not ready (by default path)

    def test_licensed_marks_ready_when_pro_present(self, licensed):
        r = check_readiness()
        assert r.licensed is True
        lic = next(c for c in r.checks if c.name == "license")
        assert lic.ok is True

    def test_optional_deps_present_in_checks(self, licensed):
        names = {c.name for c in check_readiness().checks}
        for dep in OPTIONAL_DEPS:
            assert dep in names

    def test_optional_deps_never_required(self, licensed):
        for c in check_readiness().checks:
            if c.name in OPTIONAL_DEPS:
                assert c.required is False


class TestDoctorReport:
    def test_report_when_not_ready(self, no_license):
        out = doctor_report()
        assert "readiness check" in out
        assert "MISSING" in out and "GENESIS_PRO_LICENSE" in out

    def test_report_when_ready(self, licensed):
        out = doctor_report()
        # may still list optional gaps, but no required item is missing
        assert "Ready" in out or "Almost there" not in out

    def test_customer_flow_is_four_steps(self):
        assert CUSTOMER_FLOW.count("\n") == 3  # 4 lines
        assert "license key" in CUSTOMER_FLOW.lower()


class TestOfflineReport:
    def test_online_everything_available(self):
        rep = offline_capability_report(network_available=True)
        assert rep["unavailable"] == []
        assert set(LOCAL_CAPABILITIES).issubset(set(rep["available"]))
        assert set(NETWORK_CAPABILITIES).issubset(set(rep["available"]))

    def test_offline_local_still_works(self):
        rep = offline_capability_report(network_available=False)
        # local analysis always available
        assert set(LOCAL_CAPABILITIES).issubset(set(rep["available"]))
        # network features honestly marked unavailable, not faked
        assert set(rep["unavailable"]) == set(NETWORK_CAPABILITIES)
        assert "fabricated" in rep["note"]


class TestSelfHeal:
    def test_status_check_never_installs(self):
        # auto_install=False must never attempt installation
        res = ensure_optional_dep("ffmpeg", auto_install=False)
        assert res.attempted is False
        # either already present, or guidance only
        assert res.already_present or "missing" in res.message.lower()

    def test_unknown_dep(self):
        res = ensure_optional_dep("postgresql")
        assert res.ok is False and "not a known optional" in res.message

    def test_present_dep_is_noop(self, monkeypatch):
        monkeypatch.setattr("genesis_architect_pro.first_run._have",
                            lambda d: True)
        res = ensure_optional_dep("ffmpeg", auto_install=True)
        assert res.already_present is True and res.ok is True
        assert res.attempted is False

    def test_git_not_silently_installed(self, monkeypatch):
        monkeypatch.setattr("genesis_architect_pro.first_run._have",
                            lambda d: False)
        res = ensure_optional_dep("git", auto_install=True)
        # system tools are guided, not silently installed
        assert "package manager" in res.message


class TestResilience:
    def test_check_readiness_never_raises(self, monkeypatch):
        # even if license probing explodes, status must degrade, not crash
        def boom():
            raise RuntimeError("x")
        monkeypatch.setattr("genesis_architect_pro.license.is_licensed", boom)
        r = check_readiness()  # must not raise
        assert r.licensed is False
