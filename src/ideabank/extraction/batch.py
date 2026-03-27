"""Batch extraction orchestration."""

import asyncio
import json
import re
from typing import Optional
from urllib.parse import urlparse

from ..core.models import LinkedContent, ExtractionStatus, now_iso
from ..core.repository import Repository, compute_content_hash
from .router import route_url
from .base import ExtractionResult


# URL pattern to find URLs in tweet text and metadata
URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)]+")


def extract_urls_from_item(item) -> list[str]:
    """Extract all URLs from an item's text and metadata."""
    urls = set()

    # From metadata_json
    if item.metadata_json:
        meta = item.metadata_json if isinstance(item.metadata_json, dict) else {}
        # Direct URL fields
        for key in ("urls", "expanded_urls", "link_urls"):
            for u in meta.get(key, []):
                if isinstance(u, str) and u.startswith("http"):
                    urls.add(u)
                elif isinstance(u, dict):
                    for url_key in ("expanded_url", "url", "expanded"):
                        if url_key in u and isinstance(u[url_key], str):
                            urls.add(u[url_key])

        # String fields that may contain URLs
        for key in ("full_text", "text"):
            text = meta.get(key, "")
            if isinstance(text, str):
                urls.update(URL_PATTERN.findall(text))

    # Filter out social media / image / tracking URLs
    skip_domains = {
        "twitter.com", "x.com", "t.co", "pic.twitter.com",
        "instagram.com", "facebook.com", "tiktok.com",
        "pbs.twimg.com", "abs.twimg.com",
    }

    filtered = []
    for url in urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            if domain not in skip_domains:
                filtered.append(url)
        except Exception:
            continue

    return sorted(set(filtered))


async def extract_single(
    repo: Repository,
    item_id: str,
    url: str,
    semaphore: asyncio.Semaphore,
    rate_limit_delay: float = 1.0,
) -> Optional[LinkedContent]:
    """Extract content from a single URL with rate limiting."""
    async with semaphore:
        # Check if already extracted
        canonical = url  # Will be updated by extractor
        if await repo.linked_content_exists(item_id, url):
            return None

        extractor = route_url(url)
        if not extractor:
            # No suitable extractor — create a skipped record
            lc = LinkedContent(
                source_item_id=item_id,
                url=url,
                canonical_url=url,
                status=ExtractionStatus.SKIPPED,
                error_message="No extractor available",
            )
            try:
                parsed = urlparse(url)
                lc.domain = parsed.netloc.lower().replace("www.", "")
            except Exception:
                pass
            await repo.insert_linked_content(lc)
            return lc

        # Run extraction
        result: ExtractionResult = await extractor.extract(url)

        # Rate limit
        await asyncio.sleep(rate_limit_delay)

        # Build LinkedContent record
        try:
            parsed = urlparse(result.canonical_url or url)
            domain = parsed.netloc.lower().replace("www.", "")
        except Exception:
            domain = None

        lc = LinkedContent(
            source_item_id=item_id,
            url=url,
            canonical_url=result.canonical_url or url,
            domain=domain,
            content_type=result.content_type,
            title=result.title,
            extracted_text=result.text,
            word_count=result.word_count,
            extractor=result.extractor,
            status=ExtractionStatus.SUCCESS if result.success else ExtractionStatus.FAILED,
            error_message=result.error,
            content_hash=compute_content_hash(result.text) if result.text else None,
        )

        # Check for duplicate canonical URL (extractor may have resolved redirects)
        if await repo.linked_content_exists(item_id, lc.canonical_url):
            return None

        await repo.insert_linked_content(lc)
        return lc


async def extract_batch(
    repo: Repository,
    items: list,
    concurrency: int = 3,
    rate_limit_delay: float = 1.0,
) -> dict:
    """Extract linked content for a batch of items.

    Returns stats dict with counts.
    """
    stats = {"processed": 0, "extracted": 0, "skipped": 0, "failed": 0, "no_urls": 0}
    semaphore = asyncio.Semaphore(concurrency)

    for item in items:
        urls = extract_urls_from_item(item)
        if not urls:
            stats["no_urls"] += 1
            stats["processed"] += 1
            continue

        tasks = [
            extract_single(repo, item.id, url, semaphore, rate_limit_delay)
            for url in urls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                stats["failed"] += 1
            elif r is None:
                stats["skipped"] += 1  # Already existed
            elif r.status == ExtractionStatus.SUCCESS:
                stats["extracted"] += 1
            elif r.status == ExtractionStatus.SKIPPED:
                stats["skipped"] += 1
            else:
                stats["failed"] += 1

        stats["processed"] += 1

    return stats
