import json

import pytest
from sqlalchemy import text

from app.audit_queue import service
from app.database import create_audit, get_audit, update_audit_report_objects, update_audit_status
from app.models import AuditStatus


@pytest.fixture(autouse=True)
def dispatcher_calls(monkeypatch):
    """The routes kick the dispatcher after queueing, which would start real audits in a thread"""
    calls = []
    monkeypatch.setattr("app.routes.audit.start_dispatcher", lambda launcher: calls.append(launcher))
    return calls


@pytest.fixture
def in_tmp_dir(tmp_path, monkeypatch):
    """Resend writes logs and downloads relative to the working directory"""
    monkeypatch.chdir(tmp_path)


FREE_PAYLOAD = {"url": "https://example.com", "email": "client@example.com", "client_name": "Acme"}

PAID_PAYLOAD = {
    "customerName": "Acme Co",
    "customerEmail": "client@example.com",
    "websiteUrl": "https://example.com",
    "socialLinks": ["https://x.com/acme"],
    "orderId": "order-1",
    "callbackUrl": "https://shop.example.com/hook",
}


def queue_row(isolated_db, job_token):
    with isolated_db.connect() as conn:
        return conn.execute(text("SELECT * FROM audit_jobs WHERE job_token = :t"), {"t": job_token}).mappings().one()


def make_audit(db, status=AuditStatus.COMPLETED, target_url="https://example.com", **objects):
    audit = create_audit(db, target_url=target_url, client_email="client@example.com", client_name="Acme")
    update_audit_status(db, audit.id, status)
    if objects:
        update_audit_report_objects(db, audit.id, **objects)
    return audit


# POST /api/v1/audit

def test_free_audit_is_accepted_and_queued(client, db, isolated_db, dispatcher_calls):
    response = client.post("/api/v1/audit", json=FREE_PAYLOAD)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "Accepted"
    assert "https://example.com" in body["message"]
    assert queue_row(isolated_db, body["job_token"])["status"] == "queued"
    assert get_audit(db, body["job_id"]).tier == "free"
    assert dispatcher_calls == [service.launch_job_in_thread]


@pytest.mark.parametrize(
    "payload",
    [
        {**FREE_PAYLOAD, "url": "not-a-url"},
        {**FREE_PAYLOAD, "email": "not-an-email"},
        {"url": "https://example.com"},
        {"email": "client@example.com"},
        {},
    ],
)
def test_free_audit_rejects_invalid_payloads(client, payload, dispatcher_calls):
    response = client.post("/api/v1/audit", json=payload)

    assert response.status_code == 422
    assert dispatcher_calls == []


