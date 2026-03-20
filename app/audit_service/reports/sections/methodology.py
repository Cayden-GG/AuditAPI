from typing import Any, Dict, List

from reportlab.platypus import Paragraph, Spacer, Table

from ..helpers import style_table
from ..styles import CONTENT_W, SectionRule, get_styles


def methodology_section(lh: Dict[str, Any], tested_urls: List[str]) -> List[Any]:
    styles = get_styles()
    story: List[Any] = []

    story.append(SectionRule("Audit Methodology"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("This audit uses Lighthouse in navigation mode with mobile emulation.", styles["Body"]))
    story.append(Spacer(1, 6))

    story.append(style_table(Table([
        ["Lighthouse version", str(lh.get("lighthouse_version", "n/a"))],
        ["Audit date", str(lh.get("run_at", "n/a"))],
        ["Categories tested", lh.get("categories") or "n/a"],
        ["Mode", str(lh.get("mode", "n/a"))],
        ["Device emulation", ", ".join(lh.get("devices") or []) or "n/a"],
        ["URLs tested", str(lh.get("tested_url_count", "n/a"))],
    ], colWidths=[CONTENT_W * 0.4, CONTENT_W * 0.6])))
    story.append(Spacer(1, 6))

    config = lh.get("config", {}) or {}
    if config:
        story.append(Paragraph("Execution config", styles["H2"]))
        story.append(style_table(Table([
            ["Config key", "Value"],
            ["only_categories", str(config.get("only_categories", "n/a"))],
            ["mobile", "mobile emulation + throttling"],
            ["desktop", "desktop preset"],
        ], colWidths=[CONTENT_W * 0.4, CONTENT_W * 0.6])))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Standards Alignment Statement", styles["H2"]))
    story.append(Paragraph(
        "This report aligns findings to WCAG 2.1 Level A and AA (automated checks only), "
        "Google Core Web Vitals, and Google Search Essentials.", styles["Body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This audit reflects automated testing only and does not constitute full legal compliance certification.",
        styles["Body"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Limitations & Scope Disclaimer", styles["H2"]))
    story.append(Paragraph(
        "This report is based on automated Lighthouse checks and reflects a point-in-time snapshot. "
        "It does not replace manual testing, user research, or full compliance reviews.", styles["Body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Findings should be validated in real user conditions and with assistive technologies where applicable.",
        styles["Body"]))
    story.append(Spacer(1, 6))

    if tested_urls:
        story.append(Paragraph("Tested URLs", styles["H2"]))
        story.append(Paragraph("All URLs included in this audit run.", styles["Body"]))
        story.append(Spacer(1, 4))
        url_rows = [["#", "URL"]]
        for i, u in enumerate(tested_urls, start=1):
            url_rows.append([str(i), Paragraph(u, styles["TableURL"])])
        url_tbl = Table(url_rows, colWidths=[CONTENT_W * 0.08, CONTENT_W * 0.92], repeatRows=1)
        story.append(style_table(url_tbl))

    return story
