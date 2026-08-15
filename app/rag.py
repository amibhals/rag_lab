import json
from datetime import datetime, timezone
from google import genai
from google.genai import types
from .config import settings
from .embeddings import GeminiEmbeddingService
from .store import VectorStore

class RAGEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.embedder = GeminiEmbeddingService(api_key)
        self.store = VectorStore()
        self.client = genai.Client(api_key=api_key)

    def answer(self, question: str):
        trace = {"started_at": datetime.now(timezone.utc).isoformat(), "question": question, "config": {
            "generation_model": settings.generation_model, "embedding_model": settings.embedding_model,
            "retrieval_k": settings.retrieval_k, "similarity_threshold": settings.similarity_threshold,
            "final_context_k": settings.final_context_k, "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap,
        }}
        if self.store.count() == 0:
            raise ValueError("No indexed chunks found. Upload and index documents first.")
        q_embedding = self.embedder.embed([question])[0]
        trace["query_embedding"] = {"dimensions": len(q_embedding), "model": settings.embedding_model, "status": "generated"}
        raw = self.store.query(q_embedding, settings.retrieval_k)
        retrieved = []
        rejected = []
        for i, (doc, meta, dist) in enumerate(zip(raw["documents"][0], raw["metadatas"][0], raw["distances"][0]), 1):
            similarity = max(-1.0, min(1.0, 1.0 - float(dist)))
            row = {"rank": i, "chunk_id": meta.get("chunk_id"), "document": meta.get("document"), "page": meta.get("page"), "section": meta.get("section"), "similarity": round(similarity, 4), "text": doc, "distance": float(dist)}
            (retrieved if similarity >= settings.similarity_threshold else rejected).append(row)
        selected = retrieved[:settings.final_context_k]
        enough = len(selected) > 0
        trace["retrieval"] = {"searched": self.store.count(), "returned": len(retrieved) + len(rejected), "retrieved": retrieved, "rejected": rejected}
        trace["decision"] = {"question_answerable": enough, "threshold": settings.similarity_threshold, "reason": "At least one chunk met the similarity threshold." if enough else "No chunk met the similarity threshold."}
        if not enough:
            trace["final_context"] = []
            trace["answer"] = "I couldn't find sufficient evidence in the indexed documents to answer this confidently."
            return trace
        context = "\n\n".join([f"[C{i+1}] {c['document']} p.{c['page']}\n{c['text']}" for i, c in enumerate(selected)])
        prompt = f"""You are a document-grounded RAG assistant. Answer ONLY from the supplied context. If the context is insufficient, say so. Every substantive factual claim must include one or more citations like [C1]. Do not invent citations.\n\nQUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nReturn concise HTML suitable for rendering in a web UI. Use headings, paragraphs, bullets or tables when useful. Keep citations exactly in [C#] form."""
        trace["final_context"] = selected
        trace["prompt"] = prompt
        response = self.client.models.generate_content(model=settings.generation_model, contents=prompt, config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="medium")))
        answer = response.text or "No answer was generated."
        citations = sorted(set(int(x) for x in __import__('re').findall(r"\[C(\d+)\]", answer)))
        valid_citations = [x for x in citations if 1 <= x <= len(selected)]
        trace["validation"] = {"has_citation": bool(citations), "valid_citations": valid_citations, "invalid_citations": [x for x in citations if x not in valid_citations], "grounding_status": "PASS" if citations and not any(x not in valid_citations for x in citations) else "REVIEW"}
        trace["answer"] = answer
        trace["sources"] = [{"citation": f"C{i+1}", "chunk_id": c["chunk_id"], "document": c["document"], "page": c["page"]} for i, c in enumerate(selected)]
        trace["completed_at"] = datetime.now(timezone.utc).isoformat()
        return trace
