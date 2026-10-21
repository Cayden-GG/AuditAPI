"""Builders for Lighthouse payloads shared across tests"""


def performance_audits():
    return {
        "first-contentful-paint": {"numericValue": 100},
        "largest-contentful-paint": {"numericValue": 200},
        "speed-index": {"numericValue": 300},
        "total-blocking-time": {"numericValue": 10},
        "mainthread-work-breakdown": {
            "numericValue": 5,
            "details": {"items": [{"group": "script", "duration": 1.0}]},
        },
        "diagnostics": {
            "details": {"items": [{"numRequests": 1, "numTasks": 2, "totalByteWeight": 3}]},
        },
        "network-requests": {
            "details": {"items": [{"statusCode": 200, "transferSize": 100}]},
        },
        "resource-summary": {
            "details": {
                "items": [
                    {"resourceType": "total", "transferSize": 1000},
                    {"resourceType": "image", "transferSize": 200},
                    {"resourceType": "script", "transferSize": 300},
                    {"resourceType": "stylesheet", "transferSize": 100},
                    {"resourceType": "document", "transferSize": 50},
                    {"resourceType": "third-party", "transferSize": 400},
                ]
            }
        },
        "network-server-latency": {
            "numericValue": 50,
            "details": {"items": [{"origin": "https://example.com", "serverResponseTime": 50}]},
        },
    }


def lighthouse_payload(categories="performance,seo", url="https://example.com", audits=None, cats=None):
    """A full lighthouse result with one successful url, the same data for mobile and desktop"""
    audits = performance_audits() if audits is None else audits
    cats = {} if cats is None else cats
    return {
        "meta": {"categories": categories},
        "lighthouse_data": {
            url: {
                "status": "success",
                "mobile": {"audits": audits, "categories": cats},
                "desktop": {"audits": audits, "categories": cats},
            }
        },
    }


def seo_audits(score=1, only=None, **overrides):
    """SEO audits for every SEO audit id, all with the same score. overrides maps audit id -> audit dict"""
    from app.audit_service.audit.audit_config import SEO_AUDIT_IDS

    audits = {
        audit_id: {"score": score, "displayValue": f"{audit_id} value", "numericValue": 1}
        for audit_id in (only or SEO_AUDIT_IDS)
    }
    audits.update(overrides)
    return audits


class RecordingLogger:
    """Stands in for AuditLogger. Entries are kept in .entries as (level, message, context)"""

    def __init__(self):
        self.entries = []

    def _record(self, level, message, **context):
        self.entries.append((level, message, context))

    def info(self, message, **context):
        self._record("info", message, **context)

    def warning(self, message, **context):
        self._record("warning", message, **context)

    def error(self, message, **context):
        self._record("error", message, **context)

    def exception(self, message, exc, **context):
        self._record("exception", message, **context)

    def messages(self, level):
        return [m for lvl, m, _ in self.entries if lvl == level]


def audit_insights(categories=("performance", "seo"), urls=("https://example.com/",)):
    """An AuditInsights model like the one the AI request returns"""
    from app.audit_service.ai.schema import AuditInsights

    summary = {
        "what_the_data_shows": "data",
        "key_strengths": "strengths",
        "primary_weaknesses": "weaknesses",
        "high_level_roadmap": "roadmap",
    }
    per_url = [
        {
            "url": url,
            "analysis": {
                "what_the_data_shows": "d",
                "key_strengths": "s",
                "primary_weaknesses": "w",
                "recommendations": "r",
            },
        }
        for url in urls
    ]
    return AuditInsights.model_validate(
        {
            "executive_summaries": {category: summary for category in categories},
            "prioritisation_method": "impact over effort",
            "key_findings": [
                {"issue": "Slow LCP", "priority": "High", "impact": "i", "effort": "Low", "explanation": "e"}
            ],
            "per_url_summaries": {category: per_url for category in categories},
        }
    )


# ---- PDF report data and text extraction

def story_text(story):
    """All the text in a list of platypus flowables (paragraphs, tables, keep-together blocks and section titles)"""
    from reportlab.platypus import KeepTogether, Paragraph, Table

    parts = []
    for item in story:
        if isinstance(item, Paragraph):
            parts.append(item.getPlainText())
        elif isinstance(item, Table):
            for row in item._cellvalues:
                for cell in row:
                    parts.append(story_text([cell]) if not isinstance(cell, str) else cell)
        elif isinstance(item, KeepTogether):
            parts.append(story_text(item._content))
        elif isinstance(item, str):
            parts.append(item)
        elif hasattr(item, "title") and isinstance(item.title, str):
            parts.append(item.title)
            if getattr(item, "subtitle", None):
                parts.append(item.subtitle)
        elif hasattr(item, "text") and isinstance(item.text, str):
            parts.append(item.text)
    return "\n".join(p for p in parts if p)


def audit_result(categories="performance,seo", urls=("https://example.com/", "https://example.com/about"), start="https://example.com"):
    """The audit dict the CLI builds (sitemap + lighthouse sections), made with the real formatter and normalizer"""
    from app.audit_service.audit.formatter import format_lighthouse_output
    from app.audit_service.audit.normalizer import normalize_lighthouse_results

    failing = {"robots-txt": {"score": 0, "title": "robots.txt is not valid", "description": "Fix robots."}}
    audits = {**performance_audits(), **seo_audits(**failing), "color-contrast": {"score": 0, "title": "Contrast"}}
    audits["largest-contentful-paint"] = {"numericValue": 5200}
    payload = lighthouse_payload(categories, url=urls[0], audits=audits)
    for url in urls[1:]:
        payload["lighthouse_data"][url] = payload["lighthouse_data"][urls[0]]
    payload["meta"].update({"tool": "lighthouse-automation", "run_at": "2026-01-02T03:04:05+00:00", "lighthouse_version": "12.0.0", "mode": "navigation", "devices": ["mobile", "desktop"], "config": {"only_categories": categories}})
    for entry in payload["lighthouse_data"].values():
        for platform in ("mobile", "desktop"):
            entry[platform]["categories"] = {
                "performance": {"score": 0.62},
                "seo": {"score": 0.91},
                "accessibility": {"score": 0.7},
            }

    formatted = format_lighthouse_output(payload)
    normalized = normalize_lighthouse_results(payload)
    meta = payload["meta"]
    return {
        "sitemap": {"start": start, "indexes": [], "sitemaps": [f"{start}/sitemap.xml"], "url_count": len(urls) + 3, "per_sitemap": [], "errors": [], "logs": []},
        "lighthouse": {
            "tested_url_count": len(urls),
            "tested_urls": list(urls),
            "run_at": meta["run_at"],
            "lighthouse_version": meta["lighthouse_version"],
            "categories": categories,
            "mode": meta["mode"],
            "devices": meta["devices"],
            "config": meta["config"],
            "website_performance_data": formatted["website"],
            "per_url_performance_data": formatted["per_url"],
            "normalized_findings": normalized["findings"],
            "summary": normalized["summary"],
        },
    }


def ai_result(categories=("performance", "seo"), urls=("https://example.com/", "https://example.com/about")):
    """The AI summary dict call_openai returns, with per url summaries reshaped to {category: {url: analysis}}"""
    insights = audit_insights(categories=categories, urls=urls).model_dump()
    insights["per_url_summaries"] = {
        category: {item["url"]: item["analysis"] for item in items}
        for category, items in insights["per_url_summaries"].items()
        if items
    }
    return {k: v for k, v in insights.items()}
