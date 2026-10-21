import base64
import os

import pytest

from app.emails.brevo_email import (
    BREVO_API_URL,
    _build_attachments,
    normalize_client_name,
    collect_report_paths,
    find_latest_report_dir,
    send_audit_email,
    send_generic_email,
)
from tests.conftest import brevo_http_error


# report discovery

def make_dir(base, name, files=(), mtime=None):
    folder = base / name
    folder.mkdir()
    for file in files:
        (folder / file).write_bytes(b"%PDF")
    if mtime is not None:
        os.utime(folder, (mtime, mtime))
    return folder


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Acme Co", "Acme_Co"),
        ("  Acme  ", "Acme"),
        ("Acme", "Acme"),
        ("", None),
        ("   ", None),
        (None, None),
        ("Café Münch", "Café_Münch"),
        ("Acme-Co_2", "Acme-Co_2"),
        ("../evil", "___evil"),
        ("a/../../evil", "a_______evil"),
        ("a\\b:c*d", "a_b_c_d"),
        ("Acme & Sons, Ltd.", "Acme___Sons__Ltd_"),
    ],
)
def testnormalize_client_name(name, expected):
    assert normalize_client_name(name) == expected


def test_find_latest_report_dir_returns_the_newest_directory_with_pdfs(tmp_path):
    make_dir(tmp_path, "old", ["a.pdf"], mtime=1000)
    new = make_dir(tmp_path, "new", ["a.pdf"], mtime=2000)

    assert find_latest_report_dir(tmp_path) == new


def test_find_latest_report_dir_skips_newer_directories_without_pdfs(tmp_path):
    good = make_dir(tmp_path, "good", ["a.pdf"], mtime=1000)
    make_dir(tmp_path, "empty", ["notes.txt"], mtime=2000)

    assert find_latest_report_dir(tmp_path) == good


def test_find_latest_report_dir_filters_by_client_name(tmp_path):
    make_dir(tmp_path, "Other_audit_1", ["a.pdf"], mtime=3000)
    acme = make_dir(tmp_path, "Acme_Co_audit_1", ["a.pdf"], mtime=1000)

    assert find_latest_report_dir(tmp_path, "Acme Co") == acme


def test_find_latest_report_dir_ignores_plain_files(tmp_path):
    (tmp_path / "stray.pdf").write_bytes(b"%PDF")
    good = make_dir(tmp_path, "good", ["a.pdf"])

    assert find_latest_report_dir(tmp_path) == good


@pytest.mark.parametrize(
    "setup, message",
    [
        (lambda p: None, "No audit result directories"),
        (lambda p: make_dir(p, "Acme_audit_1"), "No PDF reports"),
        (lambda p: make_dir(p, "Other_audit_1", ["a.pdf"]), "No audit result directories"),
    ],
)
def test_find_latest_report_dir_errors(tmp_path, setup, message):
    setup(tmp_path)

    with pytest.raises(FileNotFoundError, match=message):
        find_latest_report_dir(tmp_path, "Acme")


