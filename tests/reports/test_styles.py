import pytest
from reportlab.pdfbase import pdfmetrics

from app.audit_service.reports import styles
from app.audit_service.reports.styles import (
    CONTENT_W,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_HEADING,
    FONT_HEADING_BOLD,
    SectionRule,
    fonts_registered,
    get_styles,
)


def test_the_brand_fonts_register():
    styles._register_fonts()

    assert fonts_registered() is True
    registered = set(pdfmetrics.getRegisteredFontNames())
    assert {FONT_HEADING, FONT_HEADING_BOLD, FONT_BODY, FONT_BODY_BOLD} <= registered


def test_registering_twice_is_harmless():
    styles._register_fonts()
    styles._register_fonts()

    assert fonts_registered() is True


def test_missing_font_files_fall_back_to_helvetica(tmp_path, monkeypatch):
    monkeypatch.setattr(styles, "_FONTS_REGISTERED", False)
    monkeypatch.setattr(styles, "FONT_DIR", str(tmp_path))
    monkeypatch.setattr(styles.pdfmetrics, "getRegisteredFontNames", lambda: [])

    styles._register_fonts()

    assert fonts_registered() is False
    assert get_styles()["Body"].fontName == "Helvetica"
    assert get_styles()["H1"].fontName == "Helvetica-Bold"


def test_report_styles_exist_and_use_the_brand_fonts():
    sheet = get_styles()

    for name in ("H1", "H2", "Body", "Small", "Caption", "URLCell", "TableURL", "SeverityCell"):
        assert name in sheet.byName
    assert sheet["Body"].fontName == FONT_BODY
    assert sheet["H1"].fontName == FONT_HEADING_BOLD
    assert sheet["SeverityCell"].fontName == FONT_BODY_BOLD
    assert sheet["SeverityCell"].alignment == 1  # centred


def test_each_call_builds_a_fresh_stylesheet():
    assert get_styles() is not get_styles()


def test_section_rule_height_grows_with_a_subtitle():
    plain = SectionRule("Title")
    with_subtitle = SectionRule("Title", "Subtitle")

    assert plain.wrap(400, 800) == (400, 6 + 3 + 6 + 13 + 14)
    assert with_subtitle.wrap(400, 800)[1] > plain.wrap(400, 800)[1]


def test_section_rule_uses_the_content_width_by_default():
    assert SectionRule("Title").wrap(0, 800)[0] == CONTENT_W
