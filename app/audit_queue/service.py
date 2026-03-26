from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import text

from app.database import SessionLocal, create_audit, engine, update_audit_status
from app.models import AuditStatus

FREE_MAX_URLS = 5
PAID_MAX_URLS = 100
FREE_TIMEOUT_MS = 30 * 60 * 1000
PAID_TIMEOUT_MS = 120 * 60 * 1000
PAID_SKIP_LIMIT = 5

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"


@dataclass
class DispatchJob:
    job_id: int
    audit_id: str
    tier: str


def _now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def normalize_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    return domain.rstrip("/").lower()


def _max_urls_for_tier(tier: str) -> int:
    return PAID_MAX_URLS if tier == "paid" else FREE_MAX_URLS


def _timeout_ms_for_tier(tier: str) -> int:
    return PAID_TIMEOUT_MS if tier == "paid" else FREE_TIMEOUT_MS


def _timeout_s_for_tier(tier: str) -> int:
    return int(_timeout_ms_for_tier(tier) / 1000)


def _select_next_job(conn, allow_paid: bool) -> Optional[Dict[str, Any]]:
    # Slot selection order matches AUDIT_QUEUE_SPEC.md.
    params: Dict[str, Any] = {}
    if allow_paid:
        paid_skip = conn.execute(
            text(
                """
                SELECT * FROM audit_jobs
                WHERE status = :status
                  AND tier = 'paid'
                  AND skip_count >= :skip_limit
                  AND audit_id IS NOT NULL
                ORDER BY queued_at ASC
                LIMIT 1
                """
            ),
            {"status": STATUS_QUEUED, "skip_limit": PAID_SKIP_LIMIT},
        ).mappings().first()
        if paid_skip:
            return dict(paid_skip)

    free_job = conn.execute(
        text(
            """
            SELECT * FROM audit_jobs
            WHERE status = :status
              AND tier = 'free'
              AND audit_id IS NOT NULL
            ORDER BY queued_at ASC
            LIMIT 1
            """
        ),
        {"status": STATUS_QUEUED},
    ).mappings().first()
    if free_job:
        return dict(free_job)

    if not allow_paid:
        return None

    paid_job = conn.execute(
        text(
            """
            SELECT * FROM audit_jobs
            WHERE status = :status
              AND tier = 'paid'
              AND audit_id IS NOT NULL
            ORDER BY queued_at ASC
            LIMIT 1
            """
        ),
        {"status": STATUS_QUEUED},
    ).mappings().first()
    if paid_job:
        return dict(paid_job)
    return None


