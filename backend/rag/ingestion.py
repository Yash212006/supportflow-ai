from __future__ import annotations

import uuid
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from backend.models.knowledge import KnowledgeDocument
from backend.rag.vectorstore import get_vectorstore, reset_vectorstore_cache


POLICY_TYPE_MAP = {
    "refund": "refund",
    "shipping": "shipping",
    "cancellation": "cancellation",
    "replacement": "replacement",
    "customer_support": "customer_support",
    "escalation": "escalation",
    "warranty": "warranty",
}


def infer_policy_type(filename: str) -> str:
    stem = Path(filename).stem.lower()
    for key, value in POLICY_TYPE_MAP.items():
        if key in stem:
            return value
    return "general"


def ingest_pdf(path: str | Path, db: Session | None = None) -> dict:
    path = Path(path)
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path.name}"}

    loader = PyPDFLoader(str(path))
    pages = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    chunks = splitter.split_documents(pages)
    policy_type = infer_policy_type(path.name)

    docs = []
    ids = []
    for i, chunk in enumerate(chunks):
        page = chunk.metadata.get("page", 0)
        page_number = int(page) + 1 if page is not None else 1
        chunk_id = f"{path.stem}-{i}-{uuid.uuid4().hex[:8]}"
        chunk.metadata = {
            "document_name": path.name,
            "page_number": page_number,
            "policy_type": policy_type,
            "chunk_id": chunk_id,
            "source": path.name,
        }
        docs.append(chunk)
        ids.append(chunk_id)

    store = get_vectorstore()
    existing = store.get(where={"document_name": path.name})
    if existing and existing.get("ids"):
        store.delete(ids=existing["ids"])
    if docs:
        store.add_documents(docs, ids=ids)

    if db is not None:
        rec = db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == path.name).first()
        if rec is None:
            rec = KnowledgeDocument(filename=path.name, policy_type=policy_type)
            db.add(rec)
        rec.chunk_count = len(docs)
        rec.status = "indexed"
        rec.policy_type = policy_type
        db.commit()

    return {
        "ok": True,
        "filename": path.name,
        "pages": len(pages),
        "chunks": len(docs),
        "policy_type": policy_type,
        "steps": [
            "Document uploaded",
            f"{len(docs)} chunks created",
            "Embeddings generated",
            "Stored in ChromaDB",
        ],
    }


def ingest_directory(directory: str | Path, db: Session | None = None) -> list[dict]:
    directory = Path(directory)
    results = []
    if not directory.exists():
        return [{"ok": False, "error": f"Directory missing: {directory}"}]
    for pdf in sorted(directory.glob("*.pdf")):
        results.append(ingest_pdf(pdf, db=db))
    return results


def delete_document(filename: str, db: Session | None = None) -> dict:
    store = get_vectorstore()
    existing = store.get(where={"document_name": filename})
    deleted = 0
    if existing and existing.get("ids"):
        store.delete(ids=existing["ids"])
        deleted = len(existing["ids"])
    if db is not None:
        rec = db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == filename).first()
        if rec:
            db.delete(rec)
            db.commit()
    reset_vectorstore_cache()
    return {"ok": True, "filename": filename, "chunks_removed": deleted}
