import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    generation_model: str = os.getenv("GENERATION_MODEL", "gemini-3.6-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "12"))
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))
    final_context_k: int = int(os.getenv("FINAL_CONTEXT_K", "6"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    chroma_path: str = os.getenv("CHROMA_PATH", "data/index")
    upload_path: str = os.getenv("UPLOAD_PATH", "data/uploads")

settings = Settings()
