import requests
import json

# Load dataset
with open("eval_dataset.json") as f:
    dataset = json.load(f)

hits = 0

pdf_path = "0009-01_E1.pdf"

for item in dataset:
    question = item["question"]
    expected = item["expected_answer_contains"].lower()

    # Always send PDF
    with open(pdf_path, "rb") as f:
        response = requests.post(
            "http://localhost:8000/api/ask",
            files={"files": f},
            data={"question": question}
        ).json()

    if "error" in response:
        print("API returned an error:", response["error"])
        chunks = []
    else:
        chunks = response.get("retrieved_chunks", [])

    found = any(expected in chunk.lower() for chunk in chunks)

    print("\nQUESTION:", question)
    print("FOUND:", found)

    if found:
        hits += 1

accuracy = hits / len(dataset)
print("\n=== RETRIEVAL ACCURACY ===")
print(f"{accuracy:.2f}")