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
