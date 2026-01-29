import pdfplumber
import docx
import io

def parse_document(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        return parse_pdf(content)

    elif filename.lower().endswith(".docx"):
        return parse_docx(content)

    else:
        return ""

def parse_pdf(content: bytes) -> str:
    text = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def parse_docx(content: bytes) -> str:
    text = ""
    doc = docx.Document(io.BytesIO(content))
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text
