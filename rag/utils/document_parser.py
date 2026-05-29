# from email.mime import text

# import pdfplumber
# import docx
# import io
# import re
# import pytesseract
# from pdf2image import convert_from_bytes

# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# def detect_language(text: str) -> str:
#     devanagari = len(re.findall(r'[\u0900-\u097F]', text))
#     total_alpha = len(re.findall(r'[^\W\d_]', text, re.UNICODE))
#     if total_alpha == 0:
#         return 'english'
#     lang = 'nepali' if (devanagari / total_alpha) > 0.2 else 'english'
#     print(f"[Language Detection] Devanagari ratio: {devanagari}/{total_alpha} → {lang}")
#     return lang

# def parse_document(filename: str, content: bytes) -> dict:
#     print(f"[Document Parsing] Starting parsing for file: {filename}")
    
#     if filename.lower().endswith(".pdf"):
#         text, language, method, pages = parse_pdf(content)  # unpack 4 values
#     else:
#         text = ""
#         method = "unsupported format"
#         language = "unknown"
#         pages = []  # empty pages for unsupported formats

#     print(f"[Document Parsing] Method used: {method}")
#     print(f"[Document Parsing] Detected language: {language}")

#     return {"text": text, "language": language, "method": method, "pages": pages}  # return pages

# def parse_pdf(content: bytes) -> tuple[str, str, str, list]:
#     print("[PDF Parsing] Extracting with pdfplumber...")
#     text = ""
#     pages = []  # add this

#     with pdfplumber.open(io.BytesIO(content)) as pdf:
#         for page_num, page in enumerate(pdf.pages):
#             page_text = page.extract_text() or ""
#             text += page_text
#             pages.append({
#                 "page_number": page_num + 1,
#                 "text": page_text
#             })

#     print("=" * 60)
#     print("[DEBUG] Raw text preview:")
#     print(text[:500])
#     print("=" * 60)

#     language = detect_language(text)
#     raw_plumber_text = text  # keep this for old doc detection
#     plumber_word_count = len(raw_plumber_text.split())

#     language = detect_language(text)
#     return text, language, "pdfplumber raw (debug)", pages

#     if language == "english":
#         print("[Pipeline] English document detected")

#         if is_preeti(text):
#             print("[Decision] Preeti font detected → OCR")
#             text, pages = _ocr_pdf(content)
#             text = fix_ocr_spacing(text)
#             method = "OCR (Preeti detected)"

#         elif plumber_word_count < 100:
#             print("[Decision] Too little text → OCR")
#             text, pages = _ocr_pdf(content)
#             text = fix_ocr_spacing(text)
#             method = "OCR (insufficient text)"

#         # elif is_old_document(text, raw_plumber_text):
#         #     print("[Decision] Old English document → OCR")
#         #     text, pages = _ocr_pdf(content)
#         #     text = fix_ocr_spacing(text)
#         #     method = "OCR (old English doc)"

#         elif is_garbled(raw_plumber_text):
#             print("[Decision] Garbled text → attempting clean first")
#             cleaned, still_garbled = try_clean_before_ocr(raw_plumber_text)
#             if not still_garbled:
#                 print("[Decision] Cleaning succeeded → using cleaned pdfplumber text")
#                 text = cleaned
#                 pages = [{"page_number": p["page_number"], "text": clean_newlines(clean_glued_words(p["text"]))} for p in pages]
#                 method = "pdfplumber + cleaned"
#             else:
#                 print("[Decision] Cleaning failed → OCR")
#                 text, pages = _ocr_pdf(content)
#                 text = fix_ocr_spacing(text)
#                 method = "OCR (garbled English)"

#         else:
#             print("[Decision] Clean English text → keep pdfplumber")
#             method = "pdfplumber extraction"

