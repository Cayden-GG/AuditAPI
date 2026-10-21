import pytest

from app.audit_service.audit.formatters import performance_formatter as perf
from app.audit_service.audit.formatters.performance_formatter import (
    aggregate_website_performance,
    format_lighthouse_output,
    reduce_url_performance,
)
from tests.builders import lighthouse_payload, performance_audits


def reduce(audits, url="https://example.com"):
    logs, errors = [], []
    result = reduce_url_performance(url, audits, logs=logs, errors=errors)
    return result, logs, errors


def test_reduces_the_core_metrics():
    result, logs, errors = reduce(performance_audits())

    assert result["first_contentful_paint"] == {"value": 100.0}
    assert result["largest_contentful_paint"] == {"value": 200.0}
    assert result["speed_index"] == {"value": 300.0}
    assert result["total_blocking_time"] == {"value": 10.0}
    assert result["main_thread_work_breakdown"]["value"] == 5.0
    assert result["diagnostics"] == {"request_count": 1, "task_count": 2, "total_byte_weight": 3}
    assert result["network_server_latency"]["server_latency"] == 50.0
    assert errors == []
    assert logs == [{"level": "info", "message": "Reduced performance data for https://example.com"}]


def test_resource_sizes_are_matched_by_resource_type():
    result, _, _ = reduce(performance_audits())

    assert result["resource_summary"] == {
        "total_transfer_size": 1000.0,
        "image_transfer_size": 200.0,
        "script_transfer_size": 300.0,
        "stylesheet_transfer_size": 100.0,
        "document_transfer_size": 50.0,
        "third_party_transfer_size": 400.0,
    }


def test_resource_sizes_fall_back_to_positions_when_types_are_missing():
    items = [{"transferSize": size} for size in (10, 20, 30, 40, 50, 60, 70, 80)]
    audits = {"resource-summary": {"details": {"items": items}}}

    result, _, _ = reduce(audits)

    assert result["resource_summary"] == {
        "total_transfer_size": 10,
        "image_transfer_size": 20,
        "script_transfer_size": 30,
        "stylesheet_transfer_size": 40,
        "document_transfer_size": 50,
        "third_party_transfer_size": 80,
    }


def test_network_requests_are_counted_and_the_three_biggest_listed():
    items = [{"statusCode": 200, "transferSize": s} for s in (5, 500, 50, 5000)] + [{"statusCode": 404, "transferSize": 1}]
    audits = {"network-requests": {"details": {"items": items}}}

    result, _, _ = reduce(audits)

    requests = result["network_requests"]
    assert requests["code_200_requests_count"] == 4
    assert requests["code_non_200_requests_count"] == 1
    assert [r["transferSize"] for r in requests["top_by_transfer_size"]] == [5000, 500, 50]


def test_only_the_first_three_main_thread_items_and_five_latency_origins_are_kept():
    audits = {
        "mainthread-work-breakdown": {"numericValue": 1, "details": {"items": [{"group": g} for g in "abcde"]}},
        "network-server-latency": {"details": {"items": [{"origin": str(i)} for i in range(8)]}},
    }

    result, _, _ = reduce(audits)

    assert [i["group"] for i in result["main_thread_work_breakdown"]["mainthread_work_items"]] == ["a", "b", "c"]
    assert len(result["network_server_latency"]["server_latency_types"]) == 5


def test_missing_audits_give_empty_values_instead_of_errors():
    result, _, errors = reduce({})

    assert result["first_contentful_paint"] == {"value": None}
    assert result["diagnostics"] == {"request_count": None, "task_count": None, "total_byte_weight": None}
    assert result["network_requests"]["code_200_requests_count"] == 0
    assert result["resource_summary"]["total_transfer_size"] is None
    assert errors == []


@pytest.mark.parametrize(
    "key, value",
    [
        ("network-requests", {"details": {"items": "junk"}}),
        ("network-requests", {"details": {"items": None}}),
        ("mainthread-work-breakdown", {"details": {"items": {"a": 1}}}),
        ("resource-summary", {"details": {"items": "junk"}}),
        ("diagnostics", {"details": {"items": ["junk"]}}),
        ("network-server-latency", {"details": {"items": "junk"}}),
    ],
)
def test_malformed_detail_sections_are_ignored(key, value):
    result, _, errors = reduce({key: value})

    assert result is not None
    assert errors == []


def test_non_numeric_metric_values_become_none():
    result, _, _ = reduce({"first-contentful-paint": {"numericValue": "fast"}})

    assert result["first_contentful_paint"] == {"value": None}


def test_failed_urls_are_skipped_with_a_warning():
    result, _, errors = reduce({"status": "error", "message": "boom"})

    assert result is None
    assert errors[0]["level"] == "warning"
    assert "'error'" in errors[0]["message"]


