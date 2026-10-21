import math
import os

import pytest
from PIL import Image
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib import colors
from reportlab.platypus import Table

from app.audit_service.reports import helpers
from app.audit_service.reports.helpers import (
    _purple_palette,
    _tint_color,
    bar_chart,
    benchmarks_metric,
    domain_from_url,
    fmt_bytes,
    fmt_ms,
    fmt_num,
    mean,
    ms_to_s,
    percentile,
    pie_chart,
    render_logo,
    score_color,
    severity_color,
    style_table,
)
from app.audit_service.reports.styles import (
    ADVISORY, CRITICAL, HIGH, MODERATE, NA, PASS, PURPLE, SCORE_BAD, SCORE_GOOD, SCORE_MID,
)


@pytest.mark.parametrize(
    "value, unit, decimals, expected",
    [
        (1234, "ms", 0, "1234 ms"),
        (199.6, "ms", 0, "200 ms"),
        (199.66, "ms", 1, "199.7 ms"),
        (500, "s", 2, "0.50 s"),
        (2500, "s", 1, "2.5 s"),
        ("1500", "s", 1, "1.5 s"),
        (0, "ms", 0, "0 ms"),
        (None, "ms", 0, "n/a"),
        ("fast", "s", 1, "n/a"),
        (float("nan"), "ms", 0, "n/a"),
        ([], "ms", 0, "n/a"),
    ],
)
def test_fmt_ms(value, unit, decimals, expected):
    assert fmt_ms(value, unit, decimals) == expected


@pytest.mark.parametrize(
    "value, decimals, expected",
    [(0.6, 1, "0.6"), (199.84, 1, "199.8"), (3, 0, "3"), (2.345, 2, "2.35"), ("4.5", 1, "4.5"), (None, 1, "n/a"), ("x", 1, "n/a"), (float("nan"), 1, "n/a")],
)
def test_fmt_num(value, decimals, expected):
    assert fmt_num(value, decimals) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "0 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (5.5 * 1024 * 1024, "5.5 MB"),
        (1024**3, "1.0 GB"),
        (5 * 1024**4, "5120.0 GB"),
        ("2048", "2.0 KB"),
        (None, "n/a"),
        ("big", "n/a"),
    ],
)
def test_fmt_bytes(value, expected):
    assert fmt_bytes(value) == expected


def test_ms_to_s():
    assert ms_to_s(1500) == 1.5


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://example.com/path?x=1", "example.com"),
        ("http://sub.example.com:8080/", "sub.example.com:8080"),
        ("example.com", "example.com"),
        ("", ""),
    ],
)
def test_domain_from_url(url, expected):
    assert domain_from_url(url) == expected


def test_domain_from_url_returns_the_input_when_it_cannot_be_parsed():
    assert domain_from_url(None) is None


def test_percentile_and_mean_ignore_bad_values():
    values = [10, None, "20", "x", float("nan"), 30]

    assert percentile(values, 0) == 10.0
    assert percentile(values, 50) == 20.0
    assert percentile(values, 100) == 30.0
    assert mean(values) == 20.0


@pytest.mark.parametrize("values", [[], [None], ["x", float("nan")]])
def test_percentile_and_mean_of_nothing_are_none(values):
    assert percentile(values, 50) is None
    assert mean(values) is None


def test_percentile_interpolates():
    assert percentile([0, 100], 10) == 10.0
    assert percentile([5], 90) == 5.0


def test_benchmarks_metric_summarises_each_metric_across_urls():
    per_url = {
        "a": {"first_contentful_paint": {"value": 100}, "network_server_latency": {"server_latency": 10}},
        "b": {"first_contentful_paint": {"value": 300}, "network_server_latency": {"server_latency": 30}},
    }

    bench = benchmarks_metric(per_url)

    assert set(bench) == {"FCP", "LCP", "Speed Index", "TBT", "Server latency"}
    assert bench["FCP"] == {"p10": pytest.approx(120.0), "avg": 200.0, "p90": pytest.approx(280.0)}
    assert bench["Server latency"]["avg"] == 20.0
    assert bench["LCP"] == {"p10": None, "avg": None, "p90": None}


def test_benchmarks_metric_with_no_urls():
    assert all(v == {"p10": None, "avg": None, "p90": None} for v in benchmarks_metric({}).values())


@pytest.mark.parametrize(
    "label, expected",
    [
        ("critical", CRITICAL), ("High", HIGH), (" MODERATE ", MODERATE), ("advisory", ADVISORY), ("pass", PASS),
        ("n/a", NA), ("na", NA), ("whatever", NA), (None, NA), (5, NA),
    ],
)
def test_severity_color(label, expected):
    assert severity_color(label) == expected


