import json
from types import SimpleNamespace

import pytest

from app.audit_service.ai import request
from app.audit_service.ai.request import (
    MAX_URLS,
    _build_ai_schema,
    _extract_categories,
    _per_url_schema,
    _summary_schema,
    build_single_prompt,
    call_openai,
    load_input_file,
)
from app.audit_service.ai.schema import AuditInsights
from tests.builders import RecordingLogger, audit_insights


def audit(categories="performance,seo", per_url=None, site=None):
    return {
        "lighthouse": {
            "categories": categories,
            "website_performance_data": site or {"performance": {"mobile": {"score": 1}}},
            "per_url_performance_data": per_url
            if per_url is not None
            else {"https://example.com/": {"performance": {"mobile": {"fcp": 1}}, "seo": {"mobile": {"ok": True}}}},
        }
    }


def dataset(prompt):
    return json.loads(prompt.split("DATASET_JSON=", 1)[1])


# schema builders

def test_summary_schema_requires_the_four_sections():
    schema = _summary_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["what_the_data_shows", "key_strengths", "primary_weaknesses", "high_level_roadmap"]
    assert set(schema["properties"]) == set(schema["required"])


def test_per_url_schema_is_an_array_of_url_and_analysis():
    schema = _per_url_schema()

    assert schema["type"] == "array"
    item = schema["items"]
    assert item["required"] == ["url", "analysis"]
    assert item["properties"]["analysis"]["required"][-1] == "recommendations"


@pytest.mark.parametrize("categories", [["performance", "seo"], ["performance", "seo", "accessibility"], ["seo"]])
def test_ai_schema_has_a_section_for_each_category(categories):
    schema = _build_ai_schema(categories)

    assert schema["name"] == "audit_insights"
    body = schema["schema"]
    assert body["required"] == ["executive_summaries", "prioritisation_method", "key_findings", "per_url_summaries"]
    for section in ("executive_summaries", "per_url_summaries"):
        assert list(body["properties"][section]["properties"]) == categories
        assert body["properties"][section]["required"] == categories
    finding = body["properties"]["key_findings"]["items"]
    assert finding["properties"]["priority"]["enum"] == ["High", "Medium", "Low"]
    assert finding["properties"]["effort"]["enum"] == ["Low", "Medium", "High"]


# categories and prompt

@pytest.mark.parametrize(
    "value, expected",
    [
        ("performance,seo", ["performance", "seo"]),
        (" seo , accessibility ,, ", ["seo", "accessibility"]),
        (["performance", " seo ", ""], ["performance", "seo"]),
        ("", ["performance", "seo"]),
        (None, ["performance", "seo"]),
        ([], ["performance", "seo"]),
    ],
)
def test_extract_categories(value, expected):
    assert _extract_categories({"lighthouse": {"categories": value}}) == expected


def test_extract_categories_without_lighthouse_data():
    assert _extract_categories({}) == ["performance", "seo"]
    assert _extract_categories({"lighthouse": None}) == ["performance", "seo"]


def test_prompt_embeds_the_dataset_and_schema():
    prompt = build_single_prompt(audit())

    assert prompt.startswith("You are a senior web performance consultant.")
    data = dataset(prompt)
    assert data["site_averages"] == {"performance": {"mobile": {"score": 1}}}
    assert data["per_url_metrics_by_category"] == {
        "performance": {"https://example.com/": {"mobile": {"fcp": 1}}},
        "seo": {"https://example.com/": {"mobile": {"ok": True}}},
    }
    assert data["schema"] == _build_ai_schema(["performance", "seo"])["schema"]


def test_prompt_names_the_requested_categories():
    prompt = build_single_prompt(audit(categories="performance,seo,accessibility"))

    assert "executive summaries for: performance, seo, accessibility." in prompt
    assert list(dataset(prompt)["per_url_metrics_by_category"]) == ["performance", "seo", "accessibility"]


def test_prompt_only_includes_the_data_of_each_category():
    per_url = {"https://a.com/": {"performance": {"mobile": {"x": 1}}}, "https://b.com/": {"seo": {"mobile": {"y": 2}}}}

    data = dataset(build_single_prompt(audit(per_url=per_url)))

    assert data["per_url_metrics_by_category"] == {
        "performance": {"https://a.com/": {"mobile": {"x": 1}}},
        "seo": {"https://b.com/": {"mobile": {"y": 2}}},
    }


