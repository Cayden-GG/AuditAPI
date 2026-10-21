from app.audit_service.audit.formatter import format_lighthouse_output
from app.audit_service.cli import _should_include_accessibility
from app.main import _normalize_categories
from tests.builders import lighthouse_payload


def _build_lighthouse_payload(categories: str):
    return lighthouse_payload(categories)


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
