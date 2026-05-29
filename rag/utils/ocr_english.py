import pdfplumber
import pytesseract
from PIL import Image

# Tell pytesseract where tesseract is installed
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def reocr_scanned_pdf(pdf_path):
    full_text = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"Processing page {i+1}...")
            
            # Step 1 — ignore bad OCR text layer
            # Step 2 — get the image layer
            img = page.to_image(resolution=300).original
            
            # Step 3 — run fresh OCR on image
            text = pytesseract.image_to_string(img)
            
            full_text.append(f"--- PAGE {i+1} ---\n{text}")
    
    return "\n\n".join(full_text)


# Test it
result = reocr_scanned_pdf("0009-01_E1.pdf")
print(result)