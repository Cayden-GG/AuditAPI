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
)
from .models import AuditCreate, AuditRecord, AuditResponse, AuditStatus
from .emails.brevo_email import (
    collect_report_paths,
    find_latest_report_dir,
    send_audit_email,
)
app = FastAPI(title="Valvanta Site Audit")

@app.on_event("startup")
def startup():
    init_db()

def run_audit_task(audit_id: str):
    """
    Main audit task

    Args: 
        audit_id (str, required): created audit record id
    Outputs: 
        performance and seo audit reports
    """

    db = SessionLocal()
    update_audit_status(db, audit_id, AuditStatus.PROCESSING)
    try:
        audit = get_audit(db, audit_id)
        if not audit:
            raise ValueError(f"Audit {audit_id} not found")

        client_name = audit.client_name or "client"
        print("Audit starting")

        # Run Lighthouse Subprocess
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.audit_service.cli",
                "--client-name",
                client_name,
                "--domain-url",
                audit.target_url
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print("audit complete, starting emails")
        report_paths = _extract_report_paths(result.stdout)
        if not report_paths:
            report_dir = find_latest_report_dir(
                Path("audit_results"), client_name=client_name
            )
            report_paths = collect_report_paths(report_dir)

        # Send user and company emails
        send_audit_email(
            to_email=audit.client_email,
            client_name=audit.client_name,
            target_url=audit.target_url,
            report_paths=report_paths,
        )

        company_email = os.getenv("BREVO_COMPANY_EMAIL")
        if not company_email:
            raise ValueError("BREVO_COMPANY_EMAIL is not set")

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

        # Upload 3 PDFs to GCS

        # Delete local reports 

        update_audit_status(db, audit_id, AuditStatus.COMPLETED, completed_at=datetime.utcnow())
    except Exception as e:
        update_audit_status(db, audit_id, AuditStatus.FAILED)
        print(f"Audit {audit_id} failed: {e}")
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
    print("Audit request received")
    
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
