"""
Middle man between cli and formatters
Runs the correct formatters for the audits completed
"""
import argparse
from typing import Any, Dict, List, Optional

from ..writers.write_to_json import write_json_to_file
from .formatters.helpers import add_error, load_input_file, log
from .formatters.performance_formatter import (
    aggregate_website_performance,
    reduce_url_performance,
)
from .formatters.seo_formatter import aggregate_website_seo, reduce_url_seo
from .formatters.accessability_formatter import (
    aggregate_website_accessibility,
    reduce_url_accessibility,
)

def _platform_audits(url_obj: Dict[str, Any], platform: str) -> Dict[str, Any]:
    platform_obj = url_obj.get(platform, {}) or {}
    return platform_obj.get("audits") or platform_obj.get("audit") or {}


def format_lighthouse_output(lighthouse_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formats the lighthouse data to reduce uneccessary data and split per url
    performance data and cross site performance data.
    """
    logs: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    meta = lighthouse_data.get("meta", {})
    results = lighthouse_data.get("lighthouse_data", {})

    if not isinstance(results, dict) or not results:
        log(logs, "error", "No results found in input file.")
        return {
            "meta": meta,
            "website": {},
            "per_url": {},
            "errors": [{"level": "error", "url": "*", "stage": "input", "message": "Missing results"}],
            "logs": logs,
        }

    per_url: Dict[str, Dict[str, Any]] = {}
    perf_mobile: Dict[str, Dict[str, Any]] = {}
    perf_desktop: Dict[str, Dict[str, Any]] = {}
    seo_mobile: Dict[str, Dict[str, Any]] = {}
    seo_desktop: Dict[str, Dict[str, Any]] = {}
    access_mobile: Dict[str, Dict[str, Any]] = {}
    access_desktop: Dict[str, Dict[str, Any]] = {}

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
                message=f"URL status is '{status}'. Skipping formatting.",
                level="warning",
            )
            continue

        mobile_audits = _platform_audits(url_obj, "mobile")
        desktop_audits = _platform_audits(url_obj, "desktop")

        url_entry: Dict[str, Any] = {}

        mobile_perf = reduce_url_performance(url, mobile_audits, logs=logs, errors=errors)
        desktop_perf = reduce_url_performance(url, desktop_audits, logs=logs, errors=errors)
        if mobile_perf or desktop_perf:
            url_entry.setdefault("performance", {})
        if mobile_perf is not None:
            url_entry["performance"]["mobile"] = mobile_perf
            perf_mobile[url] = mobile_perf
        if desktop_perf is not None:
            url_entry["performance"]["desktop"] = desktop_perf
            perf_desktop[url] = desktop_perf

        mobile_seo = reduce_url_seo(url, mobile_audits, logs=logs, errors=errors)
        desktop_seo = reduce_url_seo(url, desktop_audits, logs=logs, errors=errors)
        if mobile_seo or desktop_seo:
            url_entry.setdefault("seo", {})
        if mobile_seo is not None:
            url_entry["seo"]["mobile"] = mobile_seo
            seo_mobile[url] = mobile_seo
        if desktop_seo is not None:
            url_entry["seo"]["desktop"] = desktop_seo
            seo_desktop[url] = desktop_seo

        mobile_access = reduce_url_accessibility(url, mobile_audits, logs=logs, errors=errors)
        desktop_access = reduce_url_accessibility(url, desktop_audits, logs=logs, errors=errors)
        if mobile_access or desktop_access:
            url_entry.setdefault("accessibility", {})
        if mobile_access is not None:
            url_entry["accessibility"]["mobile"] = mobile_access
            access_mobile[url] = mobile_access
        if desktop_access is not None:
            url_entry["accessibility"]["desktop"] = desktop_access
            access_desktop[url] = desktop_access

        if url_entry:
            per_url[url] = url_entry

    website = {
        "performance": {
            "mobile": aggregate_website_performance(perf_mobile, logs=logs) if perf_mobile else {},
            "desktop": aggregate_website_performance(perf_desktop, logs=logs) if perf_desktop else {},
        },
        "seo": {
            "mobile": aggregate_website_seo(seo_mobile, logs=logs) if seo_mobile else {},
            "desktop": aggregate_website_seo(seo_desktop, logs=logs) if seo_desktop else {},
        },
        "accessibility": {
            "mobile": aggregate_website_accessibility(access_mobile, logs=logs) if access_mobile else {},
            "desktop": aggregate_website_accessibility(access_desktop, logs=logs) if access_desktop else {},
        },
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
