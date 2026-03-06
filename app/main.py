from datetime import datetime

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
        # 1. Run Lighthouse Subprocess
        # 2. Upload 3 PDFs to GCS

        update_audit_status(db, audit_id, AuditStatus.COMPLETED, completed_at=datetime.utcnow())
    except Exception as e:
        update_audit_status(db, audit_id, AuditStatus.FAILED)
        print(f"Audit {audit_id} failed: {e}")
    finally:
        db.close()

@app.post("/api/v1/audit", response_model=AuditResponse, status_code=202)
async def start_website_audit(
    payload: AuditCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    # 1. Create a unique record for this job
    new_audit = create_audit(
        db,
        target_url=str(payload.url),
        client_email=payload.email,
        client_name=payload.client_name,
    )
    
    # 3. Hand off to worker (Non-blocking)
    background_tasks.add_task(run_audit_task, new_audit.id)
    
    # 4. Return immediate ticket to React
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
