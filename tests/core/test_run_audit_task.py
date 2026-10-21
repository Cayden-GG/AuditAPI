import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.main as main
from app.database import create_audit, get_audit
from app.main import run_audit_task
from app.models import AuditStatus


@pytest.fixture
def harness(db, monkeypatch, tmp_path, fake_brevo, fake_gcs):
    """Everything run_audit_task touches, faked.

    The audit subprocess is replaced by .subprocess: set .result to a CompletedProcess or an exception to raise,
    by default it writes the reports into the --output-dir it was given and prints their paths.
    Emails and the paid callback land in fake_brevo.requests, uploads in fake_gcs.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("GCS_SERVICE_ACCOUNT_JSON", str(tmp_path / "creds.json"))
    monkeypatch.setenv("VALVANTA_AUDIT_SECRET_KEY", "s3cret")

    state = SimpleNamespace(
        db=db,
        brevo=fake_brevo,
        gcs=fake_gcs,
        commands=[],
        run_kwargs=[],
        statuses_seen=[],
        result=None,
        write_reports=True,
        report_files=("Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "Key_Findings_1.pdf", "ai_audit_summary1.json", "audit_1.json"),
        cleanup_calls=0,
        cleanup_error=None,
        audit_id=None,
    )

    def option(cmd, name):
        return cmd[cmd.index(name) + 1]

    def run(cmd, **kwargs):
        state.commands.append(cmd)
        state.run_kwargs.append(kwargs)
        db.expire_all()
        state.statuses_seen.append(get_audit(db, option(cmd, "--audit-id")).status)

        if isinstance(state.result, BaseException):
            raise state.result
        if state.result is not None:
            return state.result

        output_dir = Path(option(cmd, "--output-dir"))
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in state.report_files:
            (output_dir / name).write_bytes(b"data")

        paths = {}
        if state.write_reports:
            paths = {
                "performance": str(output_dir / "Performance_PDF_1.pdf"),
                "seo": str(output_dir / "SEO_PDF_1.pdf"),
                "key_findings": str(output_dir / "Key_Findings_1.pdf"),
            }
            if "--only-categories" in cmd and "accessibility" in option(cmd, "--only-categories"):
                (output_dir / "Accessibility_PDF_1.pdf").write_bytes(b"data")
                paths["accessibility"] = str(output_dir / "Accessibility_PDF_1.pdf")
        stdout = f"working...\nREPORT_PATHS::{json.dumps(paths)}\n" if paths else "working...\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    def cleanup():
        state.cleanup_calls += 1
        if state.cleanup_error:
            raise state.cleanup_error

    monkeypatch.setattr(
        main,
        "subprocess",
        SimpleNamespace(
            run=run, TimeoutExpired=subprocess.TimeoutExpired, CalledProcessError=subprocess.CalledProcessError
        ),
    )
    monkeypatch.setattr(main, "run_full_cleanup", cleanup)

    def create(tier="free", **kwargs):
        defaults = dict(
            target_url="https://example.com/",
            client_email="client@example.com",
            client_name="Acme Co",
            tier=tier,
        )
        if tier == "paid":
            defaults.update(
                order_id="order-1",
                callback_url="https://shop.example.com/hook",
                social_links=["https://x.com/acme"],
            )
        audit = create_audit(db, **{**defaults, **kwargs})
        state.audit_id = audit.id
        return audit.id

    state.create = create
    state.run = lambda audit_id=None, **kwargs: run_audit_task(audit_id or state.audit_id, **kwargs)
    state.option = option
    state.audit = lambda: (db.expire_all(), get_audit(db, state.audit_id))[1]

    def emails():
        return [r for r in fake_brevo.requests if r.url == "https://api.brevo.com/v3/smtp/email"]

    def callbacks():
        return [r for r in fake_brevo.requests if r.url == "https://shop.example.com/hook"]

    state.emails = emails
    state.callbacks = callbacks
    return state


def recipients(requests):
    return [r.payload["to"][0]["email"] for r in requests]


# free audits

def test_free_audit_completes_and_returns_the_reports(harness):
    harness.create("free")

    result = harness.run()

    assert result["status"] == "completed"
    assert [p.name for p in result["report_paths"]] == ["Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "Key_Findings_1.pdf"]
    audit = harness.audit()
    assert audit.status == AuditStatus.COMPLETED
    assert audit.completed_at is not None


def test_the_audit_is_marked_processing_while_the_subprocess_runs(harness):
    harness.create("free")

    harness.run()

    assert harness.statuses_seen == [AuditStatus.PROCESSING]


def test_the_subprocess_gets_the_audit_details(harness):
    audit_id = harness.create("free")

    harness.run(max_urls=3, timeout_s=99)

    cmd = harness.commands[0]
    assert cmd[1:3] == ["-m", "app.audit_service.cli"]
    assert harness.option(cmd, "--client-name") == "Acme Co"
    assert harness.option(cmd, "--domain-url") == "https://example.com/"
    assert harness.option(cmd, "--audit-id") == audit_id
    assert harness.option(cmd, "--max-urls") == "3"
    assert harness.option(cmd, "--only-categories") == "performance,seo"
    assert harness.option(cmd, "--output-dir").startswith("audit_results/Acme_Co_audit_")
    assert harness.option(cmd, "--log-path").startswith(f"logs/audit_{audit_id}_")
    assert "--debug-mode" not in cmd
    assert harness.run_kwargs[0]["timeout"] == 99


def test_a_client_without_a_name_uses_a_default_folder_name(harness):
    harness.create("free", client_name=None)

    harness.run()

    assert harness.option(harness.commands[0], "--client-name") == "client"


def test_free_audit_emails_the_client_with_reports_and_the_company_without(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.create("free")

    harness.run()

    client_email, company_email = harness.emails()
    assert recipients(harness.emails()) == ["client@example.com", "company@example.com"]
    assert [a["name"] for a in client_email.payload["attachment"]] == [
        "Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "Key_Findings_1.pdf",
    ]
    assert "attachment" not in company_email.payload


def test_free_audit_does_not_call_back(harness):
    harness.create("free")

    harness.run()

    assert harness.callbacks() == []


def test_reports_are_uploaded_to_gcs_and_stored_on_the_audit(harness):
    audit_id = harness.create("free")

    harness.run()

    (_, upload), = harness.gcs.uploads
    assert upload["prefix"] == f"audits/free/{audit_id}"
    assert upload["bucket_name"] == "test-bucket"
    assert sorted(Path(p).name for p in upload["file_paths"]) == [
        "Key_Findings_1.pdf", "Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "ai_audit_summary1.json", "audit_1.json",
        "audit_log.jsonl",
    ]

    audit = harness.audit()
    prefix = f"audits/free/{audit_id}"
    assert audit.perf_report_object == f"{prefix}/Performance_PDF_1.pdf"
    assert audit.seo_report_object == f"{prefix}/SEO_PDF_1.pdf"
    assert audit.key_findings_object == f"{prefix}/Key_Findings_1.pdf"
    assert audit.ai_json_object == f"{prefix}/ai_audit_summary1.json"
    assert audit.audit_json_object == f"{prefix}/audit_1.json"
    assert audit.audit_log_object == f"{prefix}/audit_log.jsonl"


def test_local_files_are_cleaned_up_after_a_successful_audit(harness):
    harness.create("free")

    harness.run()

    assert harness.cleanup_calls == 1


def test_a_cleanup_failure_does_not_fail_the_audit(harness):
    harness.cleanup_error = OSError("disk")
    harness.create("free")

    assert harness.run()["status"] == "completed"
    assert harness.audit().status == AuditStatus.COMPLETED


# paid audits

def test_paid_audit_always_includes_accessibility(harness):
    harness.create("paid")

    result = harness.run(only_categories="performance", tier="paid")

    assert harness.option(harness.commands[0], "--only-categories") == "performance,accessibility"
    assert "Accessibility_PDF_1.pdf" in [p.name for p in result["report_paths"]]
    assert harness.audit().accessibility_report_object.endswith("Accessibility_PDF_1.pdf")


def test_paid_audit_uploads_under_the_paid_prefix(harness):
    audit_id = harness.create("paid")

    harness.run(tier="paid")

    assert harness.gcs.uploads[0][1]["prefix"] == f"audits/paid/{audit_id}"


def test_paid_audit_skips_the_client_results_email_and_sends_everything_to_the_company(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.create("paid")

    harness.run(tier="paid")

    (company_email,) = harness.emails()
    assert recipients([company_email]) == ["company@example.com"]
    assert len(company_email.payload["attachment"]) == 4
    assert "https://x.com/acme" in company_email.payload["htmlContent"]


def test_paid_audit_notifies_the_callback_url_when_completed(harness):
    harness.create("paid")

    harness.run(tier="paid")

    (callback,) = harness.callbacks()
    assert callback.payload == {"orderId": "order-1", "status": "completed"}
    assert callback.headers["authorization"] == "s3cret"


# debug mode and configuration

def test_debug_mode_is_passed_on_and_skips_the_gcs_upload(harness):
    harness.create("free", debug_mode=True)

    harness.run()

    assert "--debug-mode" in harness.commands[0]
    assert harness.gcs.uploads == []
    assert harness.audit().perf_report_object is None


def test_missing_gcs_credentials_skip_the_upload_but_still_complete(harness, monkeypatch):
    monkeypatch.delenv("GCS_SERVICE_ACCOUNT_JSON")
    harness.create("free")

    result = harness.run()

    assert result["status"] == "completed"
    assert harness.gcs.uploads == []
    assert harness.audit().seo_report_object is None


def test_a_failing_gcs_upload_does_not_fail_the_audit(harness, monkeypatch):
    def broken_upload(**kwargs):
        raise RuntimeError("bucket gone")

    monkeypatch.setattr(main, "upload_files", broken_upload)
    harness.create("free")

    assert harness.run()["status"] == "completed"


def test_nothing_is_stored_when_the_upload_returns_no_objects(harness, monkeypatch):
    monkeypatch.setattr(main, "upload_files", lambda **kwargs: {})
    harness.create("free")

    harness.run()

    assert harness.audit().perf_report_object is None


def test_the_company_email_is_skipped_without_a_company_address(harness, monkeypatch):
    monkeypatch.delenv("BREVO_COMPANY_EMAIL", raising=False)
    harness.create("free")

    harness.run()

    assert recipients(harness.emails()) == ["client@example.com"]


def test_email_failures_do_not_fail_the_audit(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.brevo.status = 500
    harness.create("free")

    result = harness.run()

    assert result["status"] == "completed"
    assert harness.audit().status == AuditStatus.COMPLETED
    assert len(harness.emails()) == 2


# finding the reports

def test_reports_are_found_on_disk_when_the_subprocess_prints_no_paths(harness):
    harness.write_reports = False
    harness.create("free", client_name="Acme")

    result = harness.run()

    assert result["status"] == "completed"
    assert [p.name for p in result["report_paths"]] == ["Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "Key_Findings_1.pdf"]


def test_reports_are_found_on_disk_for_a_client_name_with_spaces(harness):
    harness.write_reports = False
    harness.create("free", client_name="Acme Co")

    result = harness.run()

    assert [p.name for p in result["report_paths"]] == ["Performance_PDF_1.pdf", "SEO_PDF_1.pdf", "Key_Findings_1.pdf"]


@pytest.mark.parametrize("name", ["../evil", "a/../../evil"])
def test_output_stays_inside_audit_results_whatever_the_client_name(harness, name):
    harness.create("free", client_name=name)

    harness.run()

    output_dir = Path(harness.option(harness.commands[0], "--output-dir")).resolve()
    assert output_dir.is_relative_to(Path("audit_results").resolve())


def test_the_audit_still_completes_when_no_reports_can_be_found(harness):
    harness.report_files = ()
    harness.write_reports = False
    harness.create("free")

    result = harness.run()

    assert result["status"] == "completed"
    assert result["report_paths"] == []
    assert "attachment" not in harness.emails()[0].payload


# failures

def test_a_timeout_fails_the_audit_and_emails_the_client_and_company_once(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.result = subprocess.TimeoutExpired(cmd="audit", timeout=5)
    harness.create("free")

    result = harness.run()

    assert result == {"status": "timeout", "report_paths": []}
    assert harness.audit().status == AuditStatus.FAILED
    assert recipients(harness.emails()) == ["client@example.com", "company@example.com"]
    assert "Audit timed out." in harness.emails()[1].payload["htmlContent"]
    assert harness.cleanup_calls == 0


def test_a_failed_subprocess_fails_the_audit_with_its_error_in_the_company_email(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.result = subprocess.CalledProcessError(1, "audit", output="", stderr="lighthouse exploded")
    harness.create("free")

    result = harness.run()

    assert result == {"status": "failed", "report_paths": []}
    assert harness.audit().status == AuditStatus.FAILED
    assert harness.gcs.uploads == []
    assert "lighthouse exploded" in harness.emails()[1].payload["htmlContent"]


def test_a_failed_subprocess_falls_back_to_stdout_then_a_generic_message(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.result = subprocess.CalledProcessError(1, "audit", output="from stdout", stderr="")
    harness.create("free")
    harness.run()
    assert "from stdout" in harness.emails()[1].payload["htmlContent"]

    harness.brevo.requests.clear()
    harness.result = subprocess.CalledProcessError(1, "audit", output="", stderr="")
    harness.create("free", target_url="https://other.example.com/", client_email="other@example.com")
    harness.run()
    assert "Audit subprocess failed." in harness.emails()[1].payload["htmlContent"]


@pytest.mark.parametrize(
    "error, expected",
    [
        (subprocess.TimeoutExpired(cmd="audit", timeout=5), "timeout"),
        (subprocess.CalledProcessError(1, "audit", stderr="boom"), "failed"),
    ],
)
def test_paid_failures_notify_the_callback(harness, error, expected):
    harness.result = error
    harness.create("paid")

    harness.run(tier="paid")

    assert [c.payload for c in harness.callbacks()] == [{"orderId": "order-1", "status": expected}]


def test_free_failures_do_not_call_back(harness):
    harness.result = subprocess.CalledProcessError(1, "audit", stderr="boom")
    harness.create("free")

    harness.run()

    assert harness.callbacks() == []


def test_failure_emails_are_skipped_for_the_company_without_an_address(harness, monkeypatch):
    monkeypatch.delenv("BREVO_COMPANY_EMAIL", raising=False)
    harness.result = subprocess.CalledProcessError(1, "audit", stderr="boom")
    harness.create("free")

    harness.run()

    assert recipients(harness.emails()) == ["client@example.com"]


def test_failure_emails_that_cannot_be_sent_do_not_raise(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.brevo.status = 500
    harness.result = subprocess.CalledProcessError(1, "audit", stderr="boom")
    harness.create("free")

    assert harness.run()["status"] == "failed"


def test_an_unknown_audit_fails_without_crashing_or_emailing(harness):
    result = run_audit_task("does-not-exist")

    assert result == {"status": "failed", "report_paths": []}
    assert harness.emails() == []
    assert harness.commands == []


def test_an_unexpected_error_fails_the_audit_and_notifies(harness, monkeypatch):
    def broken(stdout):
        raise ValueError("corrupt REPORT_PATHS")

    monkeypatch.setattr(main, "_extract_report_paths", broken)
    harness.create("paid")

    result = harness.run(tier="paid")

    assert result["status"] == "failed"
    assert harness.audit().status == AuditStatus.FAILED
    assert "corrupt REPORT_PATHS" in " ".join(r.payload["htmlContent"] for r in harness.emails())
    assert [c.payload["status"] for c in harness.callbacks()] == ["failed"]


def test_failure_emails_are_only_sent_once_per_run(harness, monkeypatch):
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    harness.result = subprocess.TimeoutExpired(cmd="audit", timeout=5)
    harness.create("free")

    harness.run()

    assert len(harness.emails()) == 2
