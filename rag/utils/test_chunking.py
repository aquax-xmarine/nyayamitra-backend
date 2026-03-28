from document_parser import parse_document
from document_chunking import structure_aware_chunk
import os
import re

def test_chunking(filepath: str):
    filename = os.path.basename(filepath)
    
    with open(filepath, "rb") as f:
        content = f.read()

    print(f"\n{'='*60}")
    print(f"Testing: {filename}")
    print(f"{'='*60}")

    # Parse
    result = parse_document(filename, content)
    language = result["language"]
    text = result["text"]

    print(f"Language : {language}")
    print(f"Method   : {result['method']}")
    print(f"Text len : {len(text)} chars")

    # Chunk
    chunks = structure_aware_chunk(text, language=language)

    print(f"Total chunks: {len(chunks)}")
    print(f"\n--- First 3 chunks preview ---")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n[Chunk {i}] ({len(chunk)} chars)")
        print(chunk[:300])
        print("...")

    print(f"\n--- Chunk size distribution ---")
    sizes = [len(c) for c in chunks]
    print(f"Min  : {min(sizes)}")
    print(f"Max  : {max(sizes)}")
    print(f"Avg  : {sum(sizes)//len(sizes)}")

    # Flag suspicious chunks
    print(f"\n--- Suspicious chunks (< 50 chars or > 700 chars) ---")
    for i, chunk in enumerate(chunks):
        if len(chunk) < 50 or len(chunk) > 700:
            print(f"[Chunk {i}] ({len(chunk)} chars): {chunk[:100]}")


if __name__ == "__main__":
    # Test both your PDFs
    
    test_chunking(r"0040-01.pdf")       # English
    test_chunking(r"082-wh-0086.pdf")   # Nepali
