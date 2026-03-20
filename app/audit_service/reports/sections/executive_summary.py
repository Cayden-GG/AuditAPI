from typing import Dict

from reportlab.platypus import Paragraph, Spacer, Table

from ..helpers import fmt_num, style_table
from ..styles import CONTENT_W, SectionRule, get_styles

def executive_summary_section(
    ai: Dict,
    summary_by_platform: Dict,
    report_type: str,
):
    """
    Creates report section with executive summary, combining ai summaries with lighthouse audit data.
   
    Args: 
        ai (Dict, required): ai summary data
        summary_by_platform (Dict, required): summary data keyed by platform
        report_type (str, required): performance|seo
    
    Returns: 
        List of all the items in the section  
    """
    styles = get_styles()

    story = []
    
    story.append(SectionRule("Executive Summary"))
    story.append(Spacer(1, 10))

    exec_map = ai.get("executive_summaries") or {}
    exec_data = exec_map.get(report_type)
    if not exec_data:
        exec_text = None
    elif isinstance(exec_data, dict):
        exec_text = (
            # "<b>What the data shows</b><br/>"
            f"{exec_data.get('what_the_data_shows', '')}<br/><br/>"
            # "<b>Key strengths</b><br/>"
            f"{exec_data.get('key_strengths', '')}<br/><br/>"
            # "<b>Primary weaknesses</b><br/>"
            f"{exec_data.get('primary_weaknesses', '')}<br/><br/>"
            # "<b>High level roadmap</b><br/>"
            f"{exec_data.get('high_level_roadmap', '')}"
        )
    else:
        exec_text = exec_data
    if exec_text:
        safe_text = exec_text.replace("<br>", "<br/>").replace("\n", "<br/>")
        story.append(Paragraph(safe_text, styles["Body"]))
    else:
        story.append(Paragraph("AI summary not available for this section.", styles["Small"]))
    story.append(Spacer(1, 10))

    mobile_by_sev = (summary_by_platform.get("mobile", {}) or {}).get("findings_by_severity", {}) or {}
    desktop_by_sev = (summary_by_platform.get("desktop", {}) or {}).get("findings_by_severity", {}) or {}

    rows = [
        ["Summary metric", "Mobile", "Desktop"],
        ["Overall score", fmt_num((summary_by_platform.get("mobile", {}) or {}).get("overall_score"), 2),
         fmt_num((summary_by_platform.get("desktop", {}) or {}).get("overall_score"), 2)],
        ["Critical findings", str(mobile_by_sev.get("critical", 0)), str(desktop_by_sev.get("critical", 0))],
        ["High findings", str(mobile_by_sev.get("high", 0)), str(desktop_by_sev.get("high", 0))],
        ["Moderate findings", str(mobile_by_sev.get("moderate", 0)), str(desktop_by_sev.get("moderate", 0))],
        ["Advisory findings", str(mobile_by_sev.get("advisory", 0)), str(desktop_by_sev.get("advisory", 0))],
        [
            "Risk summary",
            Paragraph((summary_by_platform.get("mobile", {}) or {}).get("risk_summary", "n/a"), styles["Body"]),
            Paragraph((summary_by_platform.get("desktop", {}) or {}).get("risk_summary", "n/a"), styles["Body"]),
        ],
    ]

    story.append(style_table(Table(rows, colWidths=[CONTENT_W * 0.38, CONTENT_W * 0.31, CONTENT_W * 0.31])))

    return story