def test_audits_nested_under_performance_data_are_unwrapped():
    wrapped = {"audits": {"performance_data": performance_audits()}}

    result, _, _ = reduce(wrapped)

    assert result["first_contentful_paint"] == {"value": 100.0}


# aggregate_website_performance

def reduced(**overrides):
    audits = performance_audits()
    audits.update(overrides)
    return reduce(audits)[0]


def test_aggregate_averages_metrics_across_urls():
    per_url = {
        "a": reduced(**{"first-contentful-paint": {"numericValue": 100}}),
        "b": reduced(**{"first-contentful-paint": {"numericValue": 300}}),
    }
    logs = []

    result = aggregate_website_performance(per_url, logs=logs)

    assert result["first_contentful_paint"] == {"average_value": 200.0}
    assert result["largest_contentful_paint"] == {"average_value": 200.0}
    assert result["diagnostics"]["average_requests_count"] == 1.0
    assert result["network_requests"]["average_code_200_request_count"] == 1.0
    assert result["resource_summary_bytes"]["average_total_transfer_size"] == 1000.0
    assert result["network_server_latency"]["average_server_latency"] == 50.0
    assert logs == [{"level": "info", "message": "Aggregated website performance across 2 URLs"}]


def test_aggregate_ranks_main_thread_groups_and_server_origins_by_average():
    def with_items(groups, origins):
        return reduced(
            **{
                "mainthread-work-breakdown": {"numericValue": 1, "details": {"items": groups}},
                "network-server-latency": {"numericValue": 1, "details": {"items": origins}},
            }
        )

    per_url = {
        "a": with_items(
            [{"group": "script", "duration": 100}, {"group": "layout", "duration": 10}],
            [{"origin": "https://a.com", "serverResponseTime": 20}, {"origin": "https://cdn.com", "serverResponseTime": 300}],
        ),
        "b": with_items(
            [{"group": "script", "duration": 300}],
            [{"origin": "https://a.com", "serverResponseTime": 60}],
        ),
    }

    result = aggregate_website_performance(per_url, logs=[])

    assert result["mainthread_work_breakdown"]["mode_mainthread_work_items"] == [
        {"group": "script", "average_mainthread_item_duration": 200.0},
        {"group": "layout", "average_mainthread_item_duration": 10.0},
    ]
    assert result["network_server_latency"]["mode_server_latency_times"] == [
        {"origin": "https://cdn.com", "average_server_response_time": 300.0},
        {"origin": "https://a.com", "average_server_response_time": 40.0},
    ]


def test_aggregate_with_no_urls_has_no_averages():
    result = aggregate_website_performance({}, logs=[])

    assert result["first_contentful_paint"] == {"average_value": None}
    assert result["mainthread_work_breakdown"]["mode_mainthread_work_items"] == []


@pytest.mark.xfail(
    strict=True,
    reason="a url with no diagnostics data gives None metrics and safe_average raises a TypeError on them, "
    "which crashes the whole audit",
)
def test_aggregate_survives_a_url_without_diagnostics_data():
    per_url = {"full": reduced(), "empty": reduce({})[0]}

    result = aggregate_website_performance(per_url, logs=[])

    assert result["diagnostics"]["average_requests_count"] == 1.0
    assert result["first_contentful_paint"]["average_value"] == 100.0


# standalone format_lighthouse_output

def test_standalone_format_splits_platforms_and_aggregates():
    result = format_lighthouse_output(lighthouse_payload())

    assert set(result["per_url"]["https://example.com"]) == {"mobile", "desktop"}
    assert result["website"]["mobile"]["first_contentful_paint"] == {"average_value": 100.0}
    assert result["errors"] == []


def test_standalone_format_reports_missing_results_and_failed_urls():
    assert format_lighthouse_output({"meta": {}})["errors"][0]["message"] == "Missing results"

    payload = {"lighthouse_data": {"https://a.com": {"status": "error"}, "https://b.com": "junk"}}
    result = format_lighthouse_output(payload)

    assert result["per_url"] == {}
    assert result["website"] == {"mobile": {}, "desktop": {}}
    assert [e["level"] for e in result["errors"]] == ["warning", "error"]


def test_standalone_main_writes_the_formatted_file(tmp_path, monkeypatch):
    written = {}
    monkeypatch.setattr(perf, "load_input_file", lambda path: lighthouse_payload())
    monkeypatch.setattr(perf, "write_json_to_file", lambda data, out: written.update(data=data, out=out))

    perf.main("in.json", "out-dir")

    assert written["out"] == "out-dir"
    assert "per_url" in written["data"]

    written.clear()
    perf.main("in.json", None)
    assert written == {}
