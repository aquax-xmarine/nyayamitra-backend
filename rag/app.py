from fastapi import FastAPI, UploadFile, File
from typing import List
from utils.document_parser import parse_document

app = FastAPI()

@app.post("/parse")

async def parse_files(
    files: List[UploadFile] = File(...)
):
    documents = []

    for file in files:
        contents = await file.read()

        text = parse_document(
            filename=file.filename,
            content=contents
        )

        documents.append({
            "filename": file.filename,
            "text_length": len(text),
            "preview": text[:500]  # First 100 characters as a preview
        })

    return {"documents": documents}
