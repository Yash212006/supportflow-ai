from backend.config.settings import settings
from backend.rag.vectorstore import get_vectorstore


def retrieve_policy(query: str, top_k: int | None = None) -> dict:
    k = top_k or settings.rag_top_k
    try:
        store = get_vectorstore()
        docs = store.similarity_search(query, k=k)
    except Exception as exc:  # vector db unavailable
        return {
            "ok": False,
            "error": "Policy search is temporarily unavailable.",
            "detail": str(exc),
            "answer_context": "",
            "sources": [],
        }

    if not docs:
        return {
            "ok": True,
            "answer_context": "",
            "sources": [],
            "message": "No matching policy chunks were found.",
        }

    blocks = []
    sources = []
    seen = set()
    for doc in docs:
        name = doc.metadata.get("document_name") or doc.metadata.get("source") or "unknown"
        page = doc.metadata.get("page_number")
        policy_type = doc.metadata.get("policy_type")
        blocks.append(f"[{name} p.{page}]\n{doc.page_content.strip()}")
        key = (name, page)
        if key not in seen:
            seen.add(key)
            sources.append({"document": name, "page": page, "policy_type": policy_type})

    return {
        "ok": True,
        "answer_context": "\n\n---\n\n".join(blocks),
        "sources": sources,
    }
