import pytest

from app.audit_service.audit.audit_config import ACCESSIBILITY_AUDIT_IDS
from app.audit_service.audit.formatters.accessibility_formatter import (
    _audit_status,
    aggregate_website_accessibility,
    reduce_url_accessibility,
)


def audits_for(ids, score=1, **overrides):
    audits = {audit_id: {"score": score, "displayValue": None, "numericValue": None} for audit_id in ids}
    audits.update(overrides)
    return audits


def reduce(audits, ids, url="https://example.com"):
    logs, errors = [], []
    return reduce_url_accessibility(url, audits, ids, logs=logs, errors=errors), logs, errors


@pytest.mark.parametrize(
    "audit, expected",
    [
        ({"score": 1}, "pass"),
        ({"score": 0.9}, "pass"),
        ({"score": 0.5}, "fail"),
        ({"score": 0}, "fail"),
        ({"score": None}, "not_applicable"),
        ({}, "not_applicable"),
        ({"score": 0, "scoreDisplayMode": "notApplicable"}, "not_applicable"),
        ({"score": 1, "scoreDisplayMode": "manual"}, "not_applicable"),
        ({"score": 1, "scoreDisplayMode": "informative"}, "not_applicable"),
    ],
)
def test_audit_status(audit, expected):
    assert _audit_status(audit) == expected


def test_reduce_only_looks_at_the_given_audit_ids():
    ids = ["color-contrast", "label", "link-name"]
    audits = audits_for(
        ids + ["image-alt"],
        **{"label": {"score": 0}, "link-name": {"scoreDisplayMode": "manual"}},
    )

    result, logs, errors = reduce(audits, ids)

    assert list(result["audits"]) == ids
    assert result["summary"] == {
        "average_score": 0.5,
        "passed": 1,
        "failed": 1,
        "not_applicable": 1,
        "total_audits": 3,
    }
    assert errors == []
    assert logs == [{"level": "info", "message": "Reduced accessibility data for https://example.com"}]


def test_reduce_falls_back_to_the_default_audit_ids_with_a_warning():
    result, logs, _ = reduce(audits_for(ACCESSIBILITY_AUDIT_IDS), [])

    assert list(result["audits"]) == ACCESSIBILITY_AUDIT_IDS
    assert logs[0]["level"] == "warning"


def test_reduce_skips_malformed_audits_and_counts_missing_ones_as_not_applicable():
    result, _, _ = reduce({"color-contrast": "junk", "label": {"score": 1}}, ["color-contrast", "label", "link-name"])

    assert list(result["audits"]) == ["label", "link-name"]
    assert result["summary"]["not_applicable"] == 1


@pytest.mark.parametrize("audits", [None, "junk", []])
def test_reduce_rejects_invalid_audits(audits):
    result, _, errors = reduce(audits, ["label"])

    assert result is None
    assert errors[0]["stage"] == "input"


def reduced(ids, **overrides):
    return reduce(audits_for(ids, **overrides), ids)[0]


def test_aggregate_totals_and_ranks_failing_audits():
    ids = ["color-contrast", "label", "link-name"]
    per_url = {
        "a": reduced(ids, **{"color-contrast": {"score": 0}, "label": {"score": 0}}),
        "b": reduced(ids, **{"color-contrast": {"score": 0}}),
        "c": reduced(ids),
        "d": reduced(ids),
    }

    result = aggregate_website_accessibility(per_url, logs=[])

    assert result["total_urls"] == 4
    assert result["total_failed"] == 3
    assert result["total_passed"] == 9
    assert result["top_failed_audits"] == [
        {"audit_id": "color-contrast", "fail_count": 2, "fail_rate": 0.5},
        {"audit_id": "label", "fail_count": 1, "fail_rate": 0.25},
    ]
    assert result["audit_summaries"]["color-contrast"] == {
        "average_score": 0.5,
        "average_numeric_value": None,
        "pass_count": 2,
        "fail_count": 2,
        "not_applicable_count": 0,
        "fail_rate": 0.5,
    }


def test_aggregate_average_score_is_the_mean_of_url_averages():
    ids = ["label"]

    result = aggregate_website_accessibility({"a": reduced(ids), "b": reduced(ids, score=0.5)}, logs=[])

    assert result["average_score"] == 0.75


def test_aggregate_of_nothing():
    result = aggregate_website_accessibility({}, logs=[])

    assert result["average_score"] is None
    assert result["total_urls"] == 0
    assert result["top_failed_audits"] == []
