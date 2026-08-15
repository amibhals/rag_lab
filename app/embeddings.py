from google import genai
from google.genai import types
from .config import settings

class GeminiEmbeddingService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            result = self.client.models.embed_content(
                model=settings.embedding_model,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dimension),
            )
            out.append(result.embeddings[0].values)
        return out
