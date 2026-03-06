import os
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from ..styles import *
from ..helpers import render_logo

def cover_page(canvas, doc, sitemap, lighthouse, client_name, client_domain, logo_path, cover_image_path, report_title: str | None = None):
    """
    Generate the report cover page with branding logo.

    Args: 
        canvas (canvas, required): document canvas object
        doc (document, required): document object
        sitemap (Dict, required): sitemap data from audit
        lighthouse (Dict, required): lighthouse data from audit

    Returns: 
        None 
    """

    run_at = lighthouse.get("run_at") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    canvas.saveState()
    page_w, page_h = A4
    margin_x = 18 * mm

    # white background
    canvas.setFillColor(WHITE)
    canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # top blue band
    band_h = 55 * mm
    canvas.setFillColor(VALVANTA_BLUE)
    canvas.rect(0, page_h - band_h, page_w, band_h, fill=1, stroke=0)

    # logo block in band (left)
    box_size = 38 * mm
    box_x = 18 * mm
    box_y = page_h - band_h + (band_h - box_size) / 2
    render_logo(canvas, logo_path, box_x, box_y, box_size, box_size)

    # big white title (two lines)
    title_x = box_x + box_size + 14 * mm
    title_y1 = page_h - 20 * mm
    canvas.setFont("Helvetica-Bold", 34)
    canvas.setFillColor(WHITE)
    canvas.drawString(title_x, title_y1, "Full Website Audit")
    canvas.drawString(title_x, title_y1 - 18 * mm, "Report")

    # black subtitle
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 26)
    subtitle = report_title or "Technical & Performance Report"
    canvas.drawString(18 * mm, page_h - band_h - 22 * mm, subtitle)

    # grey cover image placeholder
    img_box_w = page_w - 2 * margin_x
    img_box_h = 95 * mm
    img_box_x = margin_x
    img_box_y = page_h - band_h - 30 * mm - img_box_h
    canvas.setFillColor(WHITE)
    canvas.rect(img_box_x, img_box_y, img_box_w, img_box_h, stroke=0, fill=1)

    if cover_image_path and os.path.exists(cover_image_path):
        try:
            img = ImageReader(cover_image_path)
            iw, ih = img.getSize()
            scale = min(img_box_w / iw, img_box_h / ih)
            dw, dh = iw * scale, ih * scale
            ix = img_box_x + (img_box_w - dw) / 2
            iy = img_box_y + (img_box_h - dh) / 2
            canvas.drawImage(img, ix, iy, width=dw, height=dh, mask='auto')
        except Exception:
            pass
    else:
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawCentredString(img_box_x + img_box_w / 2, img_box_y + img_box_h / 2, "cover image")

    # bottom-left meta text
    meta_x = 18 * mm
    meta_y = 20 * mm
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica", 12)
    lines = [
        f"Client: {client_name}",
        f"Website: {client_domain}",
        "Prepared by: Valvanta Digital Agency",
    ]
    line_h = 8 * mm
    y = meta_y + (len(lines) - 1) * line_h
    for line in lines:
        canvas.drawString(meta_x, y, line)
        y -= line_h

    canvas.restoreState()
