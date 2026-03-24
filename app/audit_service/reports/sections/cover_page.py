import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from ..helpers import render_logo, score_color
from ..styles import (
    CONTENT_W,
    COVER_BG,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_HEADING,
    FONT_HEADING_BOLD,
    INK_LIGHT,
    MARGIN_L,
    NA,
    PURPLE,
    WHITE,
    _register_fonts,
    fonts_registered,
)


def _extract_score(summary: dict, report_type: str, platform: str):
    report = summary.get(report_type, {}) or {}
    platform_entry = report.get(platform, {}) or {}
    for key in ("overall_score", "score", "average_score"):
        if platform_entry.get(key) is not None:
            return platform_entry.get(key)
    return None


def _format_score(value):
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value * 100:.0f}"


def cover_page(canvas, doc, sitemap, lighthouse, client_name, client_domain, logo_path, cover_image_path, report_title: str | None = None):
    """
    Generate the report cover page with branding logo.
    """
    run_at = lighthouse.get("run_at") or datetime.datetime.now().strftime("%Y-%m-%d")
    summary = lighthouse.get("summary", {}) or {}

    mobile_perf = _extract_score(summary, "performance", "mobile")
    desktop_perf = _extract_score(summary, "performance", "desktop")
    mobile_seo = _extract_score(summary, "seo", "mobile")
    desktop_seo = _extract_score(summary, "seo", "desktop")
    mobile_accessibility = _extract_score(summary, "accessibility", "mobile")
    desktop_accessibility = _extract_score(summary, "accessibility", "desktop")

    tested_urls = lighthouse.get("tested_url_count")
    if tested_urls is None:
        tested_urls = len(lighthouse.get("tested_urls") or []) or len(lighthouse.get("per_url_performance_data") or {})

    canvas.saveState()
    page_w, page_h = A4

    canvas.setFillColor(COVER_BG)
    canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    canvas.setStrokeColor(colors.HexColor("#181E2C"))
    canvas.setLineWidth(0.25)
    for y in range(0, int(page_h), 20):
        canvas.line(0, y, page_w, y)

    _register_fonts()
    heading_font = FONT_HEADING_BOLD if fonts_registered() else "Helvetica-Bold"
    body_font = FONT_BODY if fonts_registered() else "Helvetica"
    body_bold = FONT_BODY_BOLD if fonts_registered() else "Helvetica-Bold"

    logo_w = 92.4 * mm
    logo_h = 42 * mm

    canvas.setFillColor(PURPLE)
    label = "WEBSITE AUDIT REPORT"
    label_y = page_h - 52 * mm
    label_w = canvas.stringWidth(label, heading_font, 8)
    logo_x = MARGIN_L + (label_w - logo_w) / 2
    logo_y = label_y + 12 * mm - 40
    render_logo(canvas, logo_path, logo_x, logo_y, logo_w, logo_h)

    canvas.setFont(heading_font, 8)
    canvas.drawString(MARGIN_L, label_y, label)

    headline_y = page_h * 0.58
    canvas.setFont(heading_font, 30)
    canvas.setFillColor(WHITE)
    canvas.drawString(MARGIN_L, headline_y, client_domain)

    subtitle = report_title or "Technical & Performance Report"
    canvas.setFont(body_font, 13)
    canvas.setFillColor(colors.HexColor("#9999BB"))
    canvas.drawString(MARGIN_L, headline_y - 22, subtitle)

    canvas.setStrokeColor(PURPLE)
    canvas.setLineWidth(1.5)
    canvas.line(MARGIN_L, headline_y - 32, MARGIN_L + 80, headline_y - 32)

    kpis = [
        ("Mobile Performance", _format_score(mobile_perf), score_color(mobile_perf)),
        ("Desktop Performance", _format_score(desktop_perf), score_color(desktop_perf)),
        ("Mobile SEO", _format_score(mobile_seo), score_color(mobile_seo)),
        ("Desktop SEO", _format_score(desktop_seo), score_color(desktop_seo)),
        ("Mobile Accessibility", _format_score(mobile_accessibility), score_color(mobile_accessibility)),
        ("Desktop Accessibility", _format_score(desktop_accessibility), score_color(desktop_accessibility)),
        ("Pages Audited", str(tested_urls or "n/a"), PURPLE),
    ]

    card_gap = 8
    card_h = 60
    card_y = headline_y - 106

    row_specs = [3, 4]
    offset = 0
    for row_idx, row_count in enumerate(row_specs):
        row = kpis[offset:offset + row_count]
        if not row:
            break
        card_w = (CONTENT_W - card_gap * (row_count - 1)) / row_count
        card_x = MARGIN_L
        row_y = card_y - (row_idx * (card_h + 10))

        for label, value, color in row:
            canvas.setFillColor(colors.HexColor("#111826"))
            canvas.setStrokeColor(colors.HexColor("#242E42"))
            canvas.setLineWidth(0.8)
            canvas.rect(card_x, row_y, card_w, card_h, fill=1, stroke=1)

            canvas.setFillColor(color if color else NA)
            canvas.rect(card_x, row_y + card_h - 3, card_w, 3, fill=1, stroke=0)

            canvas.setFont(body_bold, 22)
            canvas.setFillColor(color if color else NA)
            canvas.drawString(card_x + 8, row_y + card_h - 28, str(value))

            canvas.setFont(body_font, 7)
            canvas.setFillColor(INK_LIGHT)
            canvas.drawString(card_x + 8, row_y + 8, label.upper())

            card_x += card_w + card_gap

        offset += row_count

    strip_h = 32
    strip_y = 46
    canvas.setFillColor(colors.HexColor("#0A0D16"))
    canvas.setStrokeColor(colors.HexColor("#242E42"))
    canvas.setLineWidth(0.8)
    canvas.rect(MARGIN_L, strip_y, CONTENT_W, strip_h, fill=1, stroke=1)

    columns = [
        ("CLIENT", client_name),
        ("WEBSITE", client_domain),
        ("PREPARED BY", "Valvanta Digital Agency"),
        ("DATE", str(run_at)[:10]),
    ]
    col_w = CONTENT_W / 4
    for idx, (label, value) in enumerate(columns):
        col_x = MARGIN_L + idx * col_w + 8
        canvas.setFont(heading_font, 7)
        canvas.setFillColor(PURPLE)
        canvas.drawString(col_x, strip_y + strip_h - 12, label)
        canvas.setFont(body_font, 8.5)
        canvas.setFillColor(WHITE)
        canvas.drawString(col_x, strip_y + 8, str(value))

    canvas.restoreState()
