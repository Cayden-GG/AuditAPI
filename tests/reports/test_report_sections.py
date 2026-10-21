import re

import pytest
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Table

from app.audit_service.reports.sections import audit_score_sections, per_url_section
from app.audit_service.reports.sections.audit_score_sections import (
    _fmt_score,
    _format_audit_list,
    audit_score_overview_section,
    audit_score_per_url_section,
)
from app.audit_service.reports.sections.executive_summary import executive_summary_section
from app.audit_service.reports.sections.findings import key_findings_section
from app.audit_service.reports.sections.findings_section import findings_section
from app.audit_service.reports.sections.key_findings_table import key_findings_table
from app.audit_service.reports.sections.limitations import limitations_section
from app.audit_service.reports.sections.methodology import methodology_section
from app.audit_service.reports.sections.per_url_section import (
    _clean_ai_text,
    _select_per_url_ai,
    _strip_heading,
    per_url_section as build_per_url_section,
    url_block,
)
from app.audit_service.reports.sections.site_average_metrics import site_average_section
from app.audit_service.reports.sections.standards_alignment import standards_alignment_section
from app.audit_service.reports.sections.tested_urls import tested_urls_section as build_tested_urls_section
from app.audit_service.reports.sections.upsell import UpsellBackgroundPage
from tests.builders import ai_result, audit_result, story_text

URLS = ["https://example.com/", "https://example.com/about"]


# ---- text helpers shared by the per url sections

@pytest.mark.parametrize("module", [per_url_section, audit_score_sections])
class TestAiTextHelpers:
    def test_clean_ai_text_fixes_doubled_bullets(self, module):
        def squash(text):
            return " ".join(text.split())

        assert squash(module._clean_ai_text("a<br/>- - b")) == "a<br/>- b"
        assert squash(module._clean_ai_text("a<br>- - b")) == "a<br/>- b"
        assert squash(module._clean_ai_text("a\n- - b\r\n- - c")) == "a - b - c"
        assert module._clean_ai_text("- - one") == "- one"
        assert module._clean_ai_text("- fine") == "- fine"

    @pytest.mark.parametrize("value", [None, 5, ["x"], {"a": 1}])
    def test_clean_ai_text_of_a_non_string_is_empty(self, module, value):
        assert module._clean_ai_text(value) == ""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("What the data shows: LCP is slow", "LCP is slow"),
            ("what the data shows\nLCP is slow", "LCP is slow"),
            ("- What the data shows - LCP is slow", "LCP is slow"),
            ("• What the data shows: LCP is slow", "LCP is slow"),
            ("LCP is slow", "LCP is slow"),
            ("  Something else first", "  Something else first"),
        ],
    )
    def test_strip_heading_removes_a_repeated_plain_heading(self, module, value, expected):
        assert module._strip_heading(value, "What the data shows") == expected

    @pytest.mark.parametrize("value", [None, 3, []])
    def test_strip_heading_of_a_non_string_is_empty(self, module, value):
        assert module._strip_heading(value, "Key strengths") == ""

    def test_strip_heading_removes_a_bold_heading(self, module):
        assert module._strip_heading("<b>Key strengths</b><br/>- fast", "Key strengths") == "- fast"

    @pytest.mark.parametrize(
        "ai, expected",
        [
            ({"per_url_summaries": {"seo": {"u": {"a": 1}}}}, {"u": {"a": 1}}),
            ({"per_url_summaries": [{"url": "u", "analysis": {"a": 1}}, "junk"]}, {"u": {"a": 1}}),
            ({"per_url_summaries": {"performance": {"u": 1}}}, {}),  # a category format without this report type
            ({"per_url_summaries": {"u": {"a": 1}}}, {"u": {"a": 1}}),  # the older flat format
            ({"per_url_summaries": None}, {}),
            ({}, {}),
        ],
    )
    def test_select_per_url_ai_handles_every_format(self, module, ai, expected):
        assert module._select_per_url_ai(ai, "seo") == expected


# ---- executive summary

def test_executive_summary_shows_the_ai_text_and_the_findings_table():
    ai = ai_result()
    summary = audit_result()["lighthouse"]["summary"]["performance"]

    story = executive_summary_section(ai, summary, report_type="performance")
    text = story_text(story)

    assert "Executive Summary" in text
    for part in ("data", "strengths", "weaknesses", "roadmap"):
        assert part in text
    assert "Overall score" in text and "Risk summary" in text
    assert summary["mobile"]["risk_summary"] in text


