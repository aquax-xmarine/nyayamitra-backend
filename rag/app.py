from typing import List as PyList
from langchain_groq import ChatGroq
from datasets import Dataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy
)
from ragas import evaluate
from pydantic import BaseModel
import uuid
import os
from importlib_metadata import files
import requests
import torch
import chromadb
import hashlib
import re
import json
import io

from fastapi import FastAPI, UploadFile, File, Form, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from dotenv import load_dotenv
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from rag.utils.document_parser import parse_document
from rag.utils.document_chunking import structure_aware_chunk
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi

load_dotenv()

app = FastAPI()

# Groq API Setup

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ChromaDB Setup
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(name="legal_documents")


# Embedding Model
model_name = "BAAI/bge-m3"
model = SentenceTransformer(model_name)

device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)

# OPEN_API_KEY = os.getenv("OPENAI_API_KEY")


def rerank_chunks(query_embedding, chunks, chunk_embeddings, holding_chunks, argument_chunks, question, bm25_scores, chunk_type_map):

    scores = cosine_similarity(
        [query_embedding],
        chunk_embeddings
    )[0]

    weighted = []

    for i, (chunk, score) in enumerate(zip(chunks, scores)):
        bm25_score = bm25_scores[i]

        # normalize BM25
        bm25_score = bm25_score / (max(bm25_scores) + 1e-6)

        final_score = (0.7 * score) + (0.3 * bm25_score)

        chunk_type = chunk_type_map.get(chunk, "general")

        if chunk_type == "holding":
            final_score += 0.3
        elif chunk_type == "argument":
            final_score -= 0.2

        keywords = [w for w in question.lower().split() if len(w) > 3]
        if any(word in chunk.lower() for word in keywords):
            final_score += 0.1

        weighted.append((chunk, final_score))

    ranked = sorted(weighted, key=lambda x: x[1], reverse=True)

    return [chunk for chunk, score in ranked[:10]]


def detect_query_type(question: str):
    summary_keywords_en = ["summarize", "summary", "overview", "brief"]
    summary_keywords_ne = ["सारांश", "संक्षेप", "अवलोकन", "संक्षिप्त"]

    factual_keywords_en = ["what", "who", "when",
                           "where", "how much", "how many", "which"]
    factual_keywords_ne = ["कुन", "के", "कहाँ", "कसले", "कहिले", "कति"]

    if any(word in question.lower() for word in summary_keywords_en):
        return "summary"
    if any(word in question for word in summary_keywords_ne):
        return "summary"
    if any(word in question.lower() for word in factual_keywords_en):
        return "factual"
    if any(word in question for word in factual_keywords_ne):
        return "factual"
    return "qa"


def summarize_document(chunks):
    if not chunks:
        raise ValueError("No chunks provided for summarization")
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
    # response = requests.post(GROQ_URL, headers=headers, json=payload)
    response = requests.post(GROQ_URL, headers=headers, json=payload)
    data = response.json()

    if "choices" not in data:
        print("Groq error:", data)
        raise ValueError(f"Groq API error: {data.get('error', data)}")

    return data["choices"][0]["message"]["content"]


def clean_chunk(chunk: str) -> str:
    # Preserve argument tag
    prefix = ""
    if chunk.startswith("[ARGUMENT]"):
        prefix = "[ARGUMENT]\n"
        chunk = chunk[len("[ARGUMENT]\n"):]

    chunk = re.sub(r'^\d+\s+[A-Z\s]+—[A-Z\s,]+\d{4}\.?\s*', '', chunk.strip())
    chunk = re.sub(r'^[A-Za-z]+\s+v\.\s*[A-Za-z]+\.\s*', '', chunk.strip())
    chunk = re.sub(
        r'^[\d\s]+[A-Z]\.\s*[A-Z]\.\s*[A-Z]\..*?\n', '', chunk.strip())
    chunk = re.sub(r'^\d+\.\s+[A-Z][a-z]+.*?\n', '', chunk.strip())

    return (prefix + chunk).strip()


