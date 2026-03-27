"""LLM classifier using OpenAI SDK."""

import json
import asyncio
from typing import Optional

from openai import AsyncOpenAI

from ..core.models import Classification, DomainTag, ContentType, now_iso
from ..core.repository import Repository, compute_content_hash
from .taxonomy import detect_domain_from_text, detect_content_type_from_url, detect_content_type_from_text
from .prompts import SYSTEM_PROMPT, build_user_prompt, VALID_DOMAINS, VALID_CONTENT_TYPES


DEFAULT_MODEL = "gpt-4.1-mini"
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0


async def classify_item(
    repo: Repository,
    item_id: str,
    text: str,
    author: Optional[str] = None,
    url: Optional[str] = None,
    linked_content_text: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[Classification]:
    """Classify a single item using LLM.

    Returns Classification or None on failure.
    """
    if not text or not text.strip():
        return None

    user_prompt = build_user_prompt(
        text=text,
        author=author,
        url=url,
        linked_content=linked_content_text,
    )

    # Call LLM with retries
    client = AsyncOpenAI()
    result = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            content = response.choices[0].message.content
            result = json.loads(content)
            break

        except Exception as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                # Detect rate limiting
                err_str = str(e).lower()
                if "rate limit" in err_str or "429" in err_str:
                    delay *= 1.5
                await asyncio.sleep(delay)
            else:
                return _fallback_classification(item_id, text, url, model)

    if not result:
        return _fallback_classification(item_id, text, url, model)

    # Validate and normalize LLM response
    domain = result.get("domain", "general")
    if domain not in VALID_DOMAINS:
        domain = detect_domain_from_text(text, url) or "general"

    content_type = result.get("content_type", "tweet")
    if content_type not in VALID_CONTENT_TYPES:
        content_type = detect_content_type_from_url(url) if url else "tweet"
        if not content_type:
            content_type = detect_content_type_from_text(text)

    domain_secondary = result.get("domain_secondary")
    if domain_secondary and domain_secondary not in VALID_DOMAINS:
        domain_secondary = None
    if domain_secondary == domain:
        domain_secondary = None

    summary = result.get("summary", "")
    tags = result.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = tags[:7]  # Max 7 tags

    content_hash = compute_content_hash(text)

    cls = Classification(
        item_id=item_id,
        domain=domain,
        domain_secondary=domain_secondary,
        content_type=content_type,
        summary=summary[:500] if summary else None,
        tags_json=tags if tags else None,
        confidence=1.0,
        model_name=model,
        content_hash=content_hash,
    )

    return cls


def _fallback_classification(
    item_id: str,
    text: str,
    url: Optional[str],
    model: str,
) -> Classification:
    """Create a classification using heuristic fallback when LLM fails."""
    domain = detect_domain_from_text(text, url) or "general"
    content_type = None
    if url:
        content_type = detect_content_type_from_url(url)
    if not content_type:
        content_type = detect_content_type_from_text(text, has_urls=bool(url))

    return Classification(
        item_id=item_id,
        domain=domain,
        content_type=content_type,
        summary=None,
        tags_json=None,
        confidence=0.5,  # Lower confidence for heuristic
        model_name=f"{model}+fallback",
        content_hash=compute_content_hash(text),
    )


async def classify_batch(
    repo: Repository,
    limit: int = 100,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Classify a batch of items.

    Returns stats dict with counts and cost estimate.
    """
    stats = {
        "classified": 0, "skipped": 0, "errors": 0, "fallback": 0,
        "estimated_tokens": 0, "estimated_cost": 0.0,
    }

    # Get items needing classification
    if force:
        items = await repo.get_all_items(limit=limit)
    else:
        items = await repo.get_items_needing_classification(limit=limit)

    if not items:
        return stats

    # Build classification inputs
    to_classify = []
    for item in items:
        content_text = await repo.get_representation_text(item.id, "extracted_text")
        if not content_text:
            stats["skipped"] += 1
            continue

        # Check if content changed (skip if hash matches)
        if not force:
            existing = await repo.get_classification_for_item(item.id)
            if existing and existing.content_hash == compute_content_hash(content_text):
                stats["skipped"] += 1
                continue

        # Get linked content for context
        linked_contents = await repo.get_linked_content_for_item(item.id)
        linked_text = None
        if linked_contents:
            linked_parts = [lc.extracted_text for lc in linked_contents if lc.extracted_text]
            if linked_parts:
                linked_text = "\n\n".join(linked_parts)[:2000]

        to_classify.append({
            "item": item,
            "text": content_text,
            "linked_text": linked_text,
        })

    # Estimate cost
    total_chars = sum(len(c["text"][:4000]) + len(c.get("linked_text", "") or "")[:2000] for c in to_classify)
    estimated_tokens = total_chars // 4 + len(to_classify) * 200  # System prompt + output
    stats["estimated_tokens"] = estimated_tokens
    stats["estimated_cost"] = estimated_tokens * 0.0000008  # gpt-4.1-mini: ~$0.80/1M tokens

    if dry_run:
        stats["would_classify"] = len(to_classify)
        return stats

    # Classify items
    for entry in to_classify:
        item = entry["item"]
        try:
            cls = await classify_item(
                repo=repo,
                item_id=item.id,
                text=entry["text"],
                author=item.author_name or item.author_handle,
                url=item.canonical_uri,
                linked_content_text=entry.get("linked_text"),
                model=model,
            )

            if cls:
                await repo.upsert_classification(cls)
                if cls.confidence < 1.0:
                    stats["fallback"] += 1
                else:
                    stats["classified"] += 1
            else:
                stats["errors"] += 1

        except Exception:
            stats["errors"] += 1

    return stats
