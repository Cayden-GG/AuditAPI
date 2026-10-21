"""
Upsell page
Full page flowable shown after the free audit urls to promote the premium audit
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

from ..styles import (
    FONT_BODY,
    FONT_HEADING_BOLD,
    INK,
    PURPLE,
    _register_fonts,
    fonts_registered,
)

ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
UPSELL_BG = ASSETS_DIR / "upsell_blur_bg.png"


@lru_cache(maxsize=1)
def _upsell_background() -> Image.Image:
    """
    Draws placeholder rows on the upsell background and blurs it, in memory only.
    The image file is never modified, so the blur does not compound between runs.

    @Returns:
        blurred upsell background image (Image.Image)
    """
    width_px = 1240
    height_px = 1754
    img = Image.open(UPSELL_BG)
    draw = ImageDraw.Draw(img)

    for i in range(12):
        y = 120 + i * 120
        shade = 240 - i
        draw.rectangle([80, y, width_px - 80, y + 28], fill=(shade, shade, shade))

    for i in range(6):
        y = 240 + i * 180
        draw.rectangle([120, y, width_px - 120, y + 90], outline=(220, 220, 230), width=2)

    img = img.filter(ImageFilter.GaussianBlur(radius=8))
    downscaled = img.resize((width_px // 2, height_px // 2), Image.LANCZOS)

    return downscaled.resize((width_px, height_px), Image.LANCZOS)


class UpsellBackgroundPage(Flowable):
    """Full page flowable with the blurred upsell background and a premium audit message

    @Args:
        text (str) -- message drawn in the centre of the page
    """
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
        self._image = ImageReader(_upsell_background())

    def wrap(self, availWidth, availHeight):
        """Takes no layout space, the page is drawn straight onto the canvas in drawOn"""
        return 0, 0

    def drawOn(self, canvas, x, y, _sW=0):
        """Draws the background across the whole page with the message and premium audit label"""
        _register_fonts()
        canvas.saveState()
        page_w, page_h = canvas._pagesize

        canvas.drawImage(self._image, 0, 0, width=page_w, height=page_h, mask="auto")

        font = FONT_HEADING_BOLD if fonts_registered() else "Helvetica-Bold"
        body_font = FONT_BODY if fonts_registered() else "Helvetica"
        canvas.setFillColor(INK)
        canvas.setFont(font, 13)
        canvas.drawCentredString(page_w / 2, page_h / 2, self.text)
        canvas.setFillColor(PURPLE)
        canvas.setFont(body_font, 12)
        canvas.drawCentredString(page_w / 2, page_h / 2 - 16, "Premium Brand audit required")

        canvas.restoreState()
