"""Database management for IdeaBank."""

import aiosqlite
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "4.0"  # Added linked_content, classifications, embeddings

PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
"""

SCHEMA = """
-- ============================================
-- ITEMS: Canonical objects
-- ============================================
CREATE TABLE IF NOT EXISTS items (
    item_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    canonical_uri TEXT UNIQUE,
    canonicalizer_version TEXT DEFAULT '1',

    title TEXT,
    author_name TEXT,
    author_handle TEXT,
    author_uri TEXT,

    created_at TEXT,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    metadata_json TEXT,

    CHECK (json_valid(metadata_json) OR metadata_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_items_id ON items(id);
CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
CREATE INDEX IF NOT EXISTS idx_items_uri ON items(canonical_uri);
CREATE INDEX IF NOT EXISTS idx_items_created ON items(created_at);

-- ============================================
-- EVENTS: Activity log (append-only)
-- ============================================
CREATE TABLE IF NOT EXISTS events (
    event_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,

    item_id TEXT NOT NULL REFERENCES items(id),

    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,

    context_json TEXT,
    dedupe_key TEXT,

    CHECK (json_valid(context_json) OR context_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_events_item ON events(item_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_events_dedupe
ON events(source, event_type, dedupe_key)
WHERE dedupe_key IS NOT NULL;

-- ============================================
-- SOURCE_STATE: Watermarks for incremental updates
-- ============================================
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    last_checked_at TEXT,
    last_ingested_at TEXT,
    watermark_occurred_at TEXT,
    last_file_hash TEXT,
    state_json TEXT,

    CHECK (json_valid(state_json) OR state_json IS NULL)
);

-- ============================================
-- REPRESENTATIONS: Raw and processed forms
-- ============================================
CREATE TABLE IF NOT EXISTS representations (
    rep_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL REFERENCES items(id),

    rep_type TEXT NOT NULL,

    content_text TEXT,
    content_json TEXT,

    source_rep_id TEXT REFERENCES representations(id),
    processor TEXT,
    processor_version TEXT,

    content_hash TEXT,

    created_at TEXT NOT NULL,

    CHECK (json_valid(content_json) OR content_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_reps_id ON representations(id);
CREATE INDEX IF NOT EXISTS idx_reps_item ON representations(item_id);
CREATE INDEX IF NOT EXISTS idx_reps_type ON representations(rep_type);

-- ============================================
-- ANNOTATIONS: Your notes, tags, ratings
-- ============================================
CREATE TABLE IF NOT EXISTS annotations (
    annotation_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(id),

    note_text TEXT,
    tags_json TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5 OR rating IS NULL),
    stage TEXT DEFAULT 'inbox',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    obsidian_path TEXT,
    obsidian_hash TEXT,
    exported_at TEXT,

    CHECK (json_valid(tags_json) OR tags_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_annotations_id ON annotations(id);
CREATE INDEX IF NOT EXISTS idx_annotations_item ON annotations(item_id);
CREATE INDEX IF NOT EXISTS idx_annotations_stage ON annotations(stage);

CREATE INDEX IF NOT EXISTS idx_annotations_export
ON annotations(updated_at, exported_at);

-- ============================================
-- TOPICS: Categories with detection patterns
-- ============================================
CREATE TABLE IF NOT EXISTS topics (
    topic_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    parent_id TEXT REFERENCES topics(id),

    patterns_json TEXT,
    accounts_json TEXT,

    color TEXT,

    created_at TEXT NOT NULL,

    CHECK (json_valid(patterns_json) OR patterns_json IS NULL),
    CHECK (json_valid(accounts_json) OR accounts_json IS NULL)
);

-- ============================================
-- ITEM_TOPICS: Many-to-many
-- ============================================
CREATE TABLE IF NOT EXISTS item_topics (
    item_id TEXT NOT NULL REFERENCES items(id),
    topic_id TEXT NOT NULL REFERENCES topics(id),

    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'pattern',

    created_at TEXT NOT NULL,

    PRIMARY KEY (item_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_item_topics_topic ON item_topics(topic_id);

-- ============================================
-- CONVERSATIONS: First-class chat logs
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(id),

    platform TEXT NOT NULL,
    model TEXT,
    title TEXT,

    started_at TEXT,
    ended_at TEXT,

    summary_text TEXT,
    key_insights_json TEXT,

    CHECK (json_valid(key_insights_json) OR key_insights_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_conversations_id ON conversations(id);
CREATE INDEX IF NOT EXISTS idx_conversations_item ON conversations(item_id);
CREATE INDEX IF NOT EXISTS idx_conversations_platform ON conversations(platform);

-- ============================================
-- MESSAGES: Conversation messages
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    message_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),

    role TEXT NOT NULL,
    content_text TEXT,
    content_json TEXT,

    message_index INTEGER NOT NULL,

    created_at TEXT NOT NULL,

    CHECK (json_valid(content_json) OR content_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_conv_index
ON messages(conversation_id, message_index);

-- ============================================
-- RAW_INGESTIONS: Track imports
-- ============================================
CREATE TABLE IF NOT EXISTS raw_ingestions (
    ingestion_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,

    record_count INTEGER,
    schema_version TEXT,

    imported_at TEXT NOT NULL,

    UNIQUE(file_hash)
);

-- ============================================
-- LINKED_CONTENT: Extracted URL content
-- ============================================
CREATE TABLE IF NOT EXISTS linked_content (
    lc_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    source_item_id TEXT NOT NULL REFERENCES items(id),
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    domain TEXT,
    content_type TEXT,
    title TEXT,
    extracted_text TEXT,
    word_count INTEGER DEFAULT 0,
    extractor TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_item_id, canonical_url)
);

CREATE INDEX IF NOT EXISTS idx_lc_source_item ON linked_content(source_item_id);
CREATE INDEX IF NOT EXISTS idx_lc_status ON linked_content(status);
CREATE INDEX IF NOT EXISTS idx_lc_domain ON linked_content(domain);

-- ============================================
-- CLASSIFICATIONS: LLM classification results
-- ============================================
CREATE TABLE IF NOT EXISTS classifications (
    cls_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(id),
    domain TEXT NOT NULL,
    domain_secondary TEXT,
    content_type TEXT NOT NULL,
    summary TEXT,
    tags_json TEXT,
    confidence REAL DEFAULT 1.0,
    model_name TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (json_valid(tags_json) OR tags_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_cls_item ON classifications(item_id);
CREATE INDEX IF NOT EXISTS idx_cls_domain ON classifications(domain);
CREATE INDEX IF NOT EXISTS idx_cls_content_type ON classifications(content_type);

-- ============================================
-- EMBEDDINGS: Vector embeddings
-- ============================================
CREATE TABLE IF NOT EXISTS embeddings (
    emb_rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    item_id TEXT NOT NULL REFERENCES items(id),
    embedding_model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding_json TEXT,
    source_text_hash TEXT,
    token_count INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(item_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_emb_item ON embeddings(item_id);
CREATE INDEX IF NOT EXISTS idx_emb_model ON embeddings(embedding_model);

-- ============================================
-- SCHEMA_MIGRATIONS: Track applied migrations
-- ============================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

FTS_SCHEMA = """
-- ============================================
-- FTS5: Full-text search
-- ============================================

-- Items FTS
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title,
    author_name,
    content='items',
    content_rowid='item_rowid',
    tokenize='porter unicode61'
);

-- Representations FTS
CREATE VIRTUAL TABLE IF NOT EXISTS representations_fts USING fts5(
    content_text,
    content='representations',
    content_rowid='rep_rowid',
    tokenize='porter unicode61'
);

-- Annotations FTS
CREATE VIRTUAL TABLE IF NOT EXISTS annotations_fts USING fts5(
    note_text,
    content='annotations',
    content_rowid='annotation_rowid',
    tokenize='porter unicode61'
);

-- Messages FTS
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content_text,
    content='messages',
    content_rowid='message_rowid',
    tokenize='porter unicode61'
);

-- Linked Content FTS
CREATE VIRTUAL TABLE IF NOT EXISTS linked_content_fts USING fts5(
    title,
    extracted_text,
    content='linked_content',
    content_rowid='lc_rowid',
    tokenize='porter unicode61'
);
"""

FTS_TRIGGERS = """
-- Items FTS triggers
CREATE TRIGGER IF NOT EXISTS items_fts_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, author_name)
    VALUES (new.item_rowid, new.title, new.author_name);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, author_name)
    VALUES('delete', old.item_rowid, old.title, old.author_name);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, author_name)
    VALUES('delete', old.item_rowid, old.title, old.author_name);
    INSERT INTO items_fts(rowid, title, author_name)
    VALUES (new.item_rowid, new.title, new.author_name);
END;

-- Representations FTS triggers
CREATE TRIGGER IF NOT EXISTS reps_fts_ai AFTER INSERT ON representations
WHEN new.content_text IS NOT NULL BEGIN
    INSERT INTO representations_fts(rowid, content_text)
    VALUES (new.rep_rowid, new.content_text);
END;

CREATE TRIGGER IF NOT EXISTS reps_fts_ad AFTER DELETE ON representations BEGIN
    INSERT INTO representations_fts(representations_fts, rowid)
    VALUES('delete', old.rep_rowid);
END;

CREATE TRIGGER IF NOT EXISTS reps_fts_au AFTER UPDATE ON representations BEGIN
    INSERT INTO representations_fts(representations_fts, rowid)
    VALUES('delete', old.rep_rowid);
    INSERT INTO representations_fts(rowid, content_text)
    SELECT new.rep_rowid, new.content_text
    WHERE new.content_text IS NOT NULL;
END;

-- Annotations FTS triggers
CREATE TRIGGER IF NOT EXISTS annotations_fts_ai AFTER INSERT ON annotations
WHEN new.note_text IS NOT NULL BEGIN
    INSERT INTO annotations_fts(rowid, note_text)
    VALUES (new.annotation_rowid, new.note_text);
END;

CREATE TRIGGER IF NOT EXISTS annotations_fts_ad AFTER DELETE ON annotations BEGIN
    INSERT INTO annotations_fts(annotations_fts, rowid)
    VALUES('delete', old.annotation_rowid);
END;

CREATE TRIGGER IF NOT EXISTS annotations_fts_au AFTER UPDATE ON annotations BEGIN
    INSERT INTO annotations_fts(annotations_fts, rowid)
    VALUES('delete', old.annotation_rowid);
    INSERT INTO annotations_fts(rowid, note_text)
    SELECT new.annotation_rowid, new.note_text
    WHERE new.note_text IS NOT NULL;
END;

-- Messages FTS triggers
CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages
WHEN new.content_text IS NOT NULL BEGIN
    INSERT INTO messages_fts(rowid, content_text)
    VALUES (new.message_rowid, new.content_text);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid)
    VALUES('delete', old.message_rowid);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid)
    VALUES('delete', old.message_rowid);
    INSERT INTO messages_fts(rowid, content_text)
    SELECT new.message_rowid, new.content_text
    WHERE new.content_text IS NOT NULL;
END;

-- Linked Content FTS triggers
CREATE TRIGGER IF NOT EXISTS lc_fts_ai AFTER INSERT ON linked_content
WHEN new.extracted_text IS NOT NULL BEGIN
    INSERT INTO linked_content_fts(rowid, title, extracted_text)
    VALUES (new.lc_rowid, new.title, new.extracted_text);
END;

CREATE TRIGGER IF NOT EXISTS lc_fts_ad AFTER DELETE ON linked_content BEGIN
    INSERT INTO linked_content_fts(linked_content_fts, rowid)
    VALUES('delete', old.lc_rowid);
END;

CREATE TRIGGER IF NOT EXISTS lc_fts_au AFTER UPDATE ON linked_content BEGIN
    INSERT INTO linked_content_fts(linked_content_fts, rowid)
    VALUES('delete', old.lc_rowid);
    INSERT INTO linked_content_fts(rowid, title, extracted_text)
    SELECT new.lc_rowid, new.title, new.extracted_text
    WHERE new.extracted_text IS NOT NULL;
END;

-- ============================================
-- INTEGRITY TRIGGERS
-- ============================================

CREATE TRIGGER IF NOT EXISTS conversations_item_kind_check
BEFORE INSERT ON conversations
BEGIN
    SELECT CASE
        WHEN (SELECT kind FROM items WHERE id = new.item_id) != 'conversation'
        THEN RAISE(ABORT, 'items.kind must be conversation for conversations.item_id')
    END;
END;
"""


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to the database."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        # Apply PRAGMAs
        for pragma in PRAGMAS.strip().split("\n"):
            if pragma.strip():
                await self._conn.execute(pragma)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        return await self._conn.execute(sql, params)

    async def executemany(self, sql: str, params: list) -> aiosqlite.Cursor:
        """Execute a SQL statement with multiple parameter sets."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        return await self._conn.executemany(sql, params)

    async def executescript(self, sql: str) -> None:
        """Execute multiple SQL statements."""
        if not self._conn:
            raise RuntimeError("Database not connected")
        await self._conn.executescript(sql)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        """Fetch a single row."""
        cursor = await self.execute(sql, params)
        return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        """Fetch all rows."""
        cursor = await self.execute(sql, params)
        return await cursor.fetchall()

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn:
            await self._conn.commit()

    async def init_schema(self) -> None:
        """Initialize the database schema."""
        await self.executescript(SCHEMA)
        await self.executescript(FTS_SCHEMA)
        await self.executescript(FTS_TRIGGERS)
        # Try to load sqlite-vec for vector search
        await self._try_init_vec()
        # Record migration
        await self.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (SCHEMA_VERSION,),
        )
        await self.commit()

    async def _try_init_vec(self) -> None:
        """Try to initialize sqlite-vec virtual table. Graceful fallback if unavailable."""
        try:
            # Test if sqlite-vec extension is available
            await self.execute("SELECT vec_version()")
            await self.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_vec USING vec0(
                    item_id TEXT PRIMARY KEY,
                    embedding FLOAT[1536]
                );
            """)
            self._has_vec = True
        except Exception:
            self._has_vec = False

    @property
    def has_vec(self) -> bool:
        """Whether sqlite-vec is available."""
        return getattr(self, "_has_vec", False)

    async def get_schema_version(self) -> Optional[str]:
        """Get the current schema version."""
        try:
            row = await self.fetch_one(
                "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
            )
            return row["version"] if row else None
        except Exception:
            return None


async def get_database(db_path: Path) -> Database:
    """Get a connected database instance."""
    db = Database(db_path)
    await db.connect()
    return db


async def init_database(db_path: Path) -> Database:
    """Initialize and return a new database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await get_database(db_path)
    await db.init_schema()
    return db
