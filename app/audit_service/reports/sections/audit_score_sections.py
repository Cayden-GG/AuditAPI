"""
Audit score sections
SEO and accessibility report sections: site wide score overview and per url breakdown
"""
from typing import Any, Dict, List

from reportlab.platypus import Paragraph, Spacer, Table, PageBreak, KeepTogether

from ..helpers import bar_chart, fmt_num, style_table


from ..styles import CONTENT_W, MAX_URLS, SectionRule, get_styles
from .ai_text import ai_note_text, clean_ai_text as _clean_ai_text, select_per_url_ai as _select_per_url_ai, strip_heading as _strip_heading
from .upsell import UpsellBackgroundPage


def _fmt_score(value: Any) -> str:
    """Formats a 0-1 score as a percentage ("92.5%"), "n/a" if value is not a number"""
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value * 100:.1f}%"

def _format_audit_list(items: List[str], max_items: int = 30) -> str:
    """Joins audit ids with line breaks, trimmed to max_items with a count of the rest"""
    if not items:
        return "n/a"
    if len(items) <= max_items:
        return "<br/>".join(items)
    remainder = len(items) - max_items
    trimmed = "<br/>".join(items[:max_items])
    return f"{trimmed}<br/>...and {remainder} more"


def audit_score_overview_section(website: Dict[str, Any], report_label: str, section_label: str | None = None) -> List[Any]:
    """
    Creates report section with the site wide score averages, audit outcome chart and most failed audits

    @Args:
        website (Dict[str, Any]) -- website wide audit data for one platform
        report_label (str) -- report name shown in the title: SEO | Accessibility
        section_label (str | None) -- platform shown in the title: Mobile | Desktop

    @Returns:
        list of all the items in the section (List[Any])
    """
    styles = get_styles()
    story: List[Any] = []

    label = f" ({section_label})" if section_label else ""
    story.append(SectionRule(f"{report_label} Site Averages - Detailed Breakdown{label}"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Average scores and audit outcomes across tested URLs.", styles["Body"]))
    story.append(Paragraph("Good target: average score >= 0.90 (Lighthouse pass threshold).", styles["Small"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Metric definitions", styles["H2"]))
    story.append(style_table(Table([
        ["Metric", "Meaning", "Good target"],
        ["Average score", "Mean of per-URL audit scores.", ">= 0.90"],
        ["Passed audits", "Total audits with score >= 0.90.", "Higher is better"],
        ["Failed audits", "Total audits with score < 0.90.", "Lower is better"],
        ["Not applicable", "Audits that are manual/informative.", "Contextual"],
    ], colWidths=[CONTENT_W * 0.38, CONTENT_W * 0.42, CONTENT_W * 0.20])))
    story.append(Spacer(1, 6))

    story.append(style_table(Table([
        ["Metric", "Value"],
        ["Average score", _fmt_score(website.get("average_score"))],
        ["Total URLs", str(website.get("total_urls", "n/a"))],
        ["Passed audits (total)", str(website.get("total_passed", "n/a"))],
        ["Failed audits (total)", str(website.get("total_failed", "n/a"))],
        ["Not applicable (total)", str(website.get("total_not_applicable", "n/a"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])))
    story.append(Spacer(1, 6))

    passed = website.get("total_passed")
    failed = website.get("total_failed")
    not_applicable = website.get("total_not_applicable")
    story.append(Paragraph("Audit outcomes (counts)", styles["Small"]))
    story.append(bar_chart(
        ["Passed", "Failed", "N/A"],
        [("Total", [passed or 0, failed or 0, not_applicable or 0])],
    ))
    story.append(Spacer(1, 6))

    top_failed = website.get("top_failed_audits") or []
    if top_failed:
        rows = [["Audit ID", "Fail count", "Fail rate"]]
        for item in top_failed[:10]:
            rows.append([
                str(item.get("audit_id", "n/a")),
                str(item.get("fail_count", "n/a")),
                f"{fmt_num(item.get('fail_rate'), 2)}",
            ])
        story.append(Paragraph("Most frequently failed audits", styles["H2"]))
        story.append(style_table(Table(rows, colWidths=[CONTENT_W * 0.56, CONTENT_W * 0.20, CONTENT_W * 0.24])))
        story.append(Spacer(1, 6))

    audit_summaries = website.get("audit_summaries") or {}
    if audit_summaries:
        summary_rows = [["Audit ID", "Avg score", "Pass", "Fail", "N/A", "Fail rate"]]
        sorted_items = sorted(
            audit_summaries.items(),
            key=lambda item: item[1].get("fail_rate", 0),
            reverse=True,
        )
        for audit_id, stats in sorted_items[:10]:
            summary_rows.append([
                str(audit_id),
                _fmt_score(stats.get("average_score")),
                str(stats.get("pass_count", "n/a")),
                str(stats.get("fail_count", "n/a")),
                str(stats.get("not_applicable_count", "n/a")),
                f"{fmt_num(stats.get('fail_rate'), 2)}",
            ])
        story.append(Paragraph("Audit-level benchmarks (top 10 by fail rate)", styles["H2"]))
        story.append(style_table(Table(
            summary_rows,
            colWidths=[
                CONTENT_W * 0.36,
                CONTENT_W * 0.13,
                CONTENT_W * 0.10,
                CONTENT_W * 0.10,
                CONTENT_W * 0.10,
                CONTENT_W * 0.11,
            ],
        )))
        story.append(Spacer(1, 6))

    return story


def audit_score_per_url_section(
    per_url: Dict[str, Any],
    report_label: str,
    section_label: str | None = None,
    ai: Dict[str, Any] | None = None,
    report_type: str = "seo",
    *,
    show_upsell: bool = False,
) -> List[Any]:
    """
    Creates report section with each url's AI notes, score summary and passed / failed audits

    @Args:
        per_url (Dict[str, Any]) -- reduced audit data keyed by url for one platform
        report_label (str) -- report name shown in the title: SEO | Accessibility
        section_label (str | None) -- platform shown in the title: Mobile | Desktop
        ai (Dict[str, Any] | None) -- ai summary data
        report_type (str) -- seo | accessibility
        show_upsell (bool) -- if true an upsell page follows the urls

    @Returns:
        list of all the items in the section (List[Any])
    """
    styles = get_styles()
    story: List[Any] = []

    label = f" ({section_label})" if section_label else ""
    story.append(SectionRule(f"{report_label} Per URL Breakdown{label}"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Per-URL audit results with AI notes and pass/fail detail.", styles["Body"]))
    story.append(Spacer(1, 6))

    per_url_ai = _select_per_url_ai(ai or {}, report_type)

    def _build_url_blocks(url: str, data: Dict[str, Any]) -> List[Any]:
        summary = data.get("summary", {}) or {}
        audits = data.get("audits", {}) or {}

        passed = []
        failed = []
        not_applicable = []
        for audit_id, audit in audits.items():
            status = audit.get("status")
            if status == "pass":
                passed.append(audit_id)
            elif status == "fail":
                failed.append(audit_id)
            else:
                not_applicable.append(audit_id)

        blocks: List[Any] = [
            Paragraph(url, styles["H2"]),
        ]

        note_text = ai_note_text(per_url_ai.get(url))
        if note_text:
            blocks.append(Paragraph(note_text, styles["Body"]))
            blocks.append(Spacer(1, 4))

        blocks.append(style_table(Table([
            ["Metric", "Value"],
            ["Average score", _fmt_score(summary.get("average_score"))],
            ["Passed audits", str(summary.get("passed", "n/a"))],
            ["Failed audits", str(summary.get("failed", "n/a"))],
            ["Not applicable", str(summary.get("not_applicable", "n/a"))],
        ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])))
        blocks.append(Spacer(1, 4))

        blocks.append(style_table(Table([
            ["Audit status", "Tests"],
            ["Passed", Paragraph(_format_audit_list(passed), styles["URLCell"])],
            ["Failed", Paragraph(_format_audit_list(failed), styles["URLCell"])],
            ["N/A", Paragraph(_format_audit_list(not_applicable), styles["URLCell"])],
        ], colWidths=[CONTENT_W * 0.18, CONTENT_W * 0.82])))
        blocks.append(Spacer(1, 8))

        return blocks

    items = list(per_url.items())[:MAX_URLS]
    for url, data in items:
        story.extend(_build_url_blocks(url, data))

    if show_upsell and items:
        story.append(PageBreak())
        story.append(
            UpsellBackgroundPage("Upgrade to the premium audit to access data for the rest of the URLs.")
        )

    return story
