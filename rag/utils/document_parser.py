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
    # elif filename.lower().endswith(".docx"):
    #     text = parse_docx(content)
    #     method = "docx parser"
    #     language = detect_language(text)
    # elif filename.lower().endswith(".txt"):
    #     text = parse_txt(content)
    #     method = "txt parser"
    #     language = detect_language(text)
    else:
        text = ""
        method = "unsupported format"
        language = "unknown"
    
    print(f"[Document Parsing] Method used: {method}")
    print(f"[Document Parsing] Detected language: {language}")
    
    return {"text": text, "language": language, "method": method}

def parse_pdf(content: bytes) -> tuple[str, str, str]:
    print("[PDF Parsing] Extracting with pdfplumber...")
    text = ""

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    print("=" * 60)
    print("[DEBUG] Raw text preview:")
    print(text[:500])
    print("=" * 60)

    # 1. Detect language FIRST
    language = detect_language(text)

    # 2. Apply language-specific rules

    # 🇬🇧 ENGLISH LOGIC
    if language == "english":
        print("[Pipeline] English document detected")

        if is_preeti(text):
            print("[Decision] Preeti font detected → OCR")
            text = _ocr_pdf(content)
            text = fix_ocr_spacing(text)
            method = "OCR (Preeti detected)"

        elif is_old_document(text):
            print("[Decision] Old English document → OCR")
            text = _ocr_pdf(content)
            text = fix_ocr_spacing(text)
            method = "OCR (old English doc)"

        elif is_garbled(text):
            print("[Decision] Garbled English text → OCR")
            text = _ocr_pdf(content)
            text = fix_ocr_spacing(text)
            method = "OCR (garbled English)"

        else:
            print("[Decision] Clean English text → keep pdfplumber")
            method = "pdfplumber extraction"

    # 🇳🇵 NEPALI LOGIC
    elif language == "nepali":
        print("[Pipeline] Nepali document detected")

        if is_preeti(text):
            print("[Decision] Preeti font detected → OCR")
            text = _ocr_pdf(content)
            text = fix_ocr_spacing(text)
            method = "OCR (Preeti detected)"

        elif is_garbled(text):
            print("[Decision] Garbled Nepali text → OCR")
            text = _ocr_pdf(content)
            text = fix_ocr_spacing(text)
            method = "OCR (garbled Nepali)"

        else:
            print("[Decision] Clean Nepali text → keep pdfplumber")
            method = "pdfplumber extraction"

    else:
        print("[Pipeline] Unknown language → fallback OCR")
        text = _ocr_pdf(content)
        text = fix_ocr_spacing(text)
        method = "OCR (unknown language)"

    # 3. Final language detection (after cleaning/OCR)
    language = detect_language(text)

    return text, language, method

# def parse_docx(content: bytes) -> str:
#     print("[DOCX Parsing] Using docx parser")
#     text = ""
#     doc = docx.Document(io.BytesIO(content))
#     for para in doc.paragraphs:
#         text += para.text + "\n"
#     return text

# def parse_txt(content: bytes) -> str:
#     print("[TXT Parsing] Using text parser")
#     try:
#         return content.decode("utf-8")  # handles Devanagari
#     except UnicodeDecodeError:
#         return content.decode("latin-1")

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

    total_chars = len(text)

    # 1. Weird characters
    weird_chars = len(re.findall(r'[^\x00-\x7F\u0900-\u097F\s.,;:!?()\-\n]', text))
    weird_ratio = weird_chars / total_chars

    # 2. Too many single-letter words
    single_letters = len(re.findall(r'\b[a-zA-Z]\b', text))
    words = len(re.findall(r'\b\w+\b', text))
    single_ratio = single_letters / max(words, 1)

    # 3. Glued words (key for your PDFs)
    glued_words = len(re.findall(r'(doesnot|Actof|inthe|ofthe|tothe)', text))

    # Final decision
    garbled = (
        weird_ratio > 0.1 or
        single_ratio > 0.3 or
        glued_words > 5
    )

    if garbled:
        print(f"[Garbled] weird={weird_ratio:.2f}, single={single_ratio:.2f}, glued={glued_words}")

    return garbled


def is_old_document(text: str) -> bool:
    years = re.findall(r'\b(18\d{2}|19[0-4]\d)\b', text[:1000])
    return len(years) > 0

def is_preeti(text: str) -> bool:
    preeti_chars = re.findall(r'[vkJtpm]', text)  # common Preeti letters
    return len(preeti_chars) > 30  # threshold tweak as needed


def fix_ocr_spacing(text: str) -> str:
    # 1. Fix hyphenated line breaks
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    
    # 2 Fix number joins (like "May1st" → "May 1st")
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
    
    # 3. Fix camelCase joins (like "Actof1851" → "Act of 1851")
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    
    # 4. Fix comma joins (like "per cent,above" → "per cent, above")
    text = re.sub(r',([a-zA-Z])', r', \1', text)
    
    # 5. Remove stray OCR symbols
    text = re.sub(r'[¢°z]', '', text)
    
    # 6. Normalize multiple spaces and newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)  # double newlines between paragraphs
    
    return text.strip()
