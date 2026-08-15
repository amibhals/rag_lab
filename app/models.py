from typing import Any, Optional
from pydantic import BaseModel

class Chunk(BaseModel):
    id: str
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    text: str
    start_char: int
    end_char: int
    chunk_size: int
    overlap: int
    metadata: dict[str, Any] = {}

class QueryRequest(BaseModel):
    question: str
    api_key: Optional[str] = None

class ApiKeyRequest(BaseModel):
    api_key: str

class IndexRequest(BaseModel):
    api_key: Optional[str] = None
