"""Vector storage and similarity computation."""

import json
import math
from typing import Optional
from dataclasses import dataclass

from ..core.database import Database
from ..core.repository import Repository


@dataclass
class SimilarityResult:
    """Result from a similarity search."""
    item_id: str
    score: float
    title: Optional[str] = None
    kind: Optional[str] = None
    author: Optional[str] = None
    snippet: Optional[str] = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """Vector store with sqlite-vec primary and JSON fallback."""

    def __init__(self, db: Database, repo: Repository):
        self.db = db
        self.repo = repo

    async def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        kind: Optional[str] = None,
    ) -> list[SimilarityResult]:
        """Search for similar items using the best available method."""
        if self.db.has_vec:
            return await self._search_vec(query_vector, limit, kind)
        return await self._search_json_fallback(query_vector, limit, kind)

    async def _search_vec(
        self,
        query_vector: list[float],
        limit: int,
        kind: Optional[str],
    ) -> list[SimilarityResult]:
        """Search using sqlite-vec virtual table."""
        vec_json = json.dumps(query_vector)

        if kind:
            rows = await self.db.fetch_all(
                """
                SELECT v.item_id, v.distance, i.title, i.kind, i.author_name
                FROM embeddings_vec v
                JOIN items i ON v.item_id = i.id
                WHERE i.kind = ?
                ORDER BY v.distance
                LIMIT ?
                """,
                (kind, limit),
            )
        else:
            rows = await self.db.fetch_all(
                """
                SELECT v.item_id, v.distance, i.title, i.kind, i.author_name
                FROM embeddings_vec v
                JOIN items i ON v.item_id = i.id
                WHERE v.embedding MATCH ?
                ORDER BY v.distance
                LIMIT ?
                """,
                (vec_json, limit),
            )

        results = []
        for row in rows:
            results.append(SimilarityResult(
                item_id=row["item_id"],
                score=1.0 - row["distance"],  # Convert distance to similarity
                title=row["title"],
                kind=row["kind"],
                author=row["author_name"],
            ))
        return results

    async def _search_json_fallback(
        self,
        query_vector: list[float],
        limit: int,
        kind: Optional[str],
    ) -> list[SimilarityResult]:
        """Fallback: load all embeddings into memory and compute cosine similarity."""
        # Load all embeddings
        if kind:
            rows = await self.db.fetch_all(
                """
                SELECT e.item_id, e.embedding_json, i.title, i.kind, i.author_name
                FROM embeddings e
                JOIN items i ON e.item_id = i.id
                WHERE i.kind = ?
                """,
                (kind,),
            )
        else:
            rows = await self.db.fetch_all(
                """
                SELECT e.item_id, e.embedding_json, i.title, i.kind, i.author_name
                FROM embeddings e
                JOIN items i ON e.item_id = i.id
                """
            )

        if not rows:
            return []

        # Compute similarities
        scored = []
        for row in rows:
            try:
                stored_vec = json.loads(row["embedding_json"])
                sim = cosine_similarity(query_vector, stored_vec)
                scored.append((sim, row))
            except (json.JSONDecodeError, TypeError):
                continue

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, row in scored[:limit]:
            results.append(SimilarityResult(
                item_id=row["item_id"],
                score=sim,
                title=row["title"],
                kind=row["kind"],
                author=row["author_name"],
            ))

        return results
