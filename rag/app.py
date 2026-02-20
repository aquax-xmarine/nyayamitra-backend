## vector embedding code - currently not used, but can be re-integrated later for more advanced RAG capabilities

# from fastapi import FastAPI, UploadFile, File
# from typing import List
# from utils.document_parser import parse_document
# from utils.document_chunking import structure_aware_chunk
# from sentence_transformers import SentenceTransformer
# import torch

# app = FastAPI()

# # Load the multilingual embedding model once at startup
# model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
# model = SentenceTransformer(model_name)

# # Move model to GPU if available
# device = 'cuda' if torch.cuda.is_available() else 'cpu'
# model = model.to(device)

# @app.post("/parse")

# async def parse_files(
#     files: List[UploadFile] = File(...)
# ):
#     documents = []

#     for file in files:
#         contents = await file.read()

#         # 1. Parse the document to extract text
#         text = parse_document(
#             filename=file.filename,
#             content=contents
#         )

#         # 2. Chunk the parsed text
#         chunks = structure_aware_chunk(text, max_chunk_size=500)


#         # 3. Convert chunks to embeddings (batching for speed)
#         embeddings = model.encode(
#             chunks,
#             batch_size=16,          # adjust based on GPU memory
#             show_progress_bar=False,
#             device=device
#         )

#         # 4. Store document info along with chunk embeddings
#         documents.append({
#             "filename": file.filename,
#             "text_length": len(text),
#             "num_chunks": len(chunks),
#             "chunks": [
#                 {
#                     "text": chunk,
#                     "embedding": embedding.tolist()  # convert numpy array to list for JSON serialization
#                 }
#                 for chunk, embedding in zip(chunks, embeddings)
#             ]
#         })

#     return {"documents": documents}





from fastapi import FastAPI, UploadFile, File, Form
from typing import List
import requests
from utils.document_parser import parse_document
import os
from dotenv import load_dotenv

load_dotenv() 
app = FastAPI()

# Groq API setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

print("GROQ_API_KEY:", GROQ_API_KEY)

@app.post("/api/ask")
async def ask(
    files: List[UploadFile] = File(...),
    question: str = Form(...)
):
    try:
        # Read and parse all uploaded files
        combined_text = ""
        for file in files:
            content = await file.read()
            text = parse_document(file.filename, content)
            combined_text += f"\n\n--- {file.filename} ---\n{text}"

        # Limit tokens
        combined_text = combined_text[:8000]

        # Build prompt
        prompt = f"""
You are a legal assistant. Answer the question based only on the documents below.

DOCUMENTS:
{combined_text}

QUESTION:
{question}

Answer concisely, only using information from the documents.
"""

        # Call Groq
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1024
        }

        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            return {"error": f"Groq error: {response.text}"}

        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        return {"answer": answer}

    except Exception as e:
        return {"error": str(e)}