@pytest.mark.parametrize(
    "value, expected",
    [(1, SCORE_GOOD), (0.9, SCORE_GOOD), (0.89, SCORE_MID), (0.5, SCORE_MID), (0.49, SCORE_BAD), (0, SCORE_BAD), (None, NA), ("0.9", NA)],
)
def test_score_color(value, expected):
    assert score_color(value) == expected


def test_style_table_applies_the_report_style():
    table = Table([["Head", "Value"], ["a", "1"], ["b", "2"]])

    styled = style_table(table, header_bg=colors.red)

    assert styled is table
    backgrounds = [cmd for cmd in table._bkgrndcmds if cmd[0] == "BACKGROUND"]
    assert backgrounds[0][1:] == (( 0, 0), (-1, 0), colors.red)
    assert any(cmd[0] == "ROWBACKGROUNDS" for cmd in table._bkgrndcmds)


def test_tint_color_moves_towards_white_and_clamps():
    base = colors.Color(0.2, 0.4, 0.6)

    assert _tint_color(base, 0) == base
    assert _tint_color(base, 1) == colors.Color(1, 1, 1)
    assert _tint_color(base, 5) == colors.Color(1, 1, 1)
    assert _tint_color(base, -3) == base
    half = _tint_color(base, 0.5)
    assert (half.red, half.green, half.blue) == pytest.approx((0.6, 0.7, 0.8))


def test_purple_palette():
    assert _purple_palette(0) == [PURPLE]
    assert _purple_palette(1) == [PURPLE]
    palette = _purple_palette(4)
    assert len(palette) == 4
    assert [c.red for c in palette] == sorted(c.red for c in palette)  # light shades get lighter


def chart_of(drawing, kind):
    return next(c for c in drawing.contents if isinstance(c, kind))


def test_bar_chart_plots_each_series():
    drawing = bar_chart(["A", "B"], [("x", [1, 2]), ("y", [3, None])], width=300, height=150)

    chart = chart_of(drawing, VerticalBarChart)
    assert (drawing.width, drawing.height) == (300, 150)
    assert chart.data == [[1.0, 2.0], [3.0, 0]]
    assert chart.categoryAxis.categoryNames == ["A", "B"]
    assert chart.valueAxis.valueMax == pytest.approx(3 * 1.15)


def test_bar_chart_with_all_zero_or_empty_data_still_has_an_axis():
    chart = chart_of(bar_chart(["A"], [("x", [0])]), VerticalBarChart)
    assert chart.valueAxis.valueMax == 0

    chart = chart_of(bar_chart([], []), VerticalBarChart)
    assert chart.valueAxis.valueMax == 1


def test_pie_chart_skips_empty_and_non_positive_parts():
    drawing = pie_chart([("Images", 10), ("None", None), ("Zero", 0), ("Neg", -5), ("Bad", "x"), ("Scripts", "30")])

    pie = chart_of(drawing, Pie)
    assert pie.data == [10.0, 30.0]
    assert pie.labels == ["Images", "Scripts"]


@pytest.mark.parametrize("parts", [[], [("a", None)], [("a", 0)]])
def test_pie_chart_without_values_is_an_empty_drawing(parts):
    assert pie_chart(parts).contents == []


# render_logo

class FakeCanvas:
    def __init__(self):
        self.calls = []

    def saveState(self):
        self.calls.append(("saveState",))

    def restoreState(self):
        self.calls.append(("restoreState",))

    def drawImage(self, *args, **kwargs):
        self.calls.append(("drawImage", args, kwargs))


def test_render_logo_fits_the_image_inside_the_box_keeping_its_ratio(tmp_path):
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), "purple").save(logo)
    canvas = FakeCanvas()

    render_logo(canvas, str(logo), 10, 20, 112, 62)

    (_, args, kwargs), = [c for c in canvas.calls if c[0] == "drawImage"]
    # box is 112x62 with 6pt padding: a 2:1 image is limited by height (50) so it is 100 wide
    assert kwargs["width"] == pytest.approx(100)
    assert kwargs["height"] == pytest.approx(50)
    assert args[1:] == (10 + 6, 20 + 6)
    assert canvas.calls[0] == ("saveState",) and canvas.calls[-1] == ("restoreState",)


@pytest.mark.parametrize("path", [None, "", "/does/not/exist.png"])
def test_render_logo_draws_nothing_without_a_logo(path):
    canvas = FakeCanvas()

    render_logo(canvas, path, 0, 0, 100, 50)

    assert [c[0] for c in canvas.calls] == ["saveState", "restoreState"]


def test_render_logo_ignores_an_unreadable_image(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    canvas = FakeCanvas()

    render_logo(canvas, str(bad), 0, 0, 100, 50)

    assert canvas.calls == [("saveState",), ("restoreState",)]


def test_the_real_logo_renders(tmp_path):
    canvas = FakeCanvas()

    render_logo(canvas, "app/assets/valvanta-digital-logo.png", 0, 0, 200, 90)

    assert any(c[0] == "drawImage" for c in canvas.calls)
