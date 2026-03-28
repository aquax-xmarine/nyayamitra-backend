from document_parser import parse_document

with open("nep_cod.pdf", "rb") as f:
    result = parse_document("nep_cod.pdf", f.read())
    print("\n[Result]")
    print("Language:", result["language"])
    print("Method used:", result["method"])
    print("Text preview:", result["text"][:1000])