def test_free_audit_rejects_a_second_active_job_for_the_customer(client):
    assert client.post("/api/v1/audit", json=FREE_PAYLOAD).status_code == 202

    response = client.post("/api/v1/audit", json={**FREE_PAYLOAD, "url": "https://other.example.com"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Customer already has an active job."


def test_free_audit_rejects_a_domain_that_was_already_audited(client, isolated_db):
    first = client.post("/api/v1/audit", json=FREE_PAYLOAD).json()
    job = service.dispatch_jobs()[0]
    service.mark_job_complete(job.job_id, "completed", None)

    response = client.post("/api/v1/audit", json={**FREE_PAYLOAD, "email": "another@example.com"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Free audit already completed for this domain."


def test_free_audit_returns_500_when_no_audit_record_was_created(client, monkeypatch, dispatcher_calls):
    monkeypatch.setattr("app.routes.audit.enqueue_job", lambda **kw: ("token", None))

    response = client.post("/api/v1/audit", json=FREE_PAYLOAD)

    assert response.status_code == 500
    assert dispatcher_calls == []


# POST /api/v1/paidAudit

def test_paid_audit_is_queued_and_confirmation_email_sent(client, db, isolated_db, fake_brevo, dispatcher_calls):
    response = client.post("/api/v1/paidAudit", json=PAID_PAYLOAD)

    assert response.status_code == 202
    body = response.json()
    assert queue_row(isolated_db, body["job_token"])["tier"] == "paid"

    audit = get_audit(db, body["job_id"])
    assert audit.tier == "paid"
    assert audit.order_id == "order-1"
    assert audit.callback_url == "https://shop.example.com/hook"
    assert json.loads(audit.social_links) == ["https://x.com/acme"]

    assert len(fake_brevo.requests) == 1
    assert fake_brevo.requests[0].payload["to"][0]["email"] == "client@example.com"
    assert dispatcher_calls == [service.launch_job_in_thread]


def test_paid_audit_still_accepted_when_the_confirmation_email_fails(client, fake_brevo, dispatcher_calls):
    fake_brevo.status = 500

    response = client.post("/api/v1/paidAudit", json=PAID_PAYLOAD)

    assert response.status_code == 202
    assert dispatcher_calls == [service.launch_job_in_thread]


@pytest.mark.parametrize(
    "change",
    [
        {"customerEmail": "bad"},
        {"websiteUrl": "nope"},
        {"callbackUrl": "nope"},
        {"socialLinks": ["a", "b", "c", "d"]},
        {"orderId": None},
    ],
)
def test_paid_audit_rejects_invalid_payloads(client, fake_brevo, change):
    response = client.post("/api/v1/paidAudit", json={**PAID_PAYLOAD, **change})

    assert response.status_code == 422
    assert fake_brevo.requests == []


def test_paid_audit_requires_every_mandatory_field(client, fake_brevo):
    for field in ("customerEmail", "websiteUrl", "socialLinks", "orderId", "callbackUrl"):
        payload = {k: v for k, v in PAID_PAYLOAD.items() if k != field}

        assert client.post("/api/v1/paidAudit", json=payload).status_code == 422, field


def test_paid_audit_rejects_a_second_active_paid_job_for_the_domain(client, fake_brevo):
    assert client.post("/api/v1/paidAudit", json=PAID_PAYLOAD).status_code == 202

    response = client.post("/api/v1/paidAudit", json={**PAID_PAYLOAD, "customerEmail": "other@example.com"})

    assert response.status_code == 400
    assert "Domain already has an active job" in response.json()["detail"]


# GET /api/v1/status/{identifier}

def test_status_for_a_queued_job_includes_the_estimated_wait(client, isolated_db):
    tokens = []
    for i in range(4):
        body = client.post(
            "/api/v1/audit", json={"url": f"https://site{i}.example.com", "email": f"u{i}@example.com"}
        ).json()
        tokens.append(body["job_token"])
        with isolated_db.begin() as conn:
            conn.execute(text("UPDATE audit_jobs SET queued_at = :q WHERE job_token = :t"), {"q": 1000 + i, "t": body["job_token"]})

    body = client.get(f"/api/v1/status/{tokens[3]}").json()

    # position 3 -> floor(3 * 10 / 1.5)
    assert body["status"] == "queued"
    assert body["estimated_wait_minutes"] == 20
    assert body["message"] == "Estimated wait: 20 minutes"
    assert body["job_token"] == tokens[3]


@pytest.mark.parametrize(
    "status, message",
    [
        ("running", "Auditing your site now"),
        ("completed", "Audit completed"),
        ("failed", "Audit failed"),
        ("timeout", "Audit timed out"),
    ],
)
def test_status_message_for_each_job_state(client, isolated_db, status, message):
    token = client.post("/api/v1/audit", json=FREE_PAYLOAD).json()["job_token"]
    with isolated_db.begin() as conn:
        conn.execute(
            text("UPDATE audit_jobs SET status = :s, result_path = 'out.pdf' WHERE job_token = :t"), {"s": status, "t": token}
        )

    body = client.get(f"/api/v1/status/{token}").json()

    assert body["status"] == status
    assert body["message"] == message
    assert body["estimated_wait_minutes"] is None
    assert body["result_path"] == "out.pdf"


def test_status_falls_back_to_the_audit_record_for_an_audit_id(client, db):
    audit = make_audit(db, status=AuditStatus.PROCESSING)

    response = client.get(f"/api/v1/status/{audit.id}")

    assert response.status_code == 200
    assert response.json()["id"] == audit.id
    assert response.json()["status"] == "processing"


def test_status_unknown_identifier_is_404(client):
    response = client.get("/api/v1/status/unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "Audit job not found"


# POST /api/v1/audit/resend (the happy path lives in test_resend_email.py)

@pytest.fixture
def gcs_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("GCS_SERVICE_ACCOUNT_JSON", str(tmp_path / "creds.json"))


def test_resend_requires_job_id_or_target_url(client):
    response = client.post("/api/v1/audit/resend", json={})

    assert response.status_code == 400


def test_resend_rejects_an_invalid_email(client):
    assert client.post("/api/v1/audit/resend", json={"job_id": "x", "to_email": "bad"}).status_code == 422


def test_resend_unknown_audit_is_404(client):
    assert client.post("/api/v1/audit/resend", json={"job_id": "missing"}).status_code == 404


@pytest.mark.parametrize("status", [AuditStatus.PENDING, AuditStatus.PROCESSING, AuditStatus.FAILED])
def test_resend_requires_a_completed_audit(client, db, status):
    audit = make_audit(db, status=status, perf_report_object="a/perf.pdf")

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 409
    assert response.json()["detail"] == "Audit is not completed."


def test_resend_requires_stored_report_objects(client, db):
    audit = make_audit(db)

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 409
    assert "No report objects" in response.json()["detail"]


def test_resend_needs_gcs_configuration(client, db, monkeypatch):
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    monkeypatch.delenv("GCS_SERVICE_ACCOUNT_JSON", raising=False)
    audit = make_audit(db, perf_report_object="a/perf.pdf")

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 500
    assert response.json()["detail"] == "GCS configuration is missing."


def test_resend_fails_when_nothing_could_be_downloaded(client, db, gcs_env, fake_gcs, in_tmp_dir):
    audit = make_audit(db, perf_report_object="a/perf.pdf")
    fake_gcs.download_result = {}

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to download reports from GCS."


def test_resend_fails_when_the_email_cannot_be_sent(client, db, gcs_env, fake_gcs, in_tmp_dir, monkeypatch):
    audit = make_audit(db, perf_report_object="a/perf.pdf")
    fake_gcs.download_result = {"a/perf.pdf": "perf.pdf"}

    def broken_send(**kwargs):
        raise RuntimeError("Brevo down")

    monkeypatch.setattr("app.routes.audit.send_audit_email", broken_send)

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to resend audit email."
    assert fake_gcs.uploads == []


def test_resend_defaults_to_the_audits_client_email(client, db, gcs_env, fake_gcs, in_tmp_dir, monkeypatch):
    audit = make_audit(db, perf_report_object="a/perf.pdf")
    fake_gcs.download_result = {"a/perf.pdf": "perf.pdf"}
    sent = {}
    monkeypatch.setattr("app.routes.audit.send_audit_email", lambda **kw: sent.update(kw))
    monkeypatch.setattr("app.routes.audit.run_full_cleanup", lambda: None)

    response = client.post("/api/v1/audit/resend", json={"job_id": audit.id})

    assert response.status_code == 200
    assert response.json()["resent_to"] == "client@example.com"
    assert sent["to_email"] == "client@example.com"


def test_resend_cleanup_failure_does_not_fail_the_request(client, db, gcs_env, fake_gcs, in_tmp_dir, monkeypatch):
    audit = make_audit(db, perf_report_object="a/perf.pdf")
    fake_gcs.download_result = {"a/perf.pdf": "perf.pdf"}
    monkeypatch.setattr("app.routes.audit.send_audit_email", lambda **kw: None)

    def broken_cleanup():
        raise OSError("disk")

    monkeypatch.setattr("app.routes.audit.run_full_cleanup", broken_cleanup)

    assert client.post("/api/v1/audit/resend", json={"job_id": audit.id}).status_code == 200


def test_resend_finds_the_latest_completed_audit_by_target_url(client, db, gcs_env, fake_gcs, in_tmp_dir, monkeypatch):
    # audits created through the API store the url as pydantic normalises it, with a trailing slash
    make_audit(db, target_url="https://example.com/", perf_report_object="a/perf.pdf")
    fake_gcs.download_result = {"a/perf.pdf": "perf.pdf"}
    monkeypatch.setattr("app.routes.audit.send_audit_email", lambda **kw: None)
    monkeypatch.setattr("app.routes.audit.run_full_cleanup", lambda: None)

    response = client.post("/api/v1/audit/resend", json={"target_url": "https://example.com"})

    assert response.status_code == 200
