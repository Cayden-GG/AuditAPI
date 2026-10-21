"""
Client email templates
Emails sent to the client: audit started, audit results and audit failed
"""
from __future__ import annotations

import html
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _email_shell(title: str, preheader: str, content_html: str) -> str:
    """Wraps content in the branded client email layout with a header, footer and hidden preheader

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
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2d3748; max-width: 600px; margin: 0 auto; padding: 20px; background: #f7fafc;">
  <span style="display:none; visibility:hidden; opacity:0; height:0; width:0;">{preheader}</span>
  <div style="background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%); padding: 26px; text-align: center; border-radius: 10px 10px 0 0;">
    <h1 style="color: white; margin: 0; font-size: 22px;">Valvanta Digital</h1>
    <p style="color: #a0c4b8; margin: 8px 0 0 0; font-size: 14px;">Digital Made Simple. Presence Made Powerful.</p>
  </div>
  <div style="background: #ffffff; padding: 28px; border: 1px solid #e2e8f0; border-top: none;">
    <h2 style="color: #2d3748; margin-top: 0; font-size: 20px;">{title}</h2>
    {content_html}
  </div>
  <div style="background: #f7fafc; padding: 18px; text-align: center; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 10px 10px;">
    <p style="margin: 0; color: #718096; font-size: 13px;">Valvanta Digital | Digital Marketing for South African Businesses</p>
    <p style="margin: 8px 0 0 0; color: #a0aec0; font-size: 12px;">
      <a href="https://valvantadigital.co.za" style="color: #a0aec0;">valvantadigital.co.za</a>
    </p>
  </div>
</body>
</html>"""


def _normalize_name(client_name: Optional[str]) -> str:
    """Client name for the greeting, "there" if empty"""
    return (client_name or "there").strip() or "there"


def _extract_key_findings(audit_results: Optional[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, str]]:
    """
    Gets the top key findings from the AI summary data

    @Args:
        audit_results (Optional[Dict[str, Any]]) -- AI summary data, or audit data with an "ai" section
        max_items (int) -- max number of findings to return

    @Returns:
        findings with issue, priority, impact and effort (List[Dict[str, str]]), empty if there are none
    """
    if not isinstance(audit_results, dict):
        return []
    ai_payload = {}
    if isinstance(audit_results.get("ai"), dict):
        ai_payload = audit_results["ai"]
    elif "key_findings" in audit_results or "executive_summaries" in audit_results:
        ai_payload = audit_results
    findings = ai_payload.get("key_findings", []) if isinstance(ai_payload, dict) else []
    if not isinstance(findings, list):
        return []
    trimmed = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        issue = item.get("issue")
        priority = item.get("priority")
        impact = item.get("impact")
        effort = item.get("effort")
        if not issue:
            continue
        trimmed.append(
            {
                "issue": str(issue),
                "priority": str(priority or ""),
                "impact": str(impact or ""),
                "effort": str(effort or ""),
            }
        )
        if len(trimmed) >= max_items:
            break
    return trimmed


def _render_key_findings(findings: Iterable[Dict[str, str]]) -> str:
    """Renders the findings as an escaped "Top findings" html list, empty string if there are none"""
    items = []
    for item in findings:
        issue = html.escape(item.get("issue", ""))
        priority = html.escape(item.get("priority", ""))
        impact = html.escape(item.get("impact", ""))
        effort = html.escape(item.get("effort", ""))
        meta_bits = [bit for bit in (priority, effort) if bit]
        meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
        details = f" - {impact}" if impact else ""
        items.append(f"<li style=\"margin-bottom: 8px;\"><strong>{issue}</strong>{meta}{details}</li>")
    if not items:
        return ""
    items_html = "\n".join(items)
    return f"""
    <div style="background: #f7fafc; padding: 18px; border-radius: 8px; margin: 18px 0;">
      <h3 style="color: #4a5568; margin-top: 0; font-size: 15px;">Top findings</h3>
      <ul style="padding-left: 18px; margin: 0;">{items_html}</ul>
    </div>
    """


def _needs_client_action(error_message: Optional[str]) -> bool:
    """Returns whether the failure is a sitemap or robots.txt problem only the client can fix"""
    if not error_message:
        return False
    lowered = error_message.lower()
    return "sitemap" in lowered or "robots" in lowered or "robots.txt" in lowered


