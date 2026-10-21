import pytest

from app.audit_service.audit.normalizer import (
    _category_audit_ids,
    _cw_status,
    _risk_summary,
    _severity_for_accessibility,
    _severity_for_performance,
    _severity_for_seo,
    normalize_lighthouse_results,
)
from tests.builders import lighthouse_payload


@pytest.mark.parametrize(
    "metric, value, expected",
    [
        ("LCP", 2500, "Good"),
        ("LCP", 2501, "Needs Improvement"),
        ("LCP", 4000, "Needs Improvement"),
        ("LCP", 4001, "Poor"),
        ("CLS", 0.1, "Good"),
        ("CLS", 0.11, "Needs Improvement"),
        ("CLS", 0.25, "Needs Improvement"),
        ("CLS", 0.26, "Poor"),
        ("INP", 200, "Good"),
        ("INP", 500, "Needs Improvement"),
        ("INP", 501, "Poor"),
        ("FID", 100, "Good"),
        ("FID", 300, "Needs Improvement"),
        ("FID", 301, "Poor"),
    ],
)
def test_cw_status_thresholds(metric, value, expected):
    assert _cw_status(metric, value) == expected


def test_cw_status_none_value_and_unknown_metric():
    assert _cw_status("LCP", None) is None
    assert _cw_status("TTFB", 100) is None


@pytest.mark.parametrize(
    "audit_id, manual, expected",
    [
        ("robots-txt", False, "critical"),
        ("is-crawlable", False, "critical"),
        ("meta-description", False, "high"),
        ("structured-data", False, "high"),
        ("viewport", False, "moderate"),
        ("hreflang", False, "high"),
        ("some-unknown-audit", False, "moderate"),
        # manual always wins, even for critical audits
        ("robots-txt", True, "advisory"),
        ("meta-description", True, "advisory"),
    ],
)
def test_severity_for_seo(audit_id, manual, expected):
    assert _severity_for_seo(audit_id, manual) == expected


@pytest.mark.parametrize(
    "score, status, expected",
    [
        (0.9, "Poor", "critical"),
        (None, "Poor", "critical"),
        (0.49, "Good", "high"),
        (0.49, "Needs Improvement", "high"),
        (0.9, "Needs Improvement", "moderate"),
        (0.79, None, "moderate"),
        (0.5, None, "moderate"),
        (0.8, None, "advisory"),
        (0.95, "Good", "advisory"),
        (None, None, "advisory"),
    ],
)
def test_severity_for_performance(score, status, expected):
    assert _severity_for_performance(score, status) == expected


@pytest.mark.parametrize(
    "score, manual, expected",
    [
        (0, False, "high"),
        (0.5, False, "moderate"),
        (0.89, False, "moderate"),
        (0.9, False, "advisory"),
        (1, False, "advisory"),
        (None, False, "advisory"),
        (0, True, "advisory"),
        (None, True, "advisory"),
    ],
)
def test_severity_for_accessibility(score, manual, expected):
    assert _severity_for_accessibility(score, manual) == expected


def test_risk_summary_uses_highest_severity_present():
    assert _risk_summary({"critical": 1, "high": 5}).startswith("High risk")
    assert _risk_summary({"critical": 0, "high": 1}).startswith("Elevated risk")
    assert _risk_summary({"high": 0, "moderate": 2}).startswith("Moderate risk")
    assert _risk_summary({"advisory": 4}).startswith("Low risk")
    assert _risk_summary({}).startswith("Low risk")


def test_category_audit_ids_reads_refs_and_skips_bad_entries():
    categories = {
        "accessibility": {
            "auditRefs": [{"id": "color-contrast"}, {"id": ""}, {"weight": 1}, "junk", {"id": "label"}]
        }
    }
    assert _category_audit_ids(categories, "accessibility") == ["color-contrast", "label"]


def test_category_audit_ids_handles_missing_data():
    assert _category_audit_ids({}, "accessibility") == []
    assert _category_audit_ids({"accessibility": {"auditRefs": None}}, "accessibility") == []
    assert _category_audit_ids(None, "accessibility") == []


def _normalize(audits=None, categories=None, **kwargs):
    payload = lighthouse_payload(audits=audits or {}, cats=categories or {}, **kwargs)
    return normalize_lighthouse_results(payload)


def test_poor_core_web_vitals_become_critical_performance_findings():
    result = _normalize(
        audits={
            "largest-contentful-paint": {"numericValue": 5000},
            "cumulative-layout-shift": {"numericValue": 0.3},
        }
    )

    titles = {f["title"]: f for f in result["findings"]["performance"]["mobile"]}
    assert titles["LCP is Poor"]["severity"] == "critical"
    assert titles["CLS is Poor"]["severity"] == "critical"
    assert titles["LCP is Poor"]["affected_elements"] == ["https://example.com"]
    assert titles["LCP is Poor"]["standard_reference"]["framework"] == "Core Web Vitals"
    assert result["summary"]["performance"]["mobile"]["findings_by_severity"]["critical"] == 2
    assert result["summary"]["performance"]["mobile"]["risk_summary"].startswith("High risk")


