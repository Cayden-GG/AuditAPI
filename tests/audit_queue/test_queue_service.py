import itertools

import pytest
from sqlalchemy import text

from app.audit_queue import service
from app.audit_queue.service import (
    DispatchJob,
    dispatch_jobs,
    enqueue_job,
    mark_job_complete,
    normalize_domain,
    queue_status,
    run_queue_job,
    start_dispatcher,
    watchdog_timeouts,
)
from app.database import get_audit
from app.models import AuditStatus

_counter = itertools.count(1)


@pytest.fixture(autouse=True)
def _queue_db(isolated_db):
    """Every queue test runs against the isolated database"""
    return isolated_db


def enqueue(tier="free", url=None, email=None, **kwargs):
    """Enqueues a job with a unique customer and domain unless told otherwise. Returns (job_token, audit_id)"""
    n = next(_counter)
    return enqueue_job(
        url=url or f"https://site{n}.example.com",
        email=email or f"user{n}@example.com",
        client_name="Client",
        customer_id=kwargs.pop("customer_id", None),
        tier=tier,
        urls=kwargs.pop("urls", None),
        **kwargs,
    )


def job_row(engine, job_token):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM audit_jobs WHERE job_token = :t"), {"t": job_token}).mappings().one())


def update_job(engine, job_token, **fields):
    sets = ", ".join(f"{name} = :{name}" for name in fields)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE audit_jobs SET {sets} WHERE job_token = :t"), {**fields, "t": job_token})


def slots(engine):
    with engine.connect() as conn:
        return {r["slot_id"]: r["job_id"] for r in conn.execute(text("SELECT * FROM runner_slots")).mappings()}


def start(engine, tier="free", **kwargs):
    """Enqueues a job and dispatches it so it is running. Returns (job_token, audit_id, DispatchJob)"""
    token, audit_id = enqueue(tier, **kwargs)
    jobs = dispatch_jobs()
    return token, audit_id, next(j for j in jobs if j.audit_id == audit_id)


# normalize_domain and tier limits

@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://Example.com", "example.com"),
        ("https://example.com/", "example.com"),
        ("https://example.com/some/path", "example.com"),
        ("http://sub.Example.COM", "sub.example.com"),
        ("example.com", "example.com"),
        ("example.com/", "example.com"),
    ],
)
def test_normalize_domain(url, expected):
    assert normalize_domain(url) == expected


def test_tier_limits():
    assert service._max_urls_for_tier("free") == 5
    assert service._max_urls_for_tier("paid") == 100
    assert service._timeout_ms_for_tier("free") == 30 * 60 * 1000
    assert service._timeout_ms_for_tier("paid") == 120 * 60 * 1000
    assert service._timeout_s_for_tier("free") == 1800
    assert service._timeout_s_for_tier("paid") == 7200


# enqueue_job

def test_enqueue_creates_queued_job_and_audit(isolated_db, db):
    token, audit_id = enqueue("free", url="https://Example.com/", email="a@example.com")

    row = job_row(isolated_db, token)
    assert row["status"] == "queued"
    assert row["tier"] == "free"
    assert row["domain"] == "example.com"
    assert row["customer_id"] == "a@example.com"
    assert row["audit_id"] == audit_id

    audit = get_audit(db, audit_id)
    assert audit.status == AuditStatus.PENDING
    assert audit.client_email == "a@example.com"


def test_enqueue_stores_paid_details_on_the_audit(db):
    _, audit_id = enqueue(
        "paid", order_id="ord-1", callback_url="https://cb.example.com/hook", social_links=["https://x.com/a"], debug_mode=True
    )

    audit = get_audit(db, audit_id)
    assert audit.tier == "paid"
    assert audit.order_id == "ord-1"
    assert audit.callback_url == "https://cb.example.com/hook"
    assert audit.social_links == '["https://x.com/a"]'
    assert audit.debug_mode is True


def test_enqueue_prefers_customer_id_over_email(isolated_db):
    token, _ = enqueue(customer_id="cust-9", email="a@example.com")

    assert job_row(isolated_db, token)["customer_id"] == "cust-9"


@pytest.mark.parametrize("tier, limit", [("free", 5), ("paid", 100)])
def test_enqueue_url_limit(tier, limit):
    urls = [f"https://x.example.com/{i}" for i in range(limit)]
    enqueue(tier, urls=urls)

    with pytest.raises(ValueError, match="URL limit exceeded"):
        enqueue(tier, urls=urls + ["https://x.example.com/extra"])


def test_enqueue_rejects_customer_with_active_job():
    enqueue(email="same@example.com")

    with pytest.raises(ValueError, match="Customer already has an active job"):
        enqueue(email="same@example.com")


def test_enqueue_rejects_domain_with_active_job_for_same_tier():
    enqueue(url="https://shared.example.com")

    with pytest.raises(ValueError, match="Domain already has an active job"):
        enqueue(url="https://SHARED.example.com/page")


