import json
import subprocess
from types import SimpleNamespace

import pytest

from app.audit_service.audit import lighthouse_url_audit as lh
from app.audit_service.audit.lighthouse_url_audit import (
    _classify_error,
    _get_lighthouse_version,
    audit_urls_with_lighthouse,
    resolve_chrome_path,
    run_lighthouse_json,
    validate_categories,
)


@pytest.fixture
def run(monkeypatch):
    """Replaces subprocess.run inside the lighthouse module. Set .outcome to a CompletedProcess or an exception"""
    state = SimpleNamespace(calls=[], outcome=None)

    def fake_run(cmd, **kwargs):
        state.calls.append(SimpleNamespace(cmd=cmd, kwargs=kwargs))
        if isinstance(state.outcome, BaseException):
            raise state.outcome
        return state.outcome

    monkeypatch.setattr(
        lh,
        "subprocess",
        SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired),
    )
    return state


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


# _get_lighthouse_version

def test_version_is_read_from_the_cli(run):
    run.outcome = completed(stdout="12.3.0\n")

    assert _get_lighthouse_version() == "12.3.0"
    assert run.calls[0].cmd == ["lighthouse", "--version"]


@pytest.mark.parametrize("outcome", [completed(returncode=1), completed(stdout="  "), FileNotFoundError("no lighthouse"), subprocess.TimeoutExpired("lh", 10)])
def test_version_is_none_when_it_cannot_be_read(run, outcome):
    run.outcome = outcome

    assert _get_lighthouse_version() is None


# resolve_chrome_path

def make_binary(path, executable=True):
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755 if executable else 0o644)
    return str(path)


@pytest.fixture
def no_chrome_on_path(monkeypatch):
    monkeypatch.setattr(lh, "shutil", SimpleNamespace(which=lambda name: None))
    monkeypatch.delenv("CHROME_PATH", raising=False)


def test_chrome_path_env_var_wins(tmp_path, monkeypatch, no_chrome_on_path):
    env_binary = make_binary(tmp_path / "env-chrome")
    configured = make_binary(tmp_path / "configured-chrome")
    monkeypatch.setenv("CHROME_PATH", env_binary)

    assert resolve_chrome_path(configured) == env_binary


def test_configured_path_is_used_without_the_env_var(tmp_path, no_chrome_on_path):
    configured = make_binary(tmp_path / "configured-chrome")

    assert resolve_chrome_path(configured) == configured


def test_chrome_is_found_on_the_path(tmp_path, monkeypatch, no_chrome_on_path):
    chromium = make_binary(tmp_path / "chromium")
    monkeypatch.setattr(lh, "shutil", SimpleNamespace(which=lambda name: chromium if name == "chromium" else None))

    assert resolve_chrome_path("/does/not/exist") == chromium


def test_non_executable_and_missing_candidates_are_skipped(tmp_path, monkeypatch, no_chrome_on_path):
    monkeypatch.setenv("CHROME_PATH", make_binary(tmp_path / "not-executable", executable=False))
    good = make_binary(tmp_path / "good")

    assert resolve_chrome_path(good) == good


def test_a_clear_error_is_raised_when_chrome_is_missing(tmp_path, monkeypatch, no_chrome_on_path):
    monkeypatch.setenv("CHROME_PATH", "/nope/chrome")

    with pytest.raises(RuntimeError, match="No Chrome/Chromium installation found") as exc:
        resolve_chrome_path()

    assert "/nope/chrome" in str(exc.value)


def test_the_error_says_when_there_were_no_candidates(no_chrome_on_path):
    with pytest.raises(RuntimeError, match="no candidates"):
        resolve_chrome_path()


# validate_categories

@pytest.mark.parametrize("value", [None, "", "performance", "performance,seo", " seo , accessibility ", "best-practices,pwa"])
def test_valid_categories_pass(value):
    validate_categories(value)


def test_one_unknown_category_is_named():
    with pytest.raises(RuntimeError, match="Unknown Lighthouse category: speed"):
        validate_categories("performance,speed")


def test_several_unknown_categories_are_listed_sorted():
    with pytest.raises(RuntimeError, match="Unknown Lighthouse categories: alpha, zeta"):
        validate_categories("zeta,seo,alpha")


# _classify_error

@pytest.mark.parametrize(
    "exc, expected",
    [
        (subprocess.TimeoutExpired("lh", 5), "timeout"),
        (RuntimeError("Lighthouse produced no JSON for x"), "no_json_output"),
        (RuntimeError("Invalid JSON from Lighthouse"), "invalid_json"),
        (RuntimeError("Lighthouse failed for x\nReturn code: 1"), "lighthouse_failed"),
        (RuntimeError("Return code: 7"), "lighthouse_failed"),
        (ValueError("something else"), "unknown"),
    ],
)
def test_classify_error(exc, expected):
    assert _classify_error(exc)[0] == expected


