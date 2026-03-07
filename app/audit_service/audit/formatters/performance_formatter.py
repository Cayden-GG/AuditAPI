import argparse
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ...writers.write_to_json import write_json_to_file
from .helpers import * 


def _get_audits_from_input(url_obj_or_audits: Dict[str, Any]) -> Dict[str, Any]:
    if "audits" in url_obj_or_audits:
        return url_obj_or_audits.get("audits", {}).get("performance_data", {}) or {}
    return url_obj_or_audits


def _platform_audits(url_obj: Dict[str, Any], platform: str) -> Dict[str, Any]:
    platform_obj = url_obj.get(platform, {}) or {}
    return platform_obj.get("audits") or platform_obj.get("audit") or {}


def reduce_url_performance(
    url: str,
    url_obj_or_audits: Dict[str, Any],
    *,
    logs: List[Dict[str, str]],
    errors: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    Reduce a single URL's Lighthouse payload into a smaller summary.
    
    Args: 
        url (str, required): the url to be tested
        url_obj (Dict[str, Any], required): url's lighthouse data obj 
        logs (List[Dict[str, str]], required): logs List so logging can be continue
        errors (List[Dict[str, str]], required): error List so errors can be caught

    Returns: 
        Dict with all the necessary data formatted for that one url
    """
    status = url_obj_or_audits.get("status")
    if status and status != "success":
        add_error(
            errors,
            url=url,
            stage="input",
            message=f"URL status is '{status}'. Skipping performance extraction.",
            level="warning",
        )
        return None

    audits = _get_audits_from_input(url_obj_or_audits)
    if not isinstance(audits, dict):
        add_error(errors, url=url, stage="input", message="Missing or invalid audits object.")
        return None

    # Basic numeric metrics (may be missing)
    def num(aid: str) -> Optional[float]:
        v = safe_get(audits, [aid, "numericValue"], None)
        return float(v) if isinstance(v, (int, float)) else None

    # Network requests (details may be missing depending on how you normalize audits)
    network_items = safe_get(audits, ["network-requests", "details", "items"], [])
    if network_items is None:
        network_items = []
    if not isinstance(network_items, list):
        network_items = []

    top_requests = top_n_by_key(network_items, "transferSize", n=3)
    ok_count, fail_count = count_status_200(network_items)

    # Main thread breakdown items
    mainthread_items = safe_get(audits, ["mainthread-work-breakdown", "details", "items"], [])
    if not isinstance(mainthread_items, list):
        mainthread_items = []

    # Diagnostics items are typically at [0]
    diag0 = safe_get(audits, ["diagnostics", "details", "items", 0], {})
    if not isinstance(diag0, dict):
        diag0 = {}

    # Resource summary is an array; indexes vary in some Lighthouse versions.
    # We will extract by "resourceType" if present; fallback to fixed indexes.
    resource_items = safe_get(audits, ["resource-summary", "details", "items"], [])
    if not isinstance(resource_items, list):
        resource_items = []

    def resource_transfer(resource_type: str) -> Optional[float]:
        for item in resource_items:
            if isinstance(item, dict) and item.get("resourceType") == resource_type:
                v = item.get("transferSize")
                return float(v) if isinstance(v, (int, float)) else None
        return None

    # Fallback indexes (less stable)
    total_transfer = resource_transfer("total") or safe_get(resource_items, [0, "transferSize"], None)
    image_transfer = resource_transfer("image") or safe_get(resource_items, [1, "transferSize"], None)
    script_transfer = resource_transfer("script") or safe_get(resource_items, [2, "transferSize"], None)
    stylesheet_transfer = resource_transfer("stylesheet") or safe_get(resource_items, [3, "transferSize"], None)
    document_transfer = resource_transfer("document") or safe_get(resource_items, [4, "transferSize"], None)
    third_party_transfer = resource_transfer("third-party") or safe_get(resource_items, [7, "transferSize"], None)

    # Server latency
    server_latency = num("network-server-latency")
    server_latency_items = safe_get(audits, ["network-server-latency", "details", "items"], [])
    if not isinstance(server_latency_items, list):
        server_latency_items = []
    server_latency_top = server_latency_items[:5]

    log(logs, "info", f"Reduced performance data for {url}")

    return {
        "first_contentful_paint": {
            "value": num("first-contentful-paint")
        },
        "largest_contentful_paint": {
            "value": num("largest-contentful-paint")
        },
        "speed_index": {
            "value": num("speed-index")
        },
        "total_blocking_time": {
            "value": num("total-blocking-time")
        },
        "main_thread_work_breakdown": {
            "value": num("mainthread-work-breakdown"),
            "mainthread_work_items": mainthread_items[:3]
        },
        "diagnostics": {
            "request_count": diag0.get("numRequests"),
            "task_count": diag0.get("numTasks"),
            "total_byte_weight": diag0.get("totalByteWeight"),
        },
        "network_requests": {
            "code_200_requests_count": ok_count,
            "code_non_200_requests_count": fail_count,
            "top_by_transfer_size": top_requests,
        },
        "resource_summary": {
            "total_transfer_size": total_transfer,
            "image_transfer_size": image_transfer,
            "script_transfer_size": script_transfer,
            "stylesheet_transfer_size": stylesheet_transfer,
            "document_transfer_size": document_transfer,
            "third_party_transfer_size": third_party_transfer,
        },
        "network_server_latency": {
            "server_latency": server_latency,
            "server_latency_types": server_latency_top,
        },
    }


def aggregate_website_performance(
    per_url: Dict[str, Dict[str, Any]],
    *,
    logs: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Reduce entire website Lighthouse payload into a smaller summary.

    Args: 
        per_url (Dict[str, Dict[str, Any], required): the url to be tested
        logs (List[Dict[str, str]], required): logs List so logging can be continue

    Returns: 
        Dict with all the necessary data formatted for that the site
    """
    
    fcp = safe_average(collect("first_contentful_paint", per_url))
    lcp = safe_average(collect("largest_contentful_paint", per_url))
    speed_index = safe_average(collect("speed_index", per_url))
    tbt = safe_average(collect("total_blocking_time", per_url))

    # Mainthread group averaging
    group_durations: Dict[str, List[float]] = {}
    for _, d in per_url.items():
        for item in d.get("main_thread_work_breakdown", []) or []:
            breakdown = d.get("main_thread_work_breakdown", {})
            items = breakdown.get("mainthread_work_items", [])

            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                group = item.get("group")
                dur = item.get("duration")

                if isinstance(group, str) and isinstance(dur, (int, float)):
                    group_durations.setdefault(group, []).append(float(dur))

    mode_mainthread_work = [
        {"group": g, "average_mainthread_item_duration": float(np.mean(v))}
        for g, v in group_durations.items()
        if v
    ]
    mode_mainthread_work.sort(key=lambda x: x["average_mainthread_item_duration"], reverse=True)

    # Server response time averaging by origin
    origin_times: Dict[str, List[float]] = {}
    for _, d in per_url.items():
        top = safe_get(d, ["network_server_latency", "server_latency_types"], [])
        if not isinstance(top, list):
            continue
        for item in top:
            if not isinstance(item, dict):
                continue
            origin = item.get("origin")
            srt = item.get("serverResponseTime")
            if isinstance(origin, str) and isinstance(srt, (int, float)):
                origin_times.setdefault(origin, []).append(float(srt))

    mode_server_response_times = [
        {"origin": o, "average_server_response_time": float(np.mean(v))}
        for o, v in origin_times.items()
        if v
    ]
    mode_server_response_times.sort(key=lambda x: x["average_server_response_time"], reverse=True)

    log(logs, "info", f"Aggregated website performance across {len(per_url)} URLs")

    return {
        "first_contentful_paint": {
            "average_value": fcp
        },
        "largest_contentful_paint": {
            "average_value": lcp
        },
        "speed_index": {
            "average_value": speed_index
        },
        "total_blocking_time": {
            "average_value": tbt
        },
        "mainthread_work_breakdown": {
            "average_value": safe_average(collect("main_thread_work_breakdown", per_url)),
            "mode_mainthread_work_items": mode_mainthread_work[:10],
        },
        "diagnostics": {
            "average_requests_count": safe_average([get_audit_metric(d, "request_count", "diagnostics") for d in per_url.values()]),
            "average_tasks_count": safe_average([get_audit_metric(d, "task_count", "diagnostics") for d in per_url.values()]),
            "average_total_byte_weight": safe_average([get_audit_metric(d, "total_byte_weight", "diagnostics") for d in per_url.values()]),
        },
        "network_requests": {
            "average_code_200_request_count": safe_average([get_audit_metric(d, "code_200_requests_count", "network_requests") for d in per_url.values()]),
            "average_non_code_200_request_count": safe_average([get_audit_metric(d, "code_non_200_requests_count", "network_requests") for d in per_url.values()]),
        },
        "resource_summary_bytes": {
            "average_total_transfer_size": safe_average([get_audit_metric(d, "total_transfer_size", "resource_summary") for d in per_url.values()]),
            "average_image_transfer_size": safe_average([get_audit_metric(d, "image_transfer_size", "resource_summary") for d in per_url.values()]),
            "average_script_transfer_size": safe_average([get_audit_metric(d, "script_transfer_size", "resource_summary") for d in per_url.values()]),
            "average_stylesheet_transfer_size": safe_average([get_audit_metric(d, "stylesheet_transfer_size", "resource_summary") for d in per_url.values()]),
            "average_document_transfer_size": safe_average([get_audit_metric(d, "document_transfer_size", "resource_summary") for d in per_url.values()]),
            "average_third_party_transfer_size": safe_average([get_audit_metric(d, "third_party_transfer_size", "resource_summary") for d in per_url.values()]),
        },
        "network_server_latency": {
            "average_server_latency": safe_average([get_audit_metric(d, "server_latency", "network_server_latency") for d in per_url.values()]),
            "mode_server_latency_times": mode_server_response_times[:5],
        },
    }


def format_lighthouse_output(lighthouse_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the lighthouse data to reduce uneccessary data and split per url 
    performance data and cross site performance data

    Args: 
        lighthouse_output (Dict[str, Any], required): lighthouse audit data 

    Returns:
        formatted and reduced lighthouse audit data 

    Since: 01-02-2026
    """
    logs: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    meta = lighthouse_output.get("meta", {})
    results = lighthouse_output.get("lighthouse_data", {})

    if not isinstance(results, dict) or not results:
        log(logs, "error", "No results found in input file.")
        return {"meta": meta, "website": {}, "per_url": {}, "errors": [{"level": "error", "url": "*", "stage": "input", "message": "Missing results"}], "logs": logs}

    per_url: Dict[str, Dict[str, Any]] = {}
    per_url_mobile: Dict[str, Dict[str, Any]] = {}
    per_url_desktop: Dict[str, Dict[str, Any]] = {}

    for url, url_obj in results.items():
        if not isinstance(url_obj, dict):
            add_error(errors, url=url, stage="input", message="Result entry is not an object.")
            continue

        status = url_obj.get("status")
        if status != "success":
            add_error(
                errors,
                url=url,
                stage="input",
                message=f"URL status is '{status}'. Skipping performance extraction.",
                level="warning",
            )
            continue

        mobile_audits = _platform_audits(url_obj, "mobile")
        desktop_audits = _platform_audits(url_obj, "desktop")

        url_entry: Dict[str, Any] = {}
        mobile_reduced = reduce_url_performance(url, mobile_audits, logs=logs, errors=errors)
        if mobile_reduced is not None:
            url_entry["mobile"] = mobile_reduced
            per_url_mobile[url] = mobile_reduced

        desktop_reduced = reduce_url_performance(url, desktop_audits, logs=logs, errors=errors)
        if desktop_reduced is not None:
            url_entry["desktop"] = desktop_reduced
            per_url_desktop[url] = desktop_reduced

        if url_entry:
            per_url[url] = url_entry

    website = {
        "mobile": aggregate_website_performance(per_url_mobile, logs=logs) if per_url_mobile else {},
        "desktop": aggregate_website_performance(per_url_desktop, logs=logs) if per_url_desktop else {},
    }

    return {
        "meta": meta,
        "website": website,
        "per_url": per_url,
        "errors": errors,
        "logs": logs,
    }


def main(input_file: str, output_file: Optional[str]) -> Dict[str, Any]:
    data = load_input_file(input_file)
    formatted = format_lighthouse_output(data)

    if output_file:
        write_json_to_file(formatted, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Slim Lighthouse output and compute website averages")

    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to FRS-style Lighthouse JSON output file",
    )
    parser.add_argument(
        "--output-file",
        required=False,
        default=None,
        help="Path to write slimmed JSON output (optional)",
    )

    args = parser.parse_args()
    main(args.input_file, args.output_file)