def test_executive_summary_table_counts_findings_per_severity():
    summary = {
        "mobile": {"overall_score": 0.5, "findings_by_severity": {"critical": 2, "high": 1}, "risk_summary": "Bad"},
        "desktop": {"overall_score": 0.756, "findings_by_severity": {"moderate": 4}, "risk_summary": "Fine"},
    }

    table = next(i for i in executive_summary_section({}, summary, "seo") if isinstance(i, Table))
    rows = {row[0]: [c if isinstance(c, str) else c.getPlainText() for c in row[1:]] for row in table._cellvalues}

    assert rows["Overall score"] == ["0.50", "0.76"]
    assert rows["Critical findings"] == ["2", "0"]
    assert rows["High findings"] == ["1", "0"]
    assert rows["Moderate findings"] == ["0", "4"]
    assert rows["Advisory findings"] == ["0", "0"]
    assert rows["Risk summary"] == ["Bad", "Fine"]


def test_executive_summary_without_ai_text_says_so():
    story = executive_summary_section({}, {}, "performance")

    text = story_text(story)
    assert "AI summary not available for this section." in text
    assert "n/a" in text


def test_executive_summary_accepts_plain_text_and_cleans_it():
    ai = {"executive_summaries": {"seo": "Line one\n- - bullet<br>next"}}

    text = story_text(executive_summary_section(ai, {}, "seo"))

    assert "Line one" in text and "- bullet" in text and "- - bullet" not in text


# ---- key findings

def test_key_findings_table_lists_the_findings():
    table = key_findings_table(ai_result())

    rows = [[c if isinstance(c, str) else c.getPlainText() for c in row] for row in table._cellvalues]
    assert rows[0] == ["Issue", "Priority", "Impact", "Effort", "Short explanation"]
    assert rows[1] == ["Slow LCP", "High", "i", "Low", "e"]


def test_key_findings_table_is_limited_to_twelve():
    ai = {"key_findings": [{"issue": f"Issue {i}"} for i in range(20)]}

    assert len(key_findings_table(ai)._cellvalues) == 13


@pytest.mark.parametrize("ai", [{}, {"key_findings": []}, {"key_findings": None}])
def test_key_findings_table_has_a_placeholder_without_findings(ai):
    rows = key_findings_table(ai)._cellvalues

    assert len(rows) == 2
    assert "AI findings missing" in rows[1][0].getPlainText()


def test_key_findings_section_shows_the_method_and_ends_with_a_page_break():
    story = key_findings_section({"prioritisation_method": "Impact over effort", "key_findings": []})

    assert "Prioritisation method: Impact over effort" in story_text(story)
    assert isinstance(story[-1], PageBreak)


def test_key_findings_section_has_a_default_method():
    assert "business impact versus implementation effort" in story_text(key_findings_section({}))


# ---- findings

def finding(**overrides):
    return {
        "title": "LCP is Poor",
        "severity": "critical",
        "description": "Too slow",
        "recommendation": "Optimise images",
        "affected_elements": ["https://example.com/", "https://example.com/about"],
        "standard_reference": {"framework": "Core Web Vitals", "code": "LCP", "level": None},
        **overrides,
    }


def test_findings_section_renders_each_finding_as_a_row():
    story = findings_section([finding()], "Performance (Mobile)")

    text = story_text(story)
    assert "Performance (Mobile) Findings" in text
    for expected in ("LCP is Poor", "Critical", "Core Web Vitals LCP", "Too slow", "Optimise images"):
        assert expected in text
    assert "https://example.com/, https://example.com/about" in text


def test_findings_section_shows_wcag_levels():
    story = findings_section([finding(standard_reference={"framework": "WCAG", "code": "label", "level": "AA"})], "A11y")

    assert "WCAG label (Level AA)" in story_text(story)


def test_findings_section_is_limited_to_thirty_rows():
    table = next(i for i in findings_section([finding(title=f"F{i}") for i in range(45)], "X") if isinstance(i, Table))

    assert len(table._cellvalues) == 31  # header + 30


def test_findings_section_survives_missing_fields():
    story = findings_section([{}], "X")

    text = story_text(story)
    assert "n/a" in text


def test_findings_section_without_findings_says_so():
    story = findings_section([], "SEO (Desktop)")

    assert "No findings of high enough severity to report." in story_text(story)
    assert not any(isinstance(i, Table) for i in story)


# ---- static sections

def test_static_sections_have_their_statements():
    assert "Limitations & Scope Disclaimer" in story_text(limitations_section())
    assert "point-in-time snapshot" in story_text(limitations_section())
    assert "WCAG 2.1 Level A and AA" in story_text(standards_alignment_section())
    assert "not constitute full legal compliance" in story_text(standards_alignment_section())