def test_unknown_errors_keep_their_message():
    assert _classify_error(ValueError("something else")) == ("unknown", "something else")


# run_lighthouse_json

REPORT = {"categories": {"seo": {"score": 1}}, "audits": {}, "finalUrl": "https://example.com/"}


def test_desktop_command(run):
    run.outcome = completed(stdout=json.dumps(REPORT))

    report, duration, cmd = run_lighthouse_json("https://example.com", "desktop")

    assert report == REPORT
    assert duration >= 0
    assert cmd[:2] == ["lighthouse", "https://example.com"]
    assert "--preset=desktop" in cmd
    assert "--only-categories=performance,seo" in cmd
    assert "--output=json" in cmd and "--output-path=stdout" in cmd
    assert not any(arg.startswith("--form-factor") for arg in cmd)
    assert run.calls[0].kwargs["timeout"] == 240
    assert run.calls[0].kwargs["capture_output"] is True


def test_mobile_command(run):
    run.outcome = completed(stdout=json.dumps(REPORT))

    _, _, cmd = run_lighthouse_json("https://example.com", "mobile")

    assert "--form-factor=mobile" in cmd
    assert "--throttling-method=simulate" in cmd
    assert not any(arg.startswith("--preset") for arg in cmd)


@pytest.mark.parametrize("platform", ["desktop", "mobile"])
def test_requested_categories_replace_the_defaults(run, platform):
    run.outcome = completed(stdout=json.dumps(REPORT))

    _, _, cmd = run_lighthouse_json("https://example.com", platform, only_categories="seo,accessibility")

    assert "--only-categories=seo,accessibility" in cmd


def test_an_unknown_platform_is_run_as_mobile(run):
    run.outcome = completed(stdout=json.dumps(REPORT))

    _, _, cmd = run_lighthouse_json("https://example.com", "tablet")

    assert "--form-factor=mobile" in cmd


def test_chrome_path_is_passed_in_the_environment(run, monkeypatch):
    run.outcome = completed(stdout=json.dumps(REPORT))
    monkeypatch.delenv("CHROME_PATH", raising=False)

    run_lighthouse_json("https://example.com", "mobile", chrome_path="/opt/chrome")

    assert run.calls[0].kwargs["env"]["CHROME_PATH"] == "/opt/chrome"


def test_a_failing_process_raises_with_the_output(run):
    run.outcome = completed(stdout="out text", stderr="err text", returncode=2)

    with pytest.raises(RuntimeError, match="Lighthouse failed for https://example.com") as exc:
        run_lighthouse_json("https://example.com", "mobile")

    assert "Return code: 2" in str(exc.value)
    assert "err text" in str(exc.value)
    assert "out text" in str(exc.value)


def test_empty_output_raises(run):
    run.outcome = completed(stdout="  \n", stderr="chrome crashed")

    with pytest.raises(RuntimeError, match="produced no JSON") as exc:
        run_lighthouse_json("https://example.com", "mobile")

    assert "chrome crashed" in str(exc.value)


def test_invalid_json_raises(run):
    run.outcome = completed(stdout="<html>not json</html>")

    with pytest.raises(RuntimeError, match="Invalid JSON from Lighthouse"):
        run_lighthouse_json("https://example.com", "mobile")


def test_a_timeout_raises_a_runtime_error(run):
    run.outcome = subprocess.TimeoutExpired("lighthouse", 240)

    with pytest.raises(RuntimeError, match="timed out for https://example.com"):
        run_lighthouse_json("https://example.com", "mobile")


# audit_urls_with_lighthouse

@pytest.fixture
def lighthouse(monkeypatch):
    """Stubs the Lighthouse runner. .reports maps (url, platform) to a report or an exception, anything else is a
    simple report for that url"""
    state = SimpleNamespace(calls=[], reports={})

    def fake_run(url, platform, only_categories=None, chrome_path=None):
        state.calls.append((url, platform, only_categories, chrome_path))
        outcome = state.reports.get((url, platform))
        if isinstance(outcome, BaseException):
            raise outcome
        report = outcome or {
            "audits": {"a": {"score": 1}},
            "categories": {"seo": {"score": 0.9}},
            "finalUrl": url + "final",
            "fetchTime": "2026-01-01T00:00:00Z",
        }
        return report, 1.2345, ["lighthouse", url]

    monkeypatch.setattr(lh, "run_lighthouse_json", fake_run)
    monkeypatch.setattr(lh, "resolve_chrome_path", lambda configured=None: "/usr/bin/fake-chrome")
    monkeypatch.setattr(lh, "_get_lighthouse_version", lambda: "12.0.0")
    return state