def classify_chunk(chunk: str) -> str:
    if chunk.startswith("[ARGUMENT]"):
        return "argument"

    if re.match(r'\[\d+\]', chunk.strip()):
        return "holding"
    chunk_normalized = re.sub(r'\s+', '', chunk.lower())
    chunk_lower = chunk.lower()

    holding_phrases_en = [
        "we think", "we hold", "the court held",
        "judgment affirmed", "judgment reversed",
        "we conclude", "it is ordered",
        "we think the amendatory",
        "it is the duty",
        "it is the rule",
        "it is our view",
        "it is settled",
        "it is the general rule",
        "it is the duty of",
        "the statute begins to run",
        "where checks",
        "where the bank",
        "where the depositor",

    ]

    # Normalized versions for OCR-joined text
    holding_phrases_normalized = [
        "wethink", "wehold", "thecourteld",
        "judgmentaffirmed", "judgmentreversed",
        "weconclude", "itisordered",
        "thinktheamendatory",
        "notunconstitutional",
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
        # Counsel identification patterns
        "for appellants", "for respondent", "for appellant",
        "for petitioner", "for plaintiff", "for defendant",
        "counsel for", "counsel argues", "counsel contends",
        "forappellants", "forrespondent", "forappellant",

        # Argument verbs
        "appellant contends", "appellant argues", "appellant submits",
        "respondent contends", "respondent argues", "respondent submits",
        "petitioner contends", "petitioner argues", "petitioner submits",
        "plaintiff contends", "plaintiff argues", "plaintiff submits",
        "defendant contends", "defendant argues", "defendant submits",
        "counsel well argues", "it is argued", "it is contended",
        "it is submitted", "it is conceded", "it is urged",

        # Contract/restriction argument patterns (generic)
        "was part of the contract",
        "entered into the contract",
        "formed part of the contract",
        "is part of the contract",
        "the restriction was",
        "the limitation was",
        "any bonus paid would",
        "any premium paid would",
        "if the legislature can authorize",
        "if the legislature could authorize",

        # Slippery slope argument pattern common in legal briefs
        "they may at ten, or any higher",
        "they could at a much higher",
        "could authorize at any rate",
    ]
    argument_phrases_ne = [
        "वादीको तर्फबाट",
        "प्रतिवादीको तर्फबाट",
        "अधिवक्ताले तर्क",
        "निवेदकको तर्फबाट",
        "विपक्षीको तर्फबाट",
    ]

    chunk_lower = chunk.lower()

    # Check normalized first to catch OCR artifacts
    if any(p in chunk_normalized for p in holding_phrases_normalized):
        return "holding"

    if re.search(r'[a-z]+,\s*for\s*appellant', chunk_lower):
        return "argument"
    if re.search(r'[a-z]+,\s*for\s*respondent', chunk_lower):
        return "argument"
    if re.search(r'[a-z]+,\s*for\s*petitioner', chunk_lower):
        return "argument"
    if re.search(r'[a-z]+,\s*for\s*plaintiff', chunk_lower):
        return "argument"
    if re.search(r'[a-z]+,\s*for\s*defendant', chunk_lower):
        return "argument"
    if "duty of a depositor" in chunk_lower:
        return "holding"

    if "account stated" in chunk_lower:
        return "holding"

    if "statute of limitations begins to run" in chunk_lower:
        return "holding"

    # Then phrase checks below — order matters: holdings first
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
    # Always keep pre-tagged chunks
    if chunk.startswith("[ARGUMENT]"):
        return True

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


def generate_session_title(question: str) -> str:
    prompt = f"""Generate a short 4-6 word title for a chat that starts with this message: "{question}". Reply with ONLY the title, no punctuation, no quotes."""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 20
    }

    try:
        response = requests.post(
            GROQ_URL, headers=headers, json=payload, timeout=10)
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Title generation failed: {e}")
        return question[:50]  # fallback to first 50 chars


# Build a page lookup — find which page a chunk belongs to
def find_page_for_chunk(chunk: str, pages: list) -> int:
    for page in pages:
        if chunk[:50] in page["text"]:  # match by first 50 chars
            return page["page_number"]
    return 1  # fallback


# Add a simple in-memory store (or use Redis/DB for production)
user_document_store = {}  # { session_id: [file_hashes] }


