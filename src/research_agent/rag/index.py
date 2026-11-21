"""Batch embed text and retrieve top matches with a CPU FAISS index."""

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Protocol

from research_agent.config import OllamaSettings
from research_agent.llm.client import OllamaClient
from research_agent.rag.documents import Chunk


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def local_embedder(settings: OllamaSettings) -> Embedder:
    return OllamaClient(replace(
        settings,
        url=os.getenv("RESEARCH_EMBED_URL", settings.url),
        model=os.getenv("RESEARCH_EMBED_MODEL", "embeddinggemma"),
    ))


@dataclass(frozen=True)
class Match:
    chunk: Chunk
    score: float


class KnowledgeBase:
    def __init__(self, chunks: Sequence[Chunk], embedder: Embedder):
        try:
            import faiss
            import numpy as np
        except ImportError as error:
            raise ValueError("Install the RAG extra: pip install -e '.[rag]'") from error
        if not chunks:
            raise ValueError("No indexable document chunks were found")
        self.chunks = tuple(chunks)
        self.embedder = embedder
        self.faiss = faiss
        self.np = np
        self.index = None
        for start in range(0, len(self.chunks), 16):
            texts = [f"title: {PurePosixPath(chunk.source).name} | text: {chunk.text}"
                     for chunk in self.chunks[start:start + 16]]
            batch = self._encode(texts)
            if self.index is None:
                self.index = faiss.IndexFlatIP(batch.shape[1])
            if batch.shape[1] != self.index.d:
                raise ValueError("Embedding dimension changed between batches")
            self.index.add(batch)

    def _encode(self, texts: list[str]):
        values = self.np.asarray(self.embedder.embed(texts), dtype=self.np.float32, order="C")
        if (values.ndim != 2 or values.shape[0] != len(texts) or not values.shape[1]
                or not self.np.isfinite(values).all()):
            raise ValueError("Embedding model returned invalid vectors")
        norms = self.np.linalg.norm(values, axis=1)
        if not self.np.isfinite(norms).all() or (norms == 0).any():
            raise ValueError("Embedding model returned invalid vector norms")
        self.faiss.normalize_L2(values)
        return values

    def retrieve(self, query: str, limit: int = 4) -> tuple[Match, ...]:
        if not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
            raise ValueError("Provide a query of 1–500 characters and a limit of 1–10")
        vector = self._encode([f"task: search result | query: {query}"])
        if vector.shape[1] != self.index.d:
            raise ValueError("Query and document embedding dimensions differ")
        scores, positions = self.index.search(vector, min(limit, len(self.chunks)))
        return tuple(Match(self.chunks[position], float(score)) for score, position in zip(scores[0], positions[0]))
