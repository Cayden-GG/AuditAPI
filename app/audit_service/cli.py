

from __future__ import annotations

from .audit.sitemap_discovery import SitemapDiscoveryResult, discover_urls_from_sitemaps
from .audit.lighthouse_url_audit import audit_urls_with_lighthouse
from .writers.write_to_json import write_json_to_file
from .audit.formatter import format_lighthouse_output
from .audit.normalizer import normalize_lighthouse_results
from .config.settings import AppConfig, build_config
from .reports.pdf_report_generator import build_reports
from .ai.request import call_openai
from datetime import datetime

import json
from typing import Dict
from app.logging_utils import build_audit_logger

REPORT_KEYS = ("performance", "seo", "accessibility", "key_findings")


def _normalize_categories(value: str) -> str:
    categories = [c.strip() for c in (value or "").split(",") if c.strip()]
    return ",".join(categories) or "performance,seo"


def run_audit(config: AppConfig) -> Dict[str, str]:
    """
    Execute the audit pipeline and return generated report paths.
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    folder = f"{config.client_name}_audit_{timestamp}"
    output_dir = config.output_dir or f"audit_results/{folder}"
    log_path = config.log_path or f"{output_dir}/audit_log.jsonl"
    logger = build_audit_logger(config.audit_id, log_path)

    logger.info("Audit started", client_name=config.client_name, domain_url=config.domain_url)
    print("Discovering sitemaps/urls.")
    try:
        discovery = discover_urls_from_sitemaps(config.domain_url)
    except Exception as exc:
        logger.exception("Sitemap discovery failed.", exc)
        discovery = SitemapDiscoveryResult(
            sitemap_indexes=[],
            sitemaps=[],
            urls=[],
            per_sitemap=[],
            errors=[{"level": "error", "sitemap": config.domain_url, "stage": "discover", "message": str(exc)}],
            logs=[],
        )

    print(f"Discovery phase complete: {len(discovery.sitemaps)} sitemaps found, {len(discovery.urls)} urls found.")
    print("Starting performance tests now.")

    print(f"Errors: {discovery.errors}")
    print(f"Logs: {discovery.logs}")
    if discovery.errors:
        logger.warning("Sitemap discovery errors detected", errors=discovery.errors)
    if discovery.logs:
        logger.info("Sitemap discovery logs", logs=discovery.logs)
    
    urls_to_test = discovery.urls[:config.max_urls]
    if not urls_to_test:
        logger.warning("No URLs discovered for testing.", domain_url=config.domain_url)

    only_categories = _normalize_categories(config.only_categories)
    try:
        lighthouse_data = audit_urls_with_lighthouse(urls_to_test, only_categories=only_categories)
    except Exception as exc:
        logger.exception("Lighthouse run failed.", exc)
        lighthouse_data = {
            "meta": {
                "tool": "lighthouse-automation",
                "run_at": None,
                "lighthouse_version": None,
                "mode": "navigation",
                "categories": [c for c in only_categories.split(",") if c],
                "devices": ["mobile", "desktop"],
                "config": {},
                "tested_urls": urls_to_test,
            },
            "lighthouse_data": {},
            "logs": [str(exc)],
        }
    if lighthouse_data.get("logs"):
        logger.info("Lighthouse run logs captured.", logs=lighthouse_data.get("logs"))
    
    print(f"Performance testing complete for all {len(discovery.urls)} urls")
    print("Formatting preformance data.")
    
    formatted_data = format_lighthouse_output(lighthouse_data)
    if formatted_data.get("errors"):
        logger.warning("Formatter reported errors.", errors=formatted_data.get("errors"))
    if formatted_data.get("logs"):
        logger.info("Formatter logs captured.", logs=formatted_data.get("logs"))
    normalized = normalize_lighthouse_results(lighthouse_data)

    result = {
        "sitemap": {
            "start": config.domain_url,
            "indexes": discovery.sitemap_indexes,
            "sitemaps": discovery.sitemaps,
            "url_count": len(discovery.urls),
            "per_sitemap": discovery.per_sitemap,
            "errors": discovery.errors,
            "logs": discovery.logs,
        },
        "lighthouse": {
            "tested_url_count": len(urls_to_test),
            "tested_urls": urls_to_test,
            "run_at": lighthouse_data.get("meta", {}).get("run_at"),
            "lighthouse_version": lighthouse_data.get("meta", {}).get("lighthouse_version"),
            "categories": lighthouse_data.get("meta", {}).get("categories"),
            "mode": lighthouse_data.get("meta", {}).get("mode"),
            "devices": lighthouse_data.get("meta", {}).get("devices"),
            "config": lighthouse_data.get("meta", {}).get("config"),
            "website_performance_data": formatted_data["website"],
            "per_url_performance_data": formatted_data["per_url"],
            "normalized_findings": normalized.get("findings"),
            "summary": normalized.get("summary"),
        },
    }
    print("Performance data formatted.")
    print("Generating AI summaries.")
    
    # Get ai summary 
    ai_result = call_openai(result, logger=logger)
    if ai_result is None:
        logger.warning("AI summary missing; continuing without AI output.")
        ai_result = {}

    print("Starting PDF generation.")

    # generate json file 
    ai_save = write_json_to_file(ai_result, output_dir=output_dir, filename=f"ai_audit_summary{timestamp}.json")
    print(f"Saved audit AI data to {ai_save}")
    json_save = write_json_to_file(result, output_dir=output_dir)
    print(f"Saved JSON data to {json_save}")

    pdf_data = {"audit": result, "ai": ai_result}

    # generate pdfs
    reports: Dict[str, str] = {}
    try:
        include_accessibility = "accessibility" in only_categories.split(",")
        reports = build_reports(
            pdf_data,
            output_dir=output_dir,
            client_name=config.client_name,
            include_accessibility=include_accessibility,
        )
    except Exception as exc:
        logger.exception("PDF report generation failed.", exc)
    for report_type, path in reports.items():
        print(f"Saved {report_type} report to {path}")
    logger.info("Audit completed", report_paths=reports)
    print(f"LOG_PATH::{log_path}")
    return {key: reports[key] for key in REPORT_KEYS if key in reports}


def main():
    """
    Full Website Performance Audit
    """
    config = build_config()
    report_paths = run_audit(config)
    print(f"REPORT_PATHS::{json.dumps(report_paths)}")
    
    
if __name__ == "__main__":
    main()
