import pdfplumber
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

with pdfplumber.open("082-wh-0086_N1.pdf") as pdf:
    page = pdf.pages[0]
    
    # Ignore bad OCR layer
    # Re-OCR the image layer with Nepali language
    img = page.to_image(resolution=300).original
    
    # lang="nep" tells tesseract to use Nepali
    text = pytesseract.image_to_string(img, lang="nep")
    print(text)