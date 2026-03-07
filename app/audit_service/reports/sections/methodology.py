from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import mm

from ..helpers import style_table
from ..styles import get_styles, LIGHT_BG


def methodology_section(lh: Dict[str, Any], tested_urls: List[str]) -> List[Any]:
    styles = get_styles()
    story: List[Any] = []

    story.append(Paragraph("Methodology", styles["H1"]))
    story.append(Paragraph("This audit uses Lighthouse in navigation mode with mobile emulation.", styles["Body"]))
    story.append(Spacer(1, 6))

    story.append(style_table(Table([
        ["Lighthouse version", str(lh.get("lighthouse_version", "n/a"))],
        ["Audit date", str(lh.get("run_at", "n/a"))],
        ["Categories tested", lh.get("categories") or "n/a"],
        ["Mode", str(lh.get("mode", "n/a"))],
        ["Device emulation", ", ".join(lh.get("devices") or []) or "n/a"],
        ["URLs tested", str(lh.get("tested_url_count", "n/a"))],
    ], colWidths=[55 * mm, 110 * mm])))
    story.append(Spacer(1, 6))

    config = lh.get("config", {}) or {}
    if config:
        story.append(Paragraph("Execution config", styles["H2"]))
        story.append(style_table(Table([
            ["Config key", "Value"],
            ["only_categories", str(config.get("only_categories", "n/a"))],
            ["mobile", "mobile emulation + throttling"],
            ["desktop", "desktop preset"],
        ], colWidths=[55 * mm, 110 * mm])))
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
            url_rows.append([str(i), Paragraph(u, styles["URLCell"])])
        url_tbl = Table(url_rows, colWidths=[10 * mm, 155 * mm], repeatRows=1)
        url_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BG),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(url_tbl)

    return story
