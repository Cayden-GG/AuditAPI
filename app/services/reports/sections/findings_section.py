from typing import Any, Dict, List

from reportlab.platypus import Paragraph, Spacer, Table
from reportlab.lib.units import mm

from ..helpers import style_table
from ..styles import get_styles


def findings_section(findings: List[Dict[str, Any]], title: str) -> List[Any]:
    styles = get_styles()
    story: List[Any] = []

    story.append(Paragraph(f"{title} Findings", styles["H1"]))
    story.append(Paragraph("Findings are aligned to recognized standards and classified by severity.", styles["Body"]))
    story.append(Spacer(1, 6))

    if not findings:
        story.append(Paragraph("No findings matched the inclusion rules for this report.", styles["Body"]))
        return story

    rows = [["Title", "Severity", "Standard", "Description", "Recommendation", "Affected"]]
    for f in findings[:30]:
        std = f.get("standard_reference") or {}
        level = std.get("level")
        level_label = f" (Level {level})" if level else ""
        std_label = f"{std.get('framework', 'n/a')} {std.get('code', '')}{level_label}".strip()
        rows.append([
            Paragraph(str(f.get("title", "n/a")), styles["URLCell"]),
            str(f.get("severity", "n/a")).title(),
            Paragraph(std_label, styles["URLCell"]),
            Paragraph(str(f.get("description", "")), styles["URLCell"]),
            Paragraph(str(f.get("recommendation", "")), styles["URLCell"]),
            Paragraph(", ".join(f.get("affected_elements") or []) or "n/a", styles["URLCell"]),
        ])

    story.append(style_table(Table(rows, colWidths=[40 * mm, 15 * mm, 28 * mm, 45 * mm, 45 * mm, 22 * mm], repeatRows=1)))
    return story