def test_successful_urls_get_mobile_and_desktop_results(lighthouse):
    result = audit_urls_with_lighthouse(["https://a.com/"])

    entry = result["lighthouse_data"]["https://a.com/"]
    assert entry["status"] == "success"
    assert entry["mobile"] == {"audits": {"a": {"score": 1}}, "categories": {"seo": {"score": 0.9}}}
    assert entry["desktop"] == entry["mobile"]
    assert entry["final_url"] == "https://a.com/final"
    assert entry["diagnostics"]["timing_s"] == 1.234
    assert entry["diagnostics"]["fetch_time"] == "2026-01-01T00:00:00Z"
    assert lighthouse.calls[0][1] == "desktop" and lighthouse.calls[1][1] == "mobile"
    assert lighthouse.calls[0][3] == "/usr/bin/fake-chrome"


def test_meta_describes_the_run(lighthouse):
    result = audit_urls_with_lighthouse(["https://a.com/"], only_categories="performance, seo")

    meta = result["meta"]
    assert meta["categories"] == "performance,seo"
    assert meta["lighthouse_version"] == "12.0.0"
    assert meta["tested_urls"] == ["https://a.com/"]
    assert meta["devices"] == ["mobile", "desktop"]
    assert meta["config"]["only_categories"] == "performance,seo"
    assert meta["config"]["desktop"]["chrome_path"] == "/usr/bin/fake-chrome"
    assert meta["config"]["mobile"]["only_categories"] == "performance, seo"


def test_default_categories_are_performance_and_seo(lighthouse):
    result = audit_urls_with_lighthouse(["https://a.com/"])

    assert result["meta"]["categories"] == "performance,seo"


def test_final_url_falls_back_to_the_requested_url_then_the_url(lighthouse):
    lighthouse.reports[("https://a.com/", "desktop")] = {"audits": {}, "categories": {}, "requestedUrl": "https://requested.com/"}
    lighthouse.reports[("https://b.com/", "desktop")] = {"audits": {}, "categories": {}}

    data = audit_urls_with_lighthouse(["https://a.com/", "https://b.com/"])["lighthouse_data"]

    assert data["https://a.com/"]["final_url"] == "https://requested.com/"
    assert data["https://b.com/"]["final_url"] == "https://b.com/"


def test_a_failing_url_is_recorded_and_the_rest_still_run(lighthouse):
    lighthouse.reports[("https://bad.com/", "mobile")] = RuntimeError("Lighthouse failed for https://bad.com/\nReturn code: 1")

    result = audit_urls_with_lighthouse(["https://bad.com/", "https://good.com/"])

    bad = result["lighthouse_data"]["https://bad.com/"]
    assert bad["status"] == "error"
    assert bad["error_type"] == "lighthouse_failed"
    assert bad["message"] == "Lighthouse process failed."
    assert "Return code: 1" in bad["stderr_head"]
    assert result["lighthouse_data"]["https://good.com/"]["status"] == "success"
    assert any("Failed Lighthouse for https://bad.com/" in line for line in result["logs"])
    assert any("Completed Lighthouse for https://good.com/" in line for line in result["logs"])


def test_unknown_categories_fail_before_anything_runs(lighthouse):
    with pytest.raises(RuntimeError, match="Unknown Lighthouse category"):
        audit_urls_with_lighthouse(["https://a.com/"], only_categories="speed")

    assert lighthouse.calls == []


def test_a_missing_chrome_fails_the_whole_run(lighthouse, monkeypatch):
    def no_chrome(configured=None):
        raise RuntimeError("No Chrome/Chromium installation found.")

    monkeypatch.setattr(lh, "resolve_chrome_path", no_chrome)

    with pytest.raises(RuntimeError, match="No Chrome"):
        audit_urls_with_lighthouse(["https://a.com/"])


def test_no_urls_gives_an_empty_result(lighthouse):
    result = audit_urls_with_lighthouse([])

    assert result["lighthouse_data"] == {}
    assert result["meta"]["tested_urls"] == []


@pytest.mark.xfail(
    strict=True,
    reason="run_lighthouse_json turns a timeout into a RuntimeError, so _classify_error never sees a "
    "TimeoutExpired and timed out urls are reported as error_type 'unknown'",
)
def test_a_timed_out_url_is_reported_as_a_timeout(run, monkeypatch):
    monkeypatch.setattr(lh, "resolve_chrome_path", lambda configured=None: "/usr/bin/fake-chrome")
    monkeypatch.setattr(lh, "_get_lighthouse_version", lambda: None)

    run.outcome = subprocess.TimeoutExpired("lighthouse", 240)

    result = audit_urls_with_lighthouse(["https://slow.com/"])

    assert result["lighthouse_data"]["https://slow.com/"]["error_type"] == "timeout"