def test_tested_urls_section_numbers_the_urls():
    story = build_tested_urls_section({}, URLS)

    rows = next(i for i in story if isinstance(i, Table))._cellvalues
    assert [row[0] for row in rows] == ["#", "1", "2"]
    assert rows[2][1].getPlainText() == URLS[1]
    assert isinstance(story[0], PageBreak) and isinstance(story[-1], PageBreak)


# ---- methodology

def test_methodology_lists_the_run_details():
    lh = audit_result("performance,seo")["lighthouse"]

    text = story_text(methodology_section(lh, URLS))

    for expected in ("12.0.0", "2026-01-02T03:04:05+00:00", "performance,seo", "navigation", "mobile, desktop", "only_categories"):
        assert expected in text
    assert "Execution config" in text
    assert "Tested URLs" in text and URLS[1] in text


def test_methodology_free_audits_show_the_premium_limit():
    lh = {"tested_url_count": 5}

    free = story_text(methodology_section(lh, URLS, sitemap_url_count=120, show_upsell=True))
    paid = story_text(methodology_section(lh, URLS, sitemap_url_count=120, show_upsell=False))

    assert "5 of 120 | audit up to 100 urls with premium audit" in free
    assert "5 of 120" not in paid


def test_methodology_falls_back_to_the_tested_urls_for_the_count():
    rows = next(i for i in methodology_section({}, URLS) if isinstance(i, Table))._cellvalues

    assert ["URLs tested", "2"] in rows


def test_methodology_without_data_shows_n_a():
    story = methodology_section({}, [])

    text = story_text(story)
    assert text.count("n/a") >= 5
    assert "Execution config" not in text
    assert "Tested URLs" not in text


# ---- site averages (performance)

def perf_data(platform="mobile"):
    lh = audit_result()["lighthouse"]
    return lh["website_performance_data"]["performance"][platform], {
        url: entry["performance"][platform] for url, entry in lh["per_url_performance_data"].items()
    }


def test_site_averages_shows_the_metrics_in_tables_and_charts():
    website, per_url = perf_data()

    story = site_average_section(website, per_url, section_label="Mobile")
    text = story_text(story)

    assert "Site Averages - Detailed Breakdown (Mobile)" in text
    assert "0.10 s" in text  # FCP is 100ms everywhere
    assert "5.20 s" in text  # LCP 5200ms
    assert "Requests per page" in text and "Total byte weight" in text
    assert sum(1 for i in story if i.__class__.__name__ == "Drawing") == 3  # two bar charts and the pie


def test_site_averages_quote_one_lcp_target():
    website, per_url = perf_data()
    story = site_average_section(website, per_url, section_label="Mobile")

    intro = next(i for i in story if isinstance(i, Paragraph) and i.getPlainText().startswith("Good targets"))
    definitions = next(i for i in story if isinstance(i, Table))
    intro_target = re.search(r"LCP <= ([\d.]+)s", intro.getPlainText()).group(1)
    table_target = next(row[2] for row in definitions._cellvalues if row[0] == "LCP")

    assert table_target == f"≤ {intro_target} s"


def test_site_averages_without_data_still_renders():
    story = site_average_section({}, {})

    text = story_text(story)
    assert "Site Averages - Detailed Breakdown" in text and "(" not in text.splitlines()[0]
    assert "n/a" in text


# ---- per url (performance)

def test_url_block_shows_the_metrics_and_ai_notes():
    _, per_url = perf_data()
    ai = ai_result()

    block = url_block(ai, URLS[0], per_url[URLS[0]], report_type="performance")

    assert isinstance(block, KeepTogether)
    text = story_text([block])
    assert URLS[0] in text
    for heading in ("What the data shows", "Key strengths", "Primary weaknesses", "Recommendations"):
        assert text.count(heading) == 1, heading
    assert "0.10 s" in text and "Requests" in text and "Third-party" in text


def test_url_block_without_ai_notes_has_only_the_tables():
    _, per_url = perf_data()

    text = story_text([url_block({}, URLS[0], per_url[URLS[0]], "performance")])

    assert "Basic metrics" in text
    assert "<br/>" not in text


def test_url_block_survives_empty_metric_data():
    text = story_text([url_block({}, URLS[0], {}, "performance")])

    assert text.count("n/a") >= 8


def test_per_url_section_breaks_pages_every_three_urls():
    _, per_url = perf_data()
    many = {f"https://example.com/{i}": per_url[URLS[0]] for i in range(7)}

    story = build_per_url_section({}, many, section_label="Mobile")

    assert sum(isinstance(i, PageBreak) for i in story) == 2
    assert sum(isinstance(i, KeepTogether) for i in story) == 7
    assert "Per URL Breakdown (Mobile)" in story_text(story)