def enqueue_job(
    *,
    url: str,
    email: str,
    client_name: Optional[str],
    customer_id: Optional[str],
    tier: str,
    urls: Optional[List[str]],
    order_id: Optional[str] = None,
    callback_url: Optional[str] = None,
    social_links: Optional[List[str]] = None,
) -> Tuple[str, Optional[str]]:
    customer_key = customer_id or email
    domain = normalize_domain(url)
    urls = urls or [url]
    urls_count = len(urls)
    max_urls = _max_urls_for_tier(tier)
    if urls_count > max_urls:
        raise ValueError(f"URL limit exceeded: {urls_count} > {max_urls}")

    job_token = uuid4().hex
    queued_at = _now_ms()

    with engine.begin() as conn:
        # Validation and insert are atomic to avoid race conditions.
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO customers (id, tier, created_at)
                VALUES (:customer_id, :tier, :created_at)
                """
            ),
            {"customer_id": customer_key, "tier": tier, "created_at": queued_at},
        )
        conn.execute(
            text("UPDATE customers SET tier = :tier WHERE id = :customer_id"),
            {"tier": tier, "customer_id": customer_key},
        )

        active_customer = conn.execute(
            text(
                """
                SELECT id FROM audit_jobs
                WHERE customer_id = :customer_id
                  AND status IN ('queued', 'running')
                LIMIT 1
                """
            ),
            {"customer_id": customer_key},
        ).first()
        if active_customer:
            raise ValueError("Customer already has an active job.")

        active_domain = conn.execute(
            text(
                """
                SELECT id FROM audit_jobs
                WHERE domain = :domain
                  AND tier = :tier
                  AND status IN ('queued', 'running')
                LIMIT 1
                """
            ),
            {"domain": domain, "tier": tier},
        ).first()
        if active_domain:
            raise ValueError("Domain already has an active job for this tier.")

        if tier == "free":
            completed_domain = conn.execute(
                text(
                    """
                    SELECT id FROM audit_jobs
                    WHERE domain = :domain
                      AND tier = 'free'
                      AND status = 'completed'
                    LIMIT 1
                    """
                ),
                {"domain": domain},
            ).first()
            if completed_domain:
                raise ValueError("Free audit already completed for this domain.")

        conn.execute(
            text(
                """
                INSERT INTO audit_jobs (
                    job_token,
                    customer_id,
                    domain,
                    tier,
                    urls,
                    status,
                    queued_at
                )
                VALUES (
                    :job_token,
                    :customer_id,
                    :domain,
                    :tier,
                    :urls,
                    :status,
                    :queued_at
                )
                """
            ),
            {
                "job_token": job_token,
                "customer_id": customer_key,
                "domain": domain,
                "tier": tier,
                "urls": json.dumps(urls),
                "status": STATUS_QUEUED,
                "queued_at": queued_at,
            },
        )

    audit_id: Optional[str] = None
    try:
        # Create the audit record immediately so the queue job can reference it.
        db = SessionLocal()
        audit = create_audit(
            db,
            target_url=str(url),
            client_email=email,
            client_name=client_name,
            tier=tier,
            order_id=order_id,
            callback_url=callback_url,
            social_links=social_links,
        )
        audit_id = audit.id
    finally:
        db.close()

    if audit_id:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE audit_jobs SET audit_id = :audit_id WHERE job_token = :job_token"),
                {"audit_id": audit_id, "job_token": job_token},
            )
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE audit_jobs
                    SET status = :status,
                        completed_at = :completed_at
                    WHERE job_token = :job_token
                    """
                ),
                {"status": STATUS_FAILED, "completed_at": _now_ms(), "job_token": job_token},
            )

    return job_token, audit_id