#     elif language == "nepali":
#         print("[Pipeline] Nepali document detected")
#         if is_preeti(text):
#             print("[Decision] Preeti font detected → OCR")
#             text, pages = _ocr_pdf(content)
#             text = fix_ocr_spacing(text)
#             method = "OCR (Preeti detected)"
#         elif is_garbled(text):
#             print("[Decision] Garbled Nepali text → OCR")
#             text, pages = _ocr_pdf(content)
#             text = fix_ocr_spacing(text)
#             method = "OCR (garbled Nepali)"
#         else:
#             print("[Decision] Clean Nepali text → keep pdfplumber")
#             method = "pdfplumber extraction"
#     else:
#         print("[Pipeline] Unknown language → fallback OCR")
#         text, pages = _ocr_pdf(content)
#         text = fix_ocr_spacing(text)
#         method = "OCR (unknown language)"

#     language = detect_language(text)

#     return text, language, method, pages  # return pages too

# # def parse_docx(content: bytes) -> str:
# #     print("[DOCX Parsing] Using docx parser")
# #     text = ""
# #     doc = docx.Document(io.BytesIO(content))
# #     for para in doc.paragraphs:
# #         text += para.text + "\n"
# #     return text

# # def parse_txt(content: bytes) -> str:
# #     print("[TXT Parsing] Using text parser")
# #     try:
# #         return content.decode("utf-8")  # handles Devanagari
# #     except UnicodeDecodeError:
# #         return content.decode("latin-1")

# def _ocr_pdf(content: bytes) -> tuple[str, list]:
#     print("[OCR] Converting PDF pages to images and running Tesseract...")
#     images = convert_from_bytes(
#         content,
#         dpi=300,
#         poppler_path=r"C:\poppler\poppler-25.12.0\Library\bin"
#     )
#     pages = []
#     full_text = ""
#     for i, img in enumerate(images):
#         page_text = pytesseract.image_to_string(img, lang="nep+eng")
#         full_text += page_text + "\n"
#         pages.append({
#             "page_number": i + 1,
#             "text": page_text
#         })
#     return full_text, pages

# def is_garbled(text: str) -> bool:
#     if not text.strip():
#         return True

#     words = text.split()
#     total_words = max(len(words), 1)

#     glued = len(re.findall(r'[a-z](of|the|and|in|to|for|at|by)[a-zA-Z]', text))
#     glued_ratio = glued / total_words

#     avg_word_len = sum(len(w) for w in words) / total_words

#     stray = len(re.findall(r'(?<!\w)[b-hj-z](?!\w)', text))
#     stray_ratio = stray / total_words

#     weird = len(re.findall(
#         r'[^\x00-\x7F\u0900-\u097F\s.,;:!?()\-\n\u2018-\u201F\u2013\u2014]',
#         text
#     ))
#     weird_ratio = weird / max(len(text), 1)

#     print(f"[Garbled] glued={glued_ratio:.3f} avg_len={avg_word_len:.1f} stray={stray_ratio:.3f} weird={weird_ratio:.3f}")

#     return (
#         glued_ratio > 0.01 or
#         avg_word_len > 10 or
#         stray_ratio > 0.05 or
#         weird_ratio > 0.05
#     )

# def is_still_garbled_after_clean(text: str) -> bool:
#     words = text.split()
#     total_words = max(len(words), 1)
    
#     avg_word_len = sum(len(w) for w in words) / total_words
#     weird = len(re.findall(
#         r'[^\x00-\x7F\u0900-\u097F\s.,;:!?()\-\n\u2018-\u201F\u2013\u2014]',
#         text
#     ))
#     weird_ratio = weird / max(len(text), 1)
    
#     print(f"[Post-clean check] avg_len={avg_word_len:.1f} weird={weird_ratio:.3f}")
    
#     return avg_word_len > 8 or weird_ratio > 0.05


# def is_old_document(text: str, raw_plumber_text: str) -> bool:
#     years = re.findall(r'\b(18\d{2}|19[0-4]\d)\b', raw_plumber_text[:1000])
#     if not years:
#         return False
#     # Only trigger OCR if pdfplumber got very little text (i.e. it's a scanned image)
#     words = len(raw_plumber_text.split())
#     return words < 100  # tune this threshold

# def is_preeti(text: str) -> bool:
#     # Preeti misread as Unicode produces these specific Latin/symbol characters
#     # in unusual high frequency, combined with absence of real Devanagari
#     preeti_indicators = re.findall(r'[{|}~\x60]', text)
    
