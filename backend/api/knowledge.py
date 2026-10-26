from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.config.settings import settings
from backend.database.connection import get_db
from backend.models.knowledge import KnowledgeDocument
from backend.rag.ingestion import delete_document, ingest_directory, ingest_pdf

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    rows = db.query(KnowledgeDocument).order_by(KnowledgeDocument.filename).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "policy_type": r.policy_type,
            "chunk_count": r.chunk_count,
            "status": r.status,
            "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
        }
        for r in rows
    ]


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    dest = Path(settings.uploads_dir) / Path(file.filename).name
    dest.write_bytes(await file.read())
    kb_dest = Path(settings.knowledge_base_dir) / dest.name
    kb_dest.write_bytes(dest.read_bytes())
    result = ingest_pdf(kb_dest, db=db)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.post("/reindex")
def reindex(db: Session = Depends(get_db)):
    results = ingest_directory(settings.knowledge_base_dir, db=db)
    return {"ok": True, "results": results}


@router.delete("/documents/{filename}")
def remove_document(filename: str, db: Session = Depends(get_db)):
    path = Path(settings.knowledge_base_dir) / Path(filename).name
    result = delete_document(Path(filename).name, db=db)
    if path.exists():
        path.unlink()
    return result