def test_enqueue_allows_same_domain_for_different_tiers():
    enqueue("free", url="https://shared.example.com")

    token, audit_id = enqueue("paid", url="https://shared.example.com")

    assert token and audit_id


def test_enqueue_rejects_free_audit_when_domain_already_completed(isolated_db):
    token, _, job = start(isolated_db, url="https://done.example.com")
    mark_job_complete(job.job_id, "completed", None)

    with pytest.raises(ValueError, match="Free audit already completed"):
        enqueue("free", url="https://done.example.com")


def test_enqueue_allows_paid_after_free_completed_and_free_after_failure(isolated_db):
    token, _, job = start(isolated_db, url="https://done.example.com")
    mark_job_complete(job.job_id, "completed", None)
    enqueue("paid", url="https://done.example.com")

    token, _, job = start(isolated_db, url="https://failed.example.com")
    mark_job_complete(job.job_id, "failed", None)
    enqueue("free", url="https://failed.example.com")


def test_finished_job_does_not_block_the_customer(isolated_db):
    _, _, job = start(isolated_db, email="same@example.com")
    mark_job_complete(job.job_id, "failed", None)

    enqueue(email="same@example.com")


# dispatch_jobs

def test_dispatch_with_nothing_queued_starts_nothing():
    assert dispatch_jobs() == []


def test_dispatch_marks_job_running_and_assigns_a_slot(isolated_db):
    token, audit_id = enqueue("free")

    jobs = dispatch_jobs()

    row = job_row(isolated_db, token)
    assert jobs == [DispatchJob(job_id=row["id"], audit_id=audit_id, tier="free")]
    assert row["status"] == "running"
    assert row["timeout_at"] - row["started_at"] == 30 * 60 * 1000
    assert list(slots(isolated_db).values()).count(row["id"]) == 1


def test_paid_jobs_get_the_longer_timeout(isolated_db):
    token, _, _ = start(isolated_db, tier="paid")

    row = job_row(isolated_db, token)
    assert row["timeout_at"] - row["started_at"] == 120 * 60 * 1000


def test_dispatch_never_runs_more_than_two_jobs(isolated_db):
    for _ in range(3):
        enqueue("free")

    assert len(dispatch_jobs()) == 2
    assert dispatch_jobs() == []


def test_dispatch_takes_oldest_free_job_first(isolated_db):
    newer, _ = enqueue("free")
    older, _ = enqueue("free")
    update_job(isolated_db, newer, queued_at=2000)
    update_job(isolated_db, older, queued_at=1000)
    third, _ = enqueue("free")
    update_job(isolated_db, third, queued_at=3000)

    dispatch_jobs()

    assert job_row(isolated_db, older)["status"] == "running"
    assert job_row(isolated_db, newer)["status"] == "running"
    assert job_row(isolated_db, third)["status"] == "queued"


def test_free_jobs_run_before_older_paid_jobs(isolated_db):
    paid, _ = enqueue("paid")
    free, _ = enqueue("free")
    update_job(isolated_db, paid, queued_at=1000)
    update_job(isolated_db, free, queued_at=2000)

    jobs = dispatch_jobs()

    assert [j.tier for j in jobs] == ["free", "paid"]


def test_free_job_jumping_ahead_increments_skip_count_of_older_paid_jobs(isolated_db):
    paid, _ = enqueue("paid")
    free, _ = enqueue("free")
    update_job(isolated_db, paid, queued_at=1000)
    update_job(isolated_db, free, queued_at=2000)
    # a second free job fills the other slot, paid has no slot left
    extra, _ = enqueue("free")
    update_job(isolated_db, extra, queued_at=3000)

    dispatch_jobs()

    assert job_row(isolated_db, paid)["status"] == "queued"
    assert job_row(isolated_db, paid)["skip_count"] == 2


def test_paid_job_skipped_five_times_goes_first(isolated_db):
    paid, _ = enqueue("paid")
    free, _ = enqueue("free")
    update_job(isolated_db, paid, queued_at=1000, skip_count=5)
    update_job(isolated_db, free, queued_at=2000)

    jobs = dispatch_jobs()

    assert [j.tier for j in jobs] == ["paid", "free"]


def test_only_one_paid_job_runs_at_a_time(isolated_db):
    first, _ = enqueue("paid")
    second, _ = enqueue("paid")
    update_job(isolated_db, first, queued_at=1000)
    update_job(isolated_db, second, queued_at=2000)

    jobs = dispatch_jobs()

    assert len(jobs) == 1
    assert job_row(isolated_db, first)["status"] == "running"
    assert job_row(isolated_db, second)["status"] == "queued"


def test_second_slot_stays_free_only_while_a_paid_job_runs(isolated_db):
    start(isolated_db, tier="paid")
    paid_waiting, _ = enqueue("paid")
    assert dispatch_jobs() == []

    free, _ = enqueue("free")
    jobs = dispatch_jobs()

    assert [j.tier for j in jobs] == ["free"]
    assert job_row(isolated_db, paid_waiting)["status"] == "queued"


