from typing import Any, List

from reportlab.platypus import Paragraph, Spacer

from ..styles import SectionRule, get_styles


def standards_alignment_section() -> List[Any]:
    styles = get_styles()
    story: List[Any] = []

    story.append(SectionRule("Standards Alignment Statement"))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report aligns findings to WCAG 2.1 Level A and AA (automated checks only), "
        "Google Core Web Vitals, and Google Search Essentials.", styles["Body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This audit reflects automated testing only and does not constitute full legal compliance certification.",
        styles["Body"]))
    return story
