import json
import re
import sys

import pytest
from pypdf import PdfReader

from app.audit_service.reports import pdf_report_generator as generator
from app.audit_service.reports.pdf_report_generator import (
    _legacy_perf_payload,
    _select_per_url_data,
    _select_website_data,
    build_pdf,
    build_reports,
)
from tests.builders import ai_result, audit_result, performance_audits

URLS = ("https://example.com/", "https://example.com/about")


def data(categories="performance,seo", urls=URLS, ai=True):
    cats = tuple(categories.split(","))
    return {"audit": audit_result(categories, urls=urls), "ai": ai_result(cats, urls) if ai else {}}


def read(path):
    """The PdfReader and the text of every page, with whitespace collapsed because the PDF wraps lines mid phrase"""
    reader = PdfReader(str(path))
    return reader, " ".join(" ".join(page.extract_text().split()) for page in reader.pages)


def build(tmp_path, report_type, payload=None, **kwargs):
    path = tmp_path / f"{report_type}.pdf"
    build_pdf(payload or data("performance,seo,accessibility"), str(path), "Acme Co", report_type, **kwargs)
    return path


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    """Builds each report once per module and hands out (reader, text). Call it with a report type and free flag"""
    folder = tmp_path_factory.mktemp("pdfs")
    built = {}

    def get(report_type, free=False):
        if (report_type, free) not in built:
            path = folder / f"{report_type}-{'free' if free else 'paid'}.pdf"
            build_pdf(data("performance,seo,accessibility"), str(path), "Acme Co", report_type, is_free_audit=free)
            built[(report_type, free)] = read(path)
        return built[(report_type, free)]

    return get


# ---- data selection

def test_legacy_performance_payload_is_the_flat_format():
    assert _legacy_perf_payload({"first_contentful_paint": {}}) is True
    assert _legacy_perf_payload({"performance": {}}) is False
    assert _legacy_perf_payload(None) is False


def test_website_data_is_selected_by_report_type_and_platform():
    lh = audit_result("performance,seo")["lighthouse"]

    assert _select_website_data(lh, "seo", "desktop") is lh["website_performance_data"]["seo"]["desktop"]
    assert _select_website_data(lh, "accessibility", "mobile") == {}
    assert _select_website_data({}, "performance", "mobile") == {}


def test_website_data_in_the_legacy_format_is_used_as_is_for_performance():
    flat = {"first_contentful_paint": {"average_value": 1}}

    assert _select_website_data({"website_performance_data": flat}, "performance", "mobile") is flat
    assert _select_website_data({"website_performance_data": flat}, "seo", "mobile") == {}


def test_per_url_data_is_selected_by_report_type_and_platform():
    lh = audit_result("performance,seo")["lighthouse"]

    seo = _select_per_url_data(lh, "seo", "mobile")

    assert list(seo) == list(URLS)
    assert seo[URLS[0]] is lh["per_url_performance_data"][URLS[0]]["seo"]["mobile"]
    assert _select_per_url_data(lh, "accessibility", "mobile") == {}
    assert _select_per_url_data({}, "performance", "mobile") == {}


def test_per_url_data_skips_urls_without_that_platform():
    lh = {"per_url_performance_data": {"a": {"seo": {"mobile": {"x": 1}}}, "b": {"seo": {"desktop": {"x": 2}}}, "c": {}}}

    assert _select_per_url_data(lh, "seo", "mobile") == {"a": {"x": 1}}


def test_per_url_data_in_the_legacy_format_is_used_as_is_for_performance():
    flat = {"a": {"first_contentful_paint": {"value": 1}}}

    assert _select_per_url_data({"per_url_performance_data": flat}, "performance", "mobile") is flat


# ---- building reports

def test_performance_report_has_every_section(pdf):
    reader, text = pdf("performance")

    for expected in (
        "example.com", "Technical & Performance Report", "Acme Co",
        "Audit Methodology", "Executive Summary", "Performance (Mobile) Findings", "Performance (Desktop) Findings",
        "Site Averages - Detailed Breakdown (Mobile)", "Site Averages - Detailed Breakdown (Desktop)",
        "Per URL Breakdown (Mobile)", "Per URL Breakdown (Desktop)", "LCP is Poor",
    ):
        assert expected in text, expected
    assert len(reader.pages) > 5


