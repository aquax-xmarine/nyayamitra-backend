# eval/precision_at_k.py
import json
import requests
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("BAAI/bge-m3")

# 1. Define your test questions + the chunk they came from

with open("test_cases.json", "r", encoding="utf-8") as f:
    test_cases = json.load(f)


# 2. Check if retrieved chunk is relevant using cosine sim
def is_relevant(retrieved_chunk: str, relevant_chunk: str, threshold: float = 0.75) -> bool:
    embeddings = model.encode([retrieved_chunk, relevant_chunk])
    score = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return score >= threshold


# 3. Call your RAG API
def get_retrieved_chunks(question: str, document_id: str, pdf_path: str) -> list:
    with open(pdf_path, "rb") as f:
        files = {"files": (pdf_path, f, "application/pdf")}
        data = {"question": question, "document_id": document_id}
        response = requests.post(
            "http://localhost:8000/api/ask",
            files=files,
            data=data
        )
    return response.json().get("retrieved_chunks", [])


# 4. Calculate Precision@k
def precision_at_k(retrieved_chunks: list, relevant_chunk: str, k: int) -> float:
    top_k = retrieved_chunks[:k]
    relevant_count = sum(
        1 for chunk in top_k
        if is_relevant(chunk, relevant_chunk)
    )
    return relevant_count / k


# 5. Run evaluation
def run_evaluation(pdf_path: str, k: int = 5):
    document_id = "eval_session"
    results = []

    print(f"\nRunning Precision@{k} evaluation...\n")
    print("-" * 60)

    for i, test in enumerate(test_cases):
        retrieved = get_retrieved_chunks(
            test["question"],
            document_id,
            pdf_path
        )

        score = precision_at_k(retrieved, test["relevant_chunk"], k)

        results.append({
            "question": test["question"],
            f"precision@{k}": score,
            "retrieved_count": len(retrieved)
        })

        print(f"Q{i+1}: {test['question'][:60]}...")
        print(f"     Precision@{k}: {score:.2f} ({int(score*k)}/{k} relevant)")
        print()

    avg = sum(r[f"precision@{k}"] for r in results) / len(results)
    print("-" * 60)
    print(f"Average Precision@{k}: {avg:.2f}")

    with open("precision_results.json", "w") as f:
        json.dump({"average": avg, "results": results}, f, indent=2)

    return avg

if __name__ == "__main__":
    run_evaluation("0040-01_E2.pdf", k=5)