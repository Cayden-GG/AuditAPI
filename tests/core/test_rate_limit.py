import threading
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.rate_limit import RateLimiter, _client_ip, build_rate_limiter, rate_limit_key


class Clock:
    """Stands in for the time module inside app.rate_limit"""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr("app.rate_limit.time", fake)
    return fake


def make_request(headers=None, client=("9.9.9.9", 1234)):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


# RateLimiter

def test_allows_requests_up_to_the_limit_then_blocks(clock):
    limiter = RateLimiter(max_requests=3, window_seconds=60)

    results = [limiter.allow("ip")[0] for _ in range(5)]

    assert results == [True, True, True, False, False]


def test_allowed_requests_report_no_wait(clock):
    assert RateLimiter(1, 60).allow("ip") == (True, 0)


def test_retry_after_counts_down_to_when_the_oldest_request_expires(clock):
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    limiter.allow("ip")
    limiter.allow("ip")

    clock.now += 3
    assert limiter.allow("ip") == (False, 7)

    clock.now += 4
    assert limiter.allow("ip") == (False, 3)


def test_retry_after_is_never_less_than_one_second(clock):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    limiter.allow("ip")

    clock.now += 9.6

    assert limiter.allow("ip") == (False, 1)


def test_requests_are_allowed_again_once_the_window_has_passed(clock):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    limiter.allow("ip")

    clock.now += 10
    assert limiter.allow("ip")[0] is False  # a request exactly one window old still counts

    clock.now += 0.01
    assert limiter.allow("ip")[0] is True


def test_window_slides_rather_than_resetting(clock):
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    limiter.allow("ip")  # t=0
    clock.now += 6
    limiter.allow("ip")  # t=6

    clock.now += 5  # t=11, first request expired but the second has not
    assert limiter.allow("ip")[0] is True
    assert limiter.allow("ip")[0] is False


def test_blocked_requests_do_not_extend_the_block(clock):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    limiter.allow("ip")

    for _ in range(20):
        clock.now += 0.4
        limiter.allow("ip")

    clock.now = 1000.0 + 10.01
    assert limiter.allow("ip")[0] is True


def test_each_key_has_its_own_limit(clock):
    limiter = RateLimiter(max_requests=1, window_seconds=60)

    assert limiter.allow("a")[0] is True
    assert limiter.allow("a")[0] is False
    assert limiter.allow("b")[0] is True


def test_concurrent_requests_never_exceed_the_limit():
    limiter = RateLimiter(max_requests=50, window_seconds=60)
    allowed = []

    def hit():
        allowed.append(limiter.allow("ip")[0])

    threads = [threading.Thread(target=hit) for _ in range(200)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert allowed.count(True) == 50


def test_repr_shows_config_and_bucket_count(clock):
    limiter = RateLimiter(5, 30)
    limiter.allow("a")
    limiter.allow("b")

    assert repr(limiter) == "RateLimiter(max_requests: 5, window_seconds: 30, buckets: 2)"


# client ip

def test_client_ip_prefers_the_first_forwarded_address():
    request = make_request({"x-forwarded-for": " 1.2.3.4 , 10.0.0.1, 10.0.0.2"})

    assert _client_ip(request) == "1.2.3.4"


def test_client_ip_falls_back_to_the_socket_address():
    assert _client_ip(make_request()) == "9.9.9.9"


def test_client_ip_is_unknown_without_any_address():
    assert _client_ip(make_request(client=None)) == "unknown"


def test_rate_limit_key_is_the_client_ip():
    assert rate_limit_key(make_request({"x-forwarded-for": "5.6.7.8"})) == "5.6.7.8"


# build_rate_limiter

@pytest.fixture
def clean_env(monkeypatch):
    for name in ("RATE_LIMIT_DISABLED", "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_build_rate_limiter_defaults(clean_env):
    max_requests, window, limiter = build_rate_limiter()

    assert (max_requests, window) == (30, 60)
    assert (limiter.max_requests, limiter.window_seconds) == (30, 60)


def test_build_rate_limiter_reads_the_environment(clean_env):
    clean_env.setenv("RATE_LIMIT_REQUESTS", "5")
    clean_env.setenv("RATE_LIMIT_WINDOW_SECONDS", "120")

    max_requests, window, limiter = build_rate_limiter()

    assert (max_requests, window) == (5, 120)
    assert (limiter.max_requests, limiter.window_seconds) == (5, 120)


@pytest.mark.parametrize("value", ["True", "true", "1"])
def test_build_rate_limiter_can_be_disabled(clean_env, value):
    clean_env.setenv("RATE_LIMIT_DISABLED", value)

    assert build_rate_limiter()[2] is None


@pytest.mark.parametrize("value", ["", "false", "False", "0", "no"])
def test_build_rate_limiter_other_disabled_values_leave_it_on(clean_env, value):
    clean_env.setenv("RATE_LIMIT_DISABLED", value)

    assert build_rate_limiter()[2] is not None


def test_build_rate_limiter_falls_back_to_defaults_on_bad_numbers(clean_env):
    clean_env.setenv("RATE_LIMIT_REQUESTS", "lots")
    clean_env.setenv("RATE_LIMIT_WINDOW_SECONDS", "10")

    max_requests, window, limiter = build_rate_limiter()

    assert (max_requests, window) == (30, 60)
    assert limiter is not None


@pytest.mark.parametrize("name", ["RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_build_rate_limiter_is_off_for_non_positive_values(clean_env, name, value):
    clean_env.setenv(name, value)

    assert build_rate_limiter()[2] is None


# middleware

@pytest.fixture
def limited_client(client, monkeypatch):
    """The test client with a 2 requests per minute limiter switched on"""
    monkeypatch.setattr("app.main._rate_limit_max", 2)
    monkeypatch.setattr("app.main._rate_limit_window", 60)
    monkeypatch.setattr("app.main._rate_limiter", RateLimiter(2, 60))
    return client


def ip(address):
    return {"x-forwarded-for": address}


def test_requests_over_the_limit_get_a_429_with_retry_after(limited_client):
    for _ in range(2):
        assert limited_client.get("/api/v1/status/x", headers=ip("1.1.1.1")).status_code != 429

    response = limited_client.get("/api/v1/status/x", headers=ip("1.1.1.1"))

    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded.", "max_requests": 2, "window_seconds": 60}
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_each_client_ip_is_limited_separately(limited_client):
    for _ in range(3):
        limited_client.get("/api/v1/status/x", headers=ip("1.1.1.1"))

    assert limited_client.get("/api/v1/status/x", headers=ip("2.2.2.2")).status_code != 429


def test_only_api_paths_are_limited(limited_client):
    statuses = {limited_client.get("/openapi.json", headers=ip("1.1.1.1")).status_code for _ in range(5)}

    assert statuses == {200}


def test_limit_applies_across_api_endpoints(limited_client):
    limited_client.get("/api/v1/status/x", headers=ip("1.1.1.1"))
    limited_client.post("/api/v1/audit", json={}, headers=ip("1.1.1.1"))

    assert limited_client.get("/api/v1/status/x", headers=ip("1.1.1.1")).status_code == 429


def test_no_limiter_means_no_limit(client):
    statuses = {client.get("/api/v1/status/x", headers=ip("1.1.1.1")).status_code for _ in range(40)}

    assert 429 not in statuses
