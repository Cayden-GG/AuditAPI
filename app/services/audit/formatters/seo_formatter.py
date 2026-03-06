import argparse
from typing import Any, Dict, List, Optional

from ...writers.write_to_json import write_json_to_file
from ..audit_config import SEO_AUDIT_IDS
from .helpers import add_error, load_input_file, log, safe_average


def _audit_status(audit: Dict[str, Any]) -> str:
    mode = audit.get("scoreDisplayMode")
    if mode in ("notApplicable", "manual", "informative"):
        return "not_applicable"

    score = audit.get("score")
    if isinstance(score, (int, float)):
        return "pass" if score >= 0.9 else "fail"

    return "not_applicable"


def reduce_url_seo(
    url: str,
    audits: Dict[str, Any],
    *,
    logs: List[Dict[str, str]],
    errors: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    Reduce a single URL's SEO Lighthouse payload into a smaller summary.
    """
    if not isinstance(audits, dict):
        add_error(errors, url=url, stage="input", message="Missing or invalid SEO audits object.")
        return None

    audit_map: Dict[str, Any] = {}
    scores: List[float] = []
    passed = 0
    failed = 0
    not_applicable = 0

    for audit_id in SEO_AUDIT_IDS:
        audit = audits.get(audit_id, {})
        if not isinstance(audit, dict):
            continue

        status = _audit_status(audit)
        score = audit.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))

        if status == "pass":
            passed += 1
        elif status == "fail":
            failed += 1
        else:
            not_applicable += 1

        audit_map[audit_id] = {
            "score": score,
            "display_value": audit.get("displayValue"),
            "numeric_value": audit.get("numericValue"),
            "status": status,
        }

    log(logs, "info", f"Reduced SEO data for {url}")

    return {
        "summary": {
            "average_score": safe_average(scores),
            "passed": passed,
            "failed": failed,
            "not_applicable": not_applicable,
            "total_audits": len(audit_map),
        },
        "audits": audit_map,
    }


def aggregate_website_seo(
    per_url: Dict[str, Dict[str, Any]],
    *,
    logs: List[Dict[str, str]],
) -> Dict[str, Any]:
    scores: List[float] = []
    passed_total = 0
    failed_total = 0
    not_applicable_total = 0
    fail_counts: Dict[str, int] = {}
    audit_stats: Dict[str, Dict[str, Any]] = {}

    for data in per_url.values():
        summary = data.get("summary", {})
        avg_score = summary.get("average_score")
        if isinstance(avg_score, (int, float)):
            scores.append(float(avg_score))

        passed_total += int(summary.get("passed", 0) or 0)
        failed_total += int(summary.get("failed", 0) or 0)
        not_applicable_total += int(summary.get("not_applicable", 0) or 0)

        for audit_id, audit in (data.get("audits", {}) or {}).items():
            if isinstance(audit, dict) and audit.get("status") == "fail":
                fail_counts[audit_id] = fail_counts.get(audit_id, 0) + 1
            if not isinstance(audit, dict):
                continue
            stats = audit_stats.setdefault(
                audit_id,
                {
                    "scores": [],
                    "numeric_values": [],
                    "pass_count": 0,
                    "fail_count": 0,
                    "not_applicable_count": 0,
                },
            )
            status = audit.get("status")
            if status == "pass":
                stats["pass_count"] += 1
            elif status == "fail":
                stats["fail_count"] += 1
            else:
                stats["not_applicable_count"] += 1
            score = audit.get("score")
            if isinstance(score, (int, float)):
                stats["scores"].append(float(score))
            numeric_value = audit.get("numeric_value")
            if isinstance(numeric_value, (int, float)):
                stats["numeric_values"].append(float(numeric_value))

    total_urls = len(per_url)
    top_failed = [
        {
            "audit_id": audit_id,
            "fail_count": count,
            "fail_rate": round(count / total_urls, 3) if total_urls else 0.0,
        }
        for audit_id, count in sorted(fail_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    log(logs, "info", f"Aggregated SEO data across {total_urls} URLs")

    audit_summaries: Dict[str, Dict[str, Any]] = {}
    for audit_id, stats in audit_stats.items():
        total = stats["pass_count"] + stats["fail_count"] + stats["not_applicable_count"]
        summary = {
            "average_score": safe_average(stats["scores"]),
            "average_numeric_value": safe_average(stats["numeric_values"]),
            "pass_count": stats["pass_count"],
            "fail_count": stats["fail_count"],
            "not_applicable_count": stats["not_applicable_count"],
            "fail_rate": round(stats["fail_count"] / total, 3) if total else 0.0,
        }
        audit_summaries[audit_id] = summary

    return {
        "average_score": safe_average(scores),
        "total_urls": total_urls,
        "total_passed": passed_total,
        "total_failed": failed_total,
        "total_not_applicable": not_applicable_total,
        "top_failed_audits": top_failed[:10],
        "audit_summaries": audit_summaries,
    }


def format_lighthouse_output(lighthouse_output: Dict[str, Any]) -> Dict[str, Any]:
    logs: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    meta = lighthouse_output.get("meta", {})
    results = lighthouse_output.get("lighthouse_data", {})

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
                message=f"URL status is '{status}'. Skipping SEO extraction.",
                level="warning",
            )
            continue

        mobile_platform = url_obj.get("mobile", {}) or {}
        desktop_platform = url_obj.get("desktop", {}) or {}
        mobile_audits = (mobile_platform.get("audits") or mobile_platform.get("audit") or {}).get("seo_data", {})
        desktop_audits = (desktop_platform.get("audits") or desktop_platform.get("audit") or {}).get("seo_data", {})

        url_entry: Dict[str, Any] = {}
        mobile_reduced = reduce_url_seo(url, mobile_audits, logs=logs, errors=errors)
        if mobile_reduced is not None:
            url_entry["mobile"] = mobile_reduced
            per_url_mobile[url] = mobile_reduced

        desktop_reduced = reduce_url_seo(url, desktop_audits, logs=logs, errors=errors)
        if desktop_reduced is not None:
            url_entry["desktop"] = desktop_reduced
            per_url_desktop[url] = desktop_reduced

        if url_entry:
            per_url[url] = url_entry

    website = {
        "mobile": aggregate_website_seo(per_url_mobile, logs=logs) if per_url_mobile else {},
        "desktop": aggregate_website_seo(per_url_desktop, logs=logs) if per_url_desktop else {},
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
    parser = argparse.ArgumentParser(description="Slim Lighthouse SEO output and compute website averages")

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
