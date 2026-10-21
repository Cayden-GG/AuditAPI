import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.main as main
from app.database import create_audit, get_audit
from app.main import (
    _extract_report_paths,
    _normalize_categories,
    _parse_social_links,
    _safe_update_status,
    _send_paid_audit_callback,
    validateDomain,
)
from app.models import AuditStatus
from tests.builders import RecordingLogger
from tests.conftest import brevo_http_error


# _normalize_categories

@pytest.mark.parametrize(
    "value, include_accessibility, expected",
    [
        ("performance,seo", False, "performance,seo"),
        ("", False, "performance,seo"),
        (None, False, "performance,seo"),
        (" , ,", False, "performance,seo"),
        ("SEO, Performance", False, "seo,performance"),
        ("seo,seo,performance,SEO", False, "seo,performance"),
        ("performance", True, "performance,accessibility"),
        ("performance,accessibility", True, "performance,accessibility"),
        ("", True, "performance,seo,accessibility"),
    ],
)
def test_normalize_categories(value, include_accessibility, expected):
    assert _normalize_categories(value, include_accessibility=include_accessibility) == expected


# _parse_social_links

@pytest.mark.parametrize(
    "value, expected",
    [
        (None, []),
        ("", []),
        ([], []),
        ('["https://a.com", "https://b.com"]', ["https://a.com", "https://b.com"]),
        (["https://a.com", "", None, "https://b.com"], ["https://a.com", "https://b.com"]),
        ('["https://a.com", "", null]', ["https://a.com"]),
        ("not json", []),
        ('{"a": 1}', []),
        ('"just a string"', []),
        (42, []),
    ],
)
def test_parse_social_links(value, expected):
    assert _parse_social_links(value) == expected


# _extract_report_paths

def test_extract_report_paths_orders_known_reports_first():
    data = {"key_findings": "k.pdf", "extra": "x.pdf", "seo": "s.pdf", "performance": "p.pdf", "accessibility": "a.pdf"}
    stdout = f"some log line\nREPORT_PATHS::{json.dumps(data)}\n"

    assert _extract_report_paths(stdout) == [Path(p) for p in ("p.pdf", "s.pdf", "a.pdf", "k.pdf", "x.pdf")]


def test_extract_report_paths_handles_a_subset_of_reports():
    stdout = 'REPORT_PATHS::{"seo": "s.pdf", "performance": "p.pdf"}'

    assert _extract_report_paths(stdout) == [Path("p.pdf"), Path("s.pdf")]


@pytest.mark.parametrize("stdout", ["", "no report line here\nLOG_PATH::x", "REPORT_PATHS ::{}"])
def test_extract_report_paths_returns_nothing_without_the_marker(stdout):
    assert _extract_report_paths(stdout) == []


def test_extract_report_paths_empty_payload():
    assert _extract_report_paths("REPORT_PATHS::{}") == []


def test_extract_report_paths_uses_the_first_marker_line():
    stdout = 'REPORT_PATHS::{"seo": "first.pdf"}\nREPORT_PATHS::{"seo": "second.pdf"}'

    assert _extract_report_paths(stdout) == [Path("first.pdf")]


def test_extract_report_paths_raises_on_a_corrupt_payload():
    with pytest.raises(ValueError):
        _extract_report_paths("REPORT_PATHS::{not json")


# _safe_update_status

def test_safe_update_status_updates_the_audit(db):
    audit = create_audit(db, target_url="https://example.com/", client_email="a@example.com")

    _safe_update_status(db, audit.id, AuditStatus.PROCESSING, RecordingLogger())

    assert get_audit(db, audit.id).status == AuditStatus.PROCESSING


def test_safe_update_status_logs_instead_of_raising(db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db locked")

    monkeypatch.setattr(main, "update_audit_status", boom)
    logger = RecordingLogger()

    _safe_update_status(db, "id", AuditStatus.FAILED, logger)

    assert logger.messages("exception") == ["Failed to update audit status."]


# validateDomain

def test_validate_domain_reports_completed_audits(db):
    audit = create_audit(db, target_url="https://example.com/", client_email="a@example.com")

    assert validateDomain(db, "https://example.com/") is False

    from app.database import update_audit_status

    update_audit_status(db, audit.id, AuditStatus.COMPLETED)
    assert validateDomain(db, "https://example.com/") is True


# _send_paid_audit_callback

def paid_record(**overrides):
    fields = {"tier": "paid", "callback_url": "https://shop.example.com/hook", "order_id": "order-1"}
    return SimpleNamespace(**{**fields, **overrides})


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("VALVANTA_AUDIT_SECRET_KEY", "s3cret")


def test_callback_posts_the_status_with_the_secret(fake_brevo, secret):
    _send_paid_audit_callback(paid_record(), "completed", RecordingLogger())

    sent = fake_brevo.requests[0]
    assert sent.url == "https://shop.example.com/hook"
    assert sent.payload == {"orderId": "order-1", "status": "completed"}
    assert sent.headers["authorization"] == "s3cret"


@pytest.mark.parametrize("record", [None, SimpleNamespace(tier="free", callback_url="https://x.com", order_id="1")])
def test_callback_skips_free_and_missing_audits(fake_brevo, secret, record):
    _send_paid_audit_callback(record, "completed", RecordingLogger())

    assert fake_brevo.requests == []


@pytest.mark.parametrize("missing", ["callback_url", "order_id"])
def test_callback_skips_when_details_are_missing(fake_brevo, secret, missing):
    logger = RecordingLogger()

    _send_paid_audit_callback(paid_record(**{missing: None}), "completed", logger)

    assert fake_brevo.requests == []
    assert logger.messages("info") == ["Paid audit callback skipped; missing callback details."]


def test_callback_skips_without_the_secret(fake_brevo, monkeypatch):
    monkeypatch.delenv("VALVANTA_AUDIT_SECRET_KEY", raising=False)
    logger = RecordingLogger()

    _send_paid_audit_callback(paid_record(), "completed", logger)

    assert fake_brevo.requests == []
    assert "VALVANTA_AUDIT_SECRET_KEY is not set; skipping callback." in logger.messages("warning")


def test_callback_logs_error_statuses(fake_brevo, secret):
    fake_brevo.status = 500
    logger = RecordingLogger()

    _send_paid_audit_callback(paid_record(), "failed", logger)

    assert logger.messages("error") == ["Paid audit callback failed."]


def test_callback_logs_http_errors_instead_of_raising(fake_brevo, secret):
    fake_brevo.error = brevo_http_error(403, b"forbidden")
    logger = RecordingLogger()

    _send_paid_audit_callback(paid_record(), "failed", logger)

    assert logger.messages("exception") == ["Paid audit callback HTTP error."]


def test_callback_logs_network_errors_instead_of_raising(fake_brevo, secret):
    fake_brevo.error = urllib.error.URLError("no route")
    logger = RecordingLogger()

    _send_paid_audit_callback(paid_record(), "timeout", logger)

    assert logger.messages("exception") == ["Paid audit callback failed."]
