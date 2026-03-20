from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

from .styles import (
    BORDER,
    FOOTER_BG,
    FOOTER_H,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_HEADING_BOLD,
    HEADER_BG,
    HEADER_H,
    INK_LIGHT,
    INK_MUTED,
    MARGIN_L,
    MARGIN_R,
    PURPLE,
    WHITE,
    _register_fonts,
    fonts_registered,
)

def header_footer(canvas, doc, client_domain):
    """
    Creates the header and footer for the report
    """
    canvas.saveState()
    page_w, page_h = A4

    # Header bar
    _register_fonts()
    body_font = FONT_BODY if fonts_registered() else "Helvetica"
    body_bold = FONT_BODY_BOLD if fonts_registered() else "Helvetica-Bold"
    canvas.setFillColor(HEADER_BG)
    canvas.rect(0, page_h - HEADER_H, page_w, HEADER_H, fill=1, stroke=0)
    canvas.setFillColor(PURPLE)
    canvas.rect(0, page_h - 2, page_w, 2, fill=1, stroke=0)

    canvas.setFont(body_font, 7.5)
    canvas.setFillColor(colors.HexColor("#AAAAAA"))
    canvas.drawString(MARGIN_L, page_h - HEADER_H + 10, "Website Audit Report")
    canvas.setFont(body_bold, 7.5)
    canvas.setFillColor(WHITE)
    canvas.drawRightString(page_w - MARGIN_R, page_h - HEADER_H + 10, client_domain)

    # Footer bar
    canvas.setFillColor(FOOTER_BG)
    canvas.rect(0, 0, page_w, FOOTER_H, fill=1, stroke=0)
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(0, FOOTER_H, page_w, FOOTER_H)

    canvas.setFont(body_font, 7)
    canvas.setFillColor(INK_LIGHT)
    canvas.drawString(MARGIN_L, 10, "Prepared by Valvanta Digital Agency")
    canvas.setFont(body_bold, 7.5)
    canvas.setFillColor(INK_MUTED)
    canvas.drawRightString(page_w - MARGIN_R, 10, f"Page {doc.page}")

    canvas.restoreState()