def test_jobs_without_an_audit_id_are_never_dispatched(isolated_db):
    token, _ = enqueue("free")
    update_job(isolated_db, token, audit_id=None)

    assert dispatch_jobs() == []


def test_start_dispatcher_launches_every_dispatched_job():
    enqueue("free")
    enqueue("free")
    launched = []

    start_dispatcher(launched.append)

    assert len(launched) == 2
    assert all(isinstance(j, DispatchJob) for j in launched)


# mark_job_complete

def test_mark_job_complete_records_result_and_frees_the_slot(isolated_db):
    token, _, job = start(isolated_db)

    mark_job_complete(job.job_id, "completed", "audit_results/report.pdf")

    row = job_row(isolated_db, token)
    assert row["status"] == "completed"
    assert row["result_path"] == "audit_results/report.pdf"
    assert row["completed_at"] is not None
    assert job.job_id not in slots(isolated_db).values()


def test_mark_job_complete_ignores_jobs_that_are_not_running(isolated_db):
    queued, _ = enqueue("free")
    mark_job_complete(job_row(isolated_db, queued)["id"], "completed", "x.pdf")
    assert job_row(isolated_db, queued)["status"] == "queued"

    token, _, job = start(isolated_db)
    mark_job_complete(job.job_id, "timeout", None)
    mark_job_complete(job.job_id, "completed", "late.pdf")

    row = job_row(isolated_db, token)
    assert row["status"] == "timeout"
    assert row["result_path"] is None


# watchdog_timeouts

def test_watchdog_times_out_overdue_jobs(isolated_db, db):
    token, audit_id, job = start(isolated_db)
    update_job(isolated_db, token, timeout_at=1)

    assert watchdog_timeouts() == 1

    assert job_row(isolated_db, token)["status"] == "timeout"
    assert job.job_id not in slots(isolated_db).values()
    db.expire_all()
    assert get_audit(db, audit_id).status == AuditStatus.FAILED


def test_watchdog_leaves_jobs_within_their_timeout_alone(isolated_db):
    token, _, job = start(isolated_db)

    assert watchdog_timeouts() == 0

    assert job_row(isolated_db, token)["status"] == "running"
    assert job.job_id in slots(isolated_db).values()


def test_watchdog_ignores_queued_jobs(isolated_db):
    token, _ = enqueue("free")
    update_job(isolated_db, token, timeout_at=1)

    assert watchdog_timeouts() == 0


def test_watchdog_only_times_out_the_overdue_job(isolated_db):
    overdue, _, _ = start(isolated_db)
    healthy, _, healthy_job = start(isolated_db)
    update_job(isolated_db, overdue, timeout_at=1)

    assert watchdog_timeouts() == 1

    assert job_row(isolated_db, healthy)["status"] == "running"
    assert healthy_job.job_id in slots(isolated_db).values()


# queue_status

def test_queue_status_unknown_token():
    assert queue_status("nope") is None


def test_queue_status_reports_position_among_queued_jobs(isolated_db):
    tokens = [enqueue("free")[0] for _ in range(3)]
    for i, token in enumerate(tokens):
        update_job(isolated_db, token, queued_at=1000 + i)

    assert [queue_status(t)["queue_position"] for t in tokens] == [0, 1, 2]


def test_queue_status_has_no_position_once_running(isolated_db):
    token, _, _ = start(isolated_db)

    status = queue_status(token)

    assert status["status"] == "running"
    assert status["queue_position"] is None


# run_queue_job

@pytest.mark.parametrize(
    "result, expected_status, expected_path",
    [
        ({"status": "completed", "report_paths": ["a.pdf", "b.pdf"]}, "completed", "a.pdf"),
        ({"status": "completed"}, "completed", None),
        ({"status": "failed"}, "failed", None),
        ({"status": "timeout"}, "timeout", None),
        (None, "failed", None),
    ],
)
def test_run_queue_job_records_the_audit_outcome(isolated_db, monkeypatch, result, expected_status, expected_path):
    token, audit_id, job = start(isolated_db)
    calls = []

    def fake_run_audit_task(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr("app.main.run_audit_task", fake_run_audit_task)

    run_queue_job(job)

    row = job_row(isolated_db, token)
    assert row["status"] == expected_status
    assert row["result_path"] == expected_path
    assert calls[0][0] == (audit_id,)


@pytest.mark.parametrize(
    "tier, categories, max_urls, timeout_s",
    [("free", "performance,seo", 5, 1800), ("paid", "performance,seo,accessibility", 100, 7200)],
)
def test_run_queue_job_applies_tier_limits(isolated_db, monkeypatch, tier, categories, max_urls, timeout_s):
    _, _, job = start(isolated_db, tier=tier)
    calls = []
    monkeypatch.setattr("app.main.run_audit_task", lambda *a, **kw: calls.append(kw) or {"status": "completed"})

    run_queue_job(job)

    assert calls[0] == {
        "max_urls": max_urls,
        "only_categories": categories,
        "tier": tier,
        "timeout_s": timeout_s,
    }
