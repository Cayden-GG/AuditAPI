from typing import Any, List

from reportlab.platypus import Paragraph, Spacer

from ..styles import get_styles


def limitations_section() -> List[Any]:
    styles = get_styles()
    story: List[Any] = []

    story.append(Paragraph("Limitations & Scope Disclaimer", styles["H1"]))
    story.append(Paragraph(
        "This report is based on automated Lighthouse checks and reflects a point-in-time snapshot. "
        "It does not replace manual testing, user research, or full compliance reviews.", styles["Body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Findings should be validated in real user conditions and with assistive technologies where applicable.",
        styles["Body"]))
    return story
