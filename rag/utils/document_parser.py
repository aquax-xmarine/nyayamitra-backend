import pdfplumber
import docx
import io
import re
import pytesseract
from pdf2image import convert_from_bytes

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def detect_language(text: str) -> str:
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))
    total_alpha = len(re.findall(r'[^\W\d_]', text, re.UNICODE))
    if total_alpha == 0:
        return 'english'
    lang = 'nepali' if (devanagari / total_alpha) > 0.2 else 'english'
    print(f"[Language Detection] Devanagari ratio: {devanagari}/{total_alpha} → {lang}")
    return lang

def parse_document(filename: str, content: bytes) -> dict:
    print(f"[Document Parsing] Starting parsing for file: {filename}")
    
    if filename.lower().endswith(".pdf"):
        text, language, method = parse_pdf(content)  #  unpack 3 values
    elif filename.lower().endswith(".docx"):
        text = parse_docx(content)
        method = "docx parser"
        language = detect_language(text)
    elif filename.lower().endswith(".txt"):
        text = parse_txt(content)
        method = "txt parser"
        language = detect_language(text)
    else:
        text = ""
        method = "unsupported format"
        language = "unknown"
    
    print(f"[Document Parsing] Method used: {method}")
    print(f"[Document Parsing] Detected language: {language}")
    
    return {"text": text, "language": language, "method": method}

def parse_pdf(content: bytes) -> tuple[str, str, str]:
    print("[PDF Parsing] Attempting pdfplumber extraction...")
    text = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    # Print raw extracted text for manual inspection
    print("=" * 60)
    print("[DEBUG] Raw pdfplumber text (first 500 chars):")
    print(text[:500])
    print("=" * 60)

    # Print garbled metrics too so you can verify the decision
    if text.strip():
        noise_chars = len(re.findall(r'[{}\$\*\\\^\~\|\<\>]', text))
        total_chars = len(text.strip())
        word_count = len(re.findall(r'\b\w+\b', text))
        common_english = len(re.findall(r'\b(the|is|of|and|in|to|a|for|that|this)\b', text, re.IGNORECASE))
        print(f"[DEBUG] noise_ratio     : {noise_chars}/{total_chars} = {noise_chars/total_chars:.4f} (threshold > 0.02)")
        print(f"[DEBUG] english_ratio   : {common_english}/{word_count} = {common_english/word_count if word_count else 0:.4f} (threshold < 0.01)")
        print(f"[DEBUG] is_garbled()    : {is_garbled(text)}")
        print("=" * 60)

    # Don't trust language detection on raw pdfplumber output —
    # legacy Nepali fonts (Preeti, Kantipur) look like ASCII garbage
    if not text.strip() or is_garbled(text):
        print("[PDF Parsing] Text empty or garbled → Using OCR")
        text = _ocr_pdf(content)
        method = "OCR via Tesseract"
    else:
        method = "pdfplumber extraction"

    # Detect language AFTER we have clean text
    language = detect_language(text)
    return text, language, method

def parse_docx(content: bytes) -> str:
    print("[DOCX Parsing] Using docx parser")
    text = ""
    doc = docx.Document(io.BytesIO(content))
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def parse_txt(content: bytes) -> str:
    print("[TXT Parsing] Using text parser")
    try:
        return content.decode("utf-8")  # handles Devanagari
    except UnicodeDecodeError:
        return content.decode("latin-1")

def _ocr_pdf(content: bytes) -> str:
    print("[OCR] Converting PDF pages to images and running Tesseract...")
    images = convert_from_bytes(
        content,
        dpi=300,
        poppler_path=r"C:\poppler\poppler-25.12.0\Library\bin"
    )
    return "\n".join(pytesseract.image_to_string(img, lang="nep+eng") for img in images)

def is_garbled(text: str) -> bool:
    if not text.strip():
        return True

    # Preeti/Kantipur encoded PDFs produce high noise chars like { } * $ \ ~
    noise_chars = len(re.findall(r'[{}\$\*\\\^\~\|\<\>]', text))
    total_chars = len(text.strip())
    noise_ratio = noise_chars / total_chars

    

    garbled = noise_ratio > 0.02 
    if garbled:
        print(f"[PDF Parsing] Garbled text detected → noise={noise_ratio:.3f}")

    return garbled