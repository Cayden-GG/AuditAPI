from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .database import (
    SessionLocal,
    get_audit,
    init_db,
    update_audit_status,
    update_audit_report_objects,
)
from .models import (
    AuditRecord,
    AuditStatus,
)
from .emails.brevo_email import (
    collect_report_paths,
    find_latest_report_dir,
    send_audit_email,
    build_client_audit_failed_email,
    build_client_audit_results_email,
    build_company_audit_completion_email,
    build_company_audit_failed_email,
)
from .logging_utils import build_audit_logger
from .gcs.uploader import upload_files
from .cleanup import run_full_cleanup
from .audit_queue.worker import queue_worker
from .rate_limit import build_rate_limiter, rate_limit_key
from .routes.audit import router as audit_router
from .routes.email import router as email_router

app = FastAPI(title="Valvanta Site Audit")
_rate_limit_enabled, _rate_limit_max, _rate_limit_window, _rate_limiter = build_rate_limiter()
app.include_router(audit_router)
app.include_router(email_router)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not _rate_limit_enabled:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        key = rate_limit_key(request)
        allowed, retry_after = _rate_limiter.allow(key)
        if not allowed:
            headers = {"Retry-After": str(retry_after)}
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded.",
                    "max_requests": _rate_limit_max,
                    "window_seconds": _rate_limit_window,
                },
                headers=headers,
            )
    return await call_next(request)

@app.on_event("startup")
def startup():
    init_db()
    if os.getenv("AUDIT_QUEUE_WORKER", "1") == "1":
        # Run queue scheduler/watchdog in-process by default.
        queue_worker.start()

def _safe_update_status(db: Session, audit_id: str, status: AuditStatus, logger, completed_at=None) -> None:
    try:
        update_audit_status(db, audit_id, status, completed_at=completed_at)
    except Exception as exc:
        logger.exception("Failed to update audit status.", exc, status=status)


def _normalize_categories(value: str, *, include_accessibility: bool = False) -> str:
    categories = [c.strip().lower() for c in (value or "").split(",") if c.strip()]
    if not categories:
        categories = ["performance", "seo"]
    if include_accessibility and "accessibility" not in categories:
        categories.append("accessibility")
    seen = set()
    ordered = []
    for category in categories:
        if category not in seen:
            seen.add(category)
            ordered.append(category)
    return ",".join(ordered)


