from typing import Any, Dict

from reportlab.platypus import Paragraph, Spacer, PageBreak, Table

from ..helpers import style_table
from ..styles import CONTENT_W, SectionRule, get_styles

def tested_urls_section(lh: Dict[Any], tested_urls): 
    """
    Create report section that displays the tested urls in a table 

    Args: 
        lh (Dict, required): lighthouse audit data

    Returns: 
        List of all the items in the section
    """
    styles = get_styles()


    story = []
    
    story.append(PageBreak())
    story.append(SectionRule("Tested URLs"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("All URLs included in this audit run.", styles["Body"]))
    story.append(Spacer(1, 6))

    url_rows = [["#", "URL"]]
    for i, u in enumerate(tested_urls, start=1):
        url_rows.append([str(i), Paragraph(u, styles["TableURL"])])
    url_tbl = Table(url_rows, colWidths=[CONTENT_W * 0.08, CONTENT_W * 0.92], repeatRows=1)
    story.append(style_table(url_tbl))
    story.append(PageBreak())

    return story
