from fastapi import FastAPI, UploadFile, File
from typing import List
from utils.document_parser import parse_document
from utils.document_chunking import structure_aware_chunk
from sentence_transformers import SentenceTransformer
import torch

app = FastAPI()

# Load the multilingual embedding model once at startup
model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
model = SentenceTransformer(model_name)

# Move model to GPU if available
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = model.to(device)

@app.post("/parse")

async def parse_files(
    files: List[UploadFile] = File(...)
):
    documents = []

    for file in files:
        contents = await file.read()

        # 1. Parse the document to extract text
        text = parse_document(
            filename=file.filename,
            content=contents
        )

        # 2. Chunk the parsed text
        chunks = structure_aware_chunk(text, max_chunk_size=500)


        # 3. Convert chunks to embeddings (batching for speed)
        embeddings = model.encode(
            chunks,
            batch_size=16,          # adjust based on GPU memory
            show_progress_bar=False,
            device=device
        )

        # 4. Store document info along with chunk embeddings
        documents.append({
            "filename": file.filename,
            "text_length": len(text),
            "num_chunks": len(chunks),
            "chunks": [
                {
                    "text": chunk,
                    "embedding": embedding.tolist()  # convert numpy array to list for JSON serialization
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]
        })

    return {"documents": documents}