def dispatch_jobs() -> List[DispatchJob]:
    jobs_to_start: List[DispatchJob] = []
    with engine.begin() as conn:
        slots = conn.execute(
            text("SELECT slot_id, job_id FROM runner_slots ORDER BY slot_id")
        ).mappings().all()
        free_slots = [slot for slot in slots if slot["job_id"] is None]
        if not free_slots:
            return jobs_to_start

        # If any paid job is running, the other slot becomes free-only.
        paid_running = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM audit_jobs
                WHERE id IN (SELECT job_id FROM runner_slots WHERE job_id IS NOT NULL)
                  AND status = :status
                  AND tier = 'paid'
                """
            ),
            {"status": STATUS_RUNNING},
        ).scalar()
        paid_running = bool(paid_running)

        for slot in free_slots:
            allow_paid = not paid_running
            job = _select_next_job(conn, allow_paid=allow_paid)
            if not job:
                continue

            if job["tier"] == "free":
                # Free job jumped ahead; increment skip counts for older paid jobs.
                conn.execute(
                    text(
                        """
                        UPDATE audit_jobs
                        SET skip_count = skip_count + 1
                        WHERE status = :status
                          AND tier = 'paid'
                          AND queued_at < :queued_at
                        """
                    ),
                    {"status": STATUS_QUEUED, "queued_at": job["queued_at"]},
                )

            started_at = _now_ms()
            timeout_at = started_at + _timeout_ms_for_tier(job["tier"])
            conn.execute(
                text(
                    """
                    UPDATE audit_jobs
                    SET status = :status,
                        started_at = :started_at,
                        timeout_at = :timeout_at
                    WHERE id = :id
                    """
                ),
                {
                    "status": STATUS_RUNNING,
                    "started_at": started_at,
                    "timeout_at": timeout_at,
                    "id": job["id"],
                },
            )
            conn.execute(
                text("UPDATE runner_slots SET job_id = :job_id WHERE slot_id = :slot_id"),
                {"job_id": job["id"], "slot_id": slot["slot_id"]},
            )
            jobs_to_start.append(
                DispatchJob(job_id=job["id"], audit_id=job["audit_id"], tier=job["tier"])
            )
            if job["tier"] == "paid":
                paid_running = True

    return jobs_to_start


def mark_job_complete(job_id: int, status: str, result_path: Optional[str]) -> None:
    completed_at = _now_ms()
    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT status FROM audit_jobs WHERE id = :job_id"),
            {"job_id": job_id},
        ).scalar()
        if current != STATUS_RUNNING:
            return
        conn.execute(
            text(
                """
                UPDATE audit_jobs
                SET status = :status,
                    completed_at = :completed_at,
                    result_path = :result_path
                WHERE id = :job_id
                """
            ),
            {
                "status": status,
                "completed_at": completed_at,
                "result_path": result_path,
                "job_id": job_id,
            },
        )
        conn.execute(
            text("UPDATE runner_slots SET job_id = NULL WHERE job_id = :job_id"),
            {"job_id": job_id},
        )


def watchdog_timeouts() -> int:
    now_ms = _now_ms()
    timed_out: List[Tuple[int, Optional[str]]] = []
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, audit_id FROM audit_jobs
                WHERE status = :status
                  AND timeout_at IS NOT NULL
                  AND timeout_at < :now
                """
            ),
            {"status": STATUS_RUNNING, "now": now_ms},
        ).mappings().all()

        for row in rows:
            timed_out.append((row["id"], row.get("audit_id")))

        if timed_out:
            conn.execute(
                text(
                    """
                    UPDATE audit_jobs
                    SET status = :status,
                        completed_at = :completed_at
                    WHERE status = :running
                      AND timeout_at IS NOT NULL
                      AND timeout_at < :now
                    """
                ),
                {
                    "status": STATUS_TIMEOUT,
                    "completed_at": now_ms,
                    "running": STATUS_RUNNING,
                    "now": now_ms,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE runner_slots
                    SET job_id = NULL
                    WHERE job_id IN (
                        SELECT id FROM audit_jobs
                        WHERE status = :status
                          AND completed_at = :completed_at
                    )
                    """
                ),
                {"status": STATUS_TIMEOUT, "completed_at": now_ms},
            )

    if timed_out:
        # Mirror queue timeouts into the main audit table.
        db = SessionLocal()
        try:
            for _, audit_id in timed_out:
                if audit_id:
                    update_audit_status(db, audit_id, AuditStatus.FAILED, completed_at=datetime.utcnow())
        finally:
            db.close()
    return len(timed_out)


def start_dispatcher(background_launcher) -> None:
    jobs = dispatch_jobs()
    for job in jobs:
        background_launcher(job)


def run_queue_job(job: DispatchJob) -> None:
    from app.main import run_audit_task

    tier = job.tier
    only_categories = "performance,seo,accessibility" if tier == "paid" else "performance,seo"
    max_urls = _max_urls_for_tier(tier)
    timeout_s = _timeout_s_for_tier(tier)
    # Use audit runner to keep report generation/emails consistent.
    result = run_audit_task(
        job.audit_id,
        max_urls=max_urls,
        only_categories=only_categories,
        tier=tier,
        timeout_s=timeout_s,
    ) or {}
    status = STATUS_COMPLETED if result.get("status") == "completed" else STATUS_FAILED
    if result.get("status") == "timeout":
        status = STATUS_TIMEOUT
    report_paths = result.get("report_paths") or []
    result_path = str(report_paths[0]) if report_paths else None
    mark_job_complete(job.job_id, status, result_path)


def queue_status(job_token: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        job = conn.execute(
            text("SELECT * FROM audit_jobs WHERE job_token = :job_token"),
            {"job_token": job_token},
        ).mappings().first()
        if not job:
            return None
        job = dict(job)
        if job["status"] == STATUS_QUEUED:
            pos_in_q = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM audit_jobs
                    WHERE status = :status
                      AND queued_at < :queued_at
                    """
                ),
                {"status": STATUS_QUEUED, "queued_at": job["queued_at"]},
            ).scalar()
            job["queue_position"] = int(pos_in_q or 0)
        else:
            job["queue_position"] = None
        return job


def launch_job_in_thread(job: DispatchJob) -> None:
    thread = threading.Thread(target=run_queue_job, args=(job,), daemon=True)
    thread.start()
