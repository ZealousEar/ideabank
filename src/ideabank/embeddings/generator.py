"""OpenAI embedding generation."""

import json
import hashlib
from typing import Optional

from openai import AsyncOpenAI

from ..core.models import Embedding, now_iso
from ..core.repository import Repository


DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536
BATCH_SIZE = 500
MAX_TEXT_CHARS = 8000


def build_embedding_text(
    title: Optional[str],
    author: Optional[str],
    content_text: Optional[str],
    summary: Optional[str] = None,
    linked_text: Optional[str] = None,
) -> str:
    """Build the text string to embed for an item.

    Combines title, author, content, summary, and linked content
    into a single string optimized for embedding quality.
    """
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if author:
        parts.append(f"Author: {author}")
    if summary:
        parts.append(f"Summary: {summary}")
    if content_text:
        parts.append(content_text)
    if linked_text:
        # Add first portion of linked content
        parts.append(linked_text[:2000])

    text = "\n".join(parts)
    return text[:MAX_TEXT_CHARS] if text else ""


def _compute_text_hash(text: str) -> str:
    """Compute hash of embedding source text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def generate_embeddings(
    repo: Repository,
    model: str = DEFAULT_MODEL,
    dimensions: int = DEFAULT_DIMENSIONS,
    batch_size: int = BATCH_SIZE,
    limit: int = 500,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Generate embeddings for items that don't have them yet.

    Returns stats dict with counts and cost estimate.
    """
    stats = {"embedded": 0, "skipped": 0, "errors": 0, "total_tokens": 0, "estimated_cost": 0.0}

    # Get items needing embeddings
    if force:
        items = await repo.get_all_items(limit=limit)
    else:
        items = await repo.get_items_needing_embedding(model=model, limit=limit)

    if not items:
        return stats

    # Build texts and check hashes
    to_embed = []  # (item, text, text_hash)
    for item in items:
        content_text = await repo.get_representation_text(item.id, "extracted_text")

        # Get classification summary if available
        cls = await repo.get_classification_for_item(item.id)
        summary = cls.summary if cls else None

        # Get linked content text
        linked_contents = await repo.get_linked_content_for_item(item.id)
        linked_text = None
        if linked_contents:
            linked_parts = [lc.extracted_text for lc in linked_contents if lc.extracted_text]
            if linked_parts:
                linked_text = "\n\n".join(linked_parts)

        text = build_embedding_text(
            title=item.title,
            author=item.author_name or item.author_handle,
            content_text=content_text,
            summary=summary,
            linked_text=linked_text,
        )

        if not text.strip():
            stats["skipped"] += 1
            continue

        text_hash = _compute_text_hash(text)

        # Skip if hash unchanged (only in non-force mode)
        if not force:
            existing = await repo.get_embedding_for_item(item.id, model)
            if existing and existing.source_text_hash == text_hash:
                stats["skipped"] += 1
                continue

        to_embed.append((item, text, text_hash))

    # Estimate cost
    total_chars = sum(len(t[1]) for t in to_embed)
    estimated_tokens = total_chars // 4  # Rough estimate: 4 chars per token
    stats["total_tokens"] = estimated_tokens
    stats["estimated_cost"] = estimated_tokens * 0.00000002  # $0.02/1M tokens

    if dry_run:
        stats["would_embed"] = len(to_embed)
        return stats

    if not to_embed:
        return stats

    # Generate embeddings in batches
    client = AsyncOpenAI()

    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i:i + batch_size]
        texts = [t[1] for t in batch]

        try:
            response = await client.embeddings.create(
                input=texts,
                model=model,
                dimensions=dimensions,
            )

            for j, embedding_data in enumerate(response.data):
                item, text, text_hash = batch[j]
                vector = embedding_data.embedding

                emb = Embedding(
                    item_id=item.id,
                    embedding_model=model,
                    dimensions=dimensions,
                    embedding_json=vector,
                    source_text_hash=text_hash,
                    token_count=response.usage.total_tokens // len(texts) if response.usage else None,
                )

                await repo.upsert_embedding(emb)
                stats["embedded"] += 1

            if response.usage:
                stats["total_tokens"] = response.usage.total_tokens

        except Exception as e:
            stats["errors"] += len(batch)
            # Continue with next batch rather than failing entirely

    return stats