def test_cover_shows_the_scores(pdf):
    _, text = pdf("performance")

    cover = text.split("Audit Methodology")[0]
    assert "62" in cover and "91" in cover and "70" in cover  # performance, seo and accessibility scores


def test_seo_report_has_its_sections(pdf):
    _, text = pdf("seo")

    for expected in (
        "Technical & SEO Report", "Executive Summary", "Seo (Mobile) Findings", "SEO Site Averages - Detailed Breakdown (Mobile)",
        "SEO Per URL Breakdown (Desktop)", "robots-txt", "robots.txt is not valid",
    ):
        assert expected in text, expected
    assert "Good targets: FCP" not in text  # the performance averages are not in the SEO report


def test_accessibility_report_has_its_sections(pdf):
    _, text = pdf("accessibility")

    for expected in ("Accessibility Report", "Accessibility Site Averages - Detailed Breakdown (Mobile)", "color-contrast"):
        assert expected in text, expected


def test_key_findings_report(pdf):
    reader, text = pdf("key_findings")

    for expected in ("Key Findings & Priorities", "Prioritisation method", "impact over effort", "Slow LCP", "Audit Methodology"):
        assert expected in text, expected
    assert len(reader.pages) < 6


def test_an_unknown_report_type_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown report_type: pdf"):
        build(tmp_path, "pdf")

    assert not (tmp_path / "pdf.pdf").exists()


def test_every_page_after_the_cover_has_a_header_and_footer(pdf):
    reader, _ = pdf("performance")

    later = [" ".join(page.extract_text().split()) for page in reader.pages[1:]]
    assert all("Website Audit Report" in t and "Prepared by Valvanta Digital Agency" in t for t in later)
    assert [re.search(r"Page (\d+)", t).group(1) for t in later[:3]] == ["2", "3", "4"]
    cover = reader.pages[0].extract_text()
    assert "Valvanta Digital Agency" in cover  # in the cover's details strip
    assert "Prepared by Valvanta Digital Agency" not in cover and "Page 1" not in cover


def test_the_document_metadata_names_the_report_and_domain(pdf):
    reader, _ = pdf("seo")

    assert reader.metadata.title == "Website seo Report - example.com"
    assert reader.metadata.author == "Valvanta Digital"


def test_free_audits_get_the_upsell_pages_and_paid_audits_do_not(pdf):
    paid_reader, paid_text = pdf("performance", free=False)
    free_reader, free_text = pdf("performance", free=True)

    assert "Premium Brand audit required" not in paid_text
    assert free_text.count("Premium Brand audit required") == 2  # mobile and desktop
    assert len(free_reader.pages) == len(paid_reader.pages) + 2
    assert "audit up to 100 urls with premium audit" in free_text


@pytest.mark.parametrize("report_type", ["performance", "seo", "accessibility", "key_findings"])
def test_every_report_builds_without_any_audit_data(tmp_path, report_type):
    path = tmp_path / "empty.pdf"

    build_pdf({}, str(path), "Acme Co", report_type)

    reader, text = read(path)
    assert reader.pages
    assert "Acme Co" in text


@pytest.mark.parametrize("report_type", ["performance", "seo", "key_findings"])
def test_every_report_builds_without_ai_text(tmp_path, report_type):
    reader, text = read(build(tmp_path, report_type, data(ai=False)))

    assert reader.pages
    if report_type != "key_findings":
        assert "AI summary not available for this section." in text
    else:
        assert "AI findings missing" in text


def test_reports_with_many_urls_are_limited_to_100(tmp_path):
    urls = tuple(f"https://example.com/page-{i}" for i in range(120))

    _, text = read(build(tmp_path, "seo", data("performance,seo", urls=urls)))

    assert "https://example.com/page-99" in text
    assert "https://example.com/page-100" not in text