def test_good_core_web_vitals_produce_no_findings():
    result = _normalize(
        audits={
            "largest-contentful-paint": {"numericValue": 1000},
            "cumulative-layout-shift": {"numericValue": 0.01},
            "interaction-to-next-paint": {"numericValue": 100},
        },
        categories={"performance": {"score": 0.95}},
    )

    assert result["findings"]["performance"]["mobile"] == []
    assert result["summary"]["performance"]["mobile"]["overall_score"] == 0.95
    assert result["summary"]["performance"]["mobile"]["risk_summary"].startswith("Low risk")


def test_fid_only_used_when_inp_is_missing():
    slow_fid = {"first-input-delay": {"numericValue": 400}}

    without_inp = _normalize(audits=slow_fid)
    with_inp = _normalize(audits={**slow_fid, "interaction-to-next-paint": {"numericValue": 100}})

    assert [f["title"] for f in without_inp["findings"]["performance"]["mobile"]] == ["FID is Poor"]
    assert with_inp["findings"]["performance"]["mobile"] == []


def test_low_overall_performance_score_adds_a_finding():
    result = _normalize(categories={"performance": {"score": 0.4}})

    findings = result["findings"]["performance"]["mobile"]
    assert len(findings) == 1
    assert findings[0]["title"] == "Overall performance score is below target"
    assert findings[0]["severity"] == "high"
    assert findings[0]["score"] == 0.4


def test_failed_seo_audit_is_reported_with_its_severity():
    result = _normalize(
        audits={
            "robots-txt": {"score": 0, "title": "robots.txt is not valid", "description": "Fix it."},
            "meta-description": {"score": 1, "title": "Has meta description"},
        }
    )

    findings = result["findings"]["seo"]["mobile"]
    assert len(findings) == 1
    assert findings[0]["title"] == "robots.txt is not valid"
    assert findings[0]["severity"] == "critical"
    assert findings[0]["description"] == "Fix it. Automated check failed."


def test_manual_seo_audit_is_advisory_and_flagged_for_review():
    result = _normalize(
        audits={"structured-data": {"scoreDisplayMode": "manual", "title": "Structured data"}}
    )

    finding = result["findings"]["seo"]["mobile"][0]
    assert finding["severity"] == "advisory"
    assert finding["score"] is None
    assert "Manual review required." in finding["description"]


def test_missing_audits_are_ignored():
    result = _normalize(
        audits={
            "robots-txt": {"error": "missing_audit", "score": 0},
            "color-contrast": {"error": "missing_audit", "score": 0},
        }
    )

    assert result["findings"]["seo"]["mobile"] == []
    assert result["findings"]["accessibility"]["mobile"] == []


def test_accessibility_uses_category_audit_refs_when_present():
    audits = {
        "color-contrast": {"score": 0, "title": "Contrast"},
        "label": {"score": 0, "title": "Labels"},
    }
    categories = {"accessibility": {"score": 0.6, "auditRefs": [{"id": "label"}]}}

    result = _normalize(audits=audits, categories=categories)

    # color-contrast is a default id, but the category only lists "label"
    titles = [f["title"] for f in result["findings"]["accessibility"]["mobile"]]
    assert titles == ["Labels"]


def test_accessibility_falls_back_to_default_audit_ids():
    result = _normalize(audits={"color-contrast": {"score": 0, "title": "Contrast"}})

    finding = result["findings"]["accessibility"]["mobile"][0]
    assert finding["severity"] == "high"
    assert finding["standard_reference"]["code"] == "color-contrast"


def test_scores_are_averaged_across_urls():
    payload = lighthouse_payload(url="https://a.example.com", audits={}, cats={"seo": {"score": 1.0}})
    other = lighthouse_payload(url="https://b.example.com", audits={}, cats={"seo": {"score": 0.5}})
    payload["lighthouse_data"].update(other["lighthouse_data"])

    result = normalize_lighthouse_results(payload)

    assert result["summary"]["seo"]["mobile"]["overall_score"] == 0.75
    assert result["summary"]["seo"]["desktop"]["overall_score"] == 0.75


def test_failed_urls_and_non_dict_entries_are_skipped():
    payload = {
        "lighthouse_data": {
            "https://bad.example.com": {"status": "failed"},
            "https://junk.example.com": "not a dict",
        }
    }

    result = normalize_lighthouse_results(payload)

    assert result["findings"]["seo"] == {"mobile": [], "desktop": []}
    assert result["summary"]["seo"]["mobile"]["overall_score"] is None
    assert result["summary"]["seo"]["mobile"]["risk_summary"].startswith("Low risk")


@pytest.mark.parametrize("payload", [{}, {"lighthouse_data": None}, {"lighthouse_data": {}}])
def test_empty_input_returns_full_empty_structure(payload):
    result = normalize_lighthouse_results(payload)

    for category in ("performance", "seo", "accessibility"):
        for platform in ("mobile", "desktop"):
            assert result["findings"][category][platform] == []
            summary = result["summary"][category][platform]
            assert summary["overall_score"] is None
            assert summary["findings_by_severity"] == {"critical": 0, "high": 0, "moderate": 0, "advisory": 0}


def test_null_platform_data_does_not_crash():
    payload = {"lighthouse_data": {"https://example.com": {"status": "success", "mobile": None, "desktop": {}}}}

    result = normalize_lighthouse_results(payload)

    assert result["findings"]["performance"]["mobile"] == []
