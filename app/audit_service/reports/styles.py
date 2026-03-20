import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Page setup
PAGE_W, PAGE_H = A4
MARGIN_L = 20 * mm
MARGIN_R = 20 * mm
MARGIN_T = 14 * mm
MARGIN_B = 14 * mm
HEADER_H = 11 * mm
FOOTER_H = 9 * mm
CONTENT_W = PAGE_W - (MARGIN_L + MARGIN_R)

# Font setup
FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"))
FONT_HEADING = "KaiseiDecol"
FONT_HEADING_BOLD = "KaiseiDecol-Bold"
FONT_BODY = "Inter"
FONT_BODY_BOLD = "Inter-Bold"
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        required = {
            FONT_HEADING: os.path.join("Kaisei_Decol", "KaiseiDecol-Regular.ttf"),
            FONT_HEADING_BOLD: os.path.join("Kaisei_Decol", "KaiseiDecol-Bold.ttf"),
            FONT_BODY: os.path.join("Inter", "static", "Inter_18pt-Regular.ttf"),
            FONT_BODY_BOLD: os.path.join("Inter", "static", "Inter_18pt-Bold.ttf"),
        }
        registered = set(pdfmetrics.getRegisteredFontNames())
        for name, filename in required.items():
            if name in registered:
                continue
            font_path = os.path.join(FONT_DIR, filename)
            pdfmetrics.registerFont(TTFont(name, font_path))
        registered = set(pdfmetrics.getRegisteredFontNames())
        _FONTS_REGISTERED = all(name in registered for name in required)
        if _FONTS_REGISTERED:
            try:
                pdfmetrics.registerFontFamily(
                    FONT_BODY,
                    normal=FONT_BODY,
                    bold=FONT_BODY_BOLD,
                    italic=FONT_BODY,
                    boldItalic=FONT_BODY_BOLD,
                )
                pdfmetrics.registerFontFamily(
                    FONT_HEADING,
                    normal=FONT_HEADING,
                    bold=FONT_HEADING_BOLD,
                    italic=FONT_HEADING,
                    boldItalic=FONT_HEADING_BOLD,
                )
            except Exception:
                pass
    except Exception:
        _FONTS_REGISTERED = False


def fonts_registered() -> bool:
    return _FONTS_REGISTERED

# Brand + palette
PURPLE = colors.HexColor("#6B4EFF")
PURPLE_DARK = colors.HexColor("#4A34C8")
COVER_BG = colors.HexColor("#0D1117")
HEADER_BG = colors.HexColor("#0D1117")
FOOTER_BG = colors.HexColor("#F5F5F8")
ROW_ALT = colors.HexColor("#F8F8FC")
BORDER = colors.HexColor("#DEDEE8")

INK = colors.HexColor("#1A1A1A")
INK_MUTED = colors.HexColor("#555555")
INK_LIGHT = colors.HexColor("#888888")

CRITICAL = colors.HexColor("#CC2200")
HIGH = colors.HexColor("#D95900")
MODERATE = colors.HexColor("#9B7000")
ADVISORY = colors.HexColor("#1A55AA")
PASS = colors.HexColor("#1A7A45")
NA = colors.HexColor("#777777")

SCORE_GOOD = PASS
SCORE_MID = MODERATE
SCORE_BAD = CRITICAL

WHITE = colors.white
LIGHT_BG = PURPLE_DARK

MAX_URLS = 100


class SectionRule(Flowable):
    def __init__(self, title: str, subtitle: str | None = None) -> None:
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self._width = CONTENT_W

    def wrap(self, availWidth, availHeight):
        self._width = availWidth or CONTENT_W
        top_pad = 6
        rule_h = 3
        title_gap = 6
        title_h = 13
        subtitle_gap = 10
        subtitle_h = 8.5
        bottom_pad = 14
        height = top_pad + rule_h + title_gap + title_h + bottom_pad
        if self.subtitle:
            height += subtitle_gap + subtitle_h
        self.height = height
        return self._width, height

    def draw(self):
        canvas = self.canv
        width = self._width

        canvas.saveState()
        _register_fonts()
        top_pad = 6
        rule_h = 3
        title_gap = 6
        title_h = 13
        subtitle_gap = 10
        subtitle_h = 8.5
        y = self.height - top_pad - rule_h
        canvas.setStrokeColor(PURPLE)
        canvas.setLineWidth(3)
        canvas.line(0, y, width, y)

        title_y = y - title_gap - title_h
        canvas.setFillColor(INK)
        canvas.setFont(FONT_HEADING_BOLD if _FONTS_REGISTERED else "Helvetica-Bold", 13)
        canvas.drawString(0, title_y, self.title)

        if self.subtitle:
            subtitle_y = title_y - subtitle_gap - subtitle_h
            canvas.setFillColor(INK_MUTED)
            canvas.setFont(FONT_BODY if _FONTS_REGISTERED else "Helvetica", 8.5)
            canvas.drawString(0, subtitle_y, self.subtitle)

        canvas.restoreState()


def get_styles():
    styles = getSampleStyleSheet()
    _register_fonts()

    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            fontName=FONT_HEADING_BOLD if _FONTS_REGISTERED else "Helvetica-Bold",
            fontSize=13,
            leading=20,
            textColor=INK,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontName=FONT_HEADING_BOLD if _FONTS_REGISTERED else "Helvetica-Bold",
            fontSize=10.5,
            leading=16,
            textColor=INK,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontName=FONT_BODY if _FONTS_REGISTERED else "Helvetica",
            fontSize=9,
            leading=14,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName=FONT_BODY if _FONTS_REGISTERED else "Helvetica",
            fontSize=8.5,
            leading=13,
            textColor=INK_MUTED,
            alignment=TA_LEFT,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["BodyText"],
            fontName=FONT_BODY if _FONTS_REGISTERED else "Helvetica",
            fontSize=7.5,
            leading=11,
            textColor=INK_LIGHT,
            alignment=TA_LEFT,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="URLCell",
            parent=styles["BodyText"],
            fontName=FONT_BODY if _FONTS_REGISTERED else "Helvetica",
            fontSize=8,
            leading=12,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableURL",
            parent=styles["BodyText"],
            fontName=FONT_BODY if _FONTS_REGISTERED else "Helvetica",
            fontSize=7.5,
            leading=11,
            textColor=PURPLE,
            alignment=TA_LEFT,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SeverityCell",
            parent=styles["BodyText"],
            fontName=FONT_BODY_BOLD if _FONTS_REGISTERED else "Helvetica-Bold",
            fontSize=8,
            leading=12,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=0,
        )
    )

    return styles
