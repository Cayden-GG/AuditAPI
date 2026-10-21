"""
Key findings table
Table of the AI key findings used by the key findings section
"""
from typing import Dict, List, Any

from reportlab.platypus import Paragraph, Table
from ..helpers import style_table
from ..styles import CONTENT_W, get_styles


def key_findings_table(ai: Dict[str, Any]) -> Table:
    """
    Creates the key findings table of up to 12 findings, uses a placeholder row if the AI returned none

    @Args:
        ai (Dict[str, Any]) -- ai summary data

    @Returns:
        styled table with issue, priority, impact, effort and explanation columns (Table)
    """
    styles = get_styles()

    findings = ai.get("key_findings") or []
    if not findings:
        findings = [{
            "issue": "AI findings missing (run AI module).",
            "priority": "High",
            "impact": "Performance, UX",
            "effort": "Medium",
            "explanation": "Populate this table via one AI request using the complete dataset."
        }]

    pr_rows = [["Issue", "Priority", "Impact", "Effort", "Short explanation"]]
    for f in findings[:12]:
        pr_rows.append([
            Paragraph(str(f.get("issue", "n/a")), styles["URLCell"]),
            str(f.get("priority", "n/a")),
            Paragraph(str(f.get("impact", "n/a")), styles["URLCell"]),
            Paragraph(str(f.get("effort", "n/a")), styles["URLCell"]),
            Paragraph(str(f.get("explanation", "")), styles["URLCell"]),
        ])

    col_widths = [
        CONTENT_W * 0.28,
        CONTENT_W * 0.10,
        CONTENT_W * 0.18,
        CONTENT_W * 0.10,
        CONTENT_W * 0.34,
    ]
    return style_table(Table(pr_rows, colWidths=col_widths, repeatRows=1))
