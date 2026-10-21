from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import A4

from app.audit_service.reports.layout import header_footer
from app.audit_service.reports.sections.cover_page import _extract_score, _format_score, cover_page
from tests.builders import audit_result


class RecordingCanvas:
    """A canvas that records the text drawn on it and ignores every other drawing call"""

    def __init__(self):
        self.texts = []
        self.images = []

    def stringWidth(self, text, font, size):
        return len(text) * size * 0.5

    def drawString(self, x, y, text, *args, **kwargs):
        self.texts.append(text)

    def drawRightString(self, x, y, text, *args, **kwargs):
        self.texts.append(text)

    def drawImage(self, *args, **kwargs):
        self.images.append(args)

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def draw_cover(lighthouse=None, free=False, **kwargs):
    canvas = RecordingCanvas()
    defaults = dict(
        canvas=canvas,
        doc=SimpleNamespace(),
        sitemap={},
        lighthouse=audit_result()["lighthouse"] if lighthouse is None else lighthouse,
        client_name="Acme Co",
        client_domain="example.com",
        logo_path="app/assets/valvanta-digital-logo.png",
        cover_image_path="app/assets/pdf-cover-image.png",
        is_free_audit=free,
    )
    cover_page(**{**defaults, **kwargs})
    return canvas


# ---- score helpers

@pytest.mark.parametrize("value, expected", [(0.924, "92"), (0.925, "92"), (1, "100"), (0, "0"), (None, "n/a"), ("x", "n/a")])
def test_format_score(value, expected):
    assert _format_score(value) == expected


def test_extract_score_prefers_overall_then_score_then_average():
    summary = {"seo": {"mobile": {"overall_score": 0.9, "score": 0.5}, "desktop": {"score": 0.5, "average_score": 0.1}}}

    assert _extract_score(summary, "seo", "mobile") == 0.9
    assert _extract_score(summary, "seo", "desktop") == 0.5
    assert _extract_score({"seo": {"mobile": {"average_score": 0.3}}}, "seo", "mobile") == 0.3


@pytest.mark.parametrize("summary", [{}, {"seo": None}, {"seo": {"mobile": None}}, {"seo": {"mobile": {}}}])
def test_extract_score_missing(summary):
    assert _extract_score(summary, "seo", "mobile") is None


# ---- cover page

def test_cover_shows_the_client_details_and_scores():
    canvas = draw_cover()

    texts = canvas.texts
    assert "WEBSITE AUDIT REPORT" in texts
    assert "example.com" in texts and "Acme Co" in texts
    assert "Valvanta Digital Agency" in texts
    assert "2026-01-02" in texts  # run date
    assert "MOBILE PERFORMANCE" in texts and "62" in texts  # 0.62 performance score
    assert "91" in texts  # 0.91 seo score
    assert "2" in texts  # two pages audited


def test_cover_subtitle_defaults_and_can_be_changed():
    assert "Technical & Performance Report" in draw_cover().texts
    assert "Accessibility Report" in draw_cover(report_title="Accessibility Report").texts


def test_cover_shows_na_for_scores_that_were_not_measured():
    lighthouse = {"run_at": "2026-02-03T00:00:00", "summary": {}, "tested_urls": ["a", "b", "c"]}

    texts = draw_cover(lighthouse=lighthouse).texts

    assert texts.count("n/a") == 6
    assert "3" in texts  # pages audited falls back to the url list


def test_cover_flags_locked_accessibility_cards_on_free_audits_only():
    lighthouse = {"summary": {}}

    assert draw_cover(lighthouse=lighthouse, free=True).texts.count("Accessible in premium audit") == 2
    assert "Accessible in premium audit" not in draw_cover(lighthouse=lighthouse, free=False).texts


def test_cover_does_not_flag_measured_accessibility_scores():
    lighthouse = audit_result("performance,seo,accessibility")["lighthouse"]

    assert "Accessible in premium audit" not in draw_cover(lighthouse=lighthouse, free=True).texts


def test_cover_falls_back_to_todays_date_and_counts_per_url_data():
    lighthouse = {"summary": {}, "per_url_performance_data": {"a": {}, "b": {}}}

    texts = draw_cover(lighthouse=lighthouse).texts

    assert "2" in texts
    assert any(len(t) == 10 and t[4] == "-" and t[7] == "-" for t in texts)


def test_cover_draws_the_logo():
    assert len(draw_cover().images) == 1


# ---- header and footer

def test_header_and_footer_show_the_domain_and_page_number():
    canvas = RecordingCanvas()

    header_footer(canvas, SimpleNamespace(page=7), "example.com")

    assert canvas.texts == ["Website Audit Report", "example.com", "Prepared by Valvanta Digital Agency", "Page 7"]


def test_header_and_footer_leave_the_canvas_state_balanced():
    calls = []

    class Canvas(RecordingCanvas):
        def saveState(self):
            calls.append("save")

        def restoreState(self):
            calls.append("restore")

    header_footer(Canvas(), SimpleNamespace(page=1), "example.com")

    assert calls == ["save", "restore"]
