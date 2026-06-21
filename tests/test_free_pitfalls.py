"""Tests for the free-tier pitfall hook (the upsell preview)."""

from genesis_architect.core.free_pitfalls import (
    FREE_PITFALL_CAP,
    format_free_summary,
    top_free_pitfalls,
)
from genesis_architect.core.issue_miner import Issue


def _issue(num: int, comments: int, reactions: int) -> Issue:
    return Issue(
        repo="acme/widget",
        number=num,
        title=f"Bug {num}",
        url=f"https://github.com/acme/widget/issues/{num}",
        comments=comments,
        reactions=reactions,
        category="bug",
        labels=["bug"],
        closed=False,
    )


def test_cap_is_three():
    assert FREE_PITFALL_CAP == 3


def test_top_free_pitfalls_caps_results(monkeypatch):
    pool = [_issue(i, comments=i, reactions=0) for i in range(1, 11)]
    monkeypatch.setattr(
        "genesis_architect.core.free_pitfalls.mine_repo",
        lambda *a, **k: list(pool),
    )
    result = top_free_pitfalls(["acme/widget"])
    assert len(result) == FREE_PITFALL_CAP


def test_top_free_pitfalls_sorted_by_engagement(monkeypatch):
    pool = [_issue(1, 1, 0), _issue(2, 9, 0), _issue(3, 5, 0)]
    monkeypatch.setattr(
        "genesis_architect.core.free_pitfalls.mine_repo",
        lambda *a, **k: list(pool),
    )
    result = top_free_pitfalls(["acme/widget"])
    engagements = [i.engagement for i in result]
    assert engagements == sorted(engagements, reverse=True)
    assert result[0].number == 2


def test_format_includes_upgrade_pointer(monkeypatch):
    summary = format_free_summary([_issue(1, 5, 2)])
    assert "Pro" in summary
    assert "github.com/maioio/genesis-architect" in summary


def test_format_empty_is_graceful():
    summary = format_free_summary([])
    assert "No high-engagement pitfalls" in summary
    assert "Pro" in summary