def _parse_social_links(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
    return []


def _send_paid_audit_callback(audit_record: AuditRecord, status: str, logger) -> None:
    if not audit_record or getattr(audit_record, "tier", None) != "paid":
        return
    callback_url = getattr(audit_record, "callback_url", None)
    order_id = getattr(audit_record, "order_id", None)
    if not callback_url or not order_id:
        logger.info(
            "Paid audit callback skipped; missing callback details.",
            callback_url=callback_url,
            order_id=order_id,
        )
        return
    secret = os.getenv("VALVANTA_AUDIT_SECRET_KEY")
    if not secret:
        logger.warning("VALVANTA_AUDIT_SECRET_KEY is not set; skipping callback.")
        return
    payload = {"orderId": order_id, "status": status}
    req = urlrequest.Request(
        str(callback_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": secret},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            if response.status >= 400:
                logger.error("Paid audit callback failed.", status=response.status)
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.exception(
            "Paid audit callback HTTP error.",
            exc,
            status=exc.code,
            detail=detail,
        )
    except Exception as exc:
        logger.exception("Paid audit callback failed.", exc)


def run_audit_task(
    audit_id: str,
    *,
    max_urls: int = 5,
    only_categories: str = "performance,seo",
    tier: str = "free",
    timeout_s: int | None = None,
):
    """
    Main audit task

    Args: 
        audit_id (str, required): created audit record id
        max_urls (int, required): maximum number of URLs to audit
        only_categories (str, required): Lighthouse categories to include
    Outputs: 
        performance and seo audit reports
    """

    db = SessionLocal()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = f"logs/audit_{audit_id}_{timestamp}/audit_log.jsonl"
    logger = build_audit_logger(audit_id, log_path)
    failure_notified = False

    def _send_failure_emails(audit_record: AuditRecord, error_message: str) -> None:
        nonlocal failure_notified
        if failure_notified:
            return
        subject, html_content = build_client_audit_failed_email(
            audit_record.client_name,
            audit_record.target_url,
            error_message,
        )
        try:
            send_audit_email(
                to_email=audit_record.client_email,
                client_name=audit_record.client_name,
                target_url=audit_record.target_url,
                report_paths=[],
                subject=subject,
                html_content=html_content,
            )
            logger.info("Client failure email sent.", to_email=audit_record.client_email)
        except Exception as exc:
            logger.exception("Client failure email failed.", exc, to_email=audit_record.client_email)

        company_email = os.getenv("BREVO_COMPANY_EMAIL")
        if company_email:
            subject, html_content = build_company_audit_failed_email(
                client_name=audit_record.client_name,
                client_email=audit_record.client_email,
                target_url=audit_record.target_url,
                audit_id=audit_record.id,
                error_message=error_message,
            )
            try:
                send_audit_email(
                    to_email=company_email,
                    client_name="Valvanta Digital",
                    target_url=audit_record.target_url,
                    report_paths=[],
                    subject=subject,
                    html_content=html_content,
                )
                logger.info("Company failure email sent.", to_email=company_email)
            except Exception as exc:
                logger.exception("Company failure email failed.", exc, to_email=company_email)
        else:
            logger.warning("BREVO_COMPANY_EMAIL is not set; skipping company failure email.")
        failure_notified = True

    report_paths = []
    _safe_update_status(db, audit_id, AuditStatus.PROCESSING, logger)
    try:
        audit = get_audit(db, audit_id)
        if not audit:
            raise ValueError(f"Audit {audit_id} not found")
        social_links = _parse_social_links(getattr(audit, "social_links", None))

        normalized_categories = _normalize_categories(
            only_categories,
            include_accessibility=(tier == "paid"),
        )
        client_name = audit.client_name or "client"
        output_dir = f"audit_results/{client_name}_audit_{timestamp}"
        logger.info("Audit starting", client_name=client_name, target_url=audit.target_url, output_dir=output_dir)

        # Run Lighthouse Subprocess
        try:
            cmd = [
                sys.executable,
                "-m",
                "app.audit_service.cli",
                "--client-name",
                client_name,
                "--domain-url",
                audit.target_url,
                "--audit-id",
                audit_id,
                "--output-dir",
                output_dir,
                "--log-path",
                log_path,
                "--max-urls",
                str(max_urls),
                "--only-categories",
                normalized_categories,
            ]
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            logger.error("Audit timed out.")
            _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
            _send_failure_emails(audit, "Audit timed out.")
            _send_paid_audit_callback(audit, "timeout", logger)
            return {"status": "timeout", "report_paths": []}
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Audit service failed.",
                return_code=exc.returncode,
                stdout=exc.stdout[-4000:] if exc.stdout else "",
                stderr=exc.stderr[-4000:] if exc.stderr else "",
            )
            _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
            _send_failure_emails(audit, exc.stderr or exc.stdout or "Audit subprocess failed.")
            _send_paid_audit_callback(audit, "failed", logger)
            return {"status": "failed", "report_paths": []}

        logger.info("Audit complete, starting emails")
        report_paths = _extract_report_paths(result.stdout)
        if not report_paths:
            try:
                report_dir = find_latest_report_dir(
                    Path("audit_results"), client_name=client_name
                )
                report_paths = collect_report_paths(report_dir)
            except Exception as exc:
                logger.exception("Failed to resolve report paths.", exc)
                report_paths = []
        if report_paths:
            logger.info("Report paths resolved.", report_paths=[str(path) for path in report_paths])
        else:
            logger.warning("No report paths resolved; emails will send without attachments.")

        # Upload reports to GCS
        gcs_bucket = os.getenv("GCS_BUCKET_NAME", "")
        gcs_creds = os.getenv("GCS_SERVICE_ACCOUNT_JSON", "")
        gcs_objects = {}
        if gcs_creds:
            try: 
                output_dir_path = Path(output_dir)
                file_paths = list(output_dir_path.glob("*.pdf")) + list(output_dir_path.glob("*.json"))
                log_file = Path(log_path)
                if log_file.exists():
                    file_paths.append(log_file)
                gcs_objects = upload_files(
                    file_paths=file_paths,
                    bucket_name=gcs_bucket,
                    prefix=f"audits/{tier}/{audit_id}",
                    credentials_path=gcs_creds,
                    logger=logger,
                )
            except Exception as exc:
                logger.exception("Failed to upload reports to CGS.", exc)
        else:
            logger.warning("GCS credentials not configured; skipping upload.")

        if gcs_objects:
            db_fields = {}
            for local_path, object_name in gcs_objects.items():
                name = Path(local_path).name
                if name.startswith("Performance_PDF"):
                    db_fields["perf_report_object"] = object_name
                elif name.startswith("SEO_PDF"):
                    db_fields["seo_report_object"] = object_name
                elif name.startswith("Key_Findings"):
                    db_fields["key_findings_object"] = object_name
                elif name.startswith("Accessibility_PDF"):
                    db_fields["accessibility_report_object"] = object_name
                elif name.startswith("ai_audit_summary") and name.endswith(".json"):
                    db_fields["ai_json_object"] = object_name
                elif name.startswith("audit_") and name.endswith(".json"):
                    db_fields["audit_json_object"] = object_name
                elif name == "audit_log.jsonl":
                    db_fields["audit_log_object"] = object_name
            if db_fields:
                try:
                    update_audit_report_objects(db, audit_id, **db_fields)
                    logger.info("GCS object names stored in database.", fields=db_fields)
                except Exception as exc:
                    logger.exception("Failed to store GCS object names.", exc)

        # Send user and company emails
        if tier != "paid":
            try:
                subject, html_content = build_client_audit_results_email(
                    audit.client_name,
                    audit.target_url,
                    None,
                )
                send_audit_email(
                    to_email=audit.client_email,
                    client_name=audit.client_name,
                    target_url=audit.target_url,
                    report_paths=report_paths,
                    subject=subject,
                    html_content=html_content,
                )
                logger.info("Client email sent.", to_email=audit.client_email)
            except Exception as exc:
                logger.exception("Client email failed.", exc, to_email=audit.client_email)
        else:
            logger.info("Paid audit: skipping client results email.", to_email=audit.client_email)

        company_email = os.getenv("BREVO_COMPANY_EMAIL")
        if not company_email:
            logger.warning("BREVO_COMPANY_EMAIL is not set; skipping company email.")
        else:
            try:
                subject, html_content = build_company_audit_completion_email(
                    client_name=audit.client_name,
                    client_email=audit.client_email,
                    target_url=audit.target_url,
                    audit_id=audit.id,
                    gcs_bucket=gcs_bucket or None,
                    gcs_objects=list(gcs_objects.values()) if gcs_objects else None,
                    report_paths=[str(path) for path in report_paths] if tier == "paid" else None,
                    social_links=social_links if tier == "paid" else None,
                )
                send_audit_email(
                    to_email=company_email,
                    client_name="Valvanta Digital",
                    target_url=audit.target_url,
                    report_paths=report_paths if tier == "paid" else None,
                    subject=subject,
                    html_content=html_content,
                )
                logger.info("Company email sent.", to_email=company_email)
            except Exception as exc:
                logger.exception("Company email failed.", exc, to_email=company_email)

        # Delete local reports 
        try: 
            run_full_cleanup()
            logger.info("Service files clean up successful.")
        except Exception as exc:
            logger.exception("Service files clean up failed.", exc)

        _safe_update_status(db, audit_id, AuditStatus.COMPLETED, logger, completed_at=datetime.utcnow())
        _send_paid_audit_callback(audit, "completed", logger)
        return {"status": "completed", "report_paths": report_paths}
    except Exception as e:
        _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
        if "audit" in locals() and audit:
            _send_failure_emails(audit, str(e))
            _send_paid_audit_callback(audit, "failed", logger)
        logger.exception("Audit task failed.", e)
        return {"status": "failed", "report_paths": report_paths}
    finally:
        db.close()


def _extract_report_paths(stdout: str):
    prefix = "REPORT_PATHS::"
    for line in stdout.splitlines():
        if line.startswith(prefix):
            payload = line[len(prefix):].strip()
            data = json.loads(payload)
            ordered = []
            for key in ("performance", "seo", "accessibility", "key_findings"):
                if key in data:
                    ordered.append(Path(data[key]))
            for path in data.values():
                if Path(path) not in ordered:
                    ordered.append(Path(path))
            return ordered
    return []


def validateDomain(db, domain):
    from .database import validate_domain_audit

    # is audited
    if (validate_domain_audit(db, domain=domain)): 
        return True
    else:
        # else if not audited 
        return False