#     # Or: look for Devanagari showing up in a doc already detected as English
#     devanagari = re.findall(r'[\u0900-\u097F]', text)
#     total_alpha = len(re.findall(r'[^\W\d_]', text, re.UNICODE))
    
#     deva_ratio = len(devanagari) / max(total_alpha, 1)
    
#     # Only flag Preeti if there's a meaningful Devanagari ratio
#     # (2–5% threshold to avoid OCR artifact false positives)
#     return deva_ratio > 0.05


# def fix_ocr_spacing(text: str) -> str:
#     # 1. Fix hyphenated line breaks
#     text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    
#     # 2 Fix number joins (like "May1st" → "May 1st")
#     text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
#     text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
    
#     # 3. Fix camelCase joins (like "Actof1851" → "Act of 1851")
#     text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    
#     # 4. Fix comma joins (like "per cent,above" → "per cent, above")
#     text = re.sub(r',([a-zA-Z])', r', \1', text)
    
#     # 5. Remove stray OCR symbols
#     text = re.sub(r'[¢°z]', '', text)
    
#     # 6. Normalize multiple spaces and newlines
#     text = re.sub(r'[ \t]+', ' ', text)
#     text = re.sub(r'\n\s*\n', '\n\n', text)  # double newlines between paragraphs
    
#     return text.strip()



# def clean_glued_words(text: str) -> str:
#     # "oftheAct" → "of the Act"
#     text = re.sub(r'([a-z])(of|the|and|in|to|for|at|by|with|from)([A-Z])', r'\1 \2 \3', text)
    
#     # "Actof1858" → "Act of 1858"
#     text = re.sub(r'([a-zA-Z])(of|the|and|in|to|for)([a-z])', r'\1 \2 \3', text)
    
#     # "May1st" → "May 1st"
#     text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
#     text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
    
#     # "per cent,above" → "per cent, above"
#     text = re.sub(r',([a-zA-Z])', r', \1', text)
    
#     return text

# def clean_newlines(text: str) -> str:
#     # Fix hyphenated line breaks — "Fund-\ning" → "Funding"
#     text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    
#     # Join lines that are part of the same sentence
#     # (line doesn't end with period/colon and next line starts lowercase)
#     text = re.sub(r'(?<![.;:!?])\n(?=[a-z])', r' ', text)
    
#     # Preserve paragraph breaks (double newlines)
#     text = re.sub(r'\n{3,}', '\n\n', text)
    
#     # Normalize remaining single newlines between paragraphs
#     text = re.sub(r'[ \t]+', ' ', text)
    
#     return text.strip()


# def try_clean_before_ocr(raw_text: str) -> tuple[str, bool]:
#     cleaned = clean_glued_words(raw_text)
#     cleaned = clean_newlines(cleaned)
    
#     still_garbled = is_still_garbled_after_clean(cleaned)  # different check
#     print(f"[Cleaning] After clean → still garbled: {still_garbled}")
#     return cleaned, still_garbled


"""
pdf_parser.py
--------------
Unified PDF parsing pipeline for legal RAG system.
Handles:
  - Modern English PDFs (true text)
  - Scanned English PDFs (image + bad OCR layer)
  - Scanned Nepali PDFs (image + bad OCR layer)
 
Architecture:
    PDF uploaded
         ↓
    detect_pdf_type()
         ↓                    ↓
    true_text             scanned_with_ocr_layer
         ↓                    ↓
    detect language       detect language
    from text layer       from IMAGE layer
    (devanagari ratio)    (tesseract OSD)
         ↓                    ↓
    pdfplumber            pytesseract
                          lang="eng" or "nep"
 
Usage:
    from pdf_parser import parse_pdf
    result = parse_pdf("document.pdf")
"""
 
import re
import pdfplumber
import pytesseract
from pathlib import Path
 
# ── Windows: set tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
 
 
# ─────────────────────────────────────────────
# STEP 1 — DETECT PDF TYPE
# ─────────────────────────────────────────────
 