def test_per_url_section_is_limited_to_100_urls():
    many = {f"https://example.com/{i}": {} for i in range(130)}

    story = build_per_url_section({}, many)

    assert sum(isinstance(i, KeepTogether) for i in story) == 100


def test_per_url_section_free_audits_end_with_the_upsell_page():
    free = build_per_url_section({}, {URLS[0]: {}}, show_upsell=True)
    paid = build_per_url_section({}, {URLS[0]: {}}, show_upsell=False)
    empty = build_per_url_section({}, {}, show_upsell=True)

    assert isinstance(free[-1], UpsellBackgroundPage)
    assert not any(isinstance(i, UpsellBackgroundPage) for i in paid)
    assert not any(isinstance(i, UpsellBackgroundPage) for i in empty)


# ---- seo / accessibility score sections

@pytest.mark.parametrize("value, expected", [(0.925, "92.5%"), (1, "100.0%"), (0, "0.0%"), (None, "n/a"), ("x", "n/a")])
def test_fmt_score(value, expected):
    assert _fmt_score(value) == expected


def test_format_audit_list():
    assert _format_audit_list([]) == "n/a"
    assert _format_audit_list(["a", "b"]) == "a<br/>b"
    many = [f"audit-{i}" for i in range(35)]
    formatted = _format_audit_list(many)
    assert formatted.endswith("<br/>...and 5 more")
    assert "audit-29" in formatted and "audit-30" not in formatted
    assert _format_audit_list(many, max_items=2) == "audit-0<br/>audit-1<br/>...and 33 more"


def seo_data(platform="mobile"):
    lh = audit_result()["lighthouse"]
    return lh["website_performance_data"]["seo"][platform], {
        url: entry["seo"][platform] for url, entry in lh["per_url_performance_data"].items()
    }


def test_score_overview_shows_totals_failures_and_benchmarks():
    website, _ = seo_data()

    story = audit_score_overview_section(website, "SEO", section_label="Mobile")
    text = story_text(story)

    assert "SEO Site Averages - Detailed Breakdown (Mobile)" in text
    assert "Total URLs" in text and "2" in text
    assert "Most frequently failed audits" in text and "robots-txt" in text
    assert "Audit-level benchmarks (top 10 by fail rate)" in text
    assert sum(1 for i in story if i.__class__.__name__ == "Drawing") == 1


def test_score_overview_without_data_omits_the_optional_tables():
    story = audit_score_overview_section({}, "Accessibility")

    text = story_text(story)
    assert "Accessibility Site Averages - Detailed Breakdown" in text
    assert "Most frequently failed audits" not in text
    assert "Audit-level benchmarks" not in text
    assert "n/a" in text


def test_score_overview_benchmarks_are_sorted_by_fail_rate_and_limited():
    summaries = {f"a{i}": {"fail_rate": i / 20, "pass_count": 1} for i in range(15)}

    table = [i for i in audit_score_overview_section({"audit_summaries": summaries}, "SEO") if isinstance(i, Table)][-1]

    ids = [row[0] for row in table._cellvalues[1:]]
    assert ids == [f"a{i}" for i in range(14, 4, -1)]


def test_score_per_url_section_lists_passed_failed_and_na_audits():
    _, per_url = seo_data()

    story = audit_score_per_url_section(per_url, "SEO", section_label="Mobile", ai=ai_result(), report_type="seo")
    text = story_text(story)

    assert "SEO Per URL Breakdown (Mobile)" in text
    assert URLS[0] in text and URLS[1] in text
    assert "robots-txt" in text  # in the failed row
    assert "Average score" in text
    assert text.count("What the data shows") == 2  # one note per url


def test_score_per_url_section_is_limited_and_upsells_free_audits():
    many = {f"https://example.com/{i}": {"summary": {}, "audits": {}} for i in range(120)}

    story = audit_score_per_url_section(many, "SEO", show_upsell=True)

    assert story_text(story).count("https://example.com/") == 100
    assert isinstance(story[-1], UpsellBackgroundPage)
    assert not any(isinstance(i, UpsellBackgroundPage) for i in audit_score_per_url_section(many, "SEO"))


def test_every_report_quotes_the_same_lcp_target():
    website, per_url = perf_data()
    texts = [
        story_text(site_average_section(website, per_url)),
        story_text(build_per_url_section({}, per_url)),
    ]

    targets = {m for text in texts for m in re.findall(r"LCP (?:<= |≤ )?\s*([\d.]+) ?s", text)}
    assert targets == {"2.5"}