@app.post("/api/ask")
async def ask(
    files: List[UploadFile] = File(None),
    document_id: str = Form(None),
    question: str = Form(...)

):
    if not files and not document_id:
        return {"error": "No document context provided"}

    # Determine session/document ID
    session_id = document_id or str(uuid.uuid4())

    # Initialize session store if not exists
    if session_id not in user_document_store:
        user_document_store[session_id] = []

    # Use this list for all processed hashes (previous + new)
    processed_hashes = user_document_store[session_id]

    documents = []
    all_chunks = []

    # Process uploaded documents
    if files:
        for file in files:
            contents = await file.read()
            file_hash = hashlib.sha256(contents).hexdigest()

            if file_hash not in user_document_store[session_id]:
                user_document_store[session_id].append(file_hash)

            if file_hash not in processed_hashes:
                processed_hashes.append(file_hash)

            # Check if document already exists in ChromaDB
            existing = collection.get(
                where={"file_hash": file_hash},
                limit=1
            )

            if existing["ids"]:
                existing_docs = collection.get(where={"file_hash": file_hash})
                all_chunks.extend(existing_docs["documents"])
                print(
                    f"{file.filename} already processed. Skipping parsing and embedding.")
                continue

            # Parse document
            result = parse_document(filename=file.filename, content=contents)
            pages = result['pages']
            print("\n" + "=" * 60)
            print("FINAL RESULT")
            print("=" * 60)
            print("Language:", result["language"])
            print("Method:", result["method"])
            print("\nText Preview:\n")
            print(result["text"][:1000])
            print("=" * 60)

            text = result["text"]
            language = result["language"]

            # Chunk document
            chunks = structure_aware_chunk(
                text, language=language, max_chunk_size=1000)
            chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
            chunks = [clean_chunk(chunk) for chunk in chunks]
            chunks = [chunk for chunk in chunks if is_valid_chunk(chunk)]

            all_chunks.extend(chunks)

            # Create embeddings
            embeddings = model.encode(
                chunks,
                batch_size=16,
                show_progress_bar=False,
                device=device
            )

            # Store chunks in ChromaDB
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_type = classify_chunk(chunk)
                page_number = find_page_for_chunk(chunk, pages)
                print(f"CHUNK TYPE: {chunk_type} | PREVIEW: {chunk[:80]}")

                collection.add(
                    ids=[str(uuid.uuid4())],
                    documents=[chunk],
                    metadatas=[{
                        "filename": file.filename,
                        "file_hash": file_hash,
                        "chunk_type": chunk_type,
                        "position": i,
                        "page_number": page_number,
                        "document_id": session_id
                    }],
                    embeddings=[embedding.tolist()]
                )

            documents.append({
                "filename": file.filename,
                "num_chunks": len(chunks)
            })

    # If no files uploaded (follow-up question with document_id only), load chunks from ChromaDB using session's known hashes
    if not processed_hashes and document_id:
        print(
            f" Reloading hashes from ChromaDB for document_id: {document_id}")
        try:
            existing_docs = collection.get(
                where={"document_id": {"$eq": document_id}},
                include=["metadatas"]
            )
            if existing_docs["metadatas"]:
                reloaded_hashes = list(set(
                    meta["file_hash"] for meta in existing_docs["metadatas"]
                    if "file_hash" in meta
                ))
                processed_hashes.extend(reloaded_hashes)
                user_document_store[session_id] = processed_hashes
                print(
                    f" Reloaded {len(reloaded_hashes)} hashes: {reloaded_hashes}")
        except Exception as e:
            print(f" Failed to reload hashes: {e}")

    if not all_chunks and processed_hashes:
        existing_docs = collection.get(
            where={"file_hash": {"$in": processed_hashes}}
        )
        all_chunks.extend(existing_docs["documents"])

    print("\n=== CHUNK CLASSIFICATIONS ===")

    if not processed_hashes:
        return {"error": "No document found for this session. Please re-upload your file."}

    all_stored = collection.get(where={"file_hash": {"$in": processed_hashes}})

    chunk_type_map = {}

    for doc, meta in zip(all_stored["documents"], all_stored["metadatas"]):
        chunk_type_map[doc] = meta["chunk_type"]
    for doc, meta in zip(all_stored["documents"], all_stored["metadatas"]):
        if "par" in doc.lower() or "restriction" in doc.lower() or "contract" in doc.lower():
            print(f"TYPE: {meta['chunk_type']}")
            print(f"TEXT: {doc[:200]}")
            print("-" * 50)

    # Handle summary request
    query_type = detect_query_type(question)

    if query_type == "summary":
        if not all_chunks:
            return {"error": "No document content found to summarize."}
        summary = summarize_document(all_chunks)

        # Generate title from filename
        filename = files[0].filename if files else "Document"
        name_without_ext = os.path.splitext(
            filename)[0]  # remove .pdf/.docx etc
        title = f"Summary of {name_without_ext}"

        return {"mode": "summary", "summary": summary, "document_id": session_id, "suggested_title": title}

    # Embed user question
    BGE_PREFIX = "Represent this sentence for searching relevant passages: "

    query_embedding = model.encode(
        [BGE_PREFIX + question],
        device=device
    )[0]

    # Retrieve top chunks
    holding_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=20,
        where={
            "$and": [
                {"chunk_type": {"$eq": "holding"}},
                {"file_hash": {"$in": processed_hashes}}
            ]
        },
        include=["documents", "embeddings", "metadatas"]
    )

    general_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=15,
        where={
            "$and": [
                {"chunk_type": {"$eq": "general"}},
                {"file_hash": {"$in": processed_hashes}}
            ]
        },
        include=["documents", "embeddings", "metadatas"]
    )

    holding_chunks = holding_results["documents"][0] if holding_results["documents"][0] else [
    ]
    general_chunks = general_results["documents"][0] if general_results["documents"][0] else [
    ]

    all_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=5,
        where={"file_hash": {"$in": processed_hashes}},
        include=["documents", "embeddings", "metadatas"]
    )

    all_chunks_fallback = all_results["documents"][0] if all_results["documents"][0] else [
    ]

    argument_results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=5,
        where={
            "$and": [
                {"chunk_type": {"$eq": "argument"}},
                {"file_hash": {"$in": processed_hashes}}
            ]
        },
        include=["documents", "embeddings", "metadatas"]
    )
    argument_chunks = argument_results["documents"][0] if argument_results["documents"][0] else [
    ]
    argument_embeddings = (
        argument_results["embeddings"][0]
        if argument_results["embeddings"] and len(argument_results["embeddings"][0]) > 0
        else []
    )

    holding_embeddings = holding_results["embeddings"][0] if holding_results["embeddings"] else [
    ]
    general_embeddings = general_results["embeddings"][0] if general_results["embeddings"] else [
    ]
    argument_embeddings = argument_results["embeddings"][0] if argument_results["embeddings"] else [
    ]

    combined = list(zip(
        holding_chunks + argument_chunks + general_chunks,
        list(holding_embeddings) + list(argument_embeddings) +
        list(general_embeddings)
    ))

    combined_chunks = [c for c, _ in combined]
    combined_embeddings = [e for _, e in combined]

    tokenized_chunks = [chunk.lower().split() for chunk in combined_chunks]
    bm25 = BM25Okapi(tokenized_chunks)

    bm25_scores = bm25.get_scores(question.lower().split())

    retrieved_chunks = rerank_chunks(
        query_embedding,
        combined_chunks,
        combined_embeddings,
        holding_chunks,
        argument_chunks,
        question,
        bm25_scores,
        chunk_type_map
    )

    # only use fallback if no holding
    if not holding_chunks:
        retrieved_chunks = list(dict.fromkeys(
            retrieved_chunks + all_chunks_fallback
        ))

    # Fetch neighboring chunks
    retrieved_metadatas = (
        holding_results["metadatas"][0] +
        general_results["metadatas"][0] +
        argument_results["metadatas"][0]
    )

    neighbor_chunks = []
    for meta in retrieved_metadatas:
        base_pos = meta.get("position", -1)

        positions = [base_pos - 1, base_pos, base_pos + 1]

        for pos in positions:
            neighbors = collection.get(
                where={
                    "$and": [
                        {"file_hash": {"$eq": meta["file_hash"]}},
                        {"position": {"$eq": pos}}
                    ]
                }
            )
            if neighbors["documents"]:
                neighbor_chunks.extend(neighbors["documents"])

    retrieved_chunks = list(dict.fromkeys(retrieved_chunks + neighbor_chunks))
    retrieved_chunks = retrieved_chunks[:10]

    print("\n=== Retrieved Chunks ===")
    for i, chunk in enumerate(retrieved_chunks):
        print(f"\nChunk {i+1}")
        print(chunk)
        print("-" * 50)

    # Build RAG prompt and labeled context
    context_parts = []

    for chunk in retrieved_chunks:
        # find its type from metadata
        chunk_type = "GENERAL"

        chunk_type_raw = chunk_type_map.get(chunk, "general")

        if chunk_type_raw == "holding":
            chunk_type = "COURT HOLDING"
        elif chunk_type_raw == "argument":
            chunk_type = "PARTY ARGUMENT"
        else:
            chunk_type = "GENERAL"

        context_parts.append(f"[{chunk_type}]\n{chunk}")
    context = "\n\n".join(context_parts)

    prompt = f"""
You are a legal assistant analyzing a court opinion.

THE CONTEXT IS LABELED:
- [COURT HOLDING]: The court's final decision. Answer primarily from here. You may use [GENERAL] only to support reasoning, but never as the final conclusion.
- [PARTY ARGUMENT]: Lawyer arguments, often rejected. NEVER use as answer.
- [GENERAL]: Background facts. For factual questions about people, health, dates, 
  or events — answer directly from [GENERAL] if no [COURT HOLDING] covers it.

YOUR JOB:
1. Find the [COURT HOLDING] that addresses the question.
2. Answer based on what the court decided and reasoned — including implicit conclusions.
3. The court does not always answer every question directly — read its reasoning and state what it concluded.

RULES:
- If a [COURT HOLDING] contains reasoning that leads to a clear conclusion, state that conclusion directly.
- Do NOT say "not found" if a [COURT HOLDING] clearly implies the answer through its reasoning.
- Do NOT blend [GENERAL] or [PARTY ARGUMENT] language into your answer.
- [GENERAL] chunks with "the only question is whether X..." are question-framing — NOT answers.
- Never use outside knowledge.
- Respond in the same language as the question.
- If question is in Nepali, respond in Nepali. Not Hindi.
- Only say "Not found in document" if NO [COURT HOLDING] addresses the topic at all.
- If the court resolves the case on a different ground, answer based on that ground.
- If the court does not explicitly decide the issue but clearly resolves the case on a different legal ground, you must answer based on that ground.
- If the court ignores or does not rely on a contractual provision, treat it as not forming the basis of the decision.
- If the court mentions a fact but does not rely on it, do not use it as the conclusion.
- If the question is yes/no: Start the answer with "Yes." or "No."
- If the question asks "what", "who", "when", "where", "how much" — do NOT start with Yes/No. Answer directly.
- The explanation must be based only on the court’s reasoning.
- The case name lists parties as "X v. Y" — 
  X is typically the plaintiff/petitioner, 
  Y is typically the defendant/respondent.
  Use this to resolve ambiguity about named parties.

If the question asks about a specific argument, agreement, or issue:
- Check whether the court relied on it.
- If the court did NOT rely on it and instead decided on another ground, answer accordingly.

Context:
{context}

Question:
{question}
"""

    # Call Groq API
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

    title = None
    # Only generate title for first real question (not summarize)
    if query_type != "summary":
        title = generate_session_title(question)

    return {
        "question": question,
        "retrieved_chunks": retrieved_chunks,
        "answer": answer,
        "suggested_title": title
    }


