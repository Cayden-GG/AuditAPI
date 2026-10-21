"""
Company email templates
Internal emails sent to the company: audit completed and audit failed
"""
from __future__ import annotations

import html
from typing import Iterable, Optional, Tuple


def _email_shell(title: str, preheader: str, content_html: str) -> str:
    """Wraps content in the internal notification email layout with a header, footer and hidden preheader

    @Args:
        title (str) -- heading shown above the content
        preheader (str) -- hidden preview text
        content_html (str) -- email body html

    @Returns:
        complete email html (str)
    """
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2d3748; max-width: 700px; margin: 0 auto; padding: 20px; background: #f7fafc;">
  <span style="display:none; visibility:hidden; opacity:0; height:0; width:0;">{preheader}</span>
  <div style="background: linear-gradient(135deg, #1f2933 0%, #3e4c59 100%); padding: 22px; text-align: center; border-radius: 10px 10px 0 0;">
    <h1 style="color: white; margin: 0; font-size: 20px;">Valvanta Audit Notification</h1>
  </div>
  <div style="background: #ffffff; padding: 26px; border: 1px solid #e2e8f0; border-top: none;">
    <h2 style="color: #2d3748; margin-top: 0; font-size: 19px;">{title}</h2>
    {content_html}
  </div>
  <div style="background: #f7fafc; padding: 16px; text-align: center; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 10px 10px;">
    <p style="margin: 0; color: #718096; font-size: 12px;">Valvanta Digital | Internal notification</p>
  </div>
</body>
</html>"""


def _render_list(items: Iterable[str]) -> str:
    """Renders the items as an escaped html list, empty string if there are none"""
    safe_items = [html.escape(item) for item in items if item]
    if not safe_items:
        return ""
    list_items = "\n".join(f"<li style=\"margin-bottom: 6px;\">{item}</li>" for item in safe_items)
    return f"<ul style=\"padding-left: 18px; margin: 0;\">{list_items}</ul>"


def company_audit_completion(
    client_name: Optional[str] = None,
    client_email: Optional[str] = None,
    target_url: Optional[str] = None,
    audit_id: Optional[str] = None,
    gcs_bucket: Optional[str] = None,
    gcs_objects: Optional[Iterable[str]] = None,
    report_paths: Optional[Iterable[str]] = None,
    social_links: Optional[Iterable[str]] = None,
) -> Tuple[str, str]:
    """
    Internal email notifying that an audit completed, listing the client, uploaded GCS files and social links.
    The subject marks it as a premium brand audit when social links are provided.

    @Args:
        client_name (Optional[str]) -- client name
        client_email (Optional[str]) -- client email
        target_url (Optional[str]) -- audited website url
        audit_id (Optional[str]) -- audit id
        gcs_bucket (Optional[str]) -- GCS bucket the reports were uploaded to
        gcs_objects (Optional[Iterable[str]]) -- uploaded GCS object names
        report_paths (Optional[Iterable[str]]) -- local report paths, not shown in the email
        social_links (Optional[Iterable[str]]) -- client social links to audit

    @Returns:
        email subject and html content (Tuple[str, str])
    """
    subject = f"Audit delivered for {client_name or target_url or 'client'}"
    
    if social_links: 
        subject = f"Premium Brand Audit complete for {client_name or target_url or 'client'}"

    summary_bits = []
    if client_name:
        summary_bits.append(f"<p><strong>Client:</strong> {html.escape(client_name)}</p>")
    if client_email:
        summary_bits.append(f"<p><strong>Email:</strong> {html.escape(client_email)}</p>")
    if target_url:
        summary_bits.append(f"<p><strong>Target URL:</strong> {html.escape(target_url)}</p>")
    if audit_id:
        summary_bits.append(f"<p><strong>Audit ID:</strong> {html.escape(audit_id)}</p>")

    gcs_intro = ""
    gcs_list = ""
    if gcs_objects:
        gcs_intro = "<p><strong>GCS objects:</strong></p>"
        gcs_list = _render_list(list(gcs_objects))
    bucket_line = ""
    if gcs_bucket:
        bucket_line = f"<p><strong>Bucket:</strong> {html.escape(gcs_bucket)}</p>"

    social_list = ""
    if social_links:
        social_list = f"""
        <p><strong>Social links:</strong></p>
        <p>Use these links to audit the clients social media accounts.</p>
        {_render_list(list(social_links))}
        """

    content_html = f"""
    <p>An audit has completed.</p>
    {''.join(summary_bits)}
    {bucket_line}
    {gcs_intro}
    {gcs_list}
    {social_list}
    """
    html_content = _email_shell("Audit completed", "Audit delivered and files uploaded.", content_html)
    return subject, html_content


def company_audit_failed(
    client_name: Optional[str] = None,
    client_email: Optional[str] = None,
    target_url: Optional[str] = None,
    audit_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Internal email notifying that an audit failed, with the client details and error message

    @Args:
        client_name (Optional[str]) -- client name
        client_email (Optional[str]) -- client email
        target_url (Optional[str]) -- audited website url
        audit_id (Optional[str]) -- audit id
        error_message (Optional[str]) -- failure reason

    @Returns:
        email subject and html content (Tuple[str, str])
    """
    subject = f"Audit failed for {client_name or target_url or 'client'}"
    detail_parts = []
    if client_name:
        detail_parts.append(f"<p><strong>Client:</strong> {html.escape(client_name)}</p>")
    if client_email:
        detail_parts.append(f"<p><strong>Email:</strong> {html.escape(client_email)}</p>")
    if target_url:
        detail_parts.append(f"<p><strong>Target URL:</strong> {html.escape(target_url)}</p>")
    if audit_id:
        detail_parts.append(f"<p><strong>Audit ID:</strong> {html.escape(audit_id)}</p>")
    if error_message:
        detail_parts.append(f"<p><strong>Error:</strong> {html.escape(error_message)}</p>")

    content_html = f"""
    <p>The audit pipeline failed before completion.</p>
    {''.join(detail_parts)}
    <p style="margin-bottom: 0;">Please review logs and retry the audit when ready.</p>
    """
    html_content = _email_shell("Audit failed", "Audit failed during processing.", content_html)
    return subject, html_content
