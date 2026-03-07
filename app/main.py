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
    init_db,
    update_audit_status,
    update_audit_report_objects,
)
from .models import AuditCreate, AuditRecord, AuditResponse, AuditStatus
from .emails.brevo_email import (
    collect_report_paths,
    find_latest_report_dir,
    send_audit_email,
)
from .logging_utils import build_audit_logger
from .gcs.uploader import upload_files
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

        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_creds = os.getenv("GCS_SERVICE_ACCOUNT_JSON", "")
        gcs_objects = {}
        if gcs_creds:
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
            send_audit_email(
                to_email=audit.client_email,
                client_name=audit.client_name,
                target_url=audit.target_url,
                report_paths=report_paths,
            )
            logger.info("Client email sent.", to_email=audit.client_email)
        except Exception as exc:
            logger.exception("Client email failed.", exc, to_email=audit.client_email)

        company_email = os.getenv("BREVO_COMPANY_EMAIL")
        if not company_email:
            logger.warning("BREVO_COMPANY_EMAIL is not set; skipping company email.")
        else:
            try:
                send_audit_email(
                    to_email=company_email,
                    client_name="Valvanta Digital",
                    target_url=audit.target_url,
                    report_paths=report_paths,
                    subject=f"Audit delivered for {audit.client_name or audit.target_url}",
                    html_content=(
                        "<p>An audit has been completed and sent to the client.</p>"
                        f"<p>Client: {audit.client_name or audit.client_email}</p>"
                        f"<p>Target URL: {audit.target_url}</p>"
                    ),
                )
                logger.info("Company email sent.", to_email=company_email)
            except Exception as exc:
                logger.exception("Company email failed.", exc, to_email=company_email)

        # Upload 3 PDFs to GCS
        try:
            logger.warning("GCS upload not implemented; skipping.")
        except Exception as exc:
            logger.exception("GCS upload placeholder failed.", exc)

        # Delete local reports 
        logger.warning("Report cleanup not implemented; leaving local artifacts.")

        _safe_update_status(db, audit_id, AuditStatus.COMPLETED, logger, completed_at=datetime.utcnow())
    except Exception as e:
        _safe_update_status(db, audit_id, AuditStatus.FAILED, logger)
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

@app.post("/api/v1/audit", response_model=AuditResponse, status_code=202)
async def start_website_audit(
    payload: AuditCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
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
