import chromadb
from .config import settings
from .models import Chunk

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection(
            name="rag_lab_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self):
        try:
            self.client.delete_collection("rag_lab_chunks")
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(name="rag_lab_chunks", metadata={"hnsw:space": "cosine"})

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]):
        self.collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[c.metadata | {"document": c.document, "chunk_id": c.id, "page": c.page or 0, "start_char": c.start_char, "end_char": c.end_char, "chunk_size": c.chunk_size, "overlap": c.overlap, "section": c.section or ""} for c in chunks],
        )

    def count(self):
        return self.collection.count()

    def query(self, embedding: list[float], k: int):
        return self.collection.query(query_embeddings=[embedding], n_results=min(k, max(1, self.count())), include=["documents", "metadatas", "distances"])
