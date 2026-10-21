"""
Report helpers
Formatting, statistics, table styling, chart and logo utilities shared by the report sections
"""
from .styles import (
    ADVISORY,
    BORDER,
    CRITICAL,
    HIGH,
    INK,
    LIGHT_BG,
    MODERATE,
    NA,
    PASS,
    PURPLE,
    PURPLE_DARK,
    ROW_ALT,
    SCORE_BAD,
    SCORE_GOOD,
    SCORE_MID,
    WHITE,
    FONT_BODY,
    FONT_HEADING_BOLD,
    _register_fonts,
    fonts_registered,
)

import urllib.parse
import math
import os

import numpy as np
from PIL import Image as PILImage

from typing import Any, List, Optional, Tuple, Dict

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader

# ---- helper functions

def benchmarks_metric(per_url: Dict[str, Dict[str, Any]]) -> Dict:
    """
    Formats benchmark metrics into p10, average, and p90

    @Args:
        per_url (Dict[str, Dict[str, Any]]) -- per-url performance data

    @Returns:
        p10, avg and p90 for FCP, LCP, Speed Index, TBT and server latency (Dict)
    """

    metric_map = {
        "FCP": [d.get("first_contentful_paint", {}).get("value") for d in per_url.values()],
        "LCP": [d.get("largest_contentful_paint", {}).get("value") for d in per_url.values()],
        "Speed Index": [d.get("speed_index", {}).get("value") for d in per_url.values()],
        "TBT": [d.get("total_blocking_time", {}).get("value") for d in per_url.values()],
        "Server latency": [d.get("network_server_latency", {}).get("server_latency") for d in per_url.values()],
    }
    
    bench = {k: {"p10": percentile(v, 10), "avg": mean(v), "p90": percentile(v, 90)} for k, v in metric_map.items()}

    return bench


def domain_from_url(url: str) -> str:
    """
    Parses inputted url for domain string

    @Args:
        url (str) -- website url

    @Returns:
        domain of the url, the url itself if it cannot be parsed (str)
    """
    try:
        return urllib.parse.urlparse(url).netloc or url
    except Exception:
        return url


def ms_to_s(ms: float) -> float:
    """Converts milliseconds to seconds"""
    return ms / 1000.0

# format ms
def fmt_ms(value: Any, unit: str = "ms", decimals: int = 0) -> str:
    """
    Formats input to time

    @Args:
        value (Any) -- value in milliseconds to be converted to a time value
        unit (str) -- time unit to display: ms | s
        decimals (int) -- number of digits after the "."

    @Returns:
        formatted time value ("0.50 s", "199 ms"), "n/a" if value is not a number (str)
    """
    if value is None:
        return "n/a"

    try:
        value = float(value)
    except Exception:
        return "n/a"
    
    if math.isnan(value):
        return "n/a"
    
    if unit == "s":
        return f"{ms_to_s(value):.{decimals}f} s"
    
    return f"{value:.{decimals}f} ms"

# format numbers
def fmt_num(value: Any, decimals: int = 1) -> str:
    """
    Formats input to number

    @Args:
        value (Any) -- value to be converted to a number
        decimals (int) -- number of digits after the "."

    @Returns:
        formatted number value ("0.6", "199.8"), "n/a" if value is not a number (str)
    """
    if value is None:
        return "n/a"

    try:
        value = float(value)
    except Exception:
        return "n/a"

    if math.isnan(value):
        return "n/a"

    return f"{value:.{decimals}f}"

# format bytes
def fmt_bytes(value: Any) -> str:
    """
    Formats input to bytes

    @Args:
        value (Any) -- value in bytes to be converted to the largest fitting unit

    @Returns:
        formatted byte value ("0.6 KB", "199.8 MB"), "n/a" if value is not a number (str)
    """
    if value is None:
        return "n/a"

    try:
        n = float(value)
    except Exception:
        return "n/a"

    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}" if u != "B" else f"{n:.0f} {u}"
        n /= 1024

    return "n/a"


def percentile(values: List[Any], p: float) -> Optional[float]:
    """
    Calculates the pth percentile of the provided values

    @Args:
        values (List[Any]) -- list of values, non numeric values are ignored
        p (float) -- the percentile

    @Returns:
        pth percentile value, None if there are no numeric values (Optional[float])

    Notes:
        if p=0, output will be the smallest value
        if p=50, output will be the middle value
        if p=100, output will be the largest value
    """
    vals: List[float] = []
    for x in values:
        if x is None:
            continue

        try:
            xf = float(x)
        except Exception:
            continue

        if math.isnan(xf):
            continue
        
        vals.append(xf)
        
    if not vals:
        return None

    return float(np.percentile(vals, p))


def mean(values: List[Any]) -> Optional[float]:
    """
    Calculates the mean (average) value of the provided values

    @Args:
        values (List[Any]) -- list of values, non numeric values are ignored

    @Returns:
        mean value, None if there are no numeric values (Optional[float])
    """
    vals: List[float] = []
    for x in values:
        if x is None:
            continue

        try:
            xf = float(x)
        except Exception:
            continue

        if math.isnan(xf):
            continue
        vals.append(xf)

    if not vals:
        return None

    return float(np.mean(vals))


def style_table(t: Table, header_bg=LIGHT_BG) -> Table:
    """
    Styles all the tables consistently

    @Args:
        t (Table) -- the table object to be styled
        header_bg (Color) -- table header color, e.g. colors.HexColor("#ffffff")

    @Returns:
        the table with computed styles (Table)
    """
    _register_fonts()
    header_font = FONT_HEADING_BOLD if fonts_registered() else "Helvetica-Bold"
    body_font = FONT_BODY if fonts_registered() else "Helvetica"

    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), header_font),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTNAME", (0, 1), (-1, -1), body_font),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ROW_ALT]),
                ("LINEBELOW", (0, 0), (-1, 0), 1, PURPLE_DARK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, BORDER),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ]
        )
    )
    return t


