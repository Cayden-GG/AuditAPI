import pytest

from app.audit_service.audit import formatter
from app.audit_service.audit.formatter import (
    _category_audit_ids,
    _normalise_categories,
    _platform_audits,
    _platform_categories,
    format_lighthouse_output,
)
from tests.builders import lighthouse_payload, performance_audits, seo_audits


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("performance,seo", ["performance", "seo"]),
        (" Performance , SEO ,, ", ["performance", "seo"]),
        (["Performance", " seo ", "", None], ["performance", "seo", "none"]),
        ("", []),
        (None, []),
        (5, []),
    ],
)
def test_normalise_categories(raw, expected):
    assert _normalise_categories(raw) == expected


def test_platform_audits_accepts_audits_or_audit_keys():
    assert _platform_audits({"mobile": {"audits": {"a": 1}}}, "mobile") == {"a": 1}
    assert _platform_audits({"mobile": {"audit": {"b": 2}}}, "mobile") == {"b": 2}
    assert _platform_audits({"mobile": None}, "mobile") == {}
    assert _platform_audits({}, "desktop") == {}


def test_platform_categories():
    assert _platform_categories({"mobile": {"categories": {"seo": {}}}}, "mobile") == {"seo": {}}
    assert _platform_categories({"mobile": None}, "mobile") == {}


def test_category_audit_ids():
    categories = {"accessibility": {"auditRefs": [{"id": "label"}, {"id": ""}, "junk", {"id": "link-name"}]}}

    assert _category_audit_ids(categories, "accessibility") == ["label", "link-name"]
    assert _category_audit_ids({}, "accessibility") == []
    assert _category_audit_ids(None, "accessibility") == []


def full_audits():
    return {**performance_audits(), **seo_audits()}


def test_formats_performance_and_seo_per_url_and_for_the_website():
    result = format_lighthouse_output(lighthouse_payload("performance,seo", audits=full_audits()))

    entry = result["per_url"]["https://example.com"]
    assert set(entry) == {"performance", "seo"}
    assert set(entry["performance"]) == {"mobile", "desktop"}
    assert set(result["website"]) == {"performance", "seo"}
    assert result["website"]["performance"]["mobile"]["first_contentful_paint"] == {"average_value": 100.0}
    assert result["website"]["seo"]["desktop"]["total_urls"] == 1
    assert result["errors"] == []


def test_accessibility_is_only_formatted_when_requested():
    audits = {**full_audits(), "color-contrast": {"score": 0}}

    without = format_lighthouse_output(lighthouse_payload("performance,seo", audits=audits))
    with_ = format_lighthouse_output(lighthouse_payload("performance,seo,accessibility", audits=audits))

    assert "accessibility" not in without["website"]
    assert "accessibility" not in without["per_url"]["https://example.com"]
    assert with_["website"]["accessibility"]["mobile"]["total_failed"] == 1
    assert with_["per_url"]["https://example.com"]["accessibility"]["desktop"]["audits"]["color-contrast"]["status"] == "fail"


def test_accessibility_uses_the_audit_refs_from_the_categories():
    audits = {**full_audits(), "color-contrast": {"score": 0}, "label": {"score": 1}}
    cats = {"accessibility": {"auditRefs": [{"id": "label"}]}}

    result = format_lighthouse_output(lighthouse_payload("accessibility", audits=audits, cats=cats))

    mobile = result["per_url"]["https://example.com"]["accessibility"]["mobile"]
    assert list(mobile["audits"]) == ["label"]


def test_categories_may_be_a_list_in_the_meta():
    payload = lighthouse_payload(audits=full_audits())
    payload["meta"]["categories"] = ["performance", "seo", "accessibility"]

    assert "accessibility" in format_lighthouse_output(payload)["website"]


def test_failed_and_malformed_urls_are_reported_and_left_out_of_the_averages():
    payload = lighthouse_payload(audits=full_audits(), url="https://good.com")
    payload["lighthouse_data"]["https://failed.com"] = {"status": "error"}
    payload["lighthouse_data"]["https://junk.com"] = "junk"

    result = format_lighthouse_output(payload)

    assert list(result["per_url"]) == ["https://good.com"]
    assert result["website"]["seo"]["mobile"]["total_urls"] == 1
    assert [(e["url"], e["level"]) for e in result["errors"]] == [("https://failed.com", "warning"), ("https://junk.com", "error")]


@pytest.mark.parametrize("payload", [{}, {"lighthouse_data": {}}, {"lighthouse_data": None}, {"meta": {}, "lighthouse_data": []}])
def test_missing_results_return_an_empty_structure_with_an_error(payload):
    result = format_lighthouse_output(payload)

    assert result["website"] == {}
    assert result["per_url"] == {}
    assert result["errors"] == [{"level": "error", "url": "*", "stage": "input", "message": "Missing results"}]
    assert result["logs"][0]["level"] == "error"


def test_all_urls_failing_gives_empty_website_sections():
    payload = {"meta": {"categories": "performance,seo"}, "lighthouse_data": {"https://a.com": {"status": "error"}}}

    result = format_lighthouse_output(payload)

    assert result["website"]["performance"] == {"mobile": {}, "desktop": {}}
    assert result["website"]["seo"] == {"mobile": {}, "desktop": {}}


def test_main_reads_formats_and_writes(monkeypatch):
    written = {}
    monkeypatch.setattr(formatter, "load_input_file", lambda path: lighthouse_payload(audits=full_audits()))
    monkeypatch.setattr(formatter, "write_json_to_file", lambda data, out: written.update(data=data, out=out))

    formatter.main("in.json", "out-dir")
    assert written["out"] == "out-dir"
    assert "website" in written["data"]

    written.clear()
    formatter.main("in.json", None)
    assert written == {}
