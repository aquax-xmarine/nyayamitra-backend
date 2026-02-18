import re

def is_heading(line: str) -> bool:
    """
    Detect if a line is a heading:
    - Numbered headings (1., 1.1, etc.)
    - All caps and short lines
    """
    if re.match(r'^\d+(\.\d+)*\s+', line):
        return True
    if line.isupper() and len(line.split()) < 10:
        return True
    return False

def simple_sent_tokenize(text: str) -> list:
    """
    Split text into sentences using punctuation.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def structure_aware_chunk(parsed_text: str, max_chunk_size: int = 500) -> list:
    """
    Split parsed text into chunks, keeping headings intact
    and splitting at sentence boundaries if the chunk grows too large.
    """
    chunks = []
    current_chunk = ""

    lines = parsed_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_heading(line):
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            current_chunk += line + "\n"
        else:
            current_chunk += line + " "
            if len(current_chunk) > max_chunk_size:
                sentences = simple_sent_tokenize(current_chunk)
                temp_chunk = ""
                for sent in sentences:
                    if len(temp_chunk) + len(sent) <= max_chunk_size:
                        temp_chunk += sent + " "
                    else:
                        chunks.append(temp_chunk.strip())
                        temp_chunk = sent + " "
                current_chunk = temp_chunk

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
