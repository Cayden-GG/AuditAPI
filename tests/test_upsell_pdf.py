from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate

from app.audit_service.reports.sections.upsell import UpsellBackgroundPage


def test_upsell_page_renders_pdf():
    output = Path("./outputs/upsell_page.pdf")
    input = "outputs/upsell_page.pdf"
    doc = SimpleDocTemplate(str(input), pagesize=A4)
    doc.build([UpsellBackgroundPage("Upgrade to the premium audit to access data for the rest of the URLs.")])

    assert output.exists()
    assert output.stat().st_size > 0
