import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal, create_audit, update_audit_report_objects, update_audit_status
from app.main import app
from app.models import AuditStatus


def test_resend_requires_identifier():
    client = TestClient(app)
    response = client.post("/api/v1/audit/resend", json={})
    assert response.status_code == 400


def test_resend_email_by_job_id(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("GCS_SERVICE_ACCOUNT_JSON", str(tmp_path / "creds.json"))
    (tmp_path / "creds.json").write_text("{}", encoding="utf-8")

    db = SessionLocal()
    audit = create_audit(
        db,
        target_url="https://example.com",
        client_email="client@example.com",
        client_name="Acme Co",
    )
    update_audit_status(db, audit.id, AuditStatus.COMPLETED)
    update_audit_report_objects(
        db,
        audit.id,
        perf_report_object="audits/audit-123/Performance_PDF_1.pdf",
        seo_report_object="audits/audit-123/SEO_PDF_1.pdf",
        key_findings_object="audits/audit-123/Key_Findings_1.pdf",
        ai_json_object="audits/audit-123/ai_audit_summary.json",
    )
    db.close()

    def fake_download_objects(
        *,
        object_names,
        bucket_name,
        credentials_path,
        output_dir,
        logger=None,
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        mapping = {}
        for name in object_names:
            local_path = output_dir / Path(name).name
            if name.endswith(".json"):
                payload = {
                    "key_findings": [
                        {
                            "issue": "Test issue",
                            "priority": "High",
                            "impact": "Test impact",
                            "effort": "Low",
                            "explanation": "Test explanation",
                        }
                    ]
                }
                local_path.write_text(json.dumps(payload), encoding="utf-8")
            else:
                local_path.write_bytes(b"%PDF-1.4")
            mapping[name] = str(local_path)
        return mapping

    sent = {}

    def fake_send_audit_email(*, to_email, client_name, target_url, report_paths, subject=None, html_content=None):
        sent["to_email"] = to_email
        sent["client_name"] = client_name
        sent["target_url"] = target_url
        sent["report_count"] = len(report_paths)
        sent["subject"] = subject
        sent["html_content"] = html_content

    monkeypatch.setattr("app.main.download_objects", fake_download_objects)
    monkeypatch.setattr("app.main.send_audit_email", fake_send_audit_email)

    client = TestClient(app)
    response = client.post(
        "/api/v1/audit/resend",
        json={"job_id": audit.id, "to_email": "alt@example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resent_to"] == "alt@example.com"
    assert sent["to_email"] == "alt@example.com"
    assert sent["report_count"] == 3
    assert "audit" in (sent["subject"] or "").lower()

