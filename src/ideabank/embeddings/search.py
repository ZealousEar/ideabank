"""Semantic and hybrid search."""

from typing import Optional

from openai import AsyncOpenAI

from ..core.database import Database
from ..core.repository import Repository
from ..search.fulltext import search_all
from .store import VectorStore, SimilarityResult


async def semantic_search(
    db: Database,
    repo: Repository,
    query: str,
    limit: int = 20,
    kind: Optional[str] = None,
    model: str = "text-embedding-3-small",
    dimensions: int = 1536,
) -> list[SimilarityResult]:
    """Semantic search using embeddings.

    Embeds the query and finds the most similar items.
    """
    # Embed the query
    client = AsyncOpenAI()
    response = await client.embeddings.create(
        input=[query],
        model=model,
        dimensions=dimensions,
    )
    query_vector = response.data[0].embedding

    # Search
    store = VectorStore(db, repo)
    results = await store.search(query_vector, limit=limit, kind=kind)

    # Enrich with content snippets
    for r in results:
        text = await repo.get_representation_text(r.item_id, "extracted_text")
        if text:
            r.snippet = text[:200]

    return results


async def hybrid_search(
    db: Database,
    repo: Repository,
    query: str,
    limit: int = 20,
    kind: Optional[str] = None,
    fts_weight: float = 0.4,
    semantic_weight: float = 0.6,
    model: str = "text-embedding-3-small",
) -> list[SimilarityResult]:
    """Hybrid search combining FTS5 + semantic search using Reciprocal Rank Fusion.

    Args:
        fts_weight: Weight for FTS5 results (default 0.4)
        semantic_weight: Weight for semantic results (default 0.6)
    """
    k = 60  # RRF constant

    # Run both searches in parallel
    import asyncio

    fts_task = asyncio.create_task(
        _fts_search_wrapper(db, query, limit=limit * 2, kind=kind)
    )
    sem_task = asyncio.create_task(
        semantic_search(db, repo, query, limit=limit * 2, kind=kind, model=model)
    )

    fts_results, sem_results = await asyncio.gather(fts_task, sem_task)

    # Compute RRF scores
    rrf_scores: dict[str, float] = {}
    item_data: dict[str, SimilarityResult] = {}

    # FTS results: ranked by BM25
    for rank, result in enumerate(fts_results):
        item_id = result.item_id
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + fts_weight / (k + rank + 1)
        if item_id not in item_data:
            item_data[item_id] = result

    # Semantic results: ranked by similarity
    for rank, result in enumerate(sem_results):
        item_id = result.item_id
        rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + semantic_weight / (k + rank + 1)
        if item_id not in item_data:
            item_data[item_id] = result

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for item_id in sorted_ids[:limit]:
        r = item_data[item_id]
        r.score = rrf_scores[item_id]
        results.append(r)

    return results


async def _fts_search_wrapper(
    db: Database,
    query: str,
    limit: int,
    kind: Optional[str],
) -> list[SimilarityResult]:
    """Wrap FTS5 search results into SimilarityResult format."""
    fts_results = await search_all(db, query, limit=limit, kind=kind)

    results = []
    for r in fts_results:
        results.append(SimilarityResult(
            item_id=r.item_id,
            score=r.rank,
            title=r.item_title,
            kind=r.item_kind,
            author=r.item_author,
            snippet=r.snippet,
        ))

    return results
