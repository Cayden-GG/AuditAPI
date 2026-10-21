"""
Key findings section
Report section for the AI prioritised key findings
"""
from typing import Dict

from reportlab.platypus import Paragraph, Spacer, PageBreak

from .key_findings_table import key_findings_table
from ..styles import SectionRule, get_styles

def key_findings_section(ai: Dict):
    """
    Creates report section displaying the key findings.

    Table form with: issue, priority, impact, effort and short explanation columns.

    @Args:
        ai (Dict) -- ai summary data

    @Returns:
        list of all the items in the section (List)
    """
    styles = get_styles()
    story = []

    story.append(SectionRule("Key Findings & Priorities"))
    story.append(Spacer(1, 10))

    method = ai.get("prioritisation_method") or "Priority is determined by business impact versus implementation effort."
    story.append(Paragraph(f"<b>Prioritisation method:</b> {method}", styles["Body"]))
    story.append(Spacer(1, 8))

    story.append(key_findings_table(ai))
    story.append(PageBreak())

    return story
