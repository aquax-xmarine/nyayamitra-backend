import chromadb
from chromadb.config import Settings

client = chromadb.Client(Settings(persist_directory="./chroma_db", anonymized_telemetry=False))

# Safely get or create
collection = client.get_or_create_collection("legal_documents")

# Fetch all documents
results = collection.get()
print("Number of chunks stored:", len(results['documents']))
for idx, doc in enumerate(results['documents']):
    print(f"Chunk {idx+1}: {doc[:80]}...")  # print first 80 chars