def test_prompt_is_limited_to_the_first_max_urls():
    per_url = {f"https://a.com/{i}": {"performance": {"mobile": {"i": i}}} for i in range(MAX_URLS + 20)}

    data = dataset(build_single_prompt(audit(per_url=per_url)))

    urls = list(data["per_url_metrics_by_category"]["performance"])
    assert len(urls) == MAX_URLS
    assert urls[0] == "https://a.com/0"


def test_prompt_keeps_non_ascii_text_readable():
    prompt = build_single_prompt(audit(per_url={"https://café.com/": {"performance": {"mobile": {"n": 1}}}}))

    assert "https://café.com/" in prompt


def test_prompt_survives_an_audit_without_data():
    data = dataset(build_single_prompt({}))

    assert data["site_averages"] == {}
    assert data["per_url_metrics_by_category"] == {"performance": {}, "seo": {}}


def test_load_input_file(tmp_path):
    path = tmp_path / "audit.json"
    path.write_text(json.dumps({"a": "é"}, ensure_ascii=False), encoding="utf-8")

    assert load_input_file(str(path)) == {"a": "é"}


# call_openai

def test_debug_mode_skips_the_request(fake_openai):
    logger = RecordingLogger()

    assert call_openai(audit(), logger, debug_mode=True) == {}

    assert fake_openai.calls == []
    assert logger.messages("info") == ["AI summary skipped: debug mode enabled."]


def test_call_openai_requests_structured_output_with_the_prompt(fake_openai):
    fake_openai.parsed = audit_insights()

    call_openai(audit(), RecordingLogger())

    (call,) = fake_openai.calls
    assert call["model"] == "gpt-5.2"
    assert call["response_format"] is AuditInsights
    assert [m["role"] for m in call["messages"]] == ["system", "user"]
    assert call["messages"][1]["content"] == build_single_prompt(audit())


def test_call_openai_reshapes_per_url_summaries_by_category_and_url(fake_openai):
    urls = ("https://a.com/", "https://b.com/")
    fake_openai.parsed = audit_insights(urls=urls)

    result = call_openai(audit(), RecordingLogger())

    assert set(result) == {"executive_summaries", "prioritisation_method", "key_findings", "per_url_summaries"}
    assert result["prioritisation_method"] == "impact over effort"
    assert result["key_findings"][0]["issue"] == "Slow LCP"
    assert result["executive_summaries"]["performance"]["key_strengths"] == "strengths"
    assert set(result["per_url_summaries"]) == {"performance", "seo"}
    assert set(result["per_url_summaries"]["seo"]) == set(urls)
    assert result["per_url_summaries"]["seo"]["https://a.com/"] == {
        "what_the_data_shows": "d",
        "key_strengths": "s",
        "primary_weaknesses": "w",
        "recommendations": "r",
    }


def test_accessibility_summaries_are_included_when_it_was_audited(fake_openai):
    fake_openai.parsed = audit_insights(categories=("performance", "seo", "accessibility"))

    result = call_openai(audit(categories="performance,seo,accessibility"), RecordingLogger())

    assert set(result["per_url_summaries"]) == {"performance", "seo", "accessibility"}


def test_accessibility_summaries_are_dropped_when_it_was_not_audited(fake_openai):
    fake_openai.parsed = audit_insights(categories=("performance", "seo", "accessibility"))

    result = call_openai(audit(categories="performance,seo"), RecordingLogger())

    assert set(result["per_url_summaries"]) == {"performance", "seo"}


def test_a_failing_request_returns_none_and_is_logged(fake_openai):
    fake_openai.error = RuntimeError("rate limited")
    logger = RecordingLogger()

    assert call_openai(audit(), logger) is None
    assert logger.messages("exception") == ["AI summary request failed."]


def test_an_unexpected_response_shape_returns_none(fake_openai):
    fake_openai.parsed = None
    logger = RecordingLogger()

    assert call_openai(audit(), logger) is None
    assert logger.messages("exception") == ["AI summary request failed."]


@pytest.mark.xfail(
    strict=True,
    reason="an empty audit logs 'AI summary skipped' but the function carries on and still pays for an OpenAI request",
)
def test_an_empty_audit_does_not_call_openai(fake_openai):
    fake_openai.parsed = audit_insights()
    logger = RecordingLogger()

    call_openai({}, logger)

    assert fake_openai.calls == []
