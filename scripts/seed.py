from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database.seed import seed_database
from backend.database.connection import init_db, SessionLocal
from backend.rag.generate_policies import generate_knowledge_pdfs
from backend.rag.ingestion import ingest_directory

if __name__ == "__main__":
    init_db()
    generate_knowledge_pdfs()
    db = SessionLocal()
    try:
        ingest_directory(ROOT / "knowledge_base", db=db)
    finally:
        db.close()
    print(seed_database())
