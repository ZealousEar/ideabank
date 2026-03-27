"""Full-text search across all content."""

import json
from dataclasses import dataclass
from typing import Optional

from ..core.database import Database


@dataclass
class SearchResult:
    """A search result from FTS."""

    item_id: str
    source_table: str  # 'items', 'representations', 'annotations', 'messages', 'journal'
    source_rowid: int
    snippet: Optional[str] = None
    rank: float = 0.0

    # Item details (populated when joining)
    item_kind: Optional[str] = None
    item_title: Optional[str] = None
    item_author: Optional[str] = None
    item_uri: Optional[str] = None


async def search_all(
    db: Database,
    query: str,
    *,
    limit: int = 50,
    offset: int = 0,
    kind: Optional[str] = None,
    stage: Optional[str] = None,
) -> list[SearchResult]:
    """
    Search across all FTS tables and return unified results.

    Args:
        db: Database connection
        query: Search query (FTS5 syntax supported)
        limit: Maximum results to return
        offset: Offset for pagination
        kind: Filter by item kind
        stage: Filter by annotation stage

    Returns:
        List of SearchResult objects ranked by relevance
    """
    results: list[SearchResult] = []

    # Search items_fts
    items_results = await _search_items(db, query, limit * 2, kind)
    results.extend(items_results)

    # Search representations_fts
    reps_results = await _search_representations(db, query, limit * 2, kind)
    results.extend(reps_results)

    # Search annotations_fts
    ann_results = await _search_annotations(db, query, limit * 2, stage)
    results.extend(ann_results)

    # Search messages_fts
    msg_results = await _search_messages(db, query, limit * 2)
    results.extend(msg_results)

    # Dedupe by item_id, keeping highest rank
    seen_items: dict[str, SearchResult] = {}
    for r in results:
        if r.item_id not in seen_items or r.rank > seen_items[r.item_id].rank:
            seen_items[r.item_id] = r

    # Sort by rank and paginate
    sorted_results = sorted(seen_items.values(), key=lambda x: x.rank, reverse=True)
    return sorted_results[offset : offset + limit]


async def _search_items(
    db: Database, query: str, limit: int, kind: Optional[str] = None
) -> list[SearchResult]:
    """Search items_fts."""
    kind_filter = "AND i.kind = ?" if kind else ""
    params = [query, kind, limit] if kind else [query, limit]

    sql = f"""
        SELECT
            i.id as item_id,
            i.item_rowid,
            i.kind,
            i.title,
            i.author_name,
            i.canonical_uri,
            bm25(items_fts) as rank,
            snippet(items_fts, 0, '<b>', '</b>', '...', 32) as snippet
        FROM items_fts
        JOIN items i ON items_fts.rowid = i.item_rowid
        WHERE items_fts MATCH ?
        {kind_filter}
        ORDER BY rank
        LIMIT ?
    """

    rows = await db.fetch_all(sql, tuple(params))
    return [
        SearchResult(
            item_id=row["item_id"],
            source_table="items",
            source_rowid=row["item_rowid"],
            snippet=row["snippet"],
            rank=-row["rank"],  # BM25 returns negative scores
            item_kind=row["kind"],
            item_title=row["title"],
            item_author=row["author_name"],
            item_uri=row["canonical_uri"],
        )
        for row in rows
    ]


async def _search_representations(
    db: Database, query: str, limit: int, kind: Optional[str] = None
) -> list[SearchResult]:
    """Search representations_fts."""
    kind_filter = "AND i.kind = ?" if kind else ""
    params = [query, kind, limit] if kind else [query, limit]

    sql = f"""
        SELECT
            r.item_id,
            r.rep_rowid,
            i.kind,
            i.title,
            i.author_name,
            i.canonical_uri,
            bm25(representations_fts) as rank,
            snippet(representations_fts, 0, '<b>', '</b>', '...', 64) as snippet
        FROM representations_fts
        JOIN representations r ON representations_fts.rowid = r.rep_rowid
        JOIN items i ON r.item_id = i.id
        WHERE representations_fts MATCH ?
        {kind_filter}
        ORDER BY rank
        LIMIT ?
    """

    rows = await db.fetch_all(sql, tuple(params))
    return [
        SearchResult(
            item_id=row["item_id"],
            source_table="representations",
            source_rowid=row["rep_rowid"],
            snippet=row["snippet"],
            rank=-row["rank"],
            item_kind=row["kind"],
            item_title=row["title"],
            item_author=row["author_name"],
            item_uri=row["canonical_uri"],
        )
        for row in rows
    ]


async def _search_annotations(
    db: Database, query: str, limit: int, stage: Optional[str] = None
) -> list[SearchResult]:
    """Search annotations_fts."""
    stage_filter = "AND a.stage = ?" if stage else ""
    params = [query, stage, limit] if stage else [query, limit]

    sql = f"""
        SELECT
            a.item_id,
            a.annotation_rowid,
            i.kind,
            i.title,
            i.author_name,
            i.canonical_uri,
            bm25(annotations_fts) as rank,
            snippet(annotations_fts, 0, '<b>', '</b>', '...', 64) as snippet
        FROM annotations_fts
        JOIN annotations a ON annotations_fts.rowid = a.annotation_rowid
        JOIN items i ON a.item_id = i.id
        WHERE annotations_fts MATCH ?
        {stage_filter}
        ORDER BY rank
        LIMIT ?
    """

    rows = await db.fetch_all(sql, tuple(params))
    return [
        SearchResult(
            item_id=row["item_id"],
            source_table="annotations",
            source_rowid=row["annotation_rowid"],
            snippet=row["snippet"],
            rank=-row["rank"],
            item_kind=row["kind"],
            item_title=row["title"],
            item_author=row["author_name"],
            item_uri=row["canonical_uri"],
        )
        for row in rows
    ]


async def _search_messages(db: Database, query: str, limit: int) -> list[SearchResult]:
    """Search messages_fts."""
    sql = """
        SELECT
            c.item_id,
            m.message_rowid,
            i.kind,
            i.title,
            i.author_name,
            i.canonical_uri,
            bm25(messages_fts) as rank,
            snippet(messages_fts, 0, '<b>', '</b>', '...', 64) as snippet
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.message_rowid
        JOIN conversations c ON m.conversation_id = c.id
        JOIN items i ON c.item_id = i.id
        WHERE messages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    rows = await db.fetch_all(sql, (query, limit))
    return [
        SearchResult(
            item_id=row["item_id"],
            source_table="messages",
            source_rowid=row["message_rowid"],
            snippet=row["snippet"],
            rank=-row["rank"],
            item_kind=row["kind"],
            item_title=row["title"],
            item_author=row["author_name"],
            item_uri=row["canonical_uri"],
        )
        for row in rows
    ]


async def search_items_only(
    db: Database,
    query: str,
    *,
    limit: int = 50,
    offset: int = 0,
    kind: Optional[str] = None,
) -> list[SearchResult]:
    """Search only items and their representations (not annotations/messages)."""
    results: list[SearchResult] = []

    items_results = await _search_items(db, query, limit * 2, kind)
    results.extend(items_results)

    reps_results = await _search_representations(db, query, limit * 2, kind)
    results.extend(reps_results)

    # Dedupe by item_id
    seen_items: dict[str, SearchResult] = {}
    for r in results:
        if r.item_id not in seen_items or r.rank > seen_items[r.item_id].rank:
            seen_items[r.item_id] = r

    sorted_results = sorted(seen_items.values(), key=lambda x: x.rank, reverse=True)
    return sorted_results[offset : offset + limit]
