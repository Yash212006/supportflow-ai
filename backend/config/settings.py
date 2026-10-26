from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    database_url: str = f"sqlite:///{(ROOT_DIR / 'data' / 'supportflow.db').as_posix()}"
    chroma_persist_directory: str = str(ROOT_DIR / "chroma_db")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_top_k: int = 4
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    demo_user_email: str = "exec@supportflow.local"
    demo_user_password: str = "demo123"
    knowledge_base_dir: str = str(ROOT_DIR / "knowledge_base")
    uploads_dir: str = str(ROOT_DIR / "uploads")
    data_dir: str = str(ROOT_DIR / "data")
    agent_max_iterations: int = 8
    memory_window: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
