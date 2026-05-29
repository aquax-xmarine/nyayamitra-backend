# eval/generate_test_cases.py
import os
import sys
import json
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from utils.document_parser import parse_document
from utils.document_chunking import structure_aware_chunk

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# 1. Load chunks from your PDF using YOUR pipeline
def load_chunks(pdf_path: str) -> list:
    with open(pdf_path, "rb") as f:
        contents = f.read()

    filename = os.path.basename(pdf_path)
    result = parse_document(filename=filename, content=contents)
    chunks = structure_aware_chunk(
        result["text"],
        language=result["language"],
        max_chunk_size=1000
    )
    chunks = [c.strip() for c in chunks if c.strip()]
    # filter out very short chunks
    chunks = [c for c in chunks if len(c.split()) > 20]
    return chunks


# 2. Ask Groq to generate a question from a chunk
def generate_question_from_chunk(chunk: str) -> str:
    prompt = f"""You are evaluating a legal RAG system.

Given the following chunk of text from a legal document, generate ONE specific factual question whose answer is clearly contained within this chunk.

Rules:
- The question must be answerable ONLY from this chunk
- Do not generate yes/no questions
- Do not generate vague questions
- Output ONLY the question, nothing else

Chunk:
{chunk}

Question:"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 100
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload)
    data = response.json()

    if "choices" not in data:
        return None

    return data["choices"][0]["message"]["content"].strip()


# 3. Generate test cases
def generate_test_cases(pdf_path: str, num_cases: int = 10):
    print(f"Loading chunks from {pdf_path}...")
    chunks = load_chunks(pdf_path)
    print(f"Total chunks: {len(chunks)}")

    # pick evenly spaced chunks to cover whole document
    step = max(1, len(chunks) // num_cases)
    selected_chunks = chunks[::step][:num_cases]

    test_cases = []

    for i, chunk in enumerate(selected_chunks):
        print(f"Generating question {i+1}/{len(selected_chunks)}...")
        question = generate_question_from_chunk(chunk)

        if not question:
            print(f"  Skipping chunk {i+1} — no question generated")
            continue

        test_cases.append({
            "question": question,
            "relevant_chunk": chunk,  # this IS the ground truth
            "chunk_index": i
        })

        print(f"  Q: {question[:80]}...")

    # save
    with open("test_cases.json", "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(test_cases)} test cases to test_cases.json")
    return test_cases

if __name__ == "__main__":
    generate_test_cases("0040-01_E2.pdf", num_cases=10)