def detect_pdf_type(pdf_path: str) -> str:
    """
    Detect whether PDF is true text or scanned.
    
    Returns:
        "true_text"             → pdfplumber works fine
        "scanned_with_ocr"     → has image + bad OCR layer → re-OCR needed
        "scanned_no_ocr"       → pure image, no text layer → OCR needed
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
 
        char_count = len(page.chars)
        images = page.images
 
        # No text at all → pure scanned
        if char_count == 0:
            return "scanned_no_ocr"
 
        # Has images → check coverage
        if images:
            for img in images:
                coverage = (img['width'] * img['height']) / \
                           (page.width * page.height)
                if coverage > 0.7:
                    # Large image + some text = scanned with baked OCR
                    return "scanned_with_ocr"
 
        # No large images, has text → true text PDF
        return "true_text"
 
 
# ─────────────────────────────────────────────
# STEP 2A — DETECT LANGUAGE FROM TEXT LAYER
# (for true text PDFs)
# ─────────────────────────────────────────────
 
def detect_language_from_text(text: str) -> str:
    """
    Detect language from extracted text.
    Uses Devanagari unicode range to identify Nepali.
    
    Returns: "nepali" or "english"
    """
    if not text:
        return "english"
 
    # Count Devanagari characters (unicode range 0900-097F)
    devanagari_count = sum(
        1 for c in text
        if '\u0900' <= c <= '\u097F'
    )
 
    total_chars = len(text.strip())
    if total_chars == 0:
        return "english"
 
    ratio = devanagari_count / total_chars
 
    if ratio > 0.1:  # 10%+ Devanagari → Nepali
        return "nepali"
    return "english"
 
 
# ─────────────────────────────────────────────
# STEP 2B — DETECT LANGUAGE FROM IMAGE LAYER
# (for scanned PDFs — text layer is garbage)
# ─────────────────────────────────────────────
 
def detect_language_from_image(pdf_path: str) -> str:
    """
    Detect language by analyzing the IMAGE layer using Tesseract OSD.
    Used when text layer is garbage (scanned docs).
    
    Returns: "nepali" or "english"
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
 
        # Low resolution is enough for script detection
        img = page.to_image(resolution=150).original
 
        try:
            # Tesseract OSD detects script without full OCR
            osd = pytesseract.image_to_osd(img)
 
            if "Devanagari" in osd:
                return "nepali"
            elif "Latin" in osd:
                return "english"
            else:
                # Fallback: try OCR with Nepali and check Devanagari ratio
                text = pytesseract.image_to_string(img, lang="nep")
                devanagari_count = sum(
                    1 for c in text
                    if '\u0900' <= c <= '\u097F'
                )
                ratio = devanagari_count / max(len(text.strip()), 1)
                return "nepali" if ratio > 0.1 else "english"
 
        except Exception as e:
            print(f"[WARNING] OSD detection failed: {e}, defaulting to english")
            return "english"
 
 
# ─────────────────────────────────────────────
# STEP 3A — EXTRACT TEXT (true text PDF)
# ─────────────────────────────────────────────
 
def extract_true_text(pdf_path: str) -> list[dict]:
    """
    Extract text from true text PDF using pdfplumber.
    Returns list of pages with text and metadata.
    """
    pages = []
 
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # text = clean_text(text)
 
            pages.append({
                "page_number": i + 1,
                "text": text,
                "word_count": len(text.split()),
                "method": "pdfplumber"
            })
 
    return pages
 
 
# ─────────────────────────────────────────────
# STEP 3B — EXTRACT TEXT (scanned PDF)
# ─────────────────────────────────────────────
 
def extract_scanned_text(pdf_path: str, language: str) -> list[dict]:
    """
    Extract text from scanned PDF by re-OCRing the image layer.
    Ignores the bad OCR text layer completely.
    
    Args:
        pdf_path: path to PDF
        language: "english" or "nepali"
    """
    # Map language to tesseract lang code
    lang_map = {
        "english": "eng",
        "nepali": "nep"
    }
    tess_lang = lang_map.get(language, "eng")
 
    pages = []
 
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"  [OCR] Page {i + 1}/{len(pdf.pages)} ({language})...")
 
            # Ignore text layer — rasterize image layer instead
            img = page.to_image(resolution=300).original
 
            # Run fresh OCR on image
            text = pytesseract.image_to_string(img, lang=tess_lang)
            # text = clean_text(text)
 
            pages.append({
                "page_number": i + 1,
                "text": text,
                "word_count": len(text.split()),
                "method": f"pytesseract_{tess_lang}"
            })
 
    return pages
 
 
