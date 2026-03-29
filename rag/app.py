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
from sklearn.metrics.pairwise import cosine_similarity
from rank_bm25 import BM25Okapi

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
    if any(word in question.lower() for word in summary_keywords_en):
        return "summary"
    if any(word in question for word in summary_keywords_ne):
        return "summary"
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
    response = requests.post(GROQ_URL, headers=headers, json=payload)
    data = response.json()

    if "choices" not in data:
        print("Groq error:", data)
        raise ValueError(f"Groq API error: {data.get('error', data)}")

    return data["choices"][0]["message"]["content"]


def clean_chunk(chunk: str) -> str:
    chunk = re.sub(r'^\d+\s+[A-Z\s]+—[A-Z\s,]+\d{4}\.?\s*', '', chunk.strip())
    chunk = re.sub(r'^[A-Za-z]+\s+v\.\s*[A-Za-z]+\.\s*', '', chunk.strip())
    chunk = re.sub(
        r'^[\d\s]+[A-Z]\.\s*[A-Z]\.\s*[A-Z]\..*?\n', '', chunk.strip())
    chunk = re.sub(r'^\d+\.\s+[A-Z][a-z]+.*?\n', '', chunk.strip())
    return chunk.strip()


def classify_chunk(chunk: str) -> str:
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

    # -----------------------------
    # Process uploaded documents
    # -----------------------------
    if files:
        for file in files:
            contents = await file.read()
            file_hash = hashlib.sha256(contents).hexdigest()

            if file_hash not in user_document_store[session_id]:
                user_document_store[session_id].append(file_hash)

            if file_hash not in processed_hashes:
                processed_hashes.append(file_hash)

            # -----------------------------
            # Check if document already exists in ChromaDB
            # -----------------------------
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
                        "position": i,
                        "document_id": session_id
                    }],
                    embeddings=[embedding.tolist()]
                )

            documents.append({
                "filename": file.filename,
                "num_chunks": len(chunks)
            })

    # -----------------------------
    # If no files uploaded (follow-up question with document_id only),
    # load chunks from ChromaDB using session's known hashes
    # -----------------------------
    if not processed_hashes and document_id:
        print(f"🔄 Reloading hashes from ChromaDB for document_id: {document_id}")
        try:
            existing_docs = collection.get(
                where={"document_id": {"$eq": document_id}},
                include=["metadatas"]
            )
            reloaded_hashes = list(set(
                meta["file_hash"] for meta in existing_docs["metadatas"]
                if "file_hash" in meta
            ))
            processed_hashes.extend(reloaded_hashes)
            user_document_store[session_id] = processed_hashes
            print(f"✅ Reloaded {len(reloaded_hashes)} hashes: {reloaded_hashes}")
        except Exception as e:
            print(f"❌ Failed to reload hashes: {e}")

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

    # -----------------------------
    # Handle summary request
    # -----------------------------
    query_type = detect_query_type(question)

    if query_type == "summary":
        if not all_chunks:
            return {"error": "No document content found to summarize."}
        summary = summarize_document(all_chunks)
        return {"mode": "summary", "summary": summary, "document_id": session_id}

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

    holding_embeddings = holding_results["embeddings"][0] if holding_results["embeddings"] else []
    general_embeddings = general_results["embeddings"][0] if general_results["embeddings"] else []
    argument_embeddings = argument_results["embeddings"][0] if argument_results["embeddings"] else []

    combined = list(zip(
        holding_chunks + argument_chunks + general_chunks,
        list(holding_embeddings) + list(argument_embeddings) + list(general_embeddings)
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

    # -----------------------------
    # Fetch neighboring chunks
    # -----------------------------
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

    # -----------------------------
    # Build RAG prompt
    # -----------------------------
    # -----------------------------
    # Build labeled context
    # -----------------------------
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
- [GENERAL]: Background facts or question framing. NOT answers.

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
-If the court ignores or does not rely on a contractual provision, treat it as not forming the basis of the decision.
- If the court mentions a fact but does not rely on it, do not use it as the conclusion.
- If the question is yes/no: Start the answer with "Yes." or "No."
- The explanation must be based only on the court’s reasoning.

If the question asks about a specific argument, agreement, or issue:
- Check whether the court relied on it.
- If the court did NOT rely on it and instead decided on another ground, answer accordingly.

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
