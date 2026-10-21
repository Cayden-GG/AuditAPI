"""
Site average metrics section
Performance report section with the site wide averages, benchmarks and charts
"""
from typing import Dict

from reportlab.platypus import Paragraph, Spacer, Table

from ..styles import CONTENT_W, SectionRule, get_styles
from ..helpers import benchmarks_metric, bar_chart, fmt_bytes, fmt_ms, fmt_num, ms_to_s, pie_chart, style_table

def site_average_section(wp: Dict, per_url: Dict, section_label: str | None = None): 
    """
    Creates report section displaying the site wide average metrics

    This section has bar charts, a pie chart and tables to display all the data

    @Args:
        wp (Dict) -- website performance data
        per_url (Dict) -- per-url performance data
        section_label (str | None) -- platform shown in the title: Mobile | Desktop

    @Returns:
        list of all the items in the section (List)
    """
    styles = get_styles()
    
    bench = benchmarks_metric(per_url)

    story = []
    
    label = f" ({section_label})" if section_label else ""
    story.append(SectionRule(f"Site Averages - Detailed Breakdown{label}"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Good targets: FCP <= 1.8s, LCP <= 2.5s, Speed Index <= 3.4s, TBT <= 200ms, Server latency <= 200ms.", styles["Small"]))
    story.append(Paragraph("Benchmarks: <b>Top 10% (p10)</b> is the best-performing 10% of tested pages for each metric.", styles["Small"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Metric definitions", styles["H2"]))
    story.append(style_table(Table([
        ["Metric", "Meaning", "Good target"],
        ["FCP", "First time content appears on screen.", "≤ 1.8 s"],
        ["LCP", "Largest content element render time.", "≤ 1.5 s"],
        ["Speed Index", "How quickly the page looks complete.", "≤ 3.4 s"],
        ["TBT", "Total main-thread blocking time.", "≤ 200 ms"],
        ["Server latency", "Backend responsiveness during load.", "≤ 200 ms"],
    ], colWidths=[CONTENT_W * 0.38, CONTENT_W * 0.42, CONTENT_W * 0.20])))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Breakdown charts", styles["H2"]))
    sec_labels = ["FCP", "LCP", "Speed Index"]
    sec_series = [
        ("p10", [ms_to_s(bench[l]["p10"]) if bench[l]["p10"] is not None else None for l in sec_labels]),
        ("avg", [ms_to_s(bench[l]["avg"]) if bench[l]["avg"] is not None else None for l in sec_labels]),
        ("p90", [ms_to_s(bench[l]["p90"]) if bench[l]["p90"] is not None else None for l in sec_labels]),
    ]
    story.append(Paragraph("Timing metrics (seconds)", styles["Small"]))
    story.append(bar_chart(sec_labels, sec_series))
    story.append(Spacer(1, 6))

    ms_labels = ["TBT", "Server latency"]
    ms_series = [
        ("p10", [bench[l]["p10"] for l in ms_labels]),
        ("avg", [bench[l]["avg"] for l in ms_labels]),
        ("p90", [bench[l]["p90"] for l in ms_labels]),
    ]
    story.append(Paragraph("Blocking and latency (milliseconds)", styles["Small"]))
    story.append(bar_chart(ms_labels, ms_series))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Basic metrics", styles["H2"]))
    story.append(style_table(Table([
        ["Metric", "Top 10% (p10)", "Average", "Worst 10% (p90)"],
        ["FCP", fmt_ms(bench["FCP"]["p10"], "s", 2), fmt_ms(wp.get("first_contentful_paint", {}).get("average_value"), "s", 2), fmt_ms(bench["FCP"]["p90"], "s", 2)],
        ["LCP", fmt_ms(bench["LCP"]["p10"], "s", 2), fmt_ms(wp.get("largest_contentful_paint", {}).get("average_value"), "s", 2), fmt_ms(bench["LCP"]["p90"], "s", 2)],
        ["Speed Index", fmt_ms(bench["Speed Index"]["p10"], "s", 2), fmt_ms(wp.get("speed_index", {}).get("average_value"), "s", 2), fmt_ms(bench["Speed Index"]["p90"], "s", 2)],
        ["Total Blocking Time", fmt_ms(bench["TBT"]["p10"], "ms", 0), fmt_ms(wp.get("total_blocking_time", {}).get("average_value"), "ms", 0), fmt_ms(bench["TBT"]["p90"], "ms", 0)],
    ], colWidths=[CONTENT_W * 0.38, CONTENT_W * 0.20, CONTENT_W * 0.21, CONTENT_W * 0.21])))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Main thread work breakdown", styles["H2"]))
    mt = wp.get("mainthread_work_breakdown", {}) or {}
    story.append(Paragraph(f"Average main-thread work breakdown: <b>{fmt_ms(mt.get('average_value'), 'ms', 0)}</b>", styles["Body"]))
    mt_items = mt.get("mode_mainthread_work_items", []) or []
    mt_rows = [["Group", "Average duration (ms)"]]

    for it in mt_items[:10]:
        mt_rows.append([it.get("group", "n/a"), fmt_ms(it.get("average_mainthread_item_duration"), "ms", 0)])
   
    story.append(style_table(Table(mt_rows, colWidths=[CONTENT_W * 0.72, CONTENT_W * 0.28])))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Diagnostic metrics", styles["H2"]))
    diag = wp.get("diagnostics", {}) or {}

    story.append(style_table(Table([
        ["Metric", "Average"],
        ["Requests per page", fmt_num(diag.get("average_requests_count"), 1)],
        ["Tasks per page", fmt_num(diag.get("average_tasks_count"), 1)],
        ["Total byte weight", fmt_bytes(diag.get("average_total_byte_weight"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])))

    story.append(Spacer(1, 8))

    story.append(Paragraph("Network metrics", styles["H2"]))
    net = wp.get("network_requests", {}) or {}

    story.append(style_table(Table([
        ["Metric", "Average"],
        ["200 responses (count)", fmt_num(net.get("average_code_200_request_count"), 1)],
        ["Non-200 responses (count)", fmt_num(net.get("average_non_code_200_request_count"), 1)],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])))

    story.append(Spacer(1, 8))

    story.append(Paragraph("Resource summary", styles["H2"]))
    rs = wp.get("resource_summary_bytes", {}) or {}

    story.append(style_table(Table([
        ["Resource type", "Average transfer size"],
        ["Total", fmt_bytes(rs.get("average_total_transfer_size"))],
        ["Images", fmt_bytes(rs.get("average_image_transfer_size"))],
        ["Scripts", fmt_bytes(rs.get("average_script_transfer_size"))],
        ["Stylesheets", fmt_bytes(rs.get("average_stylesheet_transfer_size"))],
        ["Documents", fmt_bytes(rs.get("average_document_transfer_size"))],
    ], colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45])))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Average transfer composition", styles["Small"]))

    story.append(pie_chart([
        ("Images", rs.get("average_image_transfer_size")),
        ("Scripts", rs.get("average_script_transfer_size")),
        ("CSS", rs.get("average_stylesheet_transfer_size")),
        ("Docs", rs.get("average_document_transfer_size")),
    ]))

    story.append(Spacer(1, 8))

    story.append(Paragraph("Network server latency metrics", styles["H2"]))
    nsl = wp.get("network_server_latency", {}) or {}

    story.append(style_table(Table([
        ["Metric", "Top 10% (p10)", "Average", "Worst 10% (p90)"],
        ["Server latency", fmt_ms(bench["Server latency"]["p10"], "ms", 0), fmt_ms(nsl.get("average_server_latency"), "ms", 0), fmt_ms(bench["Server latency"]["p90"], "ms", 0)],
    ], colWidths=[CONTENT_W * 0.38, CONTENT_W * 0.20, CONTENT_W * 0.21, CONTENT_W * 0.21])))

    return story
