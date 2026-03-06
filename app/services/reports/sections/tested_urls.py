from typing import Any, Dict

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.units import mm

from ..styles import get_styles, MAX_URLS, LIGHT_BG

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
    story.append(Paragraph("Tested URLs", styles["H1"]))
    story.append(Paragraph("All URLs included in this audit run.", styles["Body"]))
    story.append(Spacer(1, 6))

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
    story.append(PageBreak())

    return story
