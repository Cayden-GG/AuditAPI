from typing import Any, Dict, List, Optional

from .helpers import add_error, log, safe_average


def _audit_status(audit: Dict[str, Any]) -> str:
    mode = audit.get("scoreDisplayMode")
    if mode in ("notApplicable", "manual", "informative"):
        return "not_applicable"

    score = audit.get("score")
    if isinstance(score, (int, float)):
        return "pass" if score >= 0.9 else "fail"

    return "not_applicable"


def reduce_url_accessibility(
    url: str,
    audits: Dict[str, Any],
    audit_ids: List[str],
    *,
    logs: List[Dict[str, str]],
    errors: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(audits, dict):
        add_error(errors, url=url, stage="input", message="Missing or invalid accessibility audits object.")
        return None

    if not audit_ids:
        log(logs, "warning", f"No accessibility audit IDs found for {url}")
        return None

    audit_map: Dict[str, Any] = {}
    scores: List[float] = []
    passed = 0
    failed = 0
    not_applicable = 0

    for audit_id in audit_ids:
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

    log(logs, "info", f"Reduced accessibility data for {url}")

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


def aggregate_website_accessibility(
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

    log(logs, "info", f"Aggregated accessibility data across {total_urls} URLs")

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