# Inspect ChromaDB collection
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


@app.post("/api/auto-evaluate")
async def auto_evaluate(
    files: List[UploadFile] = File(None),
):
    # Step 1: Read file contents once
    file_contents = []
    for file in files:
        contents = await file.read()
        file_contents.append((file.filename, contents))

    # Step 2: Parse and chunk
    all_chunks = []
    for filename, contents in file_contents:
        result = parse_document(filename=filename, content=contents)
        text = result["text"]
        language = result["language"]
        chunks = structure_aware_chunk(
            text, language=language, max_chunk_size=1000)
        chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
        chunks = [clean_chunk(chunk) for chunk in chunks]
        chunks = [chunk for chunk in chunks if is_valid_chunk(chunk)]
        all_chunks.extend(chunks)

    # Step 3: Generate eval set with source verification
    context = "\n\n".join(all_chunks[:15])
    gen_prompt = f"""
You are a legal document evaluator.

Based on the following document, generate 5 question and answer pairs to evaluate a RAG system.

STRICT RULES:
- Every expected_answer MUST be a direct quote from the document — copy exact words
- Do NOT paraphrase or infer — only use text that appears word for word in the document
- If you cannot find an exact quote for an answer, skip that question
- Include 1 question that is clearly not answerable from the document at all
- Return ONLY a JSON array, no markdown, no backticks, no extra text

Format:
[
  {{
    "question": "...",
    "expected_answer": "exact quote from document",
    "source_text": "the exact sentence you copied this from"
  }},
  ...
]

Document:
{context}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    gen_res = requests.post(GROQ_URL, headers=headers, json={
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": gen_prompt}],
        "temperature": 0.0,
        "max_tokens": 1000
    })

    raw = gen_res.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown backticks if present
    if raw.startswith("```"):
        raw = re.sub(r"```json|```", "", raw).strip()

    try:
        eval_set = json.loads(raw)
    except:
        return {"error": "Failed to parse eval set", "raw": raw}

    # Step 4: Verify source_text actually exists in chunks
    verified_eval_set = []
    skipped = []
    for item in eval_set:
        source = item.get("source_text", "")
        expected = item.get("expected_answer", "")

        # For unanswerable questions skip verification
        if "not found" in expected.lower() or "not answerable" in expected.lower():
            item["verified"] = True
            verified_eval_set.append(item)
            continue

        # Check if source text exists in any chunk
        found = any(source[:60] in chunk for chunk in all_chunks)
        item["verified"] = found

        if found:
            verified_eval_set.append(item)
        else:
            skipped.append({
                "question": item.get("question"),
                "reason": "source_text not found in document chunks — possible hallucination"
            })

    if not verified_eval_set:
        return {
            "error": "All generated questions failed verification — Groq may have hallucinated",
            "skipped": skipped,
            "raw": raw
        }

    # Step 5: Run each verified question through RAG and evaluate
    results = []
    document_id = str(uuid.uuid4())

    for test in verified_eval_set:
        import io

        upload_files = []
        for filename, contents in file_contents:
            upload_files.append(
                UploadFile(
                    filename=filename,
                    file=io.BytesIO(contents)
                )
            )

        rag_response = await ask(
            files=upload_files,
            document_id=document_id,
            question=test["question"]
        )
        rag_answer = rag_response.get("answer", "")

        # Step 6: Strict judge
        judge_prompt = f"""
