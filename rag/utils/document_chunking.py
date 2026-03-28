import re


def is_heading_english(line: str) -> bool:
    if re.match(r'^\d+(\.\d+)*\s+', line):
        return True
    if (line.isupper() 
        and len(line.split()) < 10
        and not line.strip().endswith(',')
        and not re.search(r'\bet\s+al\b|\bv\.\b|\bNo\.\b|\bRespondent\b|\bAppellant\b', line, re.IGNORECASE)
    ):
        return True
    return False


def is_heading_nepali(line: str) -> bool:
    # Devanagari numbered headings (१., २.१, etc.)
    if re.match(r'^[१२३४५६७८९०]+([.।][१२३४५६७८९०]+)*\s+', line):
        return True
    # Nepali legal section keywords
    if re.match(r'^(धारा|दफा|अनुच्छेद|परिच्छेद|भाग|खण्ड)\s+', line):
        return True
    # Short Devanagari line without । at end
    if re.search(r'[\u0900-\u097F]', line):
        if len(line.split()) < 10 and not line.strip().endswith('।'):
            return True
    return False


def simple_sent_tokenize_english(text: str) -> list:
    """Original — unchanged"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def simple_sent_tokenize_nepali(text: str) -> list:
    """Nepali uses । and ॥ as sentence endings"""
    sentences = re.split(r'(?<=[।॥])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def is_valid_chunk_nepali(chunk: str) -> bool:
    if len(chunk.split()) < 10:
        return False
    valid_chars = sum(
        1 for c in chunk
        if c.isalpha() or '\u0966' <= c <= '\u096F'
    )
    if valid_chars / max(len(chunk), 1) < 0.4:
        return False
    # Filter OCR noise — dashes and dots from table lines
    noise_chars = sum(1 for c in chunk if c in '-._')
    if noise_chars / max(len(chunk), 1) > 0.2:
        return False
    # Filter short uppercase tokens (table headers/footers)
    words = chunk.split()
    short_upper = sum(1 for w in words if w.isupper() and len(w) <= 4)
    if len(words) > 5 and short_upper / len(words) > 0.5:
        return False
    return True


def structure_aware_chunk(parsed_text: str, language: str = "english", max_chunk_size: int = 500) -> list:
    if language == "nepali":
        return _chunk_nepali(parsed_text, max_chunk_size=600)
    else:
        return _chunk_english(parsed_text, max_chunk_size)


def _chunk_english(parsed_text: str, max_chunk_size: int = 500) -> list:
    """Original English chunker — untouched"""
    chunks = []
    current_chunk = ""

    lines = parsed_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_heading_english(line):
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            current_chunk += line + "\n"
        else:
            current_chunk += line + " "
            if len(current_chunk) > max_chunk_size:
                sentences = simple_sent_tokenize_english(current_chunk)
                temp_chunk = ""
                for sent in sentences:
                    if len(temp_chunk) + len(sent) <= max_chunk_size:
                        temp_chunk += sent + " "
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                            temp_chunk = ""
                        while len(sent) > max_chunk_size:
                            chunks.append(sent[:max_chunk_size].strip())
                            sent = sent[max_chunk_size:]
                        temp_chunk = sent + " "
                current_chunk = temp_chunk

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def _chunk_nepali(parsed_text: str, max_chunk_size: int = 600) -> list:
    """Nepali chunker with noise filtering"""
    chunks = []
    current_chunk = ""

    lines = parsed_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_heading_nepali(line):
            if current_chunk:
                if is_valid_chunk_nepali(current_chunk):
                    chunks.append(current_chunk.strip())
                current_chunk = ""
            current_chunk += line + "\n"
        else:
            current_chunk += line + " "
            if len(current_chunk) > max_chunk_size:
                sentences = simple_sent_tokenize_nepali(current_chunk)
                temp_chunk = ""
                for sent in sentences:
                    if len(temp_chunk) + len(sent) <= max_chunk_size:
                        temp_chunk += sent + " "
                    else:
                        if temp_chunk:
                            if is_valid_chunk_nepali(temp_chunk):
                                chunks.append(temp_chunk.strip())
                            temp_chunk = ""
                        while len(sent) > max_chunk_size:
                            chunks.append(sent[:max_chunk_size].strip())
                            sent = sent[max_chunk_size:]
                        temp_chunk = sent + " "
                current_chunk = temp_chunk

    if current_chunk:
        if is_valid_chunk_nepali(current_chunk):
            chunks.append(current_chunk.strip())

    return chunks