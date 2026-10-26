from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma

from backend.config.settings import settings
from backend.rag.embeddings import get_embeddings

COLLECTION = "supportflow_policies"


@lru_cache
def get_vectorstore() -> Chroma:
    Path(settings.chroma_persist_directory).mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=settings.chroma_persist_directory,
        embedding_function=get_embeddings(),
    )


def reset_vectorstore_cache() -> None:
    get_vectorstore.cache_clear()
