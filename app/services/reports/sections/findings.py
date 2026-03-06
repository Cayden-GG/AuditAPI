from typing import Dict

from reportlab.platypus import Paragraph, Spacer, PageBreak

from .key_findings_table import key_findings_table
from ..styles import get_styles

def key_findings_section(ai: Dict):
    """
    Creates report section displaying the key findings.

    Table form with: issue, priority, impact, effort and short explaination columns.
   
    Args: 
        ai (Dict, required): ai summary data
    
    Returns: 
        List of all the items in the section  
    """
    styles = get_styles()
    story = []

    story.append(Paragraph("Key Findings & Priorities", styles["H1"]))
    story.append(Spacer(1, 8))

    method = ai.get("prioritisation_method") or "Priority is determined by business impact versus implementation effort."
    story.append(Paragraph(f"<b>Prioritisation method:</b> {method}", styles["Body"]))
    story.append(Spacer(1, 8))

    story.append(key_findings_table(ai))
    story.append(PageBreak())

    return story
