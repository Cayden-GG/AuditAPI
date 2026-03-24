from app.audit_service.audit.formatter import format_lighthouse_output
from app.audit_service.cli import _should_include_accessibility
from app.main import _normalize_categories


def _build_performance_audits():
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


def _build_lighthouse_payload(categories: str):
    audits = _build_performance_audits()
    return {
        "meta": {
            "categories": categories,
        },
        "lighthouse_data": {
            "https://example.com": {
                "status": "success",
                "mobile": {"audits": audits, "categories": {}},
                "desktop": {"audits": audits, "categories": {}},
            }
        },
    }


def test_formatter_excludes_accessibility_when_not_requested():
    payload = _build_lighthouse_payload("performance,seo")
    formatted = format_lighthouse_output(payload)

    assert "accessibility" not in formatted["website"]
    for entry in formatted["per_url"].values():
        assert "accessibility" not in entry


def test_formatter_includes_accessibility_when_requested():
    payload = _build_lighthouse_payload("performance,seo,accessibility")
    formatted = format_lighthouse_output(payload)

    assert "accessibility" in formatted["website"]
    for entry in formatted["per_url"].values():
        assert "accessibility" in entry


def test_cli_accessibility_flag_tracks_only_categories():
    assert _should_include_accessibility("performance,seo") is False
    assert _should_include_accessibility("performance,seo,accessibility") is True
    assert _should_include_accessibility("accessibility") is True


def test_paid_flow_normalizes_categories():
    assert _normalize_categories("performance,seo", include_accessibility=False) == "performance,seo"
    assert _normalize_categories("performance,seo", include_accessibility=True) == "performance,seo,accessibility"
