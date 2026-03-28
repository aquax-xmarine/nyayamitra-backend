

import uuid
import os
import requests
import torch
import chromadb
import hashlib
import re

from fastapi import FastAPI, UploadFile, File, Form, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from dotenv import load_dotenv
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from utils.document_parser import parse_document
from utils.document_chunking import structure_aware_chunk

load_dotenv()

app = FastAPI()

# -----------------------------
# Groq API Setup
# -----------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# -----------------------------
# ChromaDB Setup
# -----------------------------
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(name="legal_documents")

# -----------------------------
# Embedding Model
# -----------------------------
model_name = "BAAI/bge-m3"
model = SentenceTransformer(model_name)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)


def detect_query_type(question: str):
    summary_keywords_en = ["summarize", "summary", "overview", "brief"]
    summary_keywords_ne = ["सारांश", "संक्षेप", "अवलोकन", "संक्षिप्त"]
    if any(word in question.lower() for word in summary_keywords_en):
        return "summary"
    if any(word in question for word in summary_keywords_ne):
        return "summary"
    return "qa"


def summarize_document(chunks):
    combined_text = "\n\n".join(chunks[:20])
    prompt = f"""
You are a legal assistant.

Provide a concise summary of the following legal document.
- If the document is in Nepali (नेपाली), respond in Nepali. Do not respond in Hindi.
- If the document is in English, respond in English.

Document:
{combined_text}
"""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 700
    }
    response = requests.post(GROQ_URL, headers=headers, json=payload)
    data = response.json()
    return data["choices"][0]["message"]["content"]


def clean_chunk(chunk: str) -> str:
    chunk = re.sub(r'^\d+\s+[A-Z\s]+—[A-Z\s,]+\d{4}\.?\s*', '', chunk.strip())
    chunk = re.sub(r'^[A-Za-z]+\s+v\.\s*[A-Za-z]+\.\s*', '', chunk.strip())
    chunk = re.sub(r'^[\d\s]+[A-Z]\.\s*[A-Z]\.\s*[A-Z]\..*?\n', '', chunk.strip())
    chunk = re.sub(r'^\d+\.\s+[A-Z][a-z]+.*?\n', '', chunk.strip())
    return chunk.strip()


def classify_chunk(chunk: str) -> str:
    holding_phrases_en = [
        "we think", "we hold", "the court held",
        "judgment affirmed", "judgment reversed",
        "we conclude", "it is ordered"
    ]
    holding_phrases_ne = [
        "अदालतले निर्णय गर्यो",
        "फैसला गरिएको छ",
        "निर्णय भयो",
        "आदेश दिइएको छ",
        "अदालतको निर्णय",
        "यस अदालतको आदेश",
        "मिति देखि आदेश",
    ]
    argument_phrases_en = [
        "for appellants", "for respondent",
        "counsel argues", "appellant contends",
        "it is conceded", "it is argued",
        "for appellant", "counsel for",
        "forappellants",
        "forrespondent",
        "forappellant",
        "counsel well argues",
    ]
    argument_phrases_ne = [
        "वादीको तर्फबाट",
        "प्रतिवादीको तर्फबाट",
        "अधिवक्ताले तर्क",
        "निवेदकको तर्फबाट",
        "विपक्षीको तर्फबाट",
    ]

    chunk_lower = chunk.lower()

    if re.search(r'[a-z]+,\s*for\s*appellant', chunk_lower):
        return "argument"
    if re.search(r'[a-z]+,\s*for\s*respondent', chunk_lower):
        return "argument"

    if any(p in chunk_lower for p in holding_phrases_en):
        return "holding"
    if any(p in chunk for p in holding_phrases_ne):
        return "holding"

    if any(p in chunk_lower for p in argument_phrases_en):
        return "argument"
    if any(p in chunk for p in argument_phrases_ne):
        return "argument"

    return "general"


def is_valid_chunk(chunk: str) -> bool:
    if len(chunk.split()) < 10:
        return False
    valid_chars = sum(
        1 for c in chunk
        if c.isalpha() or '\u0966' <= c <= '\u096F'
    )
    ratio = valid_chars / max(len(chunk), 1)
    if ratio < 0.4:
        return False
    return True

# Add a simple in-memory store (or use Redis/DB for production)
user_document_store = {}  # { session_id: [file_hashes] }  

