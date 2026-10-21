from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import RateLimiter


def test_rate_limit_applies_to_api_endpoints(monkeypatch):
    monkeypatch.setattr("app.main._rate_limit_max", 2)
    monkeypatch.setattr("app.main._rate_limit_window", 60)
    monkeypatch.setattr("app.main._rate_limiter", RateLimiter(2, 60))

    client = TestClient(app)
    headers = {"x-forwarded-for": "1.2.3.4"}

    first = client.get("/api/v1/status/does-not-exist", headers=headers)
    second = client.get("/api/v1/status/does-not-exist", headers=headers)
    third = client.get("/api/v1/status/does-not-exist", headers=headers)

    assert first.status_code != 429
    assert second.status_code != 429
    assert third.status_code == 429
    assert "Retry-After" in third.headers
