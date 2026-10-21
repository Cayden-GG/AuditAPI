"""Checks the shared fixtures in conftest.py behave, so later tests can rely on them"""
import urllib.request
from types import SimpleNamespace

from app.database import SessionLocal, create_audit, get_audit
from app.models import AuditStatus


def test_isolated_db_does_not_touch_real_storage(isolated_db, tmp_path):
    assert str(isolated_db.url).startswith(f"sqlite:///{tmp_path}")

    session = SessionLocal()
    audit = create_audit(session, target_url="https://example.com", client_email="a@example.com", client_name="A")
    assert get_audit(session, audit.id).status == AuditStatus.PENDING
    session.close()


def test_db_fixture_starts_empty_each_test(db):
    assert get_audit(db, "does-not-exist") is None


def test_client_fixture_serves_requests_without_rate_limit(client):
    statuses = {client.get("/api/v1/status/nope").status_code for _ in range(50)}

    assert 429 not in statuses


def test_fake_brevo_records_requests_and_status(fake_brevo):
    req = urllib.request.Request("https://api.brevo.test/send", data=b'{"a": 1}', method="POST")

    with urllib.request.urlopen(req) as response:
        assert response.status == 201

    assert fake_brevo.requests[0].payload == {"a": 1}
    assert fake_brevo.requests[0].url == "https://api.brevo.test/send"


def test_fake_gcs_records_calls(fake_gcs):
    from app.routes import audit

    fake_gcs.download_result = {"x": "y"}

    assert audit.download_objects("bucket", ["a"]) == {"x": "y"}
    assert fake_gcs.downloads


def test_fake_openai_returns_parsed_and_can_raise(fake_openai):
    from app.audit_service.ai import request

    fake_openai.parsed = SimpleNamespace(value=1)
    response = request.client.chat.completions.parse(model="m")
    assert response.choices[0].message.parsed.value == 1

    fake_openai.error = RuntimeError("boom")
    try:
        request.client.chat.completions.parse(model="m")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the fake to raise")