def client_confirmation(client_name: Optional[str], target_url: str) -> Tuple[str, str]:
    """
    Email confirming payment was received and the audit has started

    @Args:
        client_name (Optional[str]) -- client name
        target_url (str) -- audited website url

    @Returns:
        email subject and html content (Tuple[str, str])
    """
    name = html.escape(_normalize_name(client_name))
    safe_url = html.escape(target_url)
    subject = "Payment received - your website audit is underway"
    content_html = f"""
    <p>Hi {name},</p>
    <p>Thanks for your payment. We have started the audit for <strong>{safe_url}</strong>.</p>
    <p>What happens next:</p>
    <ol style="padding-left: 18px; margin: 0 0 16px 0;">
      <li>Our team will scan your entire website and generate your Technical SEO, Performance and Accessibility reports.</li>
      <li>If you provided social media profiles, our team will audit and review them.</li>
      <li>Your full report package will be delivered to your inbox within 24 - 48 hours by the Valvanta team.</li>
    </ol>
    <p>Most audits complete within 24 - 48 hours depending on our teams current work load.</p>
    <p>If you have questions, reply to this email and we will help.</p>
    <p style="margin-bottom: 0;">Warm regards,<br><strong>The Valvanta Digital Team</strong></p>
    """
    html_content = _email_shell("Your audit is underway", f"Audit started for {safe_url}.", content_html)
    return subject, html_content


def client_audit_results(client_name: Optional[str], target_url: str, audit_results: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Email delivering the completed audit, with the top findings when the AI data has them

    @Args:
        client_name (Optional[str]) -- client name
        target_url (str) -- audited website url
        audit_results (Optional[Dict[str, Any]]) -- AI summary data the top findings are taken from

    @Returns:
        email subject and html content (Tuple[str, str])
    """
    name = html.escape(_normalize_name(client_name))
    safe_url = html.escape(target_url)
    subject = "Your website audit is ready"
    findings = _extract_key_findings(audit_results)
    findings_html = _render_key_findings(findings)
    summary_line = "Your reports are attached to this email."
    if findings_html:
        summary_line = "We included the top findings below and attached the full reports."
    content_html = f"""
    <p>Hi {name},</p>
    <p>Your website audit for <strong>{safe_url}</strong> is complete.</p>
    <p>{summary_line}</p>
    {findings_html}
    <p>If you would like a walkthrough or help prioritising fixes, reply to this email and we can schedule a call.</p>
    <p style="margin: 18px 0 24px 0;">
      <a href="https://calendly.com/valvantadigital/30min" target="_blank" rel="noopener noreferrer" style="background: #2d3748; color: #ffffff; text-decoration: none; padding: 12px 22px; border-radius: 6px; font-weight: 600; display: inline-block;">Book Now</a>
    </p>
    <p style="margin-bottom: 0;">Thank you,<br><strong>The Valvanta Digital Team</strong></p>
    """
    html_content = _email_shell("Your audit is complete", f"Audit ready for {safe_url}.", content_html)
    return subject, html_content


def client_audit_failed(client_name: Optional[str], target_url: str, error_message: Optional[str] = None) -> Tuple[str, str]:
    """
    Email telling the client the audit failed, asks them to fix their site for sitemap and robots.txt errors
    otherwise says the team is investigating. The error message itself is not shown to the client.

    @Args:
        client_name (Optional[str]) -- client name
        target_url (str) -- audited website url
        error_message (Optional[str]) -- failure reason, used to pick the follow up message

    @Returns:
        email subject and html content (Tuple[str, str])
    """
    name = html.escape(_normalize_name(client_name))
    safe_url = html.escape(target_url)
    subject = "We could not complete your website audit"
    if _needs_client_action(error_message):
        follow_up = (
            "It looks like the issue is related to your sitemap or robots.txt configuration. "
            "These are controlled on your side, so please review and update them. "
            "Once corrected, we can rerun the audit."
        )
    else:
        follow_up = (
            "Our team is already investigating and will rerun the audit once the issue is resolved."
        )
    detail_line = ""
    content_html = f"""
    <p>Hi {name},</p>
    <p>We ran into a problem while auditing <strong>{safe_url}</strong>.</p>
    <p>{follow_up}</p>
    <p>If you need help, reply to this email and we will assist.</p>
    <p style="margin-bottom: 0;">Regards,<br><strong>The Valvanta Digital Team</strong></p>
    """
    html_content = _email_shell("Audit issue detected", f"Issue encountered for {safe_url}.", content_html)
    return subject, html_content
