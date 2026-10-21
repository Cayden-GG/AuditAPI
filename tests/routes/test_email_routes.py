import base64

import pytest

from tests.conftest import brevo_http_error

PAYLOAD = {
    "to_email": "to@example.com",
    "send_email": "from@example.com",
    "subject_line": "Hello",
    "html_content": "<p>Hello</p>",
}


def test_send_email_sends_through_brevo(client, fake_brevo):
    response = client.post("/api/sendEmail", json=PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message": "Email sent.", "sent_to": "to@example.com"}

    sent = fake_brevo.requests[0].payload
    assert sent["sender"]["email"] == "from@example.com"
    assert sent["to"] == [{"email": "to@example.com"}]
    assert sent["subject"] == "Hello"
    assert sent["htmlContent"] == "<p>Hello</p>"
    assert "attachment" not in sent


def test_send_email_attaches_the_listed_files(client, fake_brevo, tmp_path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    response = client.post("/api/sendEmail", json={**PAYLOAD, "attachments": f"{first}, {second}"})

    assert response.status_code == 200
    attachments = fake_brevo.requests[0].payload["attachment"]
    assert [a["name"] for a in attachments] == ["a.pdf", "b.pdf"]
    assert attachments[0]["content"] == base64.b64encode(b"one").decode()


def test_send_email_rejects_a_missing_attachment(client, fake_brevo, tmp_path):
    response = client.post("/api/sendEmail", json={**PAYLOAD, "attachments": str(tmp_path / "nope.pdf")})

    assert response.status_code == 400
    assert "Attachment not found" in response.json()["detail"]
    assert fake_brevo.requests == []


def test_send_email_requires_html_content(client, fake_brevo):
    response = client.post("/api/sendEmail", json={**PAYLOAD, "html_content": ""})

    assert response.status_code == 400
    assert fake_brevo.requests == []


@pytest.mark.parametrize("field", ["to_email", "send_email", "subject_line", "html_content"])
def test_send_email_requires_every_field(client, fake_brevo, field):
    payload = {k: v for k, v in PAYLOAD.items() if k != field}

    assert client.post("/api/sendEmail", json=payload).status_code == 422


@pytest.mark.parametrize("field", ["to_email", "send_email"])
def test_send_email_rejects_invalid_addresses(client, fake_brevo, field):
    assert client.post("/api/sendEmail", json={**PAYLOAD, field: "nope"}).status_code == 422


def test_send_email_failure_is_a_500_with_the_reason(client, fake_brevo):
    fake_brevo.error = brevo_http_error(401, b"invalid key")

    response = client.post("/api/sendEmail", json=PAYLOAD)

    assert response.status_code == 500
    assert "invalid key" in response.json()["detail"]


def test_send_email_reports_missing_brevo_configuration(client, fake_brevo, monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY")

    response = client.post("/api/sendEmail", json=PAYLOAD)

    assert response.status_code == 500
    assert "BREVO_API_KEY" in response.json()["detail"]


def test_send_email_ignores_blank_attachment_entries(client, fake_brevo, tmp_path):
    report = tmp_path / "a.pdf"
    report.write_bytes(b"one")

    response = client.post("/api/sendEmail", json={**PAYLOAD, "attachments": f"{report},"})

    assert response.status_code == 200
    assert len(fake_brevo.requests[0].payload["attachment"]) == 1
