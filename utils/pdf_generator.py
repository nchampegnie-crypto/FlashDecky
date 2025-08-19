from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def generate_pdf(terms):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    for term, definition in terms:
        # Term page
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width/2, height/2, term)
        c.showPage()

        # Definition page
        c.setFont("Helvetica", 16)
        c.drawCentredString(width/2, height/2, definition)
        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer
