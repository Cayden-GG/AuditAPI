"""
Database
SQLite engine and session setup, schema migrations for the audit and queue tables and audit record queries
"""
from datetime import datetime
import json
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
    """FastAPI dependency that yields a database session and closes it after the request"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates any missing tables and adds any missing audit columns and queue tables"""
    Base.metadata.create_all(bind=engine)
    _ensure_audit_columns()
    _ensure_queue_tables()


def _ensure_audit_columns() -> None:
    """Adds the audits table columns introduced after the table was first created, if they are missing"""
    columns = {
        "seo_report_object": "TEXT",
        "perf_report_object": "TEXT",
        "key_findings_object": "TEXT",
        "accessibility_report_object": "TEXT",
        "audit_json_object": "TEXT",
        "ai_json_object": "TEXT",
        "audit_log_object": "TEXT",
        "tier": "TEXT",
        "order_id": "TEXT",
        "callback_url": "TEXT",
        "social_links": "TEXT",
        "debug_mode": "INTEGER",
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


def _ensure_queue_tables() -> None:
    """Creates the queue tables and indexes if missing and seeds the two runner slots"""
    table_sql = [
        """
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            tier TEXT NOT NULL,
            created_at INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_token TEXT NOT NULL UNIQUE,
            customer_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            tier TEXT NOT NULL,
            urls TEXT NOT NULL,
            status TEXT NOT NULL,
            skip_count INTEGER DEFAULT 0,
            queued_at INTEGER NOT NULL,
            started_at INTEGER,
            completed_at INTEGER,
            timeout_at INTEGER,
            result_path TEXT,
            audit_id TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS runner_slots (
            slot_id INTEGER PRIMARY KEY,
            job_id INTEGER,
            FOREIGN KEY(job_id) REFERENCES audit_jobs(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_jobs_status_tier ON audit_jobs (status, tier, queued_at)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_customer ON audit_jobs (customer_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_domain_tier ON audit_jobs (domain, tier, status)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_timeout ON audit_jobs (status, timeout_at)",
    ]

    with engine.connect() as conn:
        for statement in table_sql:
            conn.execute(text(statement))
        conn.execute(text("INSERT OR IGNORE INTO runner_slots (slot_id, job_id) VALUES (1, NULL)"))
        conn.execute(text("INSERT OR IGNORE INTO runner_slots (slot_id, job_id) VALUES (2, NULL)"))
        conn.commit()


def create_audit(
    db,
    target_url: str,
    client_email: str,
    client_name: Optional[str] = None,
    tier: str = "free",
    order_id: Optional[str] = None,
    callback_url: Optional[str] = None,
    social_links: Optional[list[str]] = None,
    debug_mode: Optional[bool] = None,
):
    """
    Creates a pending audit record

    @Args:
        db (Session) -- database session
        target_url (str) -- website url to audit
        client_email (str) -- client email
        client_name (Optional[str]) -- client name
        tier (str) -- free | paid
        order_id (Optional[str]) -- paid order id
        callback_url (Optional[str]) -- url notified when the audit completes
        social_links (Optional[list[str]]) -- client social links, stored as json
        debug_mode (Optional[bool]) -- if true the AI request is skipped

    @Returns:
        created audit (AuditTable)
    """
    from .models import AuditTable, AuditStatus

    social_links_payload = None
    if social_links:
        social_links_payload = json.dumps(social_links)

    audit = AuditTable(
        target_url=target_url,
        client_email=client_email,
        client_name=client_name or "",
        tier=tier,
        status=AuditStatus.PENDING,
        order_id=order_id,
        callback_url=str(callback_url) if callback_url else None,
        social_links=social_links_payload,
        debug_mode=bool(debug_mode) if debug_mode is not None else False,
    )

    db.add(audit)
    db.commit()
    db.refresh(audit)
    
    return audit


def get_audit(db, audit_id: str):
    """Gets an audit by id

    @Args:
        db (Session) -- database session
        audit_id (str) -- audit id

    @Returns:
        audit, None if not found (Optional[AuditTable])
    """
    from .models import AuditTable

    return db.query(AuditTable).filter(AuditTable.id == audit_id).first()


def get_latest_audit_by_target_url(db, target_url: str):
    """Gets the most recently completed audit for a url

    @Args:
        db (Session) -- database session
        target_url (str) -- audited website url

    @Returns:
        latest completed audit, None if there is none (Optional[AuditTable])
    """
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
    """Updates an audit's status and optionally its completion time

    @Args:
        db (Session) -- database session
        audit_id (str) -- audit id
        status (AuditStatus) -- new status
        completed_at (Optional[datetime]) -- completion time, left unchanged if not provided

    @Returns:
        updated audit, None if not found (Optional[AuditTable])
    """
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
    """Updates an audit's report object fields, fields that are not audit columns are ignored

    @Args:
        db (Session) -- database session
        audit_id (str) -- audit id
        fields (Any) -- column values to set, e.g. seo_report_object

    @Returns:
        updated audit, None if not found (Optional[AuditTable])
    """
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
    """Finds a completed audit for the domain, used to check if it was already audited

    @Args:
        db (Session) -- database session
        domain (str) -- website url or domain, matched against the audits' target url

    @Returns:
        completed audit, None if there is none (Optional[AuditTable])
    """
    from .models import AuditTable

    return db.query(AuditTable).filter(
        AuditTable.target_url == str(domain),
        AuditTable.status == "completed"
    ).first()
