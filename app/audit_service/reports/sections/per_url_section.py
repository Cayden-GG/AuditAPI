"""
Per url section
Performance report section with each url's AI notes and metric tables
"""
from typing import Dict, List, Any

from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table

from ..styles import CONTENT_W, SectionRule, get_styles, MAX_URLS
from .upsell import UpsellBackgroundPage
from ..helpers import fmt_ms, fmt_bytes, style_table
from .ai_text import ai_note_text, clean_ai_text as _clean_ai_text, select_per_url_ai as _select_per_url_ai, strip_heading as _strip_heading


def per_url_section(
    ai: Dict,
    per_url: Dict,
    section_label: str | None = None,
    report_type: str = "performance",
    *,
    show_upsell: bool = False,
):
    """
    Creates report section that displays all the metrics for each discovered url

    @Args:
        ai (Dict) -- ai summary data
        per_url (Dict) -- per-url performance data
        section_label (str | None) -- platform shown in the title: Mobile | Desktop
        report_type (str) -- report the AI notes are selected for
        show_upsell (bool) -- if true an upsell page follows the urls

    @Returns:
        list of all the items in the section (List)
    """
    styles = get_styles()
    story = []

    label = f" ({section_label})" if section_label else ""
    story.append(SectionRule(f"Per URL Breakdown{label}"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Each URL is reported using the same breakdown sections as Site Averages.", styles["Body"]))
    story.append(Paragraph("Targets: FCP <= 1.8s, LCP <= 2.5s, Speed Index <= 3.4s, TBT <= 200ms, Server latency <= 200ms.", styles["Small"]))
    story.append(Spacer(1, 8))


    items = list(per_url.items())[:MAX_URLS]
    for i, (url, d) in enumerate(items, start=1):
        story.append(url_block(ai, url, d, report_type=report_type))
        if i % 3 == 0:
            story.append(PageBreak())

    if show_upsell and items:
        story.append(PageBreak())
        story.append(
            UpsellBackgroundPage("Upgrade to the Premium Brand Audit to access data for the rest of the URLs.")
        )

    return story


def url_block(ai: Dict[str, Any], url: str, d: Dict[str, Any], report_type: str) -> KeepTogether:
    """
    Creates the block for one url: AI notes followed by the metric tables, kept together on a page

    @Args:
        ai (Dict[str, Any]) -- ai summary data
        url (str) -- page url of the metrics
        d (Dict[str, Any]) -- reduced performance data for the url
        report_type (str) -- report the AI notes are selected for

    @Returns:
        block of the url's items (KeepTogether)
    """
    styles = get_styles()
    blocks: List[Any] = []
    blocks.append(Paragraph(url, styles["H2"]))

    per_url_ai = _select_per_url_ai(ai, report_type)

    note_text = ai_note_text(per_url_ai.get(url))
    if note_text:
        blocks.append(Paragraph(note_text, styles["Body"]))
        blocks.append(Spacer(1, 4))

    basic = Table([
        ["Basic metrics", "Value"],
        ["FCP", fmt_ms(d.get("first_contentful_paint", {}).get("value"), "s", 2)],
        ["LCP", fmt_ms(d.get("largest_contentful_paint", {}).get("value"), "s", 2)],
        ["Speed Index", fmt_ms(d.get("speed_index", {}).get("value"), "s", 2)],
        ["TBT", fmt_ms(d.get("total_blocking_time", {}).get("value"), "ms", 0)],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    mtp = d.get("main_thread_work_breakdown", {}) or {}
    mt_items = mtp.get("mainthread_work_items", []) or []
    mt_rows = [["Main thread work breakdown", "Value"], ["Total (numericValue)", fmt_ms(mtp.get("value"), "ms", 0)]]
    for it in mt_items[:3]:
        mt_rows.append([it.get("group", "n/a"), fmt_ms(it.get("duration"), "ms", 0)])
    mt_tbl = Table(mt_rows, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    diagp = d.get("diagnostics", {}) or {}
    diag_tbl = Table([
        ["Diagnostic metrics", "Value"],
        ["Requests", str(diagp.get("request_count", "n/a"))],
        ["Tasks", str(diagp.get("task_count", "n/a"))],
        ["Total byte weight", fmt_bytes(diagp.get("total_byte_weight"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    netp = d.get("network_requests", {}) or {}
    net_tbl = Table([
        ["Network metrics", "Value"],
        ["200 responses", str(netp.get("code_200_requests_count", "n/a"))],
        ["Non-200 responses", str(netp.get("code_non_200_requests_count", "n/a"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    rsp = d.get("resource_summary", {}) or {}
    rs_tbl = Table([
        ["Resource summary", "Transfer size"],
        ["Total", fmt_bytes(rsp.get("total_transfer_size"))],
        ["Images", fmt_bytes(rsp.get("image_transfer_size"))],
        ["Scripts", fmt_bytes(rsp.get("script_transfer_size"))],
        ["Stylesheets", fmt_bytes(rsp.get("stylesheet_transfer_size"))],
        ["Documents", fmt_bytes(rsp.get("document_transfer_size"))],
        ["Third-party", fmt_bytes(rsp.get("third_party_transfer_size"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    nslp = d.get("network_server_latency", {}) or {}
    lat_tbl = Table([
        ["Network server latency", "Value"],
        ["Server latency", fmt_ms(nslp.get("server_latency"), "ms", 0)],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])

    blocks.extend([
        style_table(basic),
        Spacer(1, 4),
        style_table(mt_tbl),
        Spacer(1, 4),
        style_table(diag_tbl),
        Spacer(1, 4),
        style_table(net_tbl),
        Spacer(1, 4),
        style_table(rs_tbl),
        Spacer(1, 4),
        style_table(lat_tbl),
        Spacer(1, 10),
    ])
    return KeepTogether(blocks)
