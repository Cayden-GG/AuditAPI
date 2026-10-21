from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from app import database
from app.database import (
    create_audit,
    get_audit,
    get_db,
    get_latest_audit_by_target_url,
    init_db,
    update_audit_report_objects,
    update_audit_status,
    validate_domain_audit,
)
from app.models import AuditStatus

URL = "https://example.com/"


def new_audit(db, **kwargs):
    kwargs.setdefault("target_url", URL)
    kwargs.setdefault("client_email", "client@example.com")
    return create_audit(db, **kwargs)


# create_audit / get_audit

def test_create_audit_defaults(db):
    audit = new_audit(db)

    assert audit.id
    assert audit.status == AuditStatus.PENDING
    assert audit.tier == "free"
    assert audit.client_name == ""
    assert audit.debug_mode is False
    assert audit.social_links is None
    assert audit.callback_url is None
    assert audit.created_at is not None
    assert audit.completed_at is None


def test_create_audit_stores_every_field(db):
    audit = new_audit(
        db,
        client_name="Acme",
        tier="paid",
        order_id="o-1",
        callback_url="https://shop.example.com/hook",
        social_links=["https://x.com/a", "https://y.com/b"],
        debug_mode=True,
    )

    fetched = get_audit(db, audit.id)
    assert fetched.client_name == "Acme"
    assert fetched.tier == "paid"
    assert fetched.order_id == "o-1"
    assert fetched.callback_url == "https://shop.example.com/hook"
    assert fetched.social_links == '["https://x.com/a", "https://y.com/b"]'
    assert fetched.debug_mode is True


def test_create_audit_empty_social_links_are_not_stored(db):
    assert new_audit(db, social_links=[]).social_links is None


def test_audit_ids_are_unique(db):
    assert new_audit(db).id != new_audit(db).id


def test_get_audit_unknown_id(db):
    assert get_audit(db, "missing") is None


# update_audit_status

def test_update_audit_status_sets_status_and_completed_at(db):
    audit = new_audit(db)
    done = datetime(2026, 1, 2, 3, 4, 5)

    updated = update_audit_status(db, audit.id, AuditStatus.COMPLETED, completed_at=done)

    assert updated.status == AuditStatus.COMPLETED
    assert get_audit(db, audit.id).completed_at == done


def test_update_audit_status_leaves_completed_at_alone_when_not_given(db):
    audit = new_audit(db)
    done = datetime(2026, 1, 2, 3, 4, 5)
    update_audit_status(db, audit.id, AuditStatus.COMPLETED, completed_at=done)

    update_audit_status(db, audit.id, AuditStatus.FAILED)

    fetched = get_audit(db, audit.id)
    assert fetched.status == AuditStatus.FAILED
    assert fetched.completed_at == done


def test_update_audit_status_unknown_id(db):
    assert update_audit_status(db, "missing", AuditStatus.FAILED) is None


# update_audit_report_objects

def test_update_report_objects_sets_columns_and_ignores_unknown_fields(db):
    audit = new_audit(db)

    updated = update_audit_report_objects(
        db, audit.id, seo_report_object="a/seo.pdf", ai_json_object="a/ai.json", not_a_column="ignored"
    )

    assert updated.seo_report_object == "a/seo.pdf"
    assert updated.ai_json_object == "a/ai.json"
    assert not hasattr(updated, "not_a_column")


def test_update_report_objects_keeps_existing_values(db):
    audit = new_audit(db)
    update_audit_report_objects(db, audit.id, seo_report_object="a/seo.pdf")

    update_audit_report_objects(db, audit.id, perf_report_object="a/perf.pdf")

    fetched = get_audit(db, audit.id)
    assert fetched.seo_report_object == "a/seo.pdf"
    assert fetched.perf_report_object == "a/perf.pdf"


def test_update_report_objects_unknown_id(db):
    assert update_audit_report_objects(db, "missing", seo_report_object="x") is None


# get_latest_audit_by_target_url

def complete(db, audit, completed_at):
    update_audit_status(db, audit.id, AuditStatus.COMPLETED, completed_at=completed_at)


def test_latest_audit_is_the_most_recently_completed(db):
    base = datetime(2026, 1, 1)
    old = new_audit(db)
    new = new_audit(db)
    complete(db, new, base + timedelta(days=2))
    complete(db, old, base + timedelta(days=1))

    assert get_latest_audit_by_target_url(db, URL).id == new.id


@pytest.mark.parametrize("status", [AuditStatus.PENDING, AuditStatus.PROCESSING, AuditStatus.FAILED])
def test_latest_audit_ignores_unfinished_audits(db, status):
    audit = new_audit(db)
    update_audit_status(db, audit.id, status)

    assert get_latest_audit_by_target_url(db, URL) is None


def test_latest_audit_only_matches_the_exact_url(db):
    audit = new_audit(db, target_url="https://other.example.com/")
    complete(db, audit, datetime(2026, 1, 1))

    assert get_latest_audit_by_target_url(db, URL) is None
    assert get_latest_audit_by_target_url(db, "https://other.example.com/").id == audit.id


# validate_domain_audit

def test_validate_domain_audit_finds_a_completed_audit(db):
    audit = new_audit(db)
    complete(db, audit, datetime(2026, 1, 1))

    assert validate_domain_audit(db, URL).id == audit.id


def test_validate_domain_audit_ignores_unfinished_and_other_urls(db):
    new_audit(db)
    other = new_audit(db, target_url="https://other.example.com/")
    complete(db, other, datetime(2026, 1, 1))

    assert validate_domain_audit(db, URL) is None


# get_db

def test_get_db_yields_a_session_and_closes_it(isolated_db):
    generator = get_db()
    session = next(generator)

    assert session.execute(text("SELECT 1")).scalar() == 1
    with pytest.raises(StopIteration):
        next(generator)


# schema setup and migrations

def table_columns(engine, table):
    with engine.connect() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def test_init_db_creates_every_table_and_the_two_runner_slots(isolated_db):
    with isolated_db.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
        slot_ids = [r[0] for r in conn.execute(text("SELECT slot_id FROM runner_slots ORDER BY slot_id"))]

    assert {"audits", "customers", "audit_jobs", "runner_slots"} <= tables
    assert slot_ids == [1, 2]


def test_init_db_is_idempotent_and_keeps_runner_assignments(isolated_db):
    with isolated_db.begin() as conn:
        conn.execute(text("UPDATE runner_slots SET job_id = 7 WHERE slot_id = 1"))

    init_db()
    init_db()

    with isolated_db.connect() as conn:
        rows = conn.execute(text("SELECT slot_id, job_id FROM runner_slots ORDER BY slot_id")).fetchall()
    assert [tuple(r) for r in rows] == [(1, 7), (2, None)]


def test_ensure_audit_columns_adds_missing_columns_to_an_old_table(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE audits (id TEXT PRIMARY KEY, target_url TEXT, seo_report_object TEXT)"))
        conn.execute(text("INSERT INTO audits (id, target_url) VALUES ('a1', 'https://old.example.com')"))
    monkeypatch.setattr(database, "engine", engine)

    database._ensure_audit_columns()
    database._ensure_audit_columns()

    assert {
        "perf_report_object", "key_findings_object", "accessibility_report_object", "audit_json_object",
        "ai_json_object", "audit_log_object", "tier", "order_id", "callback_url", "social_links", "debug_mode",
    } <= table_columns(engine, "audits")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT target_url FROM audits WHERE id = 'a1'")).scalar() == "https://old.example.com"
    engine.dispose()
