import base64
import json
import os
from pathlib import Path
from typing import Iterable, List, Optional
from urllib import error, request
from dotenv import load_dotenv

load_dotenv()

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
REPORT_PREFIXES = ("Performance_PDF", "SEO_PDF", "Key_Findings")


def _normalize_client_name(client_name: Optional[str]) -> Optional[str]:
    if not client_name:
        return None
    return client_name.strip().replace(" ", "_")


def find_latest_report_dir(
    base_dir: Path, client_name: Optional[str] = None
) -> Path:
    if not base_dir.exists():
        raise FileNotFoundError(f"Report directory not found: {base_dir}")

    normalized = _normalize_client_name(client_name)
    candidates = [path for path in base_dir.iterdir() if path.is_dir()]
    if normalized:
        candidates = [
            path for path in candidates if path.name.startswith(f"{normalized}_audit_")
        ]

    if not candidates:
        raise FileNotFoundError("No audit result directories found")

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        if list(path.glob("*.pdf")):
            return path

    raise FileNotFoundError("No PDF reports found in audit results")


def collect_report_paths(report_dir: Path) -> List[Path]:
    pdfs = sorted(report_dir.glob("*.pdf"), key=lambda path: path.name)
    if not pdfs:
        raise FileNotFoundError(f"No PDF reports found in {report_dir}")

    ordered: List[Path] = []
    used = set()
    for prefix in REPORT_PREFIXES:
        for path in pdfs:
            if path.name.startswith(prefix):
                ordered.append(path)
                used.add(path)

    for path in pdfs:
        if path not in used:
            ordered.append(path)

    return ordered


def _build_attachments(paths: Iterable[Path]) -> List[dict]:
    attachments: List[dict] = []
    for path in paths:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        attachments.append({"content": encoded, "name": path.name})
    return attachments


def send_audit_email(
    *,
    to_email: str,
    client_name: Optional[str],
    target_url: str,
    report_paths: Iterable[Path],
    subject: Optional[str] = None,
    html_content: Optional[str] = None,
) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY is not set")

    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    if not sender_email:
        raise ValueError("BREVO_SENDER_EMAIL is not set")

    sender_name = os.getenv("BREVO_SENDER_NAME", "Valvanta Digital")
    recipient_name = client_name or to_email

    if not subject:
        label = client_name or target_url
        subject = f"Your website audit report for {label}"

    if not html_content:
        html_content = (
            "<p>Your website audit is complete.</p>"
            f"<p>Target URL: {target_url}</p>"
            "<p>Your reports are attached to this email.</p>"
        )

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email, "name": recipient_name}],
        "subject": subject,
        "htmlContent": html_content,
        "attachment": _build_attachments(report_paths),
    }

    req = request.Request(
        BREVO_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(
                    f"Brevo email failed with status {response.status}"
                )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo email failed: {detail}") from exc
