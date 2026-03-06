from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

def header_footer(canvas, doc, client_domain):
    """
    Creates the header and footer for the report
    """
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)

    canvas.drawString(
        18 * mm,
        12 * mm,
        f"{client_domain} | Website Audit"
    )
    canvas.drawRightString(
        A4[0] - 18 * mm,
        12 * mm,
        f"Page {doc.page}"
    )

    canvas.restoreState()

