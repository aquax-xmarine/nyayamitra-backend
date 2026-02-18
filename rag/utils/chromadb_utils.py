from chromadb.config import Settings
from chromadb import Client

# Persisted storage directory
client = Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="./chroma_storage"
))

# Create a collection (like a table)
collection = client.get_or_create_collection("documents")

# Example: store chunks with embeddings
chunks = ["Chunk 1 text", "Chunk 2 text"]
embeddings = [[0.1]*384, [0.2]*384]  # your actual 384-dim embeddings
ids = ["doc1_chunk1", "doc1_chunk2"]

collection.add(
    documents=chunks,
    embeddings=embeddings,
    ids=ids
)