def test_find_latest_report_dir_missing_base_dir(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        find_latest_report_dir(tmp_path / "missing")


def test_collect_report_paths_orders_known_reports_first(tmp_path):
    names = ["Zebra.pdf", "Key_Findings_1.pdf", "SEO_PDF_1.pdf", "Alpha.pdf", "Performance_PDF_1.pdf"]
    folder = make_dir(tmp_path, "audit", names)

    assert [p.name for p in collect_report_paths(folder)] == [
        "Performance_PDF_1.pdf",
        "SEO_PDF_1.pdf",
        "Key_Findings_1.pdf",
        "Alpha.pdf",
        "Zebra.pdf",
    ]


def test_collect_report_paths_ignores_non_pdfs_and_errors_when_empty(tmp_path):
    folder = make_dir(tmp_path, "audit", ["notes.txt"])

    with pytest.raises(FileNotFoundError):
        collect_report_paths(folder)


def test_build_attachments_base64_encodes_each_file(tmp_path):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    attachments = _build_attachments([first, second])

    assert attachments == [
        {"content": base64.b64encode(b"one").decode(), "name": "a.pdf"},
        {"content": base64.b64encode(b"two").decode(), "name": "b.pdf"},
    ]


# send_audit_email

def test_send_audit_email_sends_the_expected_request(fake_brevo, tmp_path):
    report = tmp_path / "report.pdf"
    report.write_bytes(b"pdf-bytes")

    send_audit_email(
        to_email="client@example.com",
        client_name="Acme",
        target_url="https://example.com",
        report_paths=[report],
        subject="Subject",
        html_content="<p>Body</p>",
    )

    sent = fake_brevo.requests[0]
    assert sent.url == BREVO_API_URL
    assert sent.payload == {
        "sender": {"name": "Test Sender", "email": "sender@example.com"},
        "to": [{"email": "client@example.com", "name": "Acme"}],
        "subject": "Subject",
        "htmlContent": "<p>Body</p>",
        "attachment": [{"content": base64.b64encode(b"pdf-bytes").decode(), "name": "report.pdf"}],
    }


def test_send_audit_email_defaults(fake_brevo, monkeypatch):
    monkeypatch.delenv("BREVO_SENDER_NAME")

    send_audit_email(to_email="client@example.com", client_name=None, target_url="https://example.com")

    payload = fake_brevo.requests[0].payload
    assert payload["sender"]["name"] == "Valvanta Digital"
    assert payload["to"] == [{"email": "client@example.com", "name": "client@example.com"}]
    assert payload["subject"] == "Your website audit report for https://example.com"
    assert "https://example.com" in payload["htmlContent"]
    assert "attachment" not in payload


def test_send_audit_email_subject_uses_the_client_name_when_known(fake_brevo):
    send_audit_email(to_email="c@example.com", client_name="Acme", target_url="https://example.com")

    assert fake_brevo.requests[0].payload["subject"] == "Your website audit report for Acme"


@pytest.mark.parametrize("missing", ["BREVO_API_KEY", "BREVO_SENDER_EMAIL"])
def test_send_audit_email_requires_brevo_configuration(fake_brevo, monkeypatch, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(ValueError, match=missing):
        send_audit_email(to_email="c@example.com", client_name=None, target_url="https://example.com")

    assert fake_brevo.requests == []


def test_send_audit_email_raises_on_an_error_status(fake_brevo):
    fake_brevo.status = 500

    with pytest.raises(RuntimeError, match="status 500"):
        send_audit_email(to_email="c@example.com", client_name=None, target_url="https://example.com")


def test_send_audit_email_raises_with_the_brevo_error_detail(fake_brevo):
    fake_brevo.error = brevo_http_error(400, b"sender not verified")

    with pytest.raises(RuntimeError, match="sender not verified"):
        send_audit_email(to_email="c@example.com", client_name=None, target_url="https://example.com")


# send_generic_email

def test_send_generic_email_uses_the_given_sender(fake_brevo):
    send_generic_email(
        to_email="to@example.com",
        sender_email="custom@example.com",
        subject="Hi",
        html_content="<p>Hi</p>",
        sender_name="Custom",
    )

    assert fake_brevo.requests[0].payload == {
        "sender": {"name": "Custom", "email": "custom@example.com"},
        "to": [{"email": "to@example.com"}],
        "subject": "Hi",
        "htmlContent": "<p>Hi</p>",
    }


def test_send_generic_email_falls_back_to_the_configured_sender(fake_brevo):
    send_generic_email(to_email="to@example.com", sender_email=None, subject="Hi", html_content="x")

    assert fake_brevo.requests[0].payload["sender"] == {"name": "Test Sender", "email": "sender@example.com"}


def test_send_generic_email_attaches_files(fake_brevo, tmp_path):
    report = tmp_path / "r.pdf"
    report.write_bytes(b"abc")

    send_generic_email(to_email="to@example.com", sender_email=None, subject="Hi", html_content="x", attachments=[report])

    assert fake_brevo.requests[0].payload["attachment"][0]["name"] == "r.pdf"


@pytest.mark.parametrize("missing", ["BREVO_API_KEY", "BREVO_SENDER_EMAIL"])
def test_send_generic_email_requires_brevo_configuration(fake_brevo, monkeypatch, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(ValueError, match=missing):
        send_generic_email(to_email="to@example.com", sender_email=None, subject="Hi", html_content="x")


def test_send_generic_email_a_given_sender_does_not_need_the_default(fake_brevo, monkeypatch):
    monkeypatch.delenv("BREVO_SENDER_EMAIL")

    send_generic_email(to_email="to@example.com", sender_email="custom@example.com", subject="Hi", html_content="x")

    assert len(fake_brevo.requests) == 1


def test_send_generic_email_raises_on_errors(fake_brevo):
    fake_brevo.status = 400
    with pytest.raises(RuntimeError, match="status 400"):
        send_generic_email(to_email="to@example.com", sender_email=None, subject="Hi", html_content="x")

    fake_brevo.status = 201
    fake_brevo.error = brevo_http_error(401, b"invalid key")
    with pytest.raises(RuntimeError, match="invalid key"):
        send_generic_email(to_email="to@example.com", sender_email=None, subject="Hi", html_content="x")
