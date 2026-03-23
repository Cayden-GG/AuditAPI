from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./storage/valvanta_audits.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_audit_columns()


def _ensure_audit_columns() -> None:
    columns = {
        "seo_report_object": "TEXT",
        "perf_report_object": "TEXT",
        "key_findings_object": "TEXT",
        "accessibility_report_object": "TEXT",
        "audit_json_object": "TEXT",
        "ai_json_object": "TEXT",
        "audit_log_object": "TEXT",
        "tier": "TEXT",
    }
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(audits)")).fetchall()
        }
        for name, col_type in columns.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE audits ADD COLUMN {name} {col_type}"))
        conn.commit()


def create_audit(
    db,
    target_url: str,
    client_email: str,
    client_name: Optional[str] = None,
    tier: str = "free",
):
    from .models import AuditTable, AuditStatus

    audit = AuditTable(
        target_url=target_url,
        client_email=client_email,
        client_name=client_name or "",
        tier=tier,
        status=AuditStatus.PENDING,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def get_audit(db, audit_id: str):
    from .models import AuditTable

    return db.query(AuditTable).filter(AuditTable.id == audit_id).first()


def get_latest_audit_by_target_url(db, target_url: str):
    from .models import AuditStatus, AuditTable

    return (
        db.query(AuditTable)
        .filter(
            AuditTable.target_url == target_url,
            AuditTable.status == AuditStatus.COMPLETED,
        )
        .order_by(AuditTable.completed_at.desc(), AuditTable.created_at.desc())
        .first()
    )


def update_audit_status(db, audit_id: str, status, completed_at: Optional[datetime] = None):
    audit = get_audit(db, audit_id)
    if not audit:
        return None
    audit.status = status
    if completed_at:
        audit.completed_at = completed_at
    db.commit()
    db.refresh(audit)
    return audit


def update_audit_report_objects(db, audit_id: str, **fields):
    audit = get_audit(db, audit_id)
    if not audit:
        return None
    for key, value in fields.items():
        if hasattr(audit, key):
            setattr(audit, key, value)
    db.commit()
    db.refresh(audit)
    return audit

def validate_domain_audit(db, domain: str):
    from .models import AuditTable

    return db.query(AuditTable).filter(
        AuditTable.target_url == str(domain),
        AuditTable.status == "completed"
    ).first()