You are a strict RAG evaluator.

Question: {test["question"]}
Expected Answer (exact quote from document): {test["expected_answer"]}
RAG Answer: {rag_answer}

Does the RAG answer convey the same factual information as the expected answer?
Be strict — if the RAG answer contradicts or misses key facts, mark INCORRECT.
If the question is unanswerable and RAG says "not found", mark CORRECT.

Reply with ONLY: CORRECT or INCORRECT — one sentence reason.
"""
        judge_res = requests.post(GROQ_URL, headers=headers, json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": judge_prompt}],
            "temperature": 0.0,
            "max_tokens": 100
        })
        judgment = judge_res.json()["choices"][0]["message"]["content"].strip()

        results.append({
            "question": test["question"],
            "expected": test["expected_answer"],
            "source_text": test.get("source_text", ""),
            "verified": test["verified"],
            "rag_answer": rag_answer,
            "judgment": judgment
        })

    correct = sum(1 for r in results if r["judgment"].startswith("CORRECT"))
    total = len(results)

    return {
        "score": f"{correct}/{total}",
        "percentage": f"{(correct/total)*100:.0f}%",
        "skipped_due_to_hallucination": skipped,
        "results": results
    }


@app.post("/api/test-parse")
async def test_parse(
    files: List[UploadFile] = File(None),
):
    results = []

    for file in files:
        contents = await file.read()
        result = parse_document(filename=file.filename, content=contents)

        text = result["text"]
        pages = result["pages"]
        language = result["language"]
        method = result["method"]

        # Basic stats
        word_count = len(text.split())
        char_count = len(text)

        # Check each page
        page_stats = []
        for page in pages:
            page_stats.append({
                "page_number": page["page_number"],
                "word_count": len(page["text"].split()),
                "text_preview": page["text"][:200],  # first 200 chars
                "is_empty": len(page["text"].strip()) == 0
            })

        results.append({
            "filename": file.filename,
            "language": language,
            "method": method,
            "total_pages": len(pages),
            "total_words": word_count,
            "total_chars": char_count,
            "empty_pages": sum(1 for p in page_stats if p["is_empty"]),
            "text_preview": text[:500],  # first 500 chars of full text
            "page_stats": page_stats
        })

    return {"results": results}


class ChunkRequest(BaseModel):
    text: str
    language: str = "nepali"
    max_chunk_size: int = 600


@app.post("/test-chunk-pdf")
async def test_chunk_pdf(file: UploadFile = File(...), language: str = "nepali", max_chunk_size: int = 600):
    contents = await file.read()
    result = parse_document(filename=file.filename, content=contents)

    chunks = structure_aware_chunk(
        parsed_text=result["text"],
        language=result["language"],
        max_chunk_size=max_chunk_size
    )
    return {
        "filename": file.filename,
        "language": result["language"],
        "method": result["method"],
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_number": i + 1,
                "text": chunk,
                "word_count": len(chunk.split()),
                "char_count": len(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]
    }


class EvalQuestion(BaseModel):
    question: str


class RagasEvalRequest(BaseModel):
    questions: PyList[str]
    document_id: str = None


@app.post("/api/ragas-evaluate-batch")
async def ragas_evaluate_batch(
    files: List[UploadFile] = File(None),
    questions: str = Form(...),  # JSON string of questions list
    document_id: str = Form(None)
):
    # Parse questions from JSON string
    try:
        questions_list = json.loads(questions)
    except:
        return {"error": "questions must be a valid JSON array e.g. [\"question1\", \"question2\"]"}

    if not questions_list:
        return {"error": "No questions provided"}

    # Collect data for all questions
    all_questions = []
    all_answers = []
    all_contexts = []
    all_ground_truths = []
    individual_results = []

    file_contents = []

    print("FILES RECEIVED:", files)
    print("FILE COUNT:", len(files) if files else 0)

    session_id = document_id or str(uuid.uuid4())

    if files:
        for file in files:
            contents = await file.read()
            file_contents.append((file.filename, contents))

    first_question = True

    for question in questions_list:
        # Only send files on first question — after that reuse session_id
        if first_question and file_contents:
            upload_files = [
                UploadFile(filename=name, file=io.BytesIO(contents))
                for name, contents in file_contents
            ]
            first_question = False
        else:
            upload_files = None  # ChromaDB already has chunks, reuse via session_id

        rag_response = await ask(
            files=upload_files,
            document_id=session_id,
            question=question
        )
        if "error" in rag_response:
            # ← add this
            print(f"RAG error for '{question}': {rag_response['error']}")
            individual_results.append({
                "question": question,
                "error": rag_response["error"]
            })
            continue

        retrieved_chunks = rag_response.get("retrieved_chunks", [])
        answer = rag_response.get("answer", "")

        all_questions.append(question)
        all_answers.append(answer)
        all_contexts.append(retrieved_chunks)
        all_ground_truths.append(question)

        individual_results.append({
            "question": question,
            "answer": answer,
            "retrieved_chunks_count": len(retrieved_chunks)
        })

    if not all_questions:
        return {"error": "All questions failed RAG pipeline"}

    # Build RAGAS dataset with all questions at once
    data = {
        "question": all_questions,
        "answer": all_answers,
        "contexts": all_contexts,
        "ground_truth": all_ground_truths
    }
    dataset = Dataset.from_dict(data)

    # Setup Groq as judge LLM
    groq_llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=0
    )
    wrapped_llm = LangchainLLMWrapper(groq_llm)

    # Run RAGAS evaluation on all questions together
    try:
        result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
            ],
            llm=wrapped_llm
        )

        df = result.to_pandas()

        # Per question scores
        per_question_scores = []
        for i, row in df.iterrows():
            q_result = individual_results[i]
            faithfulness_score = round(float(row.get("faithfulness", 0)), 4)
            relevancy_score = round(float(row.get("answer_relevancy", 0)), 4)
            precision_score = round(float(row.get("context_precision", 0)), 4)
            avg = round(
                (faithfulness_score + relevancy_score + precision_score) / 3, 4)

            per_question_scores.append({
                "question": q_result["question"],
                "answer": q_result["answer"],
                "scores": {
                    "faithfulness": faithfulness_score,
                    "answer_relevancy": relevancy_score,
                    "context_precision": precision_score,
                    "average": avg
                },
                "verdict": "good" if avg > 0.7 else "okay" if avg > 0.5 else "poor"
            })

        # Overall average across all questions
        overall_faithfulness = round(float(df["faithfulness"].mean()), 4)
        overall_relevancy = round(float(df["answer_relevancy"].mean()), 4)
        overall_precision = round(float(df["context_precision"].mean()), 4)
        overall_avg = round(
            (overall_faithfulness + overall_relevancy + overall_precision) / 3, 4)

        return {
            "total_questions": len(all_questions),
            "overall_scores": {
                "faithfulness": overall_faithfulness,
                "answer_relevancy": overall_relevancy,
                "context_precision": overall_precision,
                "average": overall_avg
            },
            "overall_verdict": "good" if overall_avg > 0.7 else "okay" if overall_avg > 0.5 else "poor",
            "per_question_results": per_question_scores
        }

    except Exception as e:

        return {"error": str(e)}
