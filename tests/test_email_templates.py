from app.emails.templates.client_emails import (
    client_audit_failed,
    client_audit_results,
    client_confirmation,
)
from app.emails.templates.company_emails import (
    company_audit_completion,
    company_audit_failed,
)


def test_client_confirmation_basic():
    subject, html = client_confirmation("Acme Co", "https://example.com")
    assert "audit" in subject.lower()
    assert "Acme Co" in html
    assert "https://example.com" in html
    assert "Valvanta" in html


def test_client_results_includes_findings():
    audit_results = {
        "key_findings": [
            {
                "issue": "Large images",
                "priority": "High",
                "impact": "Slower load time",
                "effort": "Medium",
                "explanation": "Compress images.",
            }
        ]
    }

    subject, html = client_audit_results("Acme Co", "https://example.com", audit_results)

    assert "ready" in subject.lower()
    assert "Large images" in html
    assert "High" in html


def test_client_failed_mentions_sitemap_for_related_errors():
    subject, html = client_audit_failed(
        "Acme Co",
        "https://example.com",
        "Sitemap fetch failed for robots.txt disallow.",
    )

    assert "could not complete" in subject.lower()
    assert "sitemap" in html.lower() or "robots" in html.lower()


def test_client_failed_default_message_for_general_errors():
    _, html = client_audit_failed(
        "Acme Co",
        "https://example.com",
        "Unexpected timeout",
    )

    assert "investigating" in html.lower()


def test_company_completion_includes_gcs_details():
    subject, html = company_audit_completion(
        client_name="Acme Co",
        client_email="client@example.com",
        target_url="https://example.com",
        audit_id="audit-123",
        gcs_bucket="valvanta-audits",
        gcs_objects=["audits/audit-123/Performance_PDF_1.pdf"],
        report_paths=["audit_results/acme_audit/report.pdf"],
    )

    assert "delivered" in subject.lower()
    assert "valvanta-audits" in html
    assert "Performance_PDF_1.pdf" in html


def test_company_failed_includes_error_details():
    subject, html = company_audit_failed(
        client_name="Acme Co",
        target_url="https://example.com",
        audit_id="audit-123",
        error_message="Pipeline crashed",
    )

    assert "failed" in subject.lower()
    assert "Pipeline crashed" in html


def full_email_test():
    audit_results = {
        "key_findings": [
            {
                "issue": "Large images",
                "priority": "High",
                "impact": "Slower load time",
                "effort": "Medium",
                "explanation": "Compress images.",
            },
            {
                "issue": "Missing meta descriptions",
                "priority": "Medium",
                "impact": "Lower click-through rates",
                "effort": "Low",
                "explanation": "Add meta descriptions to top pages.",
            },
        ]
    }

    client_confirmation("Acme Co", "https://example.com")
    client_audit_results("Acme Co", "https://example.com", audit_results)
    client_audit_failed("Acme Co", "https://example.com", "Sitemap fetch failed.")
    company_audit_completion(
        client_name="Acme Co",
        client_email="client@example.com",
        target_url="https://example.com",
        audit_id="audit-123",
        gcs_bucket="valvanta-audits",
        gcs_objects=["audits/audit-123/Performance_PDF_1.pdf"],
        report_paths=["audit_results/acme_audit/report.pdf"],
    )
    company_audit_failed(
        client_name="Acme Co",
        client_email="client@example.com",
        target_url="https://example.com",
        audit_id="audit-123",
        error_message="Pipeline crashed",
    )


def test_full_email_test_runs():
    full_email_test()
    print("\nAll email templates generated successfully!")

