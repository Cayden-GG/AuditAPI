from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate

from app.audit_service.reports.sections.upsell import UpsellBackgroundPage


def test_upsell_page_renders_pdf(tmp_path: Path):
    output = tmp_path / "upsell_page.pdf"
    doc = SimpleDocTemplate(str(output), pagesize=A4)
    doc.build([UpsellBackgroundPage("Upgrade to the premium audit to access data for the rest of the URLs.")])

    assert output.exists()
    assert output.stat().st_size > 0
