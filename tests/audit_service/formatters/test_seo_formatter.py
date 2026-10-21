import pytest

from app.audit_service.audit.audit_config import SEO_AUDIT_IDS
from app.audit_service.audit.formatters import seo_formatter as seo
from app.audit_service.audit.formatters.seo_formatter import (
    _audit_status,
    aggregate_website_seo,
    format_lighthouse_output,
    reduce_url_seo,
)
from tests.builders import seo_audits


@pytest.mark.parametrize(
    "audit, expected",
    [
        ({"score": 1}, "pass"),
        ({"score": 0.9}, "pass"),
        ({"score": 0.89}, "fail"),
        ({"score": 0}, "fail"),
        ({"score": None}, "not_applicable"),
        ({}, "not_applicable"),
        ({"score": "1"}, "not_applicable"),
        ({"score": 0, "scoreDisplayMode": "notApplicable"}, "not_applicable"),
        ({"score": 1, "scoreDisplayMode": "manual"}, "not_applicable"),
        ({"score": 1, "scoreDisplayMode": "informative"}, "not_applicable"),
        ({"score": 0, "scoreDisplayMode": "binary"}, "fail"),
    ],
)
def test_audit_status(audit, expected):
    assert _audit_status(audit) == expected


def reduce(audits, url="https://example.com"):
    logs, errors = [], []
    return reduce_url_seo(url, audits, logs=logs, errors=errors), logs, errors


def test_reduce_counts_passes_fails_and_not_applicable():
    audits = seo_audits(
        score=1,
        **{
            "robots-txt": {"score": 0},
            "canonical": {"score": 0.5},
            "viewport": {"scoreDisplayMode": "notApplicable"},
            "hreflang": {"scoreDisplayMode": "manual"},
        },
    )

    result, logs, errors = reduce(audits)

    total = len(SEO_AUDIT_IDS)
    assert result["summary"]["failed"] == 2
    assert result["summary"]["not_applicable"] == 2
    assert result["summary"]["passed"] == total - 4
    assert result["summary"]["total_audits"] == total
    assert errors == []
    assert logs == [{"level": "info", "message": "Reduced SEO data for https://example.com"}]


def test_reduce_averages_the_numeric_scores_only():
    audits = seo_audits(only=["robots-txt", "viewport", "canonical"], **{"viewport": {"score": 0}, "canonical": {"scoreDisplayMode": "manual"}})

    result, _, _ = reduce(audits)

    assert result["summary"]["average_score"] == 0.5


def test_reduce_records_each_audit():
    audits = seo_audits(only=["robots-txt"], **{"robots-txt": {"score": 0, "displayValue": "bad", "numericValue": 4}})

    result, _, _ = reduce(audits)

    assert result["audits"]["robots-txt"] == {"score": 0, "display_value": "bad", "numeric_value": 4, "status": "fail"}


def test_reduce_ignores_unknown_and_malformed_audits():
    audits = {"not-an-seo-audit": {"score": 0}, "robots-txt": "junk", "viewport": {"score": 1}}

    result, _, _ = reduce(audits)

    assert "not-an-seo-audit" not in result["audits"]
    assert "robots-txt" not in result["audits"]
    assert result["audits"]["viewport"]["status"] == "pass"


def test_reduce_counts_a_missing_audit_as_not_applicable():
    result, _, _ = reduce({})

    assert result["summary"]["total_audits"] == len(SEO_AUDIT_IDS)
    assert result["summary"]["not_applicable"] == len(SEO_AUDIT_IDS)
    assert result["summary"]["average_score"] is None


@pytest.mark.parametrize("audits", [None, "junk", []])
def test_reduce_rejects_invalid_audits(audits):
    result, _, errors = reduce(audits)

    assert result is None
    assert errors[0]["stage"] == "input"


# aggregate_website_seo

def reduced(**overrides):
    return reduce(seo_audits(**overrides))[0]


def test_aggregate_totals_and_ranks_failing_audits():
    per_url = {
        "a": reduced(**{"robots-txt": {"score": 0}, "canonical": {"score": 0}}),
        "b": reduced(**{"robots-txt": {"score": 0}}),
        "c": reduced(),
    }
    logs = []

    result = aggregate_website_seo(per_url, logs=logs)

    assert result["total_urls"] == 3
    assert result["total_failed"] == 3
    assert result["total_passed"] == 3 * len(SEO_AUDIT_IDS) - 3
    assert result["top_failed_audits"] == [
        {"audit_id": "robots-txt", "fail_count": 2, "fail_rate": 0.667},
        {"audit_id": "canonical", "fail_count": 1, "fail_rate": 0.333},
    ]
    assert result["audit_summaries"]["robots-txt"]["fail_rate"] == 0.667
    assert result["audit_summaries"]["robots-txt"]["average_score"] == pytest.approx(1 / 3)
    assert logs == [{"level": "info", "message": "Aggregated SEO data across 3 URLs"}]


def test_aggregate_average_score_is_the_mean_of_url_averages():
    per_url = {"a": reduced(), "b": reduced(score=0.5)}

    assert aggregate_website_seo(per_url, logs=[])["average_score"] == 0.75


def test_aggregate_keeps_only_the_ten_worst_audits():
    failing = {audit_id: {"score": 0} for audit_id in SEO_AUDIT_IDS[:12]}

    result = aggregate_website_seo({"a": reduced(**failing)}, logs=[])

    assert len(result["top_failed_audits"]) == 10


def test_aggregate_of_nothing():
    result = aggregate_website_seo({}, logs=[])

    assert result["average_score"] is None
    assert result["total_urls"] == 0
    assert result["top_failed_audits"] == []
    assert result["audit_summaries"] == {}


# standalone format_lighthouse_output (reads audits nested under seo_data)

def standalone_payload(audits):
    platform = {"audits": {"seo_data": audits}}
    return {"meta": {}, "lighthouse_data": {"https://example.com": {"status": "success", "mobile": platform, "desktop": platform}}}


def test_standalone_format_reduces_and_aggregates():
    result = format_lighthouse_output(standalone_payload(seo_audits(**{"robots-txt": {"score": 0}})))

    assert set(result["per_url"]["https://example.com"]) == {"mobile", "desktop"}
    assert result["website"]["mobile"]["total_failed"] == 1
    assert result["errors"] == []


def test_standalone_format_reports_missing_results_and_failed_urls():
    assert format_lighthouse_output({})["errors"][0]["message"] == "Missing results"

    result = format_lighthouse_output({"lighthouse_data": {"https://a.com": {"status": "error"}, "https://b.com": 5}})

    assert result["per_url"] == {}
    assert [e["level"] for e in result["errors"]] == ["warning", "error"]


def test_standalone_main_writes_the_formatted_file(monkeypatch):
    written = {}
    monkeypatch.setattr(seo, "load_input_file", lambda path: standalone_payload(seo_audits()))
    monkeypatch.setattr(seo, "write_json_to_file", lambda data, out: written.update(out=out, data=data))

    seo.main("in.json", "out-dir")
    assert written["out"] == "out-dir"

    written.clear()
    seo.main("in.json", None)
    assert written == {}
