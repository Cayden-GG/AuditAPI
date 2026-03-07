from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# This creates a file named 'valvanta_audits.db' in your project folder
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


def create_audit(db, target_url: str, client_email: str, client_name: Optional[str] = None):
    from .models import AuditTable, AuditStatus

    audit = AuditTable(
        target_url=target_url,
        client_email=client_email,
        client_name=client_name or "",
        status=AuditStatus.PENDING,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def get_audit(db, audit_id: str):
    from .models import AuditTable

    return db.query(AuditTable).filter(AuditTable.id == audit_id).first()


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
