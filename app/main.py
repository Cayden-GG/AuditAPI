from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .database import (
    SessionLocal,
    create_audit,
    get_audit,
    get_db,
    get_latest_audit_by_target_url,
    init_db,
    update_audit_status,
    update_audit_report_objects,
)
from .models import (
    AuditCreate,
    AuditRecord,
    AuditResendRequest,
    AuditResendResponse,
    AuditResponse,
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
from .gcs.uploader import download_objects, upload_files
from .cleanup import run_full_cleanup

app = FastAPI(title="Valvanta Site Audit")

@app.on_event("startup")
def startup():
    init_db()

def _safe_update_status(db: Session, audit_id: str, status: AuditStatus, logger, completed_at=None) -> None:
    try:
        update_audit_status(db, audit_id, status, completed_at=completed_at)
    except Exception as exc:
        logger.exception("Failed to update audit status.", exc, status=status)


def run_audit_task(audit_id: str):
    """
    Main audit task

    Args: 
        audit_id (str, required): created audit record id
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

    _safe_update_status(db, audit_id, AuditStatus.PROCESSING, logger)
    try:
        audit = get_audit(db, audit_id)
        if not audit:
            raise ValueError(f"Audit {audit_id} not found")

        client_name = audit.client_name or "client"
        output_dir = f"audit_results/{client_name}_audit_{timestamp}"
        logger.info("Audit starting", client_name=client_name, target_url=audit.target_url, output_dir=output_dir)

        # Run Lighthouse Subprocess
        try:
            result = subprocess.run(
                [
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
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error(
                "Audit service failed.",
                return_code=exc.returncode,
                stdout=exc.stdout[-4000:] if exc.stdout else "",
                stderr=exc.stderr[-4000:] if exc.stderr else "",
            )
            _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
            _send_failure_emails(audit, exc.stderr or exc.stdout or "Audit subprocess failed.")
            return

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
                    prefix=f"audits/{audit_id}",
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
                    report_paths=[str(path) for path in report_paths] if report_paths else None,
                )
                send_audit_email(
                    to_email=company_email,
                    client_name="Valvanta Digital",
                    target_url=audit.target_url,
                    report_paths=report_paths,
                    subject=subject,
                    html_content=html_content,
                )
                logger.info("Company email sent.", to_email=company_email)
            except Exception as exc:
                logger.exception("Company email failed.", exc, to_email=company_email)

        # Delete local reports 
        try: 
            run_full_cleanup()
        except Exception as exc:
            logger.exception("Service files clean up failed.", exc)

        _safe_update_status(db, audit_id, AuditStatus.COMPLETED, logger, completed_at=datetime.utcnow())
    except Exception as e:
        _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
        if "audit" in locals() and audit:
            _send_failure_emails(audit, str(e))
        logger.exception("Audit task failed.", e)
    finally:
        db.close()


def _extract_report_paths(stdout: str):
    prefix = "REPORT_PATHS::"
    for line in stdout.splitlines():
        if line.startswith(prefix):
            payload = line[len(prefix):].strip()
            data = json.loads(payload)
            ordered = []
            for key in ("performance", "seo", "key_findings"):
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


@app.post("/api/v1/audit", response_model=AuditResponse, status_code=202)
async def start_website_audit(
    payload: AuditCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    # validate target url
    # if validateDomain(db, payload.url):
    #     return AuditResponse(
    #         job_id=None,
    #         status="Denied",
    #         message="This domain has already been audited."
    #     )

    # Create a unique record for this job
    new_audit = create_audit(
        db,
        target_url=str(payload.url),
        client_email=payload.email,
        client_name=payload.client_name,
    )
    
    # Hand off to worker (Non-blocking)
    background_tasks.add_task(run_audit_task, new_audit.id)
    
    # Return immediate ticket to React
    return AuditResponse(
        job_id=new_audit.id,
        status="Accepted",
        message=f"Audit for {payload.url} is now in the queue."
    )

@app.get("/api/v1/status/{job_id}", response_model=AuditRecord)
async def get_audit_status(job_id: str, db: Session = Depends(get_db)):
    record = get_audit(db, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit job not found")
    return record


@app.post("/api/v1/audit/resend", response_model=AuditResendResponse)
async def resend_audit_email(
    payload: AuditResendRequest, db: Session = Depends(get_db)
):
    if not payload.job_id and not payload.target_url:
        raise HTTPException(status_code=400, detail="Provide job_id or target_url.")

    audit = None
    if payload.job_id:
        audit = get_audit(db, payload.job_id)
    if not audit and payload.target_url:
        audit = get_latest_audit_by_target_url(db, str(payload.target_url))

    if not audit:
        raise HTTPException(status_code=404, detail="Audit record not found.")

    if audit.status != AuditStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Audit is not completed.")

    object_names = [
        audit.perf_report_object,
        audit.seo_report_object,
        audit.key_findings_object,
    ]
    object_names = [name for name in object_names if name]
    if not object_names:
        raise HTTPException(status_code=409, detail="No report objects stored for this audit.")

    gcs_bucket = os.getenv("GCS_BUCKET_NAME", "")
    gcs_creds = os.getenv("GCS_SERVICE_ACCOUNT_JSON", "")
    if not gcs_bucket or not gcs_creds:
        raise HTTPException(status_code=500, detail="GCS configuration is missing.")

    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = Path("audit_results") / f"resend_{audit.id}_{timestamp}"
    log_path = f"logs/resend_{audit.id}_{timestamp}/resend_log.jsonl"
    logger = build_audit_logger(audit.id, log_path)
    logger.info(
        "Resend requested.",
        audit_id=audit.id,
        target_url=audit.target_url,
        requested_to_email=payload.to_email,
        object_count=len(object_names),
    )
    downloads = download_objects(
        object_names=object_names,
        bucket_name=gcs_bucket,
        credentials_path=gcs_creds,
        output_dir=output_dir,
        logger=logger,
    )
    if not downloads:
        logger.warning("No reports downloaded from GCS.", object_names=object_names)
        raise HTTPException(status_code=500, detail="Failed to download reports from GCS.")

    report_paths = []
    for name in object_names:
        local_path = downloads.get(name)
        if local_path:
            report_paths.append(Path(local_path))

    ai_payload = None
    if audit.ai_json_object:
        ai_downloads = download_objects(
            object_names=[audit.ai_json_object],
            bucket_name=gcs_bucket,
            credentials_path=gcs_creds,
            output_dir=output_dir,
            logger=logger,
        )
        ai_path = ai_downloads.get(audit.ai_json_object)
        if ai_path:
            try:
                with open(ai_path, "r", encoding="utf-8") as handle:
                    ai_payload = json.load(handle)
            except Exception:
                logger.warning("Failed to parse AI summary JSON.", path=ai_path)
                ai_payload = None

    subject, html_content = build_client_audit_results_email(
        audit.client_name, audit.target_url, ai_payload
    )
    to_email = payload.to_email or audit.client_email
    try:
        send_audit_email(
            to_email=to_email,
            client_name=audit.client_name,
            target_url=audit.target_url,
            report_paths=report_paths,
            subject=subject,
            html_content=html_content,
        )
        logger.info("Resend email sent.", to_email=to_email, report_count=len(report_paths))
    except Exception as exc:
        logger.exception("Resend email failed.", exc, to_email=to_email)
        raise HTTPException(status_code=500, detail="Failed to resend audit email.")

    gcs_prefix = ""
    if object_names:
        parent_dirs = {str(Path(name).parent) for name in object_names if name}
        if len(parent_dirs) == 1:
            gcs_prefix = parent_dirs.pop()
        else:
            gcs_prefix = str(Path(object_names[0]).parent)
            logger.warning(
                "Report objects use different prefixes; using first.",
                prefixes=sorted(parent_dirs),
                chosen_prefix=gcs_prefix,
            )
        if gcs_prefix == ".":
            gcs_prefix = ""

    uploaded_logs = upload_files(
        file_paths=[Path(log_path)],
        bucket_name=gcs_bucket,
        prefix=gcs_prefix,
        credentials_path=gcs_creds,
        logger=logger,
    )
    if not uploaded_logs:
        logger.warning("Resend log upload failed or skipped.", log_path=log_path, prefix=gcs_prefix)

    try:
        run_full_cleanup()
    except Exception as exc:
        logger.exception("Service files clean up failed.", exc)

    return AuditResendResponse(
        status="sent",
        message="Audit email resent.",
        job_id=audit.id,
        target_url=audit.target_url,
        resent_to=to_email,
    )
