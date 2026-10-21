"""
AI text helpers
Cleans the AI summary text and builds the per url notes shared by the performance, SEO and accessibility sections
"""
import re
from typing import Any, Dict, Optional

# (key in the AI per url analysis, heading shown in the report)
AI_NOTE_SECTIONS = (
    ("what_the_data_shows", "What the data shows"),
    ("key_strengths", "Key strengths"),
    ("primary_weaknesses", "Primary weaknesses"),
    ("recommendations", "Recommendations"),
)

_LEADING_BREAKS = re.compile(r"^(?:\s|<br\s*/?>)+", re.IGNORECASE)


def strip_heading(value: str, heading: str) -> str:
    """Removes the heading the AI repeats at the start of a section's text, plain ("Key strengths:") or bold
    ("<b>Key strengths</b>"), returns empty string if value is not a string"""
    if not isinstance(value, str):
        return ""

    text = value.strip()
    bold = re.match(r"<b>\s*" + re.escape(heading) + r"\s*:?\s*</b>\s*:?", text, flags=re.IGNORECASE)
    if bold:
        return _LEADING_BREAKS.sub("", text[bold.end():])

    lowered = text.lower()
    heading_l = heading.lower()
    for prefix in (heading_l, f"- {heading_l}", f"• {heading_l}"):
        if lowered.startswith(prefix):
            return text[len(prefix):].lstrip(" :\n\r-")

    return value


def clean_ai_text(value: str) -> str:
    """Fixes doubled bullet markers ("- -") in AI text, returns empty string if value is not a string"""
    if not isinstance(value, str):
        return ""
    cleaned = value.replace("<br/>- -", "<br/>- ").replace("<br>- -", "<br/>- ")
    cleaned = cleaned.replace("\n- -", "\n- ").replace("\r\n- -", "\n- ")
    cleaned = cleaned.replace("- - ", "- ")
    return cleaned


def select_per_url_ai(ai: Dict[str, Any], report_type: str) -> Dict[str, Any]:
    """Gets the AI per url summaries for a report type, as a dict keyed by url, handles the older list and flat formats"""
    per_url_ai = (ai or {}).get("per_url_summaries") or {}
    if isinstance(per_url_ai, dict) and isinstance(per_url_ai.get(report_type), dict):
        return per_url_ai.get(report_type) or {}
    if isinstance(per_url_ai, dict) and any(k in per_url_ai for k in ("performance", "seo")):
        return {}
    if isinstance(per_url_ai, list):
        return {item.get("url"): item.get("analysis") for item in per_url_ai if isinstance(item, dict)}
    if isinstance(per_url_ai, dict):
        return per_url_ai
    return {}


def ai_note_text(note: Optional[Dict[str, Any]]) -> str:
    """
    Builds the text of one url's AI note: each non empty section under a single bold heading, whether or not
    the AI repeated the heading in its own text

    @Args:
        note (Optional[Dict[str, Any]]) -- AI analysis for the url

    @Returns:
        report paragraph text, empty if the note has no content (str)
    """
    if not isinstance(note, dict):
        return ""

    parts = []
    for key, heading in AI_NOTE_SECTIONS:
        body = clean_ai_text(strip_heading(note.get(key, ""), heading)).strip()
        if body:
            parts.append(f"<b>{heading}</b><br/>{body}")

    return "<br/><br/>".join(parts)