def severity_color(label: Any):
    """Returns the report color for a severity label (critical | high | moderate | advisory | pass), NA color if unknown"""
    if not isinstance(label, str):
        return NA

    lowered = label.strip().lower()
    return {
        "critical": CRITICAL,
        "high": HIGH,
        "moderate": MODERATE,
        "advisory": ADVISORY,
        "pass": PASS,
        "na": NA,
        "n/a": NA,
    }.get(lowered, NA)


def score_color(value: Any):
    """Returns the report color for a 0-1 lighthouse score: good from 0.9, mid from 0.5, bad below, NA color if not a number"""
    if not isinstance(value, (int, float)):
        return NA
        
    if value >= 0.9:
        return SCORE_GOOD

    if value >= 0.5:
        return SCORE_MID

    return SCORE_BAD


def bar_chart(labels: List[str], series: List[Tuple[str, List[Optional[float]]]], width: int = 460, height: int = 180) -> Drawing:
    """
    Renders a bar chart with provided data

    @Args:
        labels (List[str]) -- list of chart labels
        series (List[Tuple[str, List[Optional[float]]]]) -- named series of values to add to the bar chart
        width (int) -- width of bar chart
        height (int) -- height of bar chart

    @Returns:
        drawing of bar chart to render on the canvas (Drawing)
    """

    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 30
    bc.height = height - 50
    bc.width = width - 60
    bc.data = [[0 if v is None else float(v) for v in vals] for _, vals in series]
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.fontSize = 7
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.valueMin = 0

    flat = [v for row in bc.data for v in row]
    vmax = (max(flat) * 1.15) if flat else 1
    
    bc.valueAxis.valueMax = vmax
    bc.valueAxis.valueStep = vmax / 5 if vmax else 1
    palette = _purple_palette(max(len(series), 1))

    for idx in range(len(series)):
        bc.bars[idx].fillColor = palette[idx % len(palette)]
        bc.bars[idx].strokeColor = BORDER
    d.add(bc)

    return d


def pie_chart(parts: List[Tuple[str, Any]], width: int = 460, height: int = 200) -> Drawing:
    """
    Renders a pie chart with provided data

    @Args:
        parts (List[Tuple[str, Any]]) -- labelled parts/slices of the pie chart, empty and non positive values are skipped
        width (int) -- width of pie chart
        height (int) -- height of pie chart

    @Returns:
        drawing of pie chart to render on the canvas, empty if there are no values (Drawing)
    """
    d = Drawing(width, height)
    pie = Pie()
    pie.x = width / 2 - 80
    pie.y = 15
    pie.width = 160
    pie.height = 160
    pie.sideLabels = 1
    pie.simpleLabels = 0
    pie.checkLabelOverlap = 1
    pie.pointerLabelMode = "LeftRight"
    pie.sideLabelsOffset = 0.15
    pie.slices.fontSize = 7
    pie.slices.labelRadius = 1.35

    labels: List[str] = []
    values: List[float] = []

    for lbl, v in parts:
        if v is None:
            continue

        try:
            vf = float(v)
        except Exception:
            continue

        if vf <= 0:
            continue

        labels.append(lbl)
        values.append(vf)

    if not values:
        return d

    pie.data = values
    pie.labels = labels
    palette = _purple_palette(max(len(values), 1))

    for idx in range(len(values)):
        pie.slices[idx].fillColor = palette[idx % len(palette)]

    pie.slices.strokeWidth = 0.5
    d.add(pie)

    return d


def _tint_color(base: colors.Color, factor: float) -> colors.Color:
    """Lightens a color towards white, factor is clamped between 0 (unchanged) and 1 (white)"""
    factor = max(0.0, min(1.0, factor))

    return colors.Color(
        base.red + (1 - base.red) * factor,
        base.green + (1 - base.green) * factor,
        base.blue + (1 - base.blue) * factor,
    )


def _purple_palette(count: int) -> List[colors.Color]:
    """Builds count shades of the brand purple, from dark to light, for chart series"""
    if count <= 1:
        return [PURPLE]
    
    start = 0.15
    end = 0.75
    steps = max(count - 1, 1)

    return [_tint_color(PURPLE, start + (end - start) * (i / steps)) for i in range(count)]


def render_logo(canvas, logo_path: Optional[str], x: float, y: float, w: float, h: float) -> None:
    """
    Renders brand logo on the report.

    If no logo passed logo is left blank no placeholder.

    @Args:
        canvas (Canvas) -- canvas for the logo to be rendered to
        logo_path (Optional[str]) -- path to logo
        x (float) -- x co-ordinate
        y (float) -- y co-ordinate
        w (float) -- width of logo
        h (float) -- height of logo
    """
    canvas.saveState()

    if logo_path and os.path.exists(logo_path):
        try:
            img = ImageReader(logo_path)
            pad = 6
            iw = w - 2 * pad
            ih = h - 2 * pad

            with PILImage.open(logo_path) as im:
                px_w, px_h = im.size

            scale = min(iw / px_w, ih / px_h)
            dw = px_w * scale
            dh = px_h * scale

            cx = x + (w - dw) / 2
            cy = y + (h - dh) / 2
            canvas.drawImage(img, cx, cy, width=dw, height=dh, mask="auto")

        except Exception:
            pass

    canvas.restoreState()
