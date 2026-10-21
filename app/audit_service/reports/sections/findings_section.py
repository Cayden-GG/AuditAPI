"""
Findings section
Report section listing the normalised findings with severity and standard references
"""
from typing import Any, Dict, List

from reportlab.platypus import Paragraph, Spacer, Table
from reportlab.lib.styles import ParagraphStyle

from ..helpers import severity_color, style_table
from ..styles import CONTENT_W, SectionRule, get_styles


def findings_section(findings: List[Dict[str, Any]], title: str) -> List[Any]:
    """
    Creates report section with a table of the findings, limited to the first 30

    @Args:
        findings (List[Dict[str, Any]]) -- normalised findings for one category and platform
        title (str) -- section title prefix, e.g. "Performance (Mobile)"

    @Returns:
        list of all the items in the section (List[Any])
    """
    styles = get_styles()
    story: List[Any] = []

    story.append(SectionRule(f"{title} Findings"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Findings are aligned to recognized standards and classified by severity.", styles["Body"]))
    story.append(Spacer(1, 6))

    if not findings:
        story.append(Paragraph("No findings of high enough severity to report.", styles["Body"]))
        return story

    rows = [["Issue", "Severity", "Standard", "Description", "Recommendation", "Affected URL"]]
    for f in findings[:30]:
        std = f.get("standard_reference") or {}
        level = std.get("level")
        level_label = f" (Level {level})" if level else ""
        std_label = f"{std.get('framework', 'n/a')} {std.get('code', '')}{level_label}".strip()
        sev_label = str(f.get("severity", "n/a")).title()
        sev_style = ParagraphStyle(
            "severity",
            parent=styles["SeverityCell"],
            textColor=severity_color(sev_label),
        )
        rows.append([
            Paragraph(str(f.get("title", "n/a")), styles["URLCell"]),
            Paragraph(sev_label, sev_style),
            Paragraph(std_label, styles["URLCell"]),
            Paragraph(str(f.get("description", "")), styles["URLCell"]),
            Paragraph(str(f.get("recommendation", "")), styles["URLCell"]),
            Paragraph(", ".join(f.get("affected_elements") or []) or "n/a", styles["TableURL"]),
        ])

    col_widths = [
        CONTENT_W * 0.14,
        CONTENT_W * 0.09,
        CONTENT_W * 0.11,
        CONTENT_W * 0.25,
        CONTENT_W * 0.26,
        CONTENT_W * 0.15,
    ]
    story.append(style_table(Table(rows, colWidths=col_widths, repeatRows=1)))
    return story
