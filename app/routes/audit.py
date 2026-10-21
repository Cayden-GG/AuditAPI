"""
Audit routes
Endpoints to queue free and paid audits, poll their status and resend completed audit emails
"""
import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit_queue.models import QueueStatusResponse
from app.audit_queue.service import enqueue_job, launch_job_in_thread, queue_status, start_dispatcher
from app.cleanup import run_full_cleanup
from app.database import get_audit, get_db, get_latest_audit_by_target_url
from app.emails.brevo_email import (
    build_client_audit_results_email,
    build_client_confirmation_email,
    send_audit_email,
)
from app.gcs.uploader import download_objects, upload_files
from app.logging_utils import build_audit_logger
from app.models import (
    AuditCreate,
    AuditResendRequest,
    AuditResendResponse,
    AuditResponse,
    AuditStatus,
    PaidAuditCreate,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/v1/audit", response_model=AuditResponse, status_code=202)
async def start_website_audit(payload: AuditCreate):
    """
    Queues a free audit for the website. Responds 400 if the queue rejects the job
    and 500 if the audit record could not be created.

    @Args:
        payload (AuditCreate) -- website url, client email and name

    @Returns:
        job id and job token for status polling (AuditResponse)
    """
    try:
        job_token, audit_id = enqueue_job(
            url=str(payload.url),
            email=payload.email,
            client_name=payload.client_name,
            customer_id=None,
            tier="free",
            urls=None,
            debug_mode=payload.debug_mode,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not audit_id:
        raise HTTPException(status_code=500, detail="Failed to queue audit.")

    start_dispatcher(launch_job_in_thread)

    return AuditResponse(
        job_id=audit_id,
        job_token=job_token,
        status="Accepted",
        message=f"Audit for {payload.url} is now in the queue.",
    )


@router.post("/api/v1/paidAudit", response_model=AuditResponse, status_code=202)
async def start_paid_website_audit(payload: PaidAuditCreate):
    """
    Queues a paid audit for the website and emails the client a confirmation. Responds 400 if the queue rejects the job
    and 500 if the audit record could not be created, a failed confirmation email is logged not raised.

    @Args:
        payload (PaidAuditCreate) -- website url, customer details, order id and callback url

    @Returns:
        job id and job token for status polling (AuditResponse)
    """
    try:
        job_token, audit_id = enqueue_job(
            url=str(payload.website_url),
            email=payload.customer_email,
            client_name=payload.customer_name,
            customer_id=None,
            tier="paid",
            urls=None,
            order_id=payload.order_id,
            callback_url=str(payload.callback_url),
            social_links=payload.social_links,
            debug_mode=payload.debug_mode,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not audit_id:
        raise HTTPException(status_code=500, detail="Failed to queue audit.")

    try:
        subject, html_content = build_client_confirmation_email(
            payload.customer_name,
            str(payload.website_url),
        )

        send_audit_email(
            to_email=payload.customer_email,
            client_name=payload.customer_name,
            target_url=str(payload.website_url),
            subject=subject,
            html_content=html_content,
        )
    except Exception as exc:
        logger.warning(
            "Paid audit confirmation email failed for %s.",
            payload.customer_email,
            exc_info=exc,
        )

    start_dispatcher(launch_job_in_thread)

    return AuditResponse(
        job_id=audit_id,
        job_token=job_token,
        status="Accepted",
        message=f"Paid audit for {payload.website_url} is now in the queue.",
    )


@router.get("/api/v1/status/{identifier}")
async def get_audit_status(identifier: str, db: Session = Depends(get_db)):
    """
    Gets the status of an audit, looks up the queue job token first then falls back to the audit id.
    Responds 404 if neither exists.

    @Args:
        identifier (str) -- queue job token or audit id
        db (Session) -- database session

    @Returns:
        queue status with an estimated wait for a job token (QueueStatusResponse), the audit record for an audit id
    """
    job = queue_status(identifier)
    if job:
        status = job.get("status")
        message = "Status unavailable."
        estimated_wait = None
        result_path = job.get("result_path")

        if status == "queued":
            pos_in_q = job.get("queue_position") or 0
            estimated_wait = math.floor((pos_in_q * 10) / 1.5)
            message = f"Estimated wait: {estimated_wait} minutes"

        elif status == "running":
            message = "Auditing your site now"

        elif status == "completed":
            message = "Audit completed"

        elif status == "failed":
            message = "Audit failed"
        
        elif status == "timeout":
            message = "Audit timed out"

        return QueueStatusResponse(
            job_token=identifier,
            status=status,
            message=message,
            estimated_wait_minutes=estimated_wait,
            result_path=result_path,
        )

    record = get_audit(db, identifier)
    if not record:
        raise HTTPException(status_code=404, detail="Audit job not found")

    return record


@router.post("/api/v1/audit/resend", response_model=AuditResendResponse)
async def resend_audit_email(
    payload: AuditResendRequest, db: Session = Depends(get_db)
):
    """
    Resends a completed audit's reports by email, downloading them from GCS and uploading the resend log.
    Responds 400 if no audit is identified, 404 if it is not found, 409 if it is not completed or has no stored reports
    and 500 if GCS is not configured or the download or email fails.

    @Args:
        payload (AuditResendRequest) -- audit id or website url, and an optional email to send to
        db (Session) -- database session

    @Returns:
        who the reports were resent to (AuditResendResponse)
    """
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
        audit.accessibility_report_object,
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
    logger_instance = build_audit_logger(audit.id, log_path)

    logger_instance.info(
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
        logger=logger_instance,
    )

    if not downloads:
        logger_instance.warning("No reports downloaded from GCS.", object_names=object_names)
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
            logger=logger_instance,
        )

        ai_path = ai_downloads.get(audit.ai_json_object)

        if ai_path:
            try:
                with open(ai_path, "r", encoding="utf-8") as handle:
                    ai_payload = json.load(handle)

            except Exception:
                logger_instance.warning("Failed to parse AI summary JSON.", path=ai_path)
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
        logger_instance.info(
            "Resend email sent.",
            to_email=to_email,
            report_count=len(report_paths),
        )
    except Exception as exc:
        logger_instance.exception("Resend email failed.", exc, to_email=to_email)
        raise HTTPException(status_code=500, detail="Failed to resend audit email.")

    gcs_prefix = ""
    if object_names:
        parent_dirs = {str(Path(name).parent) for name in object_names if name}

        if len(parent_dirs) == 1:
            gcs_prefix = parent_dirs.pop()

        else:
            gcs_prefix = str(Path(object_names[0]).parent)
            
            logger_instance.warning(
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
        logger=logger_instance,
    )

    if not uploaded_logs:
        logger_instance.warning(
            "Resend log upload failed or skipped.",
            log_path=log_path,
            prefix=gcs_prefix,
        )

    try:
        run_full_cleanup()
    except Exception as exc:
        logger_instance.exception("Service files clean up failed.", exc)

    return AuditResendResponse(
        status="sent",
        message="Audit email resent.",
        job_id=audit.id,
        target_url=audit.target_url,
        resent_to=to_email,
    )
