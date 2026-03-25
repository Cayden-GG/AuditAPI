from __future__ import annotations

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


def _ensure_upsell_background() -> Path:
    if not UPSELL_BG.exists():
        return UPSELL_BG

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
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
    img = downscaled.resize((width_px, height_px), Image.LANCZOS)
    img.save(UPSELL_BG, format="PNG")
    return UPSELL_BG


class UpsellBackgroundPage(Flowable):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
        bg_path = _ensure_upsell_background()
        self._image = ImageReader(str(bg_path))

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def drawOn(self, canvas, x, y, _sW=0):
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
