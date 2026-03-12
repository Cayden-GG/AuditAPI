from __future__ import annotations

import argparse
from typing import Optional

from .brevo_email import (
    build_client_audit_failed_email,
    build_client_audit_results_email,
    build_client_confirmation_email,
    build_company_audit_completion_email,
    build_company_audit_failed_email,
    send_audit_email,
)


def _send_one(
    *,
    to_email: str,
    target_url: str,
    client_name: Optional[str],
    subject_prefix: str,
    subject: str,
    html_content: str,
) -> None:
    send_audit_email(
        to_email=to_email,
        client_name=client_name,
        target_url=target_url,
        report_paths=[],
        subject=f"{subject_prefix} {subject}".strip(),
        html_content=html_content,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send test email templates via Brevo.")
    parser.add_argument("--to-email", required=True, help="Recipient address for test emails.")
    parser.add_argument("--client-name", default="Acme Co", help="Client name for template data.")
    parser.add_argument("--target-url", default="https://example.com", help="Target URL for template data.")
    parser.add_argument("--subject-prefix", default="[TEST]", help="Prefix for email subjects.")

    args = parser.parse_args()

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

    subject, html_content = build_client_confirmation_email(args.client_name, args.target_url)
    _send_one(
        to_email=args.to_email,
        target_url=args.target_url,
        client_name=args.client_name,
        subject_prefix=args.subject_prefix,
        subject=subject,
        html_content=html_content,
    )

    subject, html_content = build_client_audit_results_email(
        args.client_name, args.target_url, audit_results
    )
    _send_one(
        to_email=args.to_email,
        target_url=args.target_url,
        client_name=args.client_name,
        subject_prefix=args.subject_prefix,
        subject=subject,
        html_content=html_content,
    )

    subject, html_content = build_client_audit_failed_email(
        args.client_name, args.target_url, "Sitemap fetch failed."
    )
    _send_one(
        to_email=args.to_email,
        target_url=args.target_url,
        client_name=args.client_name,
        subject_prefix=args.subject_prefix,
        subject=subject,
        html_content=html_content,
    )

    subject, html_content = build_company_audit_completion_email(
        client_name=args.client_name,
        client_email=args.to_email,
        target_url=args.target_url,
        audit_id="audit-123",
        gcs_bucket="valvanta-audits",
        gcs_objects=["audits/audit-123/Performance_PDF_1.pdf"],
        report_paths=["audit_results/acme_audit/report.pdf"],
    )
    _send_one(
        to_email=args.to_email,
        target_url=args.target_url,
        client_name="Valvanta Digital",
        subject_prefix=args.subject_prefix,
        subject=subject,
        html_content=html_content,
    )

    subject, html_content = build_company_audit_failed_email(
        client_name=args.client_name,
        client_email=args.to_email,
        target_url=args.target_url,
        audit_id="audit-123",
        error_message="Pipeline crashed",
    )
    _send_one(
        to_email=args.to_email,
        target_url=args.target_url,
        client_name="Valvanta Digital",
        subject_prefix=args.subject_prefix,
        subject=subject,
        html_content=html_content,
    )


if __name__ == "__main__":
    main()
