

from __future__ import annotations

from .audit.sitemap_discovery import discover_urls_from_sitemaps
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

REPORT_KEYS = ("performance", "seo", "key_findings")


def run_audit(config: AppConfig) -> Dict[str, str]:
    """
    Execute the audit pipeline and return generated report paths.
    """
    print("Discovering sitemaps/urls.")
    discovery = discover_urls_from_sitemaps(config.domain_url)

    print(f"Discovery phase complete: {len(discovery.sitemaps)} sitemaps found, {len(discovery.urls)} urls found.")
    print("Starting performance tests now.")

    print(f"Errors: {discovery.errors}")
    print(f"Logs: {discovery.logs}")
    
    urls_to_test = discovery.urls[:config.max_urls]

    lighthouse_data = audit_urls_with_lighthouse(urls_to_test)
    
    print(f"Performance testing complete for all {len(discovery.urls)} urls")
    print("Formatting preformance data.")
    
    formatted_data = format_lighthouse_output(lighthouse_data)
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
    ai_result = call_openai(result)

    print("Starting PDF generation.")

    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    folder = f"{config.client_name}_audit_{timestamp}" 

    # generate json file 
    ai_save = write_json_to_file(ai_result, output_dir=f"audit_results/{folder}", filename=f"ai_audit_summary{timestamp}.json")
    print(f"Saved audit AI data to {ai_save}")
    json_save =  write_json_to_file(result, output_dir=f"audit_results/{folder}")
    print(f"Saved JSON data to {json_save}")

    pdf_data = {"audit": result, "ai": ai_result}

    # generate pdfs
    reports = build_reports(
        pdf_data,
        output_dir=f"audit_results/{folder}",
        client_name=config.client_name,
    )
    for report_type, path in reports.items():
        print(f"Saved {report_type} report to {path}")
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
