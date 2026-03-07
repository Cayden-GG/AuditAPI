from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER

VALVANTA_BLUE = colors.HexColor("#2563EB")
WHITE = colors.white
LIGHT_BG = colors.HexColor("#9D9D9D")

MAX_URLS = 100

def get_styles(): 
    styles = getSampleStyleSheet()
    
    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            spaceAfter=8)
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            spaceAfter=6)
    )
    styles.add(
        ParagraphStyle(
            name="Small", 
            parent=styles["BodyText"], 
            fontSize=9, 
            leading=11,
            textColor=colors.grey,
            spaceAfter=4)
    )
    styles.add(
        ParagraphStyle(
            name="URLCell",
            parent=styles["BodyText"], 
            fontSize=7,
            leading=8)
    )
    styles.add(
        ParagraphStyle(
            name="Body", 
            parent=styles["BodyText"], 
            fontSize=10, 
            leading=13)
    )
    
    return styles


