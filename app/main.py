from pathlib import Path
import os, json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings
from .ingestion import SUPPORTED, build_chunks
from .embeddings import GeminiEmbeddingService
from .store import VectorStore
from .models import QueryRequest, IndexRequest, Chunk
from .rag import RAGEngine

app = FastAPI(title="RAG Laboratory", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
Path(settings.upload_path).mkdir(parents=True, exist_ok=True)

# Session-local API key for the single-user local MVP. It is never written to disk.
SESSION_KEY = None

# Document metadata (chunks, page counts, indexed flags) is persisted to disk so the
# Document/Chunk Explorer still reflects reality after a restart, even though the
# Chroma vector index already survives restarts on its own.
DOCUMENTS_META_PATH = Path(settings.upload_path).parent / "documents.json"

def _load_documents() -> dict:
    if not DOCUMENTS_META_PATH.exists():
        return {}
    try:
        raw = json.loads(DOCUMENTS_META_PATH.read_text(encoding="utf-8"))
        return {name: {**item, "chunks": [Chunk(**c) for c in item["chunks"]]} for name, item in raw.items()}
    except Exception:
        return {}

def _save_documents():
    serializable = {name: {**item, "chunks": [c.model_dump() for c in item["chunks"]]} for name, item in DOCUMENTS.items()}
    DOCUMENTS_META_PATH.write_text(json.dumps(serializable), encoding="utf-8")

DOCUMENTS = _load_documents()

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/api/status")
def status():
    store = VectorStore()
    docs = []
    for name, item in DOCUMENTS.items():
        docs.append({"name": name, "chunks": len(item["chunks"]), "size": item["size"], "pages": item["pages"], "indexed": item["indexed"]})
    return {"api_key_configured": bool(SESSION_KEY or os.getenv("GEMINI_API_KEY")), "documents": docs, "total_chunks": store.count(), "config": {"chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap, "threshold": settings.similarity_threshold, "retrieval_k": settings.retrieval_k, "final_context_k": settings.final_context_k, "embedding_model": settings.embedding_model, "generation_model": settings.generation_model, "embedding_dimension": settings.embedding_dimension}}

@app.post("/api/config")
def config(req: IndexRequest):
    global SESSION_KEY
    if not req.api_key or len(req.api_key.strip()) < 10:
        raise HTTPException(400, "Enter a valid Gemini API key.")
    SESSION_KEY = req.api_key.strip()
    return {"ok": True}

@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in SUPPORTED:
            raise HTTPException(400, f"Unsupported file type: {ext}. Use PDF, DOCX, TXT or Markdown.")
        data = await f.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(400, f"{f.filename} exceeds {settings.max_upload_mb} MB.")
        safe = Path(f.filename).name
        path = Path(settings.upload_path) / safe
        path.write_bytes(data)
        chunks = build_chunks(path)
        DOCUMENTS[safe] = {"path": str(path), "chunks": chunks, "size": len(data), "pages": max([c.page or 1 for c in chunks], default=1), "indexed": False}
    _save_documents()
    return {"ok": True, "count": len(files)}

@app.get("/api/chunks")
def chunks():
    return {"documents": [{"name": n, "size": x["size"], "pages": x["pages"], "indexed": x["indexed"], "chunks": [c.model_dump() for c in x["chunks"]]} for n, x in DOCUMENTS.items()]}

@app.post("/api/index")
def index(req: IndexRequest):
    key = req.api_key or SESSION_KEY or os.getenv("GEMINI_API_KEY")
    if not key: raise HTTPException(400, "Gemini API key is required.")
    if not DOCUMENTS: raise HTTPException(400, "Upload at least one document first.")
    try:
        embedder = GeminiEmbeddingService(key)
        store = VectorStore()
        total = sum(len(x["chunks"]) for x in DOCUMENTS.values())
        newly_indexed = 0
        skipped_documents = 0
        for name, item in DOCUMENTS.items():
            if item["indexed"]:
                skipped_documents += 1
                continue
            chunks = item["chunks"]
            if chunks:
                vectors = embedder.embed([c.text for c in chunks])
                store.upsert(chunks, vectors)
            item["indexed"] = True
            newly_indexed += len(chunks)
        _save_documents()
        return {"ok": True, "indexed_chunks": newly_indexed, "total_chunks": total, "skipped_documents": skipped_documents}
    except Exception as e:
        _save_documents()
        raise HTTPException(500, f"Indexing failed: {e}")

@app.post("/api/query")
def query(req: QueryRequest):
    key = req.api_key or SESSION_KEY or os.getenv("GEMINI_API_KEY")
    if not key: raise HTTPException(400, "Gemini API key is required.")
    if not req.question.strip(): raise HTTPException(400, "Question cannot be empty.")
    try:
        return RAGEngine(key).answer(req.question.strip())
    except Exception as e:
        raise HTTPException(500, str(e))