# ─────────────────────────────────────────────
# CLEANING
# ─────────────────────────────────────────────
 
# def clean_text(text: str) -> str:
#     """Clean common OCR artifacts from extracted text."""
#     if not text:
#         return ""
 
#     # Remove CanLII watermark artifacts
#     text = re.sub(r'\)IILnaC\(|\)IIL', '', text)
#     text = re.sub(r'\n21\nCCS\n6202', '', text)
 
#     # Fix split citation numbers e.g. "SCC \n12" → "SCC 12"
#     text = re.sub(r'(SCC)\s*\n(\d+)', r'\1 \2', text)
 
#     # Remove long separator artifacts (from Nepali docs)
#     text = re.sub(r'[-_\.]{4,}', '', text)
 
#     # Remove garbage number sequences (OCR noise)
#     text = re.sub(r'[0-9]{7,}', '', text)
 
#     # Normalize whitespace
#     text = re.sub(r'\n{3,}', '\n\n', text)
#     text = re.sub(r' {2,}', ' ', text)
 
#     return text.strip()
 
 
# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────
 
def parse_document(filename: str, content: bytes) -> dict:
    """
    Main parsing function. Automatically detects PDF type and language,
    then routes to the correct parser.

    Returns:
    {
        "filename": "doc.pdf",
        "pdf_type": "true_text" | "scanned_with_ocr" | "scanned_no_ocr",
        "language": "english" | "nepali",
        "method": "pdfplumber" | "pytesseract_eng" | "pytesseract_nep",
        "total_pages": 11,
        "total_words": 2298,
        "pages": [
            {
                "page_number": 1,
                "text": "...",
                "word_count": 83,
                "method": "pdfplumber"
            },
            ...
        ]
    }
    """
    import tempfile
    import os

    # Write content bytes to a temp file so existing logic works unchanged
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        print(f"\n[PARSER] Processing: {filename}")

        # ── STEP 1: Detect PDF type
        pdf_type = detect_pdf_type(tmp_path)
        print(f"[PARSER] PDF type: {pdf_type}")

        # ── STEP 2: Detect language
        if pdf_type == "true_text":
            with pdfplumber.open(tmp_path) as pdf:
                sample_text = ""
                for page in pdf.pages[:2]:
                    sample_text += page.extract_text() or ""
            language = detect_language_from_text(sample_text)
        else:
            language = detect_language_from_image(tmp_path)

        print(f"[PARSER] Language: {language}")

        # ── STEP 3: Extract text using correct method
        if pdf_type == "true_text":
            pages = extract_true_text(tmp_path)
            method = "pdfplumber"
        else:
            pages = extract_scanned_text(tmp_path, language)
            lang_code = "nep" if language == "nepali" else "eng"
            method = f"pytesseract_{lang_code}"

        # ── Compile full text across all pages
        full_text = "\n\n".join(p["text"] for p in pages if p["text"])

        result = {
            "filename": filename,
            "text": full_text,
            "language": language,
            "method": method,
            "pages": pages
        }

        # ── PREVIEW ────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("PARSED RESULT PREVIEW")
        print("=" * 60)
        print(f"  Filename  : {filename}")
        print(f"  PDF Type  : {pdf_type}")
        print(f"  Language  : {language}")
        print(f"  Method    : {method}")
        print(f"  Pages     : {len(pages)}")
        print(f"  Total Words: {sum(p.get('word_count', 0) for p in pages)}")
        print("-" * 60)
        for page in pages:
            snippet = page["text"][:200].replace("\n", " ") if page["text"] else "[empty]"
            print(f"  Page {page['page_number']:>3} ({page.get('word_count', 0)} words): {snippet}")
            print()
        print("-" * 60)
        print("FULL TEXT PREVIEW (first 500 chars):")
        print(full_text[:500] if full_text else "[No text extracted]")
        print("=" * 60 + "\n")
        # ───────────────────────────────────────────────────────────

        print(f"[PARSER] Done — {len(pages)} pages, method: {method}")

        return result

    finally:
        os.unlink(tmp_path)  # Always clean up temp file