@app.post("/api/ask")
async def ask(
    files: List[UploadFile] = File(...),
    question: str = Form(...)
    
):
    documents = []
    all_chunks = []
    processed_hashes = []

    # -----------------------------
    # Process uploaded documents
    # -----------------------------
    for file in files:

        contents = await file.read()
        file_hash = hashlib.sha256(contents).hexdigest()
        processed_hashes.append(file_hash)

        # -----------------------------
        # Check if document already exists
        # -----------------------------
        existing = collection.get(
            where={"file_hash": file_hash},
            limit=1
        )

        if existing["ids"]:
            existing_docs = collection.get(where={"file_hash": file_hash})
            all_chunks.extend(existing_docs["documents"])
            print(f"{file.filename} already processed. Skipping parsing and embedding.")
            continue

        # -----------------------------
        # Parse document
        # -----------------------------
        result = parse_document(filename=file.filename, content=contents)
        text = result["text"]
        language = result["language"]

        # -----------------------------
        # Chunk document
        # -----------------------------
        chunks = structure_aware_chunk(text, max_chunk_size=1000)
        chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
        chunks = [clean_chunk(chunk) for chunk in chunks]
        chunks = [chunk for chunk in chunks if is_valid_chunk(chunk)]

        all_chunks.extend(chunks)

        # -----------------------------
        # Create embeddings
        # -----------------------------
        embeddings = model.encode(
            chunks,
            batch_size=16,
            show_progress_bar=False,
            device=device
        )

        # -----------------------------
        # Store chunks in ChromaDB
        # -----------------------------
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_type = classify_chunk(chunk)
            print(f"CHUNK TYPE: {chunk_type} | PREVIEW: {chunk[:80]}")

            collection.add(
                ids=[str(uuid.uuid4())],
                documents=[chunk],
                metadatas=[{
                    "filename": file.filename,
                    "file_hash": file_hash,
                    "chunk_type": chunk_type,
                    "position": i
                }],
                embeddings=[embedding.tolist()]
            )

        documents.append({
            "filename": file.filename,
            "num_chunks": len(chunks)
        })

    query_type = detect_query_type(question)

    if query_type == "summary":
        summary = summarize_document(all_chunks)
        return {"mode": "summary", "summary": summary}

    # -----------------------------
    # Embed user question
    # -----------------------------
    BGE_PREFIX = "Represent this sentence for searching relevant passages: "

    query_embedding = model.encode(
        [BGE_PREFIX + question],
        device=device
    )[0]

    # -----------------------------
    # Retrieve top chunks
    # -----------------------------
    holding_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=7,
        where={
            "$and": [
                {"chunk_type": {"$eq": "holding"}},
                {"file_hash": {"$in": processed_hashes}}
            ]
        }
    )

    general_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=7,
        where={
            "$and": [
                {"chunk_type": {"$eq": "general"}},
                {"file_hash": {"$in": processed_hashes}}
            ]
        }
    )

    holding_chunks = holding_results["documents"][0] if holding_results["documents"][0] else []
    general_chunks = general_results["documents"][0] if general_results["documents"][0] else []

    all_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=5,
        where={"file_hash": {"$in": processed_hashes}}
    )

    all_chunks_fallback = all_results["documents"][0] if all_results["documents"][0] else []

    # Combine all — holdings first, then general, then fallback
    retrieved_chunks = list(dict.fromkeys(holding_chunks + general_chunks + all_chunks_fallback))

    # -----------------------------
    # Fetch neighboring chunks
    # -----------------------------
    retrieved_metadatas = (
        holding_results["metadatas"][0] +
        general_results["metadatas"][0]
    )

    neighbor_chunks = []
    for meta in retrieved_metadatas:
        next_pos = meta.get("position", -1) + 1
        neighbors = collection.get(
            where={
                "$and": [
                    {"file_hash": {"$eq": meta["file_hash"]}},
                    {"position": {"$eq": next_pos}}
                ]
            }
        )
        if neighbors["documents"]:
            neighbor_chunks.extend(neighbors["documents"])

    retrieved_chunks = list(dict.fromkeys(retrieved_chunks + neighbor_chunks))

    print("\n=== Retrieved Chunks ===")
    for i, chunk in enumerate(retrieved_chunks):
        print(f"\nChunk {i+1}")
        print(chunk)
        print("-" * 50)

    # -----------------------------
    # Build RAG prompt
    # -----------------------------
    context = "\n\n".join(retrieved_chunks)

    prompt = f"""
You are a legal assistant analyzing a legal document.

- Detect the language of the question and respond in that same language.
- If the question is in Nepali (नेपाली), respond in Nepali. Do not respond in Hindi.
- If the question is in English, respond in English.
- Answer the question concisely and directly based on the context.
- If it is a simple factual question, give a short direct answer with one supporting sentence.
- If it is a complex legal question, provide the reasoning, relevant parties, and key facts.
- If the answer is not in the context, say "Not found in document."
- Do not restate the question in your answer.
- When analyzing court opinions, prioritize the court's final
  holding and reasoning over the arguments made by individual parties.
- Read the full context carefully before answering. The correct answer
  may contradict an earlier statement in the same passage.
- If a passage raises a question and then answers it, use the answer
  not the question as your response.
- You are ONLY allowed to use information explicitly stated in the
  context below. Do NOT apply outside legal knowledge, general legal
  principles, or inferences not directly supported by the text.
- If the document states a fact clearly, report that fact. Do not
  contradict it with legal reasoning from outside the document.
- If the answer is not clearly stated in the context, say "Not found in document." Do NOT guess or invent an answer under any circumstance.
- Never use outside knowledge even if you are confident about it.

Context:
{context}

Question:
{question}
"""

    # -----------------------------
    # Call Groq API
    # -----------------------------
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1024
    }

    response = requests.post(
        GROQ_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:
        return {"error": response.text}

    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    return {
        "question": question,
        "retrieved_chunks": retrieved_chunks,
        "answer": answer
    }


# -----------------------------
# Inspect ChromaDB collection
# -----------------------------
@app.get("/api/inspect")
async def inspect_collection():
    results = collection.get(include=["documents", "embeddings", "metadatas"])

    return {
        "total_chunks": len(results['ids']),
        "entries": [
            {
                "id": id,
                "filename": meta['filename'],
                "text": doc,
                "embedding_length": len(embedding),
                "embedding_preview": list(embedding[:10])
            }
            for id, doc, meta, embedding in zip(
                results['ids'],
                results['documents'],
                results['metadatas'],
                results['embeddings']
            )
        ]
    }

