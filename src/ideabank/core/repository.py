"""Repository layer for database operations."""

import hashlib
import json
from typing import Optional

from .database import Database
from .models import (
    Annotation,
    Classification,
    Conversation,
    Embedding,
    Event,
    Item,
    LinkedContent,
    Message,
    RawIngestion,
    Representation,
    SourceState,
    Topic,
    now_iso,
)


def _json_dumps(obj) -> Optional[str]:
    """Serialize object to JSON string or None."""
    if obj is None:
        return None
    return json.dumps(obj)


class Repository:
    """Repository for all database operations."""

    def __init__(self, db: Database):
        self.db = db

    # ============================================
    # Items
    # ============================================

    async def insert_item(self, item: Item) -> Item:
        """Insert a new item."""
        await self.db.execute(
            """
            INSERT INTO items (
                id, kind, canonical_uri, canonicalizer_version,
                title, author_name, author_handle, author_uri,
                created_at, first_seen_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.kind.value if hasattr(item.kind, "value") else item.kind,
                item.canonical_uri,
                item.canonicalizer_version,
                item.title,
                item.author_name,
                item.author_handle,
                item.author_uri,
                item.created_at,
                item.first_seen_at,
                item.updated_at,
                _json_dumps(item.metadata_json),
            ),
        )
        await self.db.commit()
        return item

    async def get_item_by_uri(self, canonical_uri: str) -> Optional[Item]:
        """Get an item by its canonical URI."""
        row = await self.db.fetch_one(
            "SELECT * FROM items WHERE canonical_uri = ?", (canonical_uri,)
        )
        if not row:
            return None
        return self._row_to_item(row)

    async def get_item_by_id(self, item_id: str) -> Optional[Item]:
        """Get an item by its ID."""
        row = await self.db.fetch_one("SELECT * FROM items WHERE id = ?", (item_id,))
        if not row:
            return None
        return self._row_to_item(row)

    async def item_exists_by_uri(self, canonical_uri: str) -> bool:
        """Check if an item exists by canonical URI."""
        row = await self.db.fetch_one(
            "SELECT 1 FROM items WHERE canonical_uri = ?", (canonical_uri,)
        )
        return row is not None

    async def count_items(self, kind: Optional[str] = None) -> int:
        """Count items, optionally filtered by kind."""
        if kind:
            row = await self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM items WHERE kind = ?", (kind,)
            )
        else:
            row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM items")
        return row["cnt"] if row else 0

    def _row_to_item(self, row) -> Item:
        """Convert a database row to an Item model."""
        return Item(
            id=row["id"],
            kind=row["kind"],
            canonical_uri=row["canonical_uri"],
            canonicalizer_version=row["canonicalizer_version"],
            title=row["title"],
            author_name=row["author_name"],
            author_handle=row["author_handle"],
            author_uri=row["author_uri"],
            created_at=row["created_at"],
            first_seen_at=row["first_seen_at"],
            updated_at=row["updated_at"],
            metadata_json=json.loads(row["metadata_json"]) if row["metadata_json"] else None,
        )

    # ============================================
    # Events
    # ============================================

    async def insert_event(self, event: Event) -> Event:
        """Insert a new event."""
        await self.db.execute(
            """
            INSERT INTO events (
                id, event_type, item_id, occurred_at, source, context_json, dedupe_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.event_type.value if hasattr(event.event_type, "value") else event.event_type,
                event.item_id,
                event.occurred_at,
                event.source,
                _json_dumps(event.context_json),
                event.dedupe_key,
            ),
        )
        await self.db.commit()
        return event

    async def event_exists_by_dedupe_key(
        self, source: str, event_type: str, dedupe_key: str
    ) -> bool:
        """Check if an event exists by dedupe key."""
        row = await self.db.fetch_one(
            """
            SELECT 1 FROM events
            WHERE source = ? AND event_type = ? AND dedupe_key = ?
            """,
            (source, event_type, dedupe_key),
        )
        return row is not None

    async def count_events(self, source: Optional[str] = None) -> int:
        """Count events, optionally filtered by source."""
        if source:
            row = await self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM events WHERE source = ?", (source,)
            )
        else:
            row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM events")
        return row["cnt"] if row else 0

    # ============================================
    # Representations
    # ============================================

    async def insert_representation(self, rep: Representation) -> Representation:
        """Insert a new representation."""
        await self.db.execute(
            """
            INSERT INTO representations (
                id, item_id, rep_type, content_text, content_json,
                source_rep_id, processor, processor_version,
                content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rep.id,
                rep.item_id,
                rep.rep_type.value if hasattr(rep.rep_type, "value") else rep.rep_type,
                rep.content_text,
                _json_dumps(rep.content_json),
                rep.source_rep_id,
                rep.processor,
                rep.processor_version,
                rep.content_hash,
                rep.created_at,
            ),
        )
        await self.db.commit()
        return rep

    # ============================================
    # Annotations
    # ============================================

    async def insert_annotation(self, ann: Annotation) -> Annotation:
        """Insert a new annotation."""
        await self.db.execute(
            """
            INSERT INTO annotations (
                id, item_id, note_text, tags_json, rating, stage,
                created_at, updated_at, obsidian_path, obsidian_hash, exported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ann.id,
                ann.item_id,
                ann.note_text,
                _json_dumps(ann.tags_json),
                ann.rating,
                ann.stage.value if hasattr(ann.stage, "value") else ann.stage,
                ann.created_at,
                ann.updated_at,
                ann.obsidian_path,
                ann.obsidian_hash,
                ann.exported_at,
            ),
        )
        await self.db.commit()
        return ann

    async def get_annotation_by_item(self, item_id: str) -> Optional[Annotation]:
        """Get annotation for an item."""
        row = await self.db.fetch_one(
            "SELECT * FROM annotations WHERE item_id = ?", (item_id,)
        )
        if not row:
            return None
        return Annotation(
            id=row["id"],
            item_id=row["item_id"],
            note_text=row["note_text"],
            tags_json=json.loads(row["tags_json"]) if row["tags_json"] else None,
            rating=row["rating"],
            stage=row["stage"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            obsidian_path=row["obsidian_path"],
            obsidian_hash=row["obsidian_hash"],
            exported_at=row["exported_at"],
        )

    async def update_annotation(self, ann: Annotation) -> Annotation:
        """Update an existing annotation."""
        ann.updated_at = now_iso()
        await self.db.execute(
            """
            UPDATE annotations SET
                note_text = ?, tags_json = ?, rating = ?, stage = ?,
                updated_at = ?, obsidian_path = ?, obsidian_hash = ?, exported_at = ?
            WHERE id = ?
            """,
            (
                ann.note_text,
                _json_dumps(ann.tags_json),
                ann.rating,
                ann.stage.value if hasattr(ann.stage, "value") else ann.stage,
                ann.updated_at,
                ann.obsidian_path,
                ann.obsidian_hash,
                ann.exported_at,
                ann.id,
            ),
        )
        await self.db.commit()
        return ann

    # ============================================
    # Source State
    # ============================================

    async def get_source_state(self, source: str) -> Optional[SourceState]:
        """Get source state by source name."""
        row = await self.db.fetch_one(
            "SELECT * FROM source_state WHERE source = ?", (source,)
        )
        if not row:
            return None
        return SourceState(
            source=row["source"],
            last_checked_at=row["last_checked_at"],
            last_ingested_at=row["last_ingested_at"],
            watermark_occurred_at=row["watermark_occurred_at"],
            last_file_hash=row["last_file_hash"],
            state_json=json.loads(row["state_json"]) if row["state_json"] else None,
        )

    async def upsert_source_state(self, state: SourceState) -> SourceState:
        """Insert or update source state."""
        await self.db.execute(
            """
            INSERT INTO source_state (
                source, last_checked_at, last_ingested_at,
                watermark_occurred_at, last_file_hash, state_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_checked_at = excluded.last_checked_at,
                last_ingested_at = excluded.last_ingested_at,
                watermark_occurred_at = excluded.watermark_occurred_at,
                last_file_hash = excluded.last_file_hash,
                state_json = excluded.state_json
            """,
            (
                state.source,
                state.last_checked_at,
                state.last_ingested_at,
                state.watermark_occurred_at,
                state.last_file_hash,
                _json_dumps(state.state_json),
            ),
        )
        await self.db.commit()
        return state

    # ============================================
    # Raw Ingestions
    # ============================================

    async def insert_raw_ingestion(self, ing: RawIngestion) -> RawIngestion:
        """Insert a raw ingestion record."""
        await self.db.execute(
            """
            INSERT INTO raw_ingestions (
                id, source, file_path, file_hash, record_count, schema_version, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ing.id,
                ing.source,
                ing.file_path,
                ing.file_hash,
                ing.record_count,
                ing.schema_version,
                ing.imported_at,
            ),
        )
        await self.db.commit()
        return ing

    async def ingestion_exists_by_hash(self, file_hash: str) -> bool:
        """Check if a file has already been ingested."""
        row = await self.db.fetch_one(
            "SELECT 1 FROM raw_ingestions WHERE file_hash = ?", (file_hash,)
        )
        return row is not None

    # ============================================
    # Conversations & Messages
    # ============================================

    async def insert_conversation(self, conv: Conversation) -> Conversation:
        """Insert a new conversation."""
        await self.db.execute(
            """
            INSERT INTO conversations (
                id, item_id, platform, model, title,
                started_at, ended_at, summary_text, key_insights_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conv.id,
                conv.item_id,
                conv.platform,
                conv.model,
                conv.title,
                conv.started_at,
                conv.ended_at,
                conv.summary_text,
                _json_dumps(conv.key_insights_json),
            ),
        )
        await self.db.commit()
        return conv

    async def insert_message(self, msg: Message) -> Message:
        """Insert a new message."""
        await self.db.execute(
            """
            INSERT INTO messages (
                id, conversation_id, role, content_text, content_json, message_index, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg.id,
                msg.conversation_id,
                msg.role,
                msg.content_text,
                _json_dumps(msg.content_json),
                msg.message_index,
                msg.created_at,
            ),
        )
        await self.db.commit()
        return msg

    # ============================================
    # Topics
    # ============================================

    async def insert_topic(self, topic: Topic) -> Topic:
        """Insert a new topic."""
        await self.db.execute(
            """
            INSERT INTO topics (
                id, name, slug, parent_id, patterns_json, accounts_json, color, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic.id,
                topic.name,
                topic.slug,
                topic.parent_id,
                _json_dumps(topic.patterns_json),
                _json_dumps(topic.accounts_json),
                topic.color,
                topic.created_at,
            ),
        )
        await self.db.commit()
        return topic

    async def get_topic_by_slug(self, slug: str) -> Optional[Topic]:
        """Get a topic by slug."""
        row = await self.db.fetch_one("SELECT * FROM topics WHERE slug = ?", (slug,))
        if not row:
            return None
        return Topic(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            parent_id=row["parent_id"],
            patterns_json=json.loads(row["patterns_json"]) if row["patterns_json"] else None,
            accounts_json=json.loads(row["accounts_json"]) if row["accounts_json"] else None,
            color=row["color"],
            created_at=row["created_at"],
        )

    async def get_all_topics(self) -> list[Topic]:
        """Get all topics."""
        rows = await self.db.fetch_all("SELECT * FROM topics ORDER BY name")
        return [
            Topic(
                id=row["id"],
                name=row["name"],
                slug=row["slug"],
                parent_id=row["parent_id"],
                patterns_json=json.loads(row["patterns_json"]) if row["patterns_json"] else None,
                accounts_json=json.loads(row["accounts_json"]) if row["accounts_json"] else None,
                color=row["color"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def add_item_topic(self, item_id: str, topic_id: str, confidence: float = 1.0, source: str = "pattern"):
        """Associate an item with a topic."""
        await self.db.execute(
            """
            INSERT OR IGNORE INTO item_topics (item_id, topic_id, confidence, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item_id, topic_id, confidence, source, now_iso()),
        )
        await self.db.commit()

    # ============================================
    # Export Queries
    # ============================================

    async def get_topics_for_item(self, item_id: str) -> list[str]:
        """Get topic slugs for an item."""
        rows = await self.db.fetch_all(
            """
            SELECT t.slug FROM topics t
            JOIN item_topics it ON t.id = it.topic_id
            WHERE it.item_id = ?
            ORDER BY it.confidence DESC, t.name
            """,
            (item_id,),
        )
        return [row["slug"] for row in rows]

    async def get_representation_text(self, item_id: str, rep_type: str = "extracted_text") -> Optional[str]:
        """Get content text from a representation."""
        row = await self.db.fetch_one(
            """
            SELECT content_text FROM representations
            WHERE item_id = ? AND rep_type = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (item_id, rep_type),
        )
        return row["content_text"] if row else None

    async def get_items_for_export(
        self,
        only_annotated: bool = True,
        only_changed: bool = False,
        kind: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[tuple[Item, Optional[Annotation]]]:
        """Get items for export with optional filters."""
        query = """
            SELECT i.*, a.id as ann_id, a.item_id as ann_item_id, a.note_text, a.tags_json,
                   a.rating, a.stage, a.created_at as ann_created_at, a.updated_at as ann_updated_at,
                   a.obsidian_path, a.obsidian_hash, a.exported_at
            FROM items i
            LEFT JOIN annotations a ON i.id = a.item_id
        """
        conditions = []
        params = []

        if only_annotated:
            conditions.append("a.id IS NOT NULL")

        if only_changed:
            conditions.append("(a.exported_at IS NULL OR a.updated_at > a.exported_at)")

        if kind:
            conditions.append("i.kind = ?")
            params.append(kind)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY i.created_at DESC"

        if limit:
            query += f" LIMIT {limit}"

        rows = await self.db.fetch_all(query, tuple(params))

        results = []
        for row in rows:
            item = self._row_to_item(row)
            annotation = None
            if row["ann_id"]:
                annotation = Annotation(
                    id=row["ann_id"],
                    item_id=row["ann_item_id"],
                    note_text=row["note_text"],
                    tags_json=json.loads(row["tags_json"]) if row["tags_json"] else None,
                    rating=row["rating"],
                    stage=row["stage"],
                    created_at=row["ann_created_at"],
                    updated_at=row["ann_updated_at"],
                    obsidian_path=row["obsidian_path"],
                    obsidian_hash=row["obsidian_hash"],
                    exported_at=row["exported_at"],
                )
            results.append((item, annotation))

        return results

    async def get_all_items(self, kind: Optional[str] = None, limit: Optional[int] = None) -> list[Item]:
        """Get all items with optional filters."""
        query = "SELECT * FROM items"
        params = []

        if kind:
            query += " WHERE kind = ?"
            params.append(kind)

        query += " ORDER BY created_at DESC"

        if limit:
            query += f" LIMIT {limit}"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_item(row) for row in rows]

    async def get_or_create_annotation(self, item_id: str) -> Annotation:
        """Get existing annotation or create a new one for an item."""
        existing = await self.get_annotation_by_item(item_id)
        if existing:
            return existing

        annotation = Annotation(item_id=item_id)
        return await self.insert_annotation(annotation)

    async def get_first_event_date(self, item_id: str) -> Optional[str]:
        """Get the date of the first event for an item."""
        row = await self.db.fetch_one(
            """
            SELECT occurred_at FROM events
            WHERE item_id = ?
            ORDER BY occurred_at ASC LIMIT 1
            """,
            (item_id,),
        )
        return row["occurred_at"] if row else None

    # ============================================
    # Linked Content
    # ============================================

    async def insert_linked_content(self, lc: LinkedContent) -> LinkedContent:
        """Insert a new linked content record."""
        await self.db.execute(
            """
            INSERT INTO linked_content (
                id, source_item_id, url, canonical_url, domain, content_type,
                title, extracted_text, word_count, extractor, status,
                error_message, content_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lc.id, lc.source_item_id, lc.url, lc.canonical_url, lc.domain,
                lc.content_type, lc.title, lc.extracted_text, lc.word_count,
                lc.extractor,
                lc.status.value if hasattr(lc.status, "value") else lc.status,
                lc.error_message, lc.content_hash, lc.created_at, lc.updated_at,
            ),
        )
        await self.db.commit()
        return lc

    async def update_linked_content(self, lc: LinkedContent) -> LinkedContent:
        """Update a linked content record."""
        lc.updated_at = now_iso()
        await self.db.execute(
            """
            UPDATE linked_content SET
                title = ?, extracted_text = ?, word_count = ?, extractor = ?,
                status = ?, error_message = ?, content_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                lc.title, lc.extracted_text, lc.word_count, lc.extractor,
                lc.status.value if hasattr(lc.status, "value") else lc.status,
                lc.error_message, lc.content_hash, lc.updated_at, lc.id,
            ),
        )
        await self.db.commit()
        return lc

    async def get_linked_content_for_item(self, item_id: str) -> list[LinkedContent]:
        """Get all linked content for an item."""
        rows = await self.db.fetch_all(
            "SELECT * FROM linked_content WHERE source_item_id = ? ORDER BY created_at",
            (item_id,),
        )
        return [self._row_to_linked_content(row) for row in rows]

    async def get_items_needing_extraction(self, limit: int = 100) -> list[Item]:
        """Get items that have URLs in metadata but no linked_content records."""
        rows = await self.db.fetch_all(
            """
            SELECT i.* FROM items i
            WHERE i.metadata_json IS NOT NULL
              AND i.id NOT IN (SELECT DISTINCT source_item_id FROM linked_content)
            ORDER BY i.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_item(row) for row in rows]

    async def count_linked_content(self, status: Optional[str] = None) -> int:
        """Count linked content records."""
        if status:
            row = await self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM linked_content WHERE status = ?", (status,)
            )
        else:
            row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM linked_content")
        return row["cnt"] if row else 0

    async def linked_content_exists(self, source_item_id: str, canonical_url: str) -> bool:
        """Check if linked content already exists."""
        row = await self.db.fetch_one(
            "SELECT 1 FROM linked_content WHERE source_item_id = ? AND canonical_url = ?",
            (source_item_id, canonical_url),
        )
        return row is not None

    def _row_to_linked_content(self, row) -> LinkedContent:
        """Convert a database row to a LinkedContent model."""
        return LinkedContent(
            id=row["id"],
            source_item_id=row["source_item_id"],
            url=row["url"],
            canonical_url=row["canonical_url"],
            domain=row["domain"],
            content_type=row["content_type"],
            title=row["title"],
            extracted_text=row["extracted_text"],
            word_count=row["word_count"],
            extractor=row["extractor"],
            status=row["status"],
            error_message=row["error_message"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ============================================
    # Classifications
    # ============================================

    async def insert_classification(self, cls: Classification) -> Classification:
        """Insert a new classification record."""
        await self.db.execute(
            """
            INSERT INTO classifications (
                id, item_id, domain, domain_secondary, content_type,
                summary, tags_json, confidence, model_name, content_hash,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cls.id, cls.item_id, cls.domain.value if hasattr(cls.domain, "value") else cls.domain,
                cls.domain_secondary,
                cls.content_type.value if hasattr(cls.content_type, "value") else cls.content_type,
                cls.summary, _json_dumps(cls.tags_json), cls.confidence,
                cls.model_name, cls.content_hash, cls.created_at, cls.updated_at,
            ),
        )
        await self.db.commit()
        return cls

    async def upsert_classification(self, cls: Classification) -> Classification:
        """Insert or update a classification record."""
        cls.updated_at = now_iso()
        await self.db.execute(
            """
            INSERT INTO classifications (
                id, item_id, domain, domain_secondary, content_type,
                summary, tags_json, confidence, model_name, content_hash,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                domain = excluded.domain,
                domain_secondary = excluded.domain_secondary,
                content_type = excluded.content_type,
                summary = excluded.summary,
                tags_json = excluded.tags_json,
                confidence = excluded.confidence,
                model_name = excluded.model_name,
                content_hash = excluded.content_hash,
                updated_at = excluded.updated_at
            """,
            (
                cls.id, cls.item_id, cls.domain.value if hasattr(cls.domain, "value") else cls.domain,
                cls.domain_secondary,
                cls.content_type.value if hasattr(cls.content_type, "value") else cls.content_type,
                cls.summary, _json_dumps(cls.tags_json), cls.confidence,
                cls.model_name, cls.content_hash, cls.created_at, cls.updated_at,
            ),
        )
        await self.db.commit()
        return cls

    async def get_classification_for_item(self, item_id: str) -> Optional[Classification]:
        """Get classification for an item."""
        row = await self.db.fetch_one(
            "SELECT * FROM classifications WHERE item_id = ?", (item_id,)
        )
        if not row:
            return None
        return self._row_to_classification(row)

    async def get_items_needing_classification(self, limit: int = 100) -> list[Item]:
        """Get items without classifications."""
        rows = await self.db.fetch_all(
            """
            SELECT i.* FROM items i
            WHERE i.id NOT IN (SELECT item_id FROM classifications)
            ORDER BY i.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_item(row) for row in rows]

    async def count_classifications(self, domain: Optional[str] = None) -> int:
        """Count classification records."""
        if domain:
            row = await self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM classifications WHERE domain = ?", (domain,)
            )
        else:
            row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM classifications")
        return row["cnt"] if row else 0

    def _row_to_classification(self, row) -> Classification:
        """Convert a database row to a Classification model."""
        return Classification(
            id=row["id"],
            item_id=row["item_id"],
            domain=row["domain"],
            domain_secondary=row["domain_secondary"],
            content_type=row["content_type"],
            summary=row["summary"],
            tags_json=json.loads(row["tags_json"]) if row["tags_json"] else None,
            confidence=row["confidence"],
            model_name=row["model_name"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ============================================
    # Embeddings
    # ============================================

    async def insert_embedding(self, emb: Embedding) -> Embedding:
        """Insert a new embedding record."""
        await self.db.execute(
            """
            INSERT INTO embeddings (
                id, item_id, embedding_model, dimensions,
                embedding_json, source_text_hash, token_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                emb.id, emb.item_id, emb.embedding_model, emb.dimensions,
                json.dumps(emb.embedding_json) if emb.embedding_json else None,
                emb.source_text_hash, emb.token_count, emb.created_at,
            ),
        )
        await self.db.commit()
        return emb

    async def upsert_embedding(self, emb: Embedding) -> Embedding:
        """Insert or update an embedding record."""
        await self.db.execute(
            """
            INSERT INTO embeddings (
                id, item_id, embedding_model, dimensions,
                embedding_json, source_text_hash, token_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, embedding_model) DO UPDATE SET
                dimensions = excluded.dimensions,
                embedding_json = excluded.embedding_json,
                source_text_hash = excluded.source_text_hash,
                token_count = excluded.token_count
            """,
            (
                emb.id, emb.item_id, emb.embedding_model, emb.dimensions,
                json.dumps(emb.embedding_json) if emb.embedding_json else None,
                emb.source_text_hash, emb.token_count, emb.created_at,
            ),
        )
        await self.db.commit()
        return emb

    async def get_embedding_for_item(self, item_id: str, model: str = "text-embedding-3-small") -> Optional[Embedding]:
        """Get embedding for an item."""
        row = await self.db.fetch_one(
            "SELECT * FROM embeddings WHERE item_id = ? AND embedding_model = ?",
            (item_id, model),
        )
        if not row:
            return None
        return self._row_to_embedding(row)

    async def get_all_embeddings(self, model: str = "text-embedding-3-small") -> list[Embedding]:
        """Get all embeddings for a model."""
        rows = await self.db.fetch_all(
            "SELECT * FROM embeddings WHERE embedding_model = ?", (model,)
        )
        return [self._row_to_embedding(row) for row in rows]

    async def get_items_needing_embedding(self, model: str = "text-embedding-3-small", limit: int = 500) -> list[Item]:
        """Get items without embeddings for the given model."""
        rows = await self.db.fetch_all(
            """
            SELECT i.* FROM items i
            WHERE i.id NOT IN (
                SELECT item_id FROM embeddings WHERE embedding_model = ?
            )
            ORDER BY i.created_at DESC
            LIMIT ?
            """,
            (model, limit),
        )
        return [self._row_to_item(row) for row in rows]

    async def count_embeddings(self, model: Optional[str] = None) -> int:
        """Count embedding records."""
        if model:
            row = await self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM embeddings WHERE embedding_model = ?", (model,)
            )
        else:
            row = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM embeddings")
        return row["cnt"] if row else 0

    def _row_to_embedding(self, row) -> Embedding:
        """Convert a database row to an Embedding model."""
        return Embedding(
            id=row["id"],
            item_id=row["item_id"],
            embedding_model=row["embedding_model"],
            dimensions=row["dimensions"],
            embedding_json=json.loads(row["embedding_json"]) if row["embedding_json"] else None,
            source_text_hash=row["source_text_hash"],
            token_count=row["token_count"],
            created_at=row["created_at"],
        )


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
