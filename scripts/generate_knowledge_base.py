from backend.rag.generate_policies import generate_knowledge_pdfs

if __name__ == "__main__":
    files = generate_knowledge_pdfs()
    print("Wrote", [p.name for p in files])
