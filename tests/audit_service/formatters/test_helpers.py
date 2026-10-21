import json

import pytest

from app.audit_service.audit.formatters.helpers import (
    add_error,
    collect,
    count_status_200,
    get_audit_metric,
    load_input_file,
    log,
    safe_average,
    safe_get,
    top_n_by_key,
)


@pytest.mark.parametrize(
    "data, path, default, expected",
    [
        ({"a": {"b": 1}}, ["a", "b"], None, 1),
        ({"a": {"b": 1}}, ["a", "c"], "d", "d"),
        ({"a": {"b": 1}}, ["x", "b"], "d", "d"),
        ({"a": [10, 20]}, ["a", 1], None, 20),
        ({"a": [10, 20]}, ["a", 5], "d", "d"),
        ({"a": [{"k": "v"}]}, ["a", 0, "k"], None, "v"),
        ({"a": None}, ["a"], "d", "d"),
        ({"a": 0}, ["a"], "d", 0),
        ({"a": ""}, ["a"], "d", ""),
        ({"a": 5}, ["a", "b"], "d", "d"),
        ({"a": [1]}, ["a", "b"], "d", "d"),
        (None, ["a"], "d", "d"),
        ("text", ["a"], "d", "d"),
        ({"a": 1}, [], "d", {"a": 1}),
    ],
)
def test_safe_get(data, path, default, expected):
    assert safe_get(data, path, default) == expected


def test_safe_average():
    assert safe_average([1, 2, 3, 4]) == 2.5
    assert safe_average([5]) == 5.0
    assert isinstance(safe_average([1, 2]), float)


@pytest.mark.parametrize("values", [[], None])
def test_safe_average_of_nothing_is_none(values):
    assert safe_average(values) is None


def test_top_n_by_key_sorts_descending_and_limits():
    items = [{"size": 5}, {"size": 50}, {"size": 20}, {"size": 1}]

    assert top_n_by_key(items, "size", n=2) == [{"size": 50}, {"size": 20}]
    assert len(top_n_by_key(items, "size")) == 3


def test_top_n_by_key_skips_items_without_the_key_and_non_dicts():
    items = [{"size": 5}, {"other": 1}, "junk", None, {"size": 9}]

    assert top_n_by_key(items, "size") == [{"size": 9}, {"size": 5}]


@pytest.mark.parametrize("items", [[], None])
def test_top_n_by_key_of_nothing(items):
    assert top_n_by_key(items, "size") == []


def test_count_status_200():
    requests = [{"statusCode": 200}, {"statusCode": 200}, {"statusCode": 404}, {"statusCode": 301}, {}]

    assert count_status_200(requests) == (2, 3)


def test_count_status_200_ignores_non_dicts_and_handles_empty():
    assert count_status_200([{"statusCode": 200}, "junk", None]) == (1, 0)
    assert count_status_200([]) == (0, 0)
    assert count_status_200(None) == (0, 0)


def test_collect_gathers_numeric_values_across_urls():
    per_url = {
        "a": {"fcp": {"value": 100}},
        "b": {"fcp": {"value": 250.5}},
        "c": {"fcp": {"value": None}},
        "d": {"fcp": "junk"},
        "e": {"other": {"value": 1}},
        "f": {"fcp": {"value": "12"}},
    }

    assert collect("fcp", per_url) == [100.0, 250.5]


def test_get_audit_metric_reads_from_dicts_and_lists():
    assert get_audit_metric({"diag": {"requests": 7}}, "requests", "diag") == 7
    assert get_audit_metric({"diag": [{"requests": 9}, {"requests": 1}]}, "requests", "diag") == 9


@pytest.mark.parametrize(
    "data",
    [{}, {"diag": {}}, {"diag": []}, {"diag": {"other": 1}}, {"diag": ["junk"]}, {"diag": "junk"}, {"diag": None}],
)
def test_get_audit_metric_returns_none_when_missing(data):
    assert get_audit_metric(data, "requests", "diag") is None


def test_log_and_add_error_append_structured_entries():
    logs, errors = [], []

    log(logs, "info", "hello")
    add_error(errors, url="https://a.com", stage="input", message="bad")
    add_error(errors, url="https://b.com", stage="parse", message="odd", level="warning")

    assert logs == [{"level": "info", "message": "hello"}]
    assert errors == [
        {"level": "error", "url": "https://a.com", "stage": "input", "message": "bad"},
        {"level": "warning", "url": "https://b.com", "stage": "parse", "message": "odd"},
    ]


def test_load_input_file_reads_utf8_json(tmp_path):
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"name": "Café"}, ensure_ascii=False), encoding="utf-8")

    assert load_input_file(str(path)) == {"name": "Café"}


def test_load_input_file_raises_for_missing_or_invalid_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_input_file(str(tmp_path / "missing.json"))

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        load_input_file(str(bad))
