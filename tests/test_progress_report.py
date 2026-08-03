"""Tests for progress_report - downloadable HTML phase reports."""
from genesis_architect.pro.progress_report import (
    PhaseReport, ReportItem, render_report, write_report,
)


def _sample():
    return PhaseReport(
        title="Phase F1 — Floating Assistant",
        subtitle="Bubble + chat panel shell.",
        version="v6.6.0", tests_passing=1602,
        shipped=[ReportItem("UI shell", "done", "bubble ↔ panel"),
                 ReportItem("WebSocket wiring", "next", "F2")],
        works_now=["Opens in any browser"],
        coming_next=["Live engine events"],
        notes=["Pro-only"],
    )


class TestRender:
    def test_self_contained(self):
        html = render_report(_sample())
        assert html.startswith("<!DOCTYPE html>")
        external = [ln for ln in html.splitlines()
                    if "http" in ln and "fonts.g" not in ln]
        assert external == []

    def test_contains_content(self):
        html = render_report(_sample())
        assert "Floating Assistant" in html
        assert "1602 tests passing" in html
        assert "v6.6.0" in html
        assert "UI shell" in html and "WebSocket wiring" in html
        assert "Opens in any browser" in html
        assert "Live engine events" in html

    def test_status_glyphs(self):
        html = render_report(_sample())
        assert "done" in html and "next" in html

    def test_escapes(self):
        r = PhaseReport(title="<script>x</script>",
                        shipped=[ReportItem("<b>y</b>")])
        html = render_report(r)
        assert "<script>x</script>" not in html.split("<body>")[1]

    def test_empty_sections_omitted(self):
        r = PhaseReport(title="Bare")
        html = render_report(r)  # no works/next/notes -> no crash
        assert "Bare" in html


class TestWrite:
    def test_write(self, tmp_path):
        p = write_report(_sample(), tmp_path, name="F1 report!")
        assert p is not None and p.exists()
        assert p.suffix == ".html"
        assert p.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