def test_a_client_domain_comes_from_the_sitemap_start_url(tmp_path):
    payload = data()
    payload["audit"]["sitemap"]["start"] = "https://shop.acme.co.za/"

    _, text = read(build(tmp_path, "key_findings", payload))

    assert "shop.acme.co.za" in text


# ---- build_reports

def test_build_reports_writes_the_three_free_reports(tmp_path):
    reports = build_reports(data(), str(tmp_path), "Acme Co")

    assert list(reports) == ["performance", "seo", "key_findings"]
    for report_type, path in reports.items():
        assert re.fullmatch(r".*/(Performance_PDF|SEO_PDF|Key_Findings)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.pdf", path)
        assert PdfReader(path).pages


def test_build_reports_adds_accessibility_when_asked(tmp_path):
    reports = build_reports(data("performance,seo,accessibility"), str(tmp_path), "Acme Co", include_accessibility=True)

    assert list(reports) == ["performance", "seo", "key_findings", "accessibility"]
    assert "Accessibility_PDF_" in reports["accessibility"]


def test_build_reports_passes_the_free_audit_flag_to_every_report(tmp_path):
    reports = build_reports(data(), str(tmp_path), "Acme Co", is_free_audit=True)

    assert "Premium Brand audit required" in read(reports["performance"])[1]
    assert "audit up to 100 urls" in read(reports["key_findings"])[1]


def test_build_reports_fails_when_the_output_directory_is_missing(tmp_path):
    with pytest.raises(OSError):
        build_reports(data(), str(tmp_path / "missing"), "Acme Co")


# ---- command line

def write_inputs(tmp_path, categories="performance,seo"):
    payload = data(categories)
    audit_file = tmp_path / "audit.json"
    ai_file = tmp_path / "ai.json"
    audit_file.write_text(json.dumps(payload["audit"]))
    ai_file.write_text(json.dumps(payload["ai"]))
    return audit_file, ai_file


def run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["pdf_report_generator", *args])
    generator.main()


def test_main_builds_a_single_report(tmp_path, monkeypatch):
    audit_file, ai_file = write_inputs(tmp_path)
    out = tmp_path / "out.pdf"

    run_main(monkeypatch, "--audit-input", str(audit_file), "--ai-input", str(ai_file), "--output", str(out),
             "--client-name", "Acme Co", "--report-type", "seo")

    assert "Technical & SEO Report" in read(out)[1]


def test_main_builds_every_report_for_a_free_audit(tmp_path, monkeypatch):
    audit_file, ai_file = write_inputs(tmp_path, "performance,seo")
    out_dir = tmp_path / "reports"
    out_dir.mkdir()

    run_main(monkeypatch, "--audit-input", str(audit_file), "--ai-input", str(ai_file), "--output", str(out_dir / "x.pdf"),
             "--client-name", "Acme Co", "--report-type", "all")

    names = sorted(p.name.split("_PDF")[0].split("_2")[0] for p in out_dir.glob("*.pdf"))
    assert names == ["Key_Findings", "Performance", "SEO"]
    assert "Premium Brand audit required" in read(next(out_dir.glob("Performance_PDF_*.pdf")))[1]


def test_main_builds_the_accessibility_report_when_it_was_audited(tmp_path, monkeypatch):
    audit_file, ai_file = write_inputs(tmp_path, "performance,seo,accessibility")
    out_dir = tmp_path / "reports"
    out_dir.mkdir()

    run_main(monkeypatch, "--audit-input", str(audit_file), "--ai-input", str(ai_file), "--output", str(out_dir / "x.pdf"),
             "--client-name", "Acme Co", "--report-type", "all")

    assert len(list(out_dir.glob("Accessibility_PDF_*.pdf"))) == 1
    assert "Premium Brand audit required" not in read(next(out_dir.glob("Performance_PDF_*.pdf")))[1]


def test_main_requires_its_arguments(monkeypatch):
    with pytest.raises(SystemExit):
        run_main(monkeypatch, "--client-name", "Acme")
