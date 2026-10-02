"""Tests for the capability map — the guard against engines nobody can find."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json

from genesis_architect_pro.capability_map import (
    CAPABILITIES,
    INTERNAL,
    format_map,
    gaps,
    stale_entries,
    to_dict,
    unmapped_modules,
)


def test_every_module_is_accounted_for():
    """The check the README never had.

    An engine that appears in neither the map nor INTERNAL is invisible: it
    exists, it works, and the only way to find it is to read the package. That
    is exactly how `recovery_scan` went unnoticed. Adding a module must force
    the decision "does this deserve a door?" — so this test fails until it does.
    """
    unmapped = unmapped_modules()
    assert not unmapped, (
        f"These modules are neither mapped to a command nor declared INTERNAL: "
        f"{sorted(unmapped)}. Add a Capability entry (with command=None if there "
        f"is no door yet) or list it in INTERNAL."
    )


def test_no_entry_points_at_a_deleted_module():
    stale = stale_entries()
    assert not stale, f"Capability entries for modules that no longer exist: {sorted(stale)}"


def test_map_and_internal_do_not_overlap():
    mapped = {c.module for c in CAPABILITIES}
    assert not (mapped & INTERNAL)


def test_entries_are_complete():
    for cap in CAPABILITIES:
        assert cap.module and cap.title and cap.what
        # command may be None (a declared gap) but must never be blank.
        assert cap.command is None or cap.command.strip()


def test_gaps_are_declared_not_hidden():
    """A doorless capability is printed as a gap rather than dropped."""
    for cap in gaps():
        assert cap.command is None
    if gaps():
        assert "no command yet" in format_map()


def test_format_map_lists_the_recovery_scan_with_its_command():
    """The specific lookup that failed: which command runs the recovery scan?"""
    output = format_map()
    assert "Recovery Scan" in output
    assert "genesis recover" in output


def test_format_map_can_show_modules():
    assert "[recovery_scan]" in format_map(show_modules=True)
    assert "[recovery_scan]" not in format_map(show_modules=False)


def test_to_dict_is_json_serializable():
    payload = json.loads(json.dumps(to_dict()))
    assert payload["engines"]
    assert payload["unmapped_modules"] == []
    assert payload["stale_entries"] == []
    modules = {e["module"] for e in payload["engines"]}
    # The three engines the critique found only by running `ls src/`.
    assert {"recovery_scan", "cross_session_memory", "package_registry"} <= modules


def test_previously_doorless_engines_now_have_commands():
    by_module = {c.module: c for c in CAPABILITIES}
    assert by_module["package_registry"].command.startswith("genesis deps")
    assert by_module["cross_session_memory"].command == "genesis memory --sessions"
    assert by_module["recovery_scan"].command.startswith("genesis recover")
