import pytest

from app.audit_service.reports.sections import audit_score_sections, executive_summary, per_url_section
from app.audit_service.reports.sections.ai_text import ai_note_text, clean_ai_text, strip_heading


def squash(text):
    return " ".join(text.split())


@pytest.mark.parametrize(
    "value, expected",
    [
        ("<b>Key strengths</b><br/>- fast", "- fast"),
        ("<b>Key strengths</b><br><br/>- fast", "- fast"),
        ("<B> key strengths </B>\\n- fast".replace("\\n", "\n"), "- fast"),
        ("<b>Key strengths:</b> fast", "fast"),
        ("<b>Key strengths</b>: fast", "fast"),
        ("  <b>Key strengths</b>  <br/>fast", "fast"),
        ("Key strengths: fast", "fast"),
        ("key strengths\nfast", "fast"),
        ("- Key strengths - fast", "fast"),
        ("• Key strengths: fast", "fast"),
        ("fast loading", "fast loading"),
        ("<b>Other heading</b><br/>text", "<b>Other heading</b><br/>text"),
        ("A sentence about Key strengths later", "A sentence about Key strengths later"),
    ],
)
def test_strip_heading(value, expected):
    assert strip_heading(value, "Key strengths") == expected


@pytest.mark.parametrize("value", [None, 3, [], {"a": 1}])
def test_strip_heading_of_a_non_string_is_empty(value):
    assert strip_heading(value, "Key strengths") == ""


def test_strip_heading_only_removes_the_leading_heading():
    value = "<b>Key strengths</b><br/>- fast<br/><b>Key strengths</b> again"

    assert strip_heading(value, "Key strengths") == "- fast<br/><b>Key strengths</b> again"


def test_clean_ai_text():
    assert squash(clean_ai_text("a<br/>- - b")) == "a<br/>- b"
    assert clean_ai_text("- - one") == "- one"
    assert clean_ai_text("- fine") == "- fine"
    assert clean_ai_text(None) == ""


FULL_NOTE = {
    "what_the_data_shows": "data",
    "key_strengths": "strengths",
    "primary_weaknesses": "weaknesses",
    "recommendations": "recs",
}


def test_ai_note_text_labels_each_section_once():
    assert ai_note_text(FULL_NOTE) == (
        "<b>What the data shows</b><br/>data<br/><br/>"
        "<b>Key strengths</b><br/>strengths<br/><br/>"
        "<b>Primary weaknesses</b><br/>weaknesses<br/><br/>"
        "<b>Recommendations</b><br/>recs"
    )


def test_ai_note_text_does_not_double_a_heading_the_ai_already_wrote():
    note = {
        **FULL_NOTE,
        "key_strengths": "<b>Key strengths</b><br/>- fast pages",
        "primary_weaknesses": "Primary weaknesses: - slow images",
        "recommendations": "- - compress images",
    }

    text = ai_note_text(note)

    assert text.count("Key strengths") == 1 and text.count("Primary weaknesses") == 1
    assert "<b>Key strengths</b><br/>- fast pages" in text
    assert "<b>Primary weaknesses</b><br/>slow images" in text
    assert "- - " not in text


def test_ai_note_text_skips_empty_sections():
    note = {"what_the_data_shows": "data", "key_strengths": "", "primary_weaknesses": None, "recommendations": "<b>Recommendations</b>"}

    assert ai_note_text(note) == "<b>What the data shows</b><br/>data"


@pytest.mark.parametrize("note", [None, {}, "text", [], {"unrelated": "x"}])
def test_ai_note_text_without_content_is_empty(note):
    assert ai_note_text(note) == ""


def test_the_report_sections_share_one_implementation():
    for module in (per_url_section, audit_score_sections):
        assert module._clean_ai_text is clean_ai_text
        assert module._strip_heading is strip_heading
    assert executive_summary.clean_ai_text is clean_ai_text
