"""Knowledge base: extraction → chunking → embeddings → pgvector storage → retrieval with citations.

Versioning: documents share a `doc_key`; uploading a new version marks earlier versions
`is_current=False` / SUPERSEDED, and retrieval only searches current READY documents, so an
outdated policy is never cited as current.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agents.llm import LOCAL_PREFIX, embed_local, embed_provider, embed_with_fallback, embedding_model_name, local_model_name
from app.core.errors import ValidationFailed
from app.models import KnowledgeChunk, KnowledgeDocument
from app.models.enums import DocumentStatus
from app.services.audit import audit

log = logging.getLogger("supportflow.knowledge")

ALLOWED = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
CATEGORIES = ("refund_policy", "shipping", "product", "procedures", "faq", "business_policy", "payments")


def extract_text(filename: str, data: bytes) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise ValidationFailed(f"Unsupported file type {ext or '(none)'}; allowed: PDF, TXT, DOCX, Markdown")
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise ValidationFailed("File is not a valid PDF")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        if not data.startswith(b"PK"):
            raise ValidationFailed("File is not a valid DOCX")
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("Text file must be UTF-8") from exc


def chunk_text(text: str, *, size: int = 900, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking with character overlap; long paragraphs are split on words."""
    text = re.sub(r"\r\n?", "\n", text)
    pieces: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n", text)):
        if not para:
            continue
        if len(para) <= size:
            pieces.append(para)
            continue
        cur = ""
        for w in para.split():
            if len(cur) + len(w) + 1 > size:
                pieces.append(cur.strip())
                cur = ""
            cur += " " + w
        if cur.strip():
            pieces.append(cur.strip())
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > size:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + "\n\n" + piece).strip()
        else:
            buf = (buf + "\n\n" + piece).strip()
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) > 20]


def ingest_document(
    db: Session,
    *,
    business_id: uuid.UUID,
    title: str,
    category: str,
    filename: str,
    data: bytes,
    uploaded_by: uuid.UUID | None,
    doc_key: str | None = None,
    content_type: str | None = None,
) -> KnowledgeDocument:
    if category not in CATEGORIES:
        raise ValidationFailed(f"Unknown category; use one of {', '.join(CATEGORIES)}")
    text = extract_text(filename, data)
    if len(text.strip()) < 20:
        raise ValidationFailed("No extractable text found in document")
    key = doc_key or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:120]
    prev = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.business_id == business_id, KnowledgeDocument.doc_key == key).order_by(KnowledgeDocument.version.desc())).first()
    version = (prev.version + 1) if prev else 1
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    doc = KnowledgeDocument(
        business_id=business_id,
        doc_key=key,
        version=version,
        is_current=False,
        title=title,
        category=category,
        filename=filename[:250],
        content_type=content_type or ALLOWED[ext],
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        status=DocumentStatus.PROCESSING,
        uploaded_by_user_id=uploaded_by,
    )
    db.add(doc)
    db.flush()
    try:
        chunks = chunk_text(text)
        vectors, used_model = embed_with_fallback(chunks)
        for i, (c, v) in enumerate(zip(chunks, vectors)):
            db.add(KnowledgeChunk(business_id=business_id, document_id=doc.id, chunk_index=i, content=c, embedding=v))
        doc.chunk_count = len(chunks)
        doc.embedding_model = used_model
        doc.status = DocumentStatus.READY
        doc.is_current = True
        db.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.business_id == business_id, KnowledgeDocument.doc_key == key, KnowledgeDocument.id != doc.id)
            .values(is_current=False, status=DocumentStatus.SUPERSEDED)
        )
    except Exception as exc:
        doc.status = DocumentStatus.FAILED
        doc.error = f"{type(exc).__name__}: {exc}"[:500]
    audit(db, business_id=business_id, actor=f"user:{uploaded_by}" if uploaded_by else "system", action="knowledge.uploaded", entity_type="knowledge_document", entity_id=doc.id, summary=f"'{title}' v{version} ({doc.chunk_count} chunks, {doc.status.value})")
    db.flush()
    return doc


@dataclass
class Citation:
    document_id: str
    title: str
    version: int
    category: str
    chunk_index: int
    content: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def search(db: Session, business_id: uuid.UUID, query: str, *, k: int = 4, category: str | None = None, min_score: float = 0.05) -> list[Citation]:
    # Search the embedding space the documents are actually in. Prefer the configured provider; fall back to
    # the local lexical space (documents seeded or uploaded without a working provider) if the provider fails.
    current_model = embedding_model_name()
    spaces = set(db.scalars(select(KnowledgeDocument.embedding_model).where(KnowledgeDocument.business_id == business_id, KnowledgeDocument.is_current.is_(True), KnowledgeDocument.status == DocumentStatus.READY)).all())
    qv: list[float] | None = None
    if current_model in spaces and not current_model.startswith(LOCAL_PREFIX):
        try:
            qv = embed_provider([query])[0]
        except Exception as exc:
            log.warning("query embedding failed (%s); falling back to local lexical search", type(exc).__name__)
    if qv is None:
        current_model = local_model_name()
        if current_model not in spaces:
            return []
        qv = embed_local([query])[0]
    distance = KnowledgeChunk.embedding.cosine_distance(qv)
    stmt = (
        select(KnowledgeChunk, KnowledgeDocument, distance.label("d"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(
            KnowledgeChunk.business_id == business_id,
            KnowledgeDocument.is_current.is_(True),
            KnowledgeDocument.status == DocumentStatus.READY,
            KnowledgeDocument.embedding_model == current_model,  # never compare vectors across embedding spaces
        )
        .order_by(distance)
        .limit(k)
    )
    if category:
        stmt = stmt.where(KnowledgeDocument.category == category)
    out: list[Citation] = []
    for chunk, doc, d in db.execute(stmt):
        score = 1.0 - float(d)
        if score >= min_score:
            out.append(Citation(str(doc.id), doc.title, doc.version, doc.category, chunk.chunk_index, chunk.content, round(score, 3)))
    return out


def reembed_all(db: Session, business_id: uuid.UUID) -> int:
    """Re-embed current documents with the configured embedding model (after switching provider)."""
    model = embedding_model_name()
    docs = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.business_id == business_id, KnowledgeDocument.is_current.is_(True), KnowledgeDocument.status == DocumentStatus.READY)).all()
    n = 0
    for doc in docs:
        if doc.embedding_model == model:
            continue
        chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id).order_by(KnowledgeChunk.chunk_index)).all()
        vecs = embed_provider([c.content for c in chunks])  # explicit manager action: provider errors are reported, not hidden
        for c, v in zip(chunks, vecs):
            c.embedding = v
        doc.embedding_model = model
        n += 1
    db.flush()
    return n
