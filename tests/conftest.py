import json
import os
import sys
from types import SimpleNamespace

# This adds the parent directory (AuditAPI) to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# app.audit_service.ai.request builds an OpenAI client at import time
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Points the app at a throwaway sqlite database so tests never touch storage/"""
    import app.audit_queue.service as queue_service
    import app.database as database

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(queue_service, "engine", engine)
    # SessionLocal is imported by name in several modules, so rebind it in place rather than replacing it
    monkeypatch.setattr(database.SessionLocal, "kw", {**database.SessionLocal.kw, "bind": engine})

    database.Base.metadata.create_all(bind=engine)
    database.init_db()

    yield engine
    engine.dispose()


@pytest.fixture
def db(isolated_db):
    """A session on the isolated database"""
    from app.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(isolated_db, monkeypatch):
    """TestClient with rate limiting off. Not used as a context manager, so startup (queue worker) never runs"""
    import app.main as main

    monkeypatch.setattr(main, "_rate_limiter", None)
    return TestClient(main.app)


@pytest.fixture
def fake_gcs(monkeypatch):
    """Replaces GCS upload and download everywhere they are imported. Calls are recorded on the returned object"""
    state = SimpleNamespace(uploads=[], downloads=[], download_result={})

    def upload_files(*args, **kwargs):
        state.uploads.append((args, kwargs))
        return {}

    def download_objects(*args, **kwargs):
        state.downloads.append((args, kwargs))
        return state.download_result

    monkeypatch.setattr("app.main.upload_files", upload_files)
    monkeypatch.setattr("app.routes.audit.upload_files", upload_files)
    monkeypatch.setattr("app.routes.audit.download_objects", download_objects)
    return state


class _FakeHTTPResponse:
    def __init__(self, status=201, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_brevo(monkeypatch):
    """Intercepts the urllib calls Brevo is sent through. Requests are recorded in .requests as parsed json.

    Set .status to simulate Brevo rejecting a call
    """
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_SENDER_NAME", "Test Sender")
    monkeypatch.setenv("BREVO_COMPANY_EMAIL", "company@example.com")
    monkeypatch.setenv("BREVO_AUDIT_SIGNUP_LIST_ID", "1")
    monkeypatch.setenv("BREVO_NEWSLETTER_SIGNUP_LIST_ID", "2")

    state = SimpleNamespace(requests=[], status=201)

    def urlopen(req, timeout=None):
        state.requests.append(
            SimpleNamespace(url=req.full_url, payload=json.loads(req.data) if req.data else None)
        )
        return _FakeHTTPResponse(status=state.status)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return state


@pytest.fixture
def fake_openai(monkeypatch):
    """Replaces the OpenAI client used by the AI summary step. Set .parsed to the object the model should return

    Set .error to make the call raise
    """
    state = SimpleNamespace(parsed=None, error=None, calls=[])

    def parse(**kwargs):
        state.calls.append(kwargs)
        if state.error:
            raise state.error
        message = SimpleNamespace(parsed=state.parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    monkeypatch.setattr("app.audit_service.ai.request.client", fake_client)
    return state
