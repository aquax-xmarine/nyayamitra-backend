from fastapi import FastAPI, UploadFile, File, Form
from typing import List
from utils.document_parser import parse_document
import requests
import os

app = FastAPI()

# Gemini API Key (store in env variable for security)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://api.openai.com/v1/responses"  # Gemini endpoint


@app.post("/api/ask")
async def ask_question(
    question: str = Form(...),
    files: List[UploadFile] = File(None)
):
    print("=== /api/ask called ===")
    print("Question received:", question)
    print("Number of uploaded files:", len(files) if files else 0)

    # Parse the uploaded files into text
    document_texts = []
    if files:
        for file in files:
            content = await file.read()
            text = parse_document(filename=file.filename, content=content)
            document_texts.append(text)

    #  Combine all document text into one string
    combined_text = "\n\n".join(document_texts)

    #  Prepare prompt for Gemini
    # We give Gemini the question + document context
    prompt = f"""
    You are a legal assistant. Answer the question based only on the following documents.
    
    DOCUMENTS:
    {combined_text}
    
    QUESTION:
    {question}
    
    Please answer concisely, only using the information from the documents.
    """

    print("Prompt prepared for Gemini (first 500 chars):")
    print(prompt[:500], "...\n")

    #  Call Gemini API
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gemini-1.5",
        "input": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    response = requests.post(GEMINI_URL, headers={
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }, json=payload)
    if response.status_code != 200:
        print("Gemini API error:", response.text)
        return {"error": "Failed to get response from Gemini", "details": response.text}

    data = response.json()
    print("Raw Gemini response:", data)

    #  Extract text answer (Gemini returns structured JSON)
    # Adjust based on actual response format
    answer = data.get("output_text") or data.get(
        "output", {}).get("content", [{}])[0].get("text", "")
    print("Extracted answer from Gemini:", answer[:500], "...")

    return {"question": question, "answer": answer}
