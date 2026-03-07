import argparse
import datetime
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from .styles import get_styles, MAX_URLS
from .helpers import domain_from_url
from .layout import header_footer
from .sections.cover_page import cover_page
from .sections.executive_summary import executive_summary_section
from .sections.findings import key_findings_section
from .sections.findings_section import findings_section
from .sections.methodology import methodology_section
from .sections.site_average_metrics import site_average_section
from .sections.per_url_section import per_url_section
from .sections.audit_score_sections import (
    audit_score_overview_section,
    audit_score_per_url_section,
)
from .sections.limitations import limitations_section


def _legacy_perf_payload(data: Dict[str, Any]) -> bool:
    return isinstance(data, dict) and "first_contentful_paint" in data


def _select_website_data(lh: Dict[str, Any], report_type: str, platform_label: str) -> Dict[str, Any]:
    website = lh.get("website_performance_data", {}) or {}
    if report_type == "performance" and _legacy_perf_payload(website):
        return website
    return (website.get(report_type, {}) or {}).get(platform_label, {}) or {}


def _select_per_url_data(lh: Dict[str, Any], report_type: str, platform_label: str) -> Dict[str, Any]:
    per_url_all = lh.get("per_url_performance_data", {}) or {}
    if report_type == "performance" and per_url_all and _legacy_perf_payload(next(iter(per_url_all.values()))):
        return per_url_all

    per_url: Dict[str, Any] = {}
    for url, data in per_url_all.items():
        report_entry = (data.get(report_type, {}) or {})
        platform_entry = report_entry.get(platform_label)
        if platform_entry:
            per_url[url] = platform_entry
    return per_url

def build_pdf(
    data: Dict[str, Any],
    output_pdf: str,
    client_name: str,
    report_type: str = "performance",
) -> None:
    """
    Creates the PDF output with all the seo and performance data 

    Args:
        data (Dict[str, Any], required): lighthouse audit data and ai summary data
        output_pdf (str, required): pdf filename
        client_name (str, required): client name

    Returns: 
        None

    Outputs:
        lighthouse audit report 

    Since: 31-01-2026 
    """
    logo_path = "app/assets/valvanta-digital-logo.png"
    cover_image_path = "app/assets/pdf-cover-image.png"
    audit = data.get("audit", {}) or {}

    sitemap = audit.get("sitemap", {}) or {}
    lh = audit.get("lighthouse", {}) or {}
    ai = data.get("ai", {}) or {}

    styles = get_styles()
    
    per_url_all = lh.get("per_url_performance_data", {}) or {}
    tested_urls = lh.get("tested_urls") or list(per_url_all.keys())
    tested_urls = list(tested_urls)[:MAX_URLS]
    client_domain = domain_from_url(sitemap.get("start", tested_urls[0] if tested_urls else client_name))

    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Website Performance Audit - {client_domain}",
        author="Valvanta Digital",
    )

    story: List[Any] = []
    story.append(PageBreak())

    normalized_findings = lh.get("normalized_findings", {}) or {}
    summary = lh.get("summary", {}) or {}

    if report_type in ("performance", "seo"):
        story += methodology_section(lh, tested_urls)
        story.append(PageBreak())
        story += executive_summary_section(ai, summary.get(report_type, {}) or {}, report_type=report_type)

        story += findings_section(
            normalized_findings.get(report_type, {}).get("mobile", []),
            f"{report_type.title()} (Mobile)",
        )
        story.append(PageBreak())
        story += findings_section(
            normalized_findings.get(report_type, {}).get("desktop", []),
            f"{report_type.title()} (Desktop)",
        )

        story.append(PageBreak())

        for platform_label in ("mobile", "desktop"):
            website_data = _select_website_data(lh, report_type, platform_label)
            per_url_data = _select_per_url_data(lh, report_type, platform_label)
            section_label = platform_label.title()

            if report_type == "performance":
                story += site_average_section(website_data, per_url_data, section_label=section_label)
                story.append(PageBreak())
            else:
                report_label = "SEO"
                story += audit_score_overview_section(website_data, report_label, section_label=section_label)
                story.append(PageBreak())

        for platform_label in ("mobile", "desktop"):
            per_url_data = _select_per_url_data(lh, report_type, platform_label)
            section_label = platform_label.title()

            if report_type == "performance":
                story += per_url_section(ai, per_url_data, section_label=section_label, report_type=report_type)
                story.append(PageBreak())
            else:
                report_label = "SEO"
                story += audit_score_per_url_section(
                    per_url_data,
                    report_label,
                    section_label=section_label,
                    ai=ai,
                    report_type=report_type,
                )
                story.append(PageBreak())

    elif report_type == "key_findings":
        story += methodology_section(lh, tested_urls)
        story.append(PageBreak())
        story += key_findings_section(ai)
    else:
        raise ValueError(f"Unknown report_type: {report_type}")

    def cover(canvas, doc):
        title_map = {
            "performance": "Technical & Performance Report",
            "seo": "Technical & SEO Report",
            "key_findings": "Key Findings & Priorities",
        }
        cover_page(
            canvas,
            doc,
            sitemap,
            lh,
            client_name,
            client_domain,
            logo_path,
            cover_image_path,
            report_title=title_map.get(report_type),
        )
    
    def _header_footer(canvas, doc):
        header_footer(canvas, doc, client_domain)

    # Cover on page 1, header/footer on later pages
    doc.build(story, onFirstPage=cover, onLaterPages=_header_footer)


def build_reports(
    data: Dict[str, Any],
    output_dir: str,
    client_name: str,
) -> Dict[str, str]:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    reports = {
        "performance": os.path.join(output_dir, f"Performance_PDF_{ts}.pdf"),
        "seo": os.path.join(output_dir, f"SEO_PDF_{ts}.pdf"),
        "key_findings": os.path.join(output_dir, f"Key_Findings_{ts}.pdf"),
    }
    for report_type, path in reports.items():
        build_pdf(
            data,
            output_pdf=path,
            client_name=client_name,
            report_type=report_type,
        )
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-input", required=True, help="Lighthouse audit json file")
    parser.add_argument("--ai-input", required=True, help="Ai summary json file")
    parser.add_argument("--output", required=True, help="output PDF")
    parser.add_argument("--report-type", required=False, default="performance", help="performance|seo|key_findings|all")
    parser.add_argument("--client-name", required=True, help="Client name for cover page")
    parser.add_argument("--logo-path", required=False, default="assets/valvanta-digital-logo-light.png", help="Path to logo")
    args = parser.parse_args()

    with open(args.audit_input, "r", encoding="utf-8") as f:
        audit = json.load(f)

    with open(args.ai_input, "r", encoding="utf-8") as af:
        ai = json.load(af)
    
    payload = {"audit": audit, "ai": ai}
    if args.report_type == "all":
        output_dir = os.path.dirname(args.output) or "."
        build_reports(payload, output_dir, client_name=args.client_name)
    else:
        build_pdf(payload, args.output, client_name=args.client_name, report_type=args.report_type)


if __name__ == "__main__":
    main()
