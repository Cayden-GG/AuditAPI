import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audit_service import cli
from app.audit_service.audit.sitemap_discovery import SitemapDiscoveryResult
from app.audit_service.cli import REPORT_KEYS, _normalize_categories, _should_include_accessibility, run_audit
from app.audit_service.config.settings import AppConfig
from tests.builders import lighthouse_payload


@pytest.mark.parametrize(
    "value, expected",
    [
        ("performance,seo", "performance,seo"),
        (" seo , performance ", "seo,performance"),
        ("", "performance,seo"),
        (None, "performance,seo"),
        (",,", "performance,seo"),
        ("Performance", "Performance"),
    ],
)
def test_normalize_categories(value, expected):
    assert _normalize_categories(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [("accessibility", True), ("Performance, Accessibility", True), ("performance,seo", False), ("", False), (None, False)],
)
def test_should_include_accessibility(value, expected):
    assert _should_include_accessibility(value) is expected


URLS = [f"https://example.com/page{i}" for i in range(8)]


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Stubs the slow stages of the audit pipeline (network, Lighthouse, OpenAI, PDF rendering).

    .discovery, .lighthouse, .ai and .reports can be changed per test, exceptions are raised. .calls records inputs
    """
    state = SimpleNamespace(
        calls={},
        discovery=SitemapDiscoveryResult(
            sitemap_indexes=[], sitemaps=["https://example.com/sitemap.xml"], urls=URLS, per_sitemap=[], errors=[], logs=[]
        ),
        lighthouse=None,
        ai={"executive_summary": "ok"},
        reports={
            "seo": "out/SEO.pdf",
            "key_findings": "out/Key.pdf",
            "performance": "out/Perf.pdf",
            "unknown_report": "out/other.pdf",
        },
    )

    def resolve(value):
        if isinstance(value, BaseException):
            raise value
        return value

    def discover(url):
        state.calls["discover"] = url
        return resolve(state.discovery)

    def lighthouse(urls, only_categories):
        state.calls["lighthouse"] = (urls, only_categories)
        return resolve(state.lighthouse) if state.lighthouse is not None else lighthouse_payload(
            only_categories, url=urls[0] if urls else "https://example.com"
        )

    def ai(result, logger, debug_mode):
        state.calls["ai"] = {"result": result, "debug_mode": debug_mode}
        return resolve(state.ai)

    def reports(pdf_data, **kwargs):
        state.calls["reports"] = {"pdf_data": pdf_data, **kwargs}
        return resolve(state.reports)

    monkeypatch.setattr(cli, "discover_urls_from_sitemaps", discover)
    monkeypatch.setattr(cli, "audit_urls_with_lighthouse", lighthouse)
    monkeypatch.setattr(cli, "call_openai", ai)
    monkeypatch.setattr(cli, "build_reports", reports)
    state.config = lambda **kw: AppConfig(
        **{
            "client_name": "Acme",
            "domain_url": "https://example.com",
            "max_urls": 5,
            "only_categories": "performance,seo",
            "output_dir": str(tmp_path / "out"),
            "log_path": str(tmp_path / "out" / "audit_log.jsonl"),
            **kw,
        }
    )
    state.out = tmp_path / "out"
    return state


def test_run_audit_discovers_urls_and_audits_the_first_max_urls(pipeline):
    run_audit(pipeline.config(max_urls=3))

    assert pipeline.calls["discover"] == "https://example.com"
    assert pipeline.calls["lighthouse"] == (URLS[:3], "performance,seo")


def test_run_audit_returns_only_known_reports_in_order(pipeline):
    reports = run_audit(pipeline.config())

    assert list(reports) == ["performance", "seo", "key_findings"]
    assert tuple(reports) == tuple(k for k in REPORT_KEYS if k in reports)


def test_run_audit_writes_the_audit_and_ai_json(pipeline):
    run_audit(pipeline.config())

    files = {p.name for p in pipeline.out.iterdir()}
    ai_file = next(p for p in pipeline.out.iterdir() if p.name.startswith("ai_audit_summary"))
    audit_file = next(p for p in pipeline.out.iterdir() if p.name.startswith("audit_") and p.suffix == ".json")

    assert "audit_log.jsonl" in files
    assert json.loads(ai_file.read_text()) == {"executive_summary": "ok"}
    audit = json.loads(audit_file.read_text())
    assert audit["sitemap"]["url_count"] == 8
    assert audit["lighthouse"]["tested_url_count"] == 5
    assert audit["lighthouse"]["tested_urls"] == URLS[:5]
    assert set(audit["lighthouse"]["normalized_findings"]) == {"performance", "seo", "accessibility"}


def test_run_audit_passes_the_data_to_the_report_builder(pipeline):
    run_audit(pipeline.config(client_name="Acme Co", only_categories="performance,seo"))

    call = pipeline.calls["reports"]
    assert call["output_dir"] == str(pipeline.out)
    assert call["client_name"] == "Acme Co"
    assert call["include_accessibility"] is False
    assert call["is_free_audit"] is True
    assert call["pdf_data"]["ai"] == {"executive_summary": "ok"}
    assert call["pdf_data"]["audit"]["sitemap"]["start"] == "https://example.com"


def test_accessibility_categories_make_it_a_paid_report(pipeline):
    run_audit(pipeline.config(only_categories="performance,seo,accessibility"))

    call = pipeline.calls["reports"]
    assert call["include_accessibility"] is True
    assert call["is_free_audit"] is False


def test_empty_categories_fall_back_to_the_defaults(pipeline):
    run_audit(pipeline.config(only_categories=""))

    assert pipeline.calls["lighthouse"][1] == "performance,seo"


def test_debug_mode_reaches_the_ai_step(pipeline):
    run_audit(pipeline.config(debug_mode=True))

    assert pipeline.calls["ai"]["debug_mode"] is True


def test_default_output_paths_are_built_from_the_client_name(pipeline, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    run_audit(pipeline.config(output_dir=None, log_path=None))

    (folder,) = (tmp_path / "audit_results").iterdir()
    assert folder.name.startswith("Acme_audit_")
    assert (folder / "audit_log.jsonl").exists()


def test_sitemap_discovery_failure_is_recorded_and_the_audit_continues(pipeline):
    pipeline.discovery = RuntimeError("dns failure")

    reports = run_audit(pipeline.config())

    assert reports
    assert pipeline.calls["lighthouse"][0] == []
    audit_file = next(p for p in pipeline.out.iterdir() if p.name.startswith("audit_") and p.suffix == ".json")
    errors = json.loads(audit_file.read_text())["sitemap"]["errors"]
    assert errors[0]["message"] == "dns failure"


def test_no_discovered_urls_still_produces_reports(pipeline):
    pipeline.discovery = SitemapDiscoveryResult([], [], [], [], [], [])

    assert run_audit(pipeline.config())


def test_lighthouse_failure_produces_an_empty_audit_instead_of_crashing(pipeline):
    pipeline.lighthouse = RuntimeError("chrome crashed")

    reports = run_audit(pipeline.config())

    assert reports
    audit_file = next(p for p in pipeline.out.iterdir() if p.name.startswith("audit_") and p.suffix == ".json")
    assert json.loads(audit_file.read_text())["lighthouse"]["per_url_performance_data"] == {}


def test_a_missing_ai_summary_is_replaced_by_an_empty_one(pipeline):
    pipeline.ai = None

    run_audit(pipeline.config())

    assert pipeline.calls["reports"]["pdf_data"]["ai"] == {}


def test_report_generation_failure_returns_no_reports(pipeline):
    pipeline.reports = RuntimeError("reportlab exploded")

    assert run_audit(pipeline.config()) == {}


def test_main_prints_the_report_paths_line(pipeline, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_config", pipeline.config)

    cli.main()

    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("REPORT_PATHS::")]
    assert json.loads(lines[0].removeprefix("REPORT_PATHS::")) == {
        "performance": "out/Perf.pdf",
        "seo": "out/SEO.pdf",
        "key_findings": "out/Key.pdf",
    }


def test_the_report_paths_line_matches_what_the_server_parses(pipeline, monkeypatch, capsys):
    from app.main import _extract_report_paths

    monkeypatch.setattr(cli, "build_config", pipeline.config)

    cli.main()

    assert _extract_report_paths(capsys.readouterr().out) == [Path("out/Perf.pdf"), Path("out/SEO.pdf"), Path("out/Key.pdf")]
