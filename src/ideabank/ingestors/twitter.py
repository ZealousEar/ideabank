"""Twitter bookmarks ingestor."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.canonicalize import canonicalize_url, extract_twitter_status_id
from ..core.models import (
    Event,
    EventType,
    Item,
    ItemKind,
    RawIngestion,
    Representation,
    RepresentationType,
    SourceState,
    now_iso,
)
from ..core.repository import Repository, compute_content_hash, compute_file_hash


SOURCE_NAME = "twitter_bookmarks"


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    items_created: int = 0
    items_skipped: int = 0
    events_created: int = 0
    events_skipped: int = 0
    representations_created: int = 0
    file_hash: str = ""
    total_records: int = 0


async def ingest_twitter_bookmarks(
    repo: Repository,
    file_path: Path,
    *,
    force: bool = False,
) -> IngestResult:
    """
    Ingest Twitter bookmarks from a JSON file.

    Args:
        repo: Repository for database operations
        file_path: Path to the bookmarks JSON file
        force: If True, re-ingest even if file was already processed

    Returns:
        IngestResult with counts of created/skipped items
    """
    result = IngestResult()

    # Check if file was already ingested
    file_hash = compute_file_hash(str(file_path))
    result.file_hash = file_hash

    if not force and await repo.ingestion_exists_by_hash(file_hash):
        return result

    # Load bookmarks
    with open(file_path, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    result.total_records = len(bookmarks)

    # Track highest bookmark_date for watermark
    max_bookmark_date: Optional[str] = None

    for bookmark in bookmarks:
        tweet_url = bookmark.get("tweet_url", "")
        if not tweet_url:
            continue

        # Canonicalize URL for deduplication
        canonical_uri = canonicalize_url(tweet_url)

        # Check if item already exists
        if await repo.item_exists_by_uri(canonical_uri):
            result.items_skipped += 1
            # Still need to check for duplicate event
            existing_item = await repo.get_item_by_uri(canonical_uri)
            if existing_item:
                await _maybe_create_bookmark_event(
                    repo, existing_item.id, bookmark, canonical_uri, result
                )
            continue

        # Extract tweet content
        full_text = bookmark.get("note_tweet_text") or bookmark.get("full_text", "")
        screen_name = bookmark.get("screen_name", "")
        display_name = bookmark.get("name", "")
        tweeted_at = bookmark.get("tweeted_at")
        bookmark_date = bookmark.get("bookmark_date")

        # Update watermark
        if bookmark_date and (max_bookmark_date is None or bookmark_date > max_bookmark_date):
            max_bookmark_date = bookmark_date

        # Create title from first line or truncated text
        title = _extract_title(full_text)

        # Build metadata
        metadata = {
            "profile_image_url": bookmark.get("profile_image_url_https"),
            "has_media": bool(bookmark.get("extended_media")),
            "media_types": [m.get("type") for m in bookmark.get("extended_media", [])],
        }

        # Create item
        item = Item(
            kind=ItemKind.TWEET,
            canonical_uri=canonical_uri,
            title=title,
            author_name=display_name,
            author_handle=f"@{screen_name}" if screen_name else None,
            author_uri=f"https://x.com/{screen_name}" if screen_name else None,
            created_at=tweeted_at,
            metadata_json=metadata,
        )

        await repo.insert_item(item)
        result.items_created += 1

        # Create bookmark event
        await _maybe_create_bookmark_event(repo, item.id, bookmark, canonical_uri, result)

        # Create raw_json representation
        raw_rep = Representation(
            item_id=item.id,
            rep_type=RepresentationType.RAW_JSON,
            content_json=bookmark,
            content_hash=compute_content_hash(json.dumps(bookmark, sort_keys=True)),
        )
        await repo.insert_representation(raw_rep)

        # Create extracted_text representation
        if full_text:
            text_rep = Representation(
                item_id=item.id,
                rep_type=RepresentationType.EXTRACTED_TEXT,
                content_text=full_text,
                source_rep_id=raw_rep.id,
                processor="twitter_ingestor",
                processor_version="1",
                content_hash=compute_content_hash(full_text),
            )
            await repo.insert_representation(text_rep)
            result.representations_created += 2
        else:
            result.representations_created += 1

    # Record raw ingestion
    ingestion = RawIngestion(
        source=SOURCE_NAME,
        file_path=str(file_path),
        file_hash=file_hash,
        record_count=result.total_records,
        schema_version="1",
    )
    await repo.insert_raw_ingestion(ingestion)

    # Update source state
    source_state = await repo.get_source_state(SOURCE_NAME) or SourceState(source=SOURCE_NAME)
    source_state.last_checked_at = now_iso()
    if result.items_created > 0:
        source_state.last_ingested_at = now_iso()
    if max_bookmark_date:
        if source_state.watermark_occurred_at is None or max_bookmark_date > source_state.watermark_occurred_at:
            source_state.watermark_occurred_at = max_bookmark_date
    source_state.last_file_hash = file_hash
    await repo.upsert_source_state(source_state)

    return result


async def _maybe_create_bookmark_event(
    repo: Repository,
    item_id: str,
    bookmark: dict,
    canonical_uri: str,
    result: IngestResult,
) -> None:
    """Create a bookmark event if it doesn't already exist."""
    bookmark_date = bookmark.get("bookmark_date", now_iso())

    # Use canonical_uri as dedupe_key for Twitter bookmarks
    if await repo.event_exists_by_dedupe_key(SOURCE_NAME, "bookmarked", canonical_uri):
        result.events_skipped += 1
        return

    event = Event(
        event_type=EventType.BOOKMARKED,
        item_id=item_id,
        occurred_at=bookmark_date,
        source=SOURCE_NAME,
        dedupe_key=canonical_uri,
    )
    await repo.insert_event(event)
    result.events_created += 1


def _extract_title(text: str, max_length: int = 100) -> str:
    """Extract a title from tweet text."""
    if not text:
        return ""

    # Take first line
    first_line = text.split("\n")[0].strip()

    # Remove URLs
    words = []
    for word in first_line.split():
        if not word.startswith(("http://", "https://", "t.co/")):
            words.append(word)
    first_line = " ".join(words)

    # Truncate if needed
    if len(first_line) > max_length:
        first_line = first_line[: max_length - 3] + "..."

    return first_line or "Tweet"


async def check_twitter_source(repo: Repository, raw_path: Path) -> list[Path]:
    """
    Check for new Twitter bookmark files to ingest.

    Args:
        repo: Repository for database operations
        raw_path: Path to raw data directory

    Returns:
        List of files that need ingestion
    """
    twitter_path = raw_path / "twitter"
    if not twitter_path.exists():
        return []

    files_to_ingest = []
    for json_file in twitter_path.glob("*.json"):
        file_hash = compute_file_hash(str(json_file))
        if not await repo.ingestion_exists_by_hash(file_hash):
            files_to_ingest.append(json_file)

    return sorted(files_to_ingest)
