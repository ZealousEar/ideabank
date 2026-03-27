# IdeaBank — Complete Reference Documentation

> **For LLM agents**: This document is the single authoritative reference for the IdeaBank codebase. Query any section by heading. Every function signature, CLI flag, database column, enum value, and config option is documented here.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Pipeline Workflow](#pipeline-workflow)
- [Installation & Setup](#installation--setup)
- [CLI Command Reference](#cli-command-reference)
- [Database Schema (v4.0)](#database-schema-v40)
- [Pydantic Models](#pydantic-models)
- [Enums](#enums)
- [Configuration](#configuration)
- [Module: core/database.py](#module-coredatabasepy)
- [Module: core/repository.py](#module-corerepositorypy)
- [Module: extraction/](#module-extraction)
- [Module: classification/](#module-classification)
- [Module: embeddings/](#module-embeddings)
- [Module: export/obsidian.py](#module-exportobsidianpy)
- [Dependencies](#dependencies)
- [Cost Estimates](#cost-estimates)
- [File Map](#file-map)

---

## Architecture Overview

IdeaBank is an async-first Python CLI tool (`ib`) for ingesting, classifying, embedding, searching, and exporting bookmarked content (tweets, articles, conversations, videos) into an Obsidian vault.

```
┌──────────────────────────────────────────────────────────────┐
│                      DATA SOURCES                            │
│  Twitter bookmarks │ Chrome history │ YouTube │ Conversations│
└──────────┬───────────────────────────────────────────────────┘
           │  ib check / ib ingest
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    SQLite DATABASE (v4.0)                     │
│  items │ events │ representations │ annotations │ topics     │
│  conversations │ messages │ source_state │ raw_ingestions     │
│  linked_content │ classifications │ embeddings               │
│  + 5 FTS5 virtual tables │ + optional sqlite-vec             │
└──────────┬───────────────────────────────────────────────────┘
           │
           ├─── ib extract ───→ linked_content (articles, YouTube, GitHub, ArXiv)
           ├─── ib classify ──→ classifications (domain, content_type, summary, tags)
           ├─── ib embed ─────→ embeddings (1536d vectors via text-embedding-3-small)
           │
           ├─── ib search ────→ FTS5 full-text search
           ├─── ib semantic ──→ Vector similarity search
           ├─── ib hybrid ────→ FTS5 + semantic via Reciprocal Rank Fusion
           │
           └─── ib export ────→ Obsidian vault (markdown + YAML frontmatter)
```

**Key design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | Single SQLite file | Portable, zero-config, WAL mode for concurrency |
| Async | aiosqlite everywhere | Non-blocking I/O for batch operations |
| IDs | ULID with prefixes | Sortable, unique, type-identifiable (`item_`, `evt_`, `cls_`, etc.) |
| Embedding model | text-embedding-3-small (1536d) | $0.02/1M tokens, proven quality |
| Classification LLM | gpt-4.1-mini | $0.80/1M tokens, structured JSON output |
| Article extraction | trafilatura + httpx | Best Python extraction library + async HTTP |
| Vector storage | sqlite-vec with JSON fallback | Single-DB architecture; works without extension |
| Search fusion | Reciprocal Rank Fusion (k=60) | Proven method for combining ranked lists |
| Obsidian export | One-way, SQLite authoritative | No sync complexity; edit via CLI, render in Obsidian |

---

## Pipeline Workflow

The recommended order for processing items:

```
1. ib init                    # Create database + directories
2. ib check twitter           # Ingest Twitter bookmarks
3. ib check conversations     # Ingest AI conversations
4. ib extract --limit 100     # Extract linked content from URLs
5. ib classify --limit 100    # LLM classification (domain, type, summary, tags)
6. ib embed --limit 100       # Generate vector embeddings
7. ib export --vault ~/Vault  # Export to Obsidian
```

Each step is idempotent — re-running skips already-processed items (use `--force` to reprocess).

---

## Installation & Setup

### Dependencies

```bash
pip install -r src/ideabank/requirements.txt
```

### Environment Variables

| Variable | Required | Used By |
|----------|----------|---------|
| `OPENAI_API_KEY` | For classify/embed/semantic/hybrid | OpenAI SDK (auto-discovered) |

### Initialize

```bash
ib init                          # Default paths
ib init --vault ~/MyVault        # Custom vault path
```

Creates:
- `~/.ideabank/db/ideabank.db` — SQLite database
- `~/.ideabank/raw/` — Raw data files (twitter/, chrome/, youtube/, conversations/, brave/)
- `~/.ideabank/cache/` — Processing cache
- `~/.ideabank/config.yaml` — Configuration file

---

## CLI Command Reference

Entry point: `ib` (via `python -m ideabank.cli.main` or installed script)

### Data Ingestion

#### `ib init`
Initialize IdeaBank database and directories.

```
ib init [--vault PATH | -v PATH]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--vault`, `-v` | Path | None | Path to Obsidian vault |

#### `ib check <source>`
Check for new data from a source and ingest automatically.

```
ib check twitter
ib check conversations
```

| Argument | Values | Description |
|----------|--------|-------------|
| `source` | `twitter`, `conversations` | Data source to check |

#### `ib ingest <source> <file_path>`
Ingest a specific file.

```
ib ingest twitter ~/data/bookmarks.json
ib ingest conversation ~/chats/export.json --force
```

| Argument | Type | Description |
|----------|------|-------------|
| `source` | `twitter`, `conversation` | Source type |
| `file_path` | Path | File to ingest |
| `--force`, `-f` | Flag | Re-ingest even if file hash matches |

### Content Processing

#### `ib extract`
Extract content from URLs found in items (articles, YouTube transcripts, GitHub READMEs, ArXiv abstracts).

```
ib extract --limit 50 --concurrency 5
ib extract --force  # Re-extract all
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | int | 100 | Maximum items to process |
| `--concurrency`, `-c` | int | 3 | Concurrent HTTP requests |
| `--force`, `-f` | Flag | False | Re-extract already extracted URLs |

**What it does:**
1. Finds items with URLs in `metadata_json` or content text
2. Routes each URL to the appropriate extractor (ArXiv → YouTube → GitHub → Article)
3. Stores extracted text in `linked_content` table
4. Indexes extracted text in FTS5 for search

#### `ib classify`
Classify items using LLM (domain, content_type, summary, fine-grained tags).

```
ib classify --dry-run                    # Cost estimate only
ib classify --limit 50 --model gpt-4.1-mini
ib classify --force                      # Reclassify all
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | int | 100 | Maximum items to classify |
| `--model`, `-m` | str | `gpt-4.1-mini` | OpenAI model for classification |
| `--force`, `-f` | Flag | False | Reclassify already classified items |
| `--dry-run` | Flag | False | Estimate cost without classifying |

**What it does:**
1. Finds unclassified items (or all with `--force`)
2. Builds prompt with item text + linked content context
3. Calls OpenAI chat completions (JSON mode) for structured classification
4. Falls back to heuristic classification if LLM fails (confidence=0.5)
5. Stores result in `classifications` table

**Classification output fields:**
- `domain`: ai-ml, software-eng, finance-quant, research-academic, math-stats, career, general
- `content_type`: paper, repo, video, article, thread, tool, insight, tweet
- `summary`: One-sentence description
- `tags`: Fine-grained topic tags (list of strings)

#### `ib embed`
Generate vector embeddings for semantic search.

```
ib embed --dry-run        # Cost estimate
ib embed --limit 200
ib embed --force          # Re-embed all
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | int | 500 | Maximum items to embed |
| `--force`, `-f` | Flag | False | Re-embed already embedded items |
| `--dry-run` | Flag | False | Estimate cost without embedding |

**What it does:**
1. Builds embedding text from title + author + content + summary + linked text
2. Computes text hash — skips if unchanged (unless `--force`)
3. Calls OpenAI embeddings API in batches of 500
4. Stores 1536-dimensional vectors in `embeddings` table
5. Optionally indexes in sqlite-vec for fast similarity search

### Search

#### `ib search <query>`
Full-text search using FTS5 indexes.

```
ib search "attention mechanism" --limit 10
ib search "pytorch" --kind tweet
```

| Argument/Flag | Type | Default | Description |
|---------------|------|---------|-------------|
| `query` | str | required | Search query |
| `--limit`, `-n` | int | 20 | Maximum results |
| `--kind`, `-k` | str | None | Filter: tweet, article, video, conversation |

#### `ib semantic <query>`
Semantic similarity search using embeddings.

```
ib semantic "how transformers work" --limit 10
ib semantic "portfolio optimization" --kind article
```

| Argument/Flag | Type | Default | Description |
|---------------|------|---------|-------------|
| `query` | str | required | Natural language query |
| `--limit`, `-n` | int | 20 | Maximum results |
| `--kind`, `-k` | str | None | Filter by item kind |

**Requires:** Embeddings generated via `ib embed`. Uses sqlite-vec if available, otherwise JSON fallback (slower for large datasets).

#### `ib hybrid <query>`
Combined FTS5 + semantic search using Reciprocal Rank Fusion.

```
ib hybrid "reinforcement learning" --limit 20
ib hybrid "async Python" --fts-weight 0.6
```

| Argument/Flag | Type | Default | Description |
|---------------|------|---------|-------------|
| `query` | str | required | Search query |
| `--limit`, `-n` | int | 20 | Maximum results |
| `--fts-weight` | float | 0.4 | Weight for FTS5 results (0.0–1.0). Semantic weight = 1 - fts_weight |

**RRF formula:** `score = Σ (weight / (k + rank))` where k=60. FTS5 and semantic searches run in parallel via `asyncio.gather`.

### Organization

#### `ib inbox`
Show items in the inbox stage.

```
ib inbox --limit 50
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | int | 20 | Maximum items to show |

#### `ib stage <item_id> <new_stage>`
Change an item's processing stage.

```
ib stage item_01HX... reviewed
ib stage item_01HX... archived
```

| Argument | Values | Description |
|----------|--------|-------------|
| `item_id` | str | Item ID (ULID with `item_` prefix) |
| `new_stage` | `inbox`, `reviewed`, `exploring`, `reference`, `archived` | Target stage |

#### `ib tag <item_id> <tags...>`
Add tags to an item.

```
ib tag item_01HX... python machine-learning
```

| Argument | Type | Description |
|----------|------|-------------|
| `item_id` | str | Item ID |
| `tags` | str... | One or more tags (variadic) |

#### `ib categorize`
Auto-categorize uncategorized items using topic patterns.

```
ib categorize --limit 200
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | int | 100 | Maximum items to categorize |

### Monitoring

#### `ib status`
Show status of all data sources (last check, last ingest, watermark timestamps).

#### `ib stats`
Show detailed statistics including:
- Total items by kind (tweet, article, video, conversation)
- Total events by source
- Total representations, annotations, topics
- Linked content counts by status (pending, success, failed, skipped)
- Classifications by domain
- Total embeddings
- Items in each stage (inbox, reviewed, exploring, reference, archived)

### Export

#### `ib export`
Export items to Obsidian vault as markdown files.

```
ib export --vault ~/MyVault
ib export --kind tweet --limit 50
ib export --all  # Export all, not just changed
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--vault`, `-v` | Path | From config | Path to Obsidian vault |
| `--kind`, `-k` | str | None | Filter by item kind |
| `--limit`, `-n` | int | None | Maximum items to export |
| `--all`, `-a` | Flag | False | Export all items (not just changed since last export) |

**Output structure:**
```
<vault>/IdeaBank/
  tweets/          # Tweet bookmark files
  conversations/   # AI conversation files
  articles/        # Article bookmark files
  other/           # Everything else
```

**Filename format:** `YYYY-MM-DD-slug-shortid.md`

---

## Database Schema (v4.0)

Database location: `~/.ideabank/db/ideabank.db`

SQLite pragmas: WAL journal mode, NORMAL synchronous, foreign keys ON, 5000ms busy timeout.

### Table: `items`

Primary content table. Every ingested piece of content gets one row.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | Auto-increment row ID |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `item_` prefix |
| `kind` | TEXT | NOT NULL | Item type: tweet, video, article, page, conversation |
| `canonical_uri` | TEXT | UNIQUE | Deduplicated URL/identifier |
| `canonicalizer_version` | TEXT | DEFAULT '1' | Version of URI normalization |
| `title` | TEXT | | Item title |
| `author_name` | TEXT | | Author display name |
| `author_handle` | TEXT | | Author username/handle |
| `author_uri` | TEXT | | Author profile URL |
| `created_at` | TEXT | | Original creation timestamp (ISO 8601) |
| `first_seen_at` | TEXT | NOT NULL | When IdeaBank first saw this item |
| `updated_at` | TEXT | NOT NULL | Last modification timestamp |
| `metadata_json` | TEXT | | JSON blob of source-specific metadata |

### Table: `events`

Immutable audit log of all actions on items.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `evt_` prefix |
| `event_type` | TEXT | NOT NULL | bookmarked, visited, liked, saved, annotated, reviewed, stage_set, tag_added, tag_removed |
| `item_id` | TEXT | NOT NULL REFERENCES items(id) | |
| `occurred_at` | TEXT | NOT NULL | When the event happened |
| `source` | TEXT | NOT NULL | Origin system (twitter, chrome, manual, etc.) |
| `context_json` | TEXT | | Extra event context as JSON |
| `dedupe_key` | TEXT | | For preventing duplicate events |

**Unique constraint:** `(source, event_type, dedupe_key)`

### Table: `representations`

Different text representations of an item (raw JSON, extracted text, summaries, chunks).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `rep_` prefix |
| `item_id` | TEXT | NOT NULL REFERENCES items(id) | |
| `rep_type` | TEXT | NOT NULL | raw_json, extracted_text, summary, chunk, transcript |
| `content_text` | TEXT | | Text content |
| `content_json` | TEXT | | JSON content |
| `source_rep_id` | TEXT | | Parent representation (for derived representations) |
| `processor` | TEXT | | What generated this (e.g., "trafilatura") |
| `processor_version` | TEXT | | Version of processor |
| `content_hash` | TEXT | | SHA256 hash for deduplication |
| `created_at` | TEXT | NOT NULL | |

**Unique constraint:** `(item_id, rep_type, content_hash)`

### Table: `annotations`

User annotations on items (notes, tags, ratings, stage).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `ann_` prefix |
| `item_id` | TEXT | NOT NULL UNIQUE REFERENCES items(id) | One annotation per item |
| `note_text` | TEXT | | User notes |
| `tags_json` | TEXT | | JSON array of user tags |
| `rating` | INTEGER | | 1–5 rating |
| `stage` | TEXT | DEFAULT 'inbox' | inbox, reviewed, exploring, reference, archived |
| `created_at` | TEXT | NOT NULL | |
| `updated_at` | TEXT | NOT NULL | |
| `obsidian_path` | TEXT | | Relative path in Obsidian vault |
| `obsidian_hash` | TEXT | | Hash of last exported markdown |
| `exported_at` | TEXT | | Last export timestamp |

### Table: `topics`

Topic/category definitions for organizing items.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `topic_` prefix |
| `name` | TEXT | NOT NULL | Display name |
| `slug` | TEXT | NOT NULL UNIQUE | URL-safe identifier |
| `parent_id` | TEXT | | Parent topic for hierarchy |
| `patterns_json` | TEXT | | JSON array of matching patterns |
| `accounts_json` | TEXT | | JSON array of associated accounts |
| `color` | TEXT | | Display color |
| `created_at` | TEXT | NOT NULL | |

### Table: `item_topics`

Many-to-many relationship between items and topics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `item_id` | TEXT | NOT NULL REFERENCES items(id) | |
| `topic_id` | TEXT | NOT NULL REFERENCES topics(id) | |
| `confidence` | REAL | DEFAULT 1.0 | Match confidence (0.0–1.0) |
| `source` | TEXT | DEFAULT 'pattern' | How the topic was assigned |
| `created_at` | TEXT | NOT NULL | |

**Primary key:** `(item_id, topic_id)`

### Table: `conversations`

AI conversation metadata (linked to an item).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `conv_` prefix |
| `item_id` | TEXT | NOT NULL UNIQUE REFERENCES items(id) | |
| `platform` | TEXT | NOT NULL | chatgpt, claude, gemini, etc. |
| `model` | TEXT | | Model name used |
| `title` | TEXT | | Conversation title |
| `started_at` | TEXT | | |
| `ended_at` | TEXT | | |
| `summary_text` | TEXT | | Conversation summary |
| `key_insights_json` | TEXT | | JSON array of key insights |

### Table: `messages`

Individual messages within conversations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `msg_` prefix |
| `conversation_id` | TEXT | NOT NULL REFERENCES conversations(id) | |
| `role` | TEXT | NOT NULL | user, assistant, system |
| `content_text` | TEXT | | Message text |
| `content_json` | TEXT | | Structured content (for tool calls, etc.) |
| `message_index` | INTEGER | NOT NULL | Order within conversation |
| `created_at` | TEXT | NOT NULL | |

### Table: `linked_content`

Extracted content from URLs found in items.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `lc_rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `lc_` prefix |
| `source_item_id` | TEXT | NOT NULL REFERENCES items(id) | Parent item |
| `url` | TEXT | NOT NULL | Original URL (may be shortened) |
| `canonical_url` | TEXT | NOT NULL | Resolved/canonical URL |
| `domain` | TEXT | | URL domain |
| `content_type` | TEXT | | article, transcript, readme, abstract |
| `title` | TEXT | | Extracted title |
| `extracted_text` | TEXT | | Full extracted text content |
| `word_count` | INTEGER | DEFAULT 0 | |
| `extractor` | TEXT | | trafilatura, youtube_transcript, github_api, arxiv_api |
| `status` | TEXT | DEFAULT 'pending' | pending, success, failed, skipped |
| `error_message` | TEXT | | Error details if failed |
| `content_hash` | TEXT | | SHA256 of extracted text |
| `created_at` | TEXT | NOT NULL | |
| `updated_at` | TEXT | NOT NULL | |

**Unique constraint:** `(source_item_id, canonical_url)`

### Table: `classifications`

LLM-generated classifications for items.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `cls_rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `cls_` prefix |
| `item_id` | TEXT | NOT NULL UNIQUE REFERENCES items(id) | One classification per item |
| `domain` | TEXT | NOT NULL | ai-ml, software-eng, finance-quant, research-academic, math-stats, career, general |
| `domain_secondary` | TEXT | | Optional secondary domain |
| `content_type` | TEXT | NOT NULL | paper, repo, video, article, thread, tool, insight, tweet |
| `summary` | TEXT | | One-sentence summary |
| `tags_json` | TEXT | | JSON array of fine-grained tags |
| `confidence` | REAL | DEFAULT 1.0 | LLM=1.0, heuristic fallback=0.5 |
| `model_name` | TEXT | | gpt-4.1-mini (or other) |
| `content_hash` | TEXT | | Hash of input text (for change detection) |
| `created_at` | TEXT | NOT NULL | |
| `updated_at` | TEXT | NOT NULL | |

### Table: `embeddings`

Vector embeddings for semantic search.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `emb_rowid` | INTEGER | PRIMARY KEY | |
| `id` | TEXT | NOT NULL UNIQUE | ULID with `emb_` prefix |
| `item_id` | TEXT | NOT NULL REFERENCES items(id) | |
| `embedding_model` | TEXT | NOT NULL | text-embedding-3-small |
| `dimensions` | INTEGER | NOT NULL | 1536 |
| `embedding_json` | TEXT | | JSON array of floats (fallback storage) |
| `source_text_hash` | TEXT | | Hash of input text (skip if unchanged) |
| `token_count` | INTEGER | | Tokens consumed |
| `created_at` | TEXT | NOT NULL | |

**Unique constraint:** `(item_id, embedding_model)`

### Table: `embeddings_vec` (optional, sqlite-vec)

```sql
CREATE VIRTUAL TABLE embeddings_vec USING vec0(
    item_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]
);
```

Only created if sqlite-vec extension loads successfully. If unavailable, search falls back to in-memory JSON cosine similarity.

### FTS5 Virtual Tables

| Table | Indexed Columns | Source Table |
|-------|----------------|-------------|
| `items_fts` | title, author_name | items |
| `representations_fts` | content_text | representations |
| `annotations_fts` | note_text | annotations |
| `messages_fts` | content_text | messages |
| `linked_content_fts` | title, extracted_text | linked_content |

All FTS5 tables have auto-sync triggers (INSERT, UPDATE, DELETE) on their source tables.

### Table: `schema_migrations`

| Column | Type | Description |
|--------|------|-------------|
| `version` | TEXT | Schema version string |
| `applied_at` | TEXT | Migration timestamp |

### Table: `source_state`

| Column | Type | Description |
|--------|------|-------------|
| `source` | TEXT | PRIMARY KEY, source name |
| `last_checked_at` | TEXT | |
| `last_ingested_at` | TEXT | |
| `watermark_occurred_at` | TEXT | High-water mark for incremental ingestion |
| `last_file_hash` | TEXT | |
| `state_json` | TEXT | Source-specific state |

### Table: `raw_ingestions`

| Column | Type | Description |
|--------|------|-------------|
| `rowid` | INTEGER | PRIMARY KEY |
| `id` | TEXT | NOT NULL UNIQUE, ULID with `ing_` prefix |
| `source` | TEXT | NOT NULL |
| `file_path` | TEXT | NOT NULL |
| `file_hash` | TEXT | NOT NULL UNIQUE |
| `record_count` | INTEGER | |
| `schema_version` | TEXT | |
| `imported_at` | TEXT | NOT NULL |

---

## Pydantic Models

All models are in `src/ideabank/core/models.py`. IDs are generated via `generate_id(prefix)` using ULID.

### Item

```python
class Item(BaseModel):
    id: str                              # generate_id("item")
    kind: ItemKind                       # tweet, video, article, page, conversation
    canonical_uri: Optional[str]         # Deduplicated URL
    canonicalizer_version: str = "1"
    title: Optional[str]
    author_name: Optional[str]
    author_handle: Optional[str]
    author_uri: Optional[str]
    created_at: Optional[str]            # Original creation time
    first_seen_at: str                   # now_iso()
    updated_at: str                      # now_iso()
    metadata_json: Optional[dict]        # Source-specific metadata
```

### Event

```python
class Event(BaseModel):
    id: str                              # generate_id("evt")
    event_type: EventType                # bookmarked, visited, liked, saved, ...
    item_id: str
    occurred_at: str                     # now_iso()
    source: str                          # twitter, chrome, manual, etc.
    context_json: Optional[dict]
    dedupe_key: Optional[str]
```

### Representation

```python
class Representation(BaseModel):
    id: str                              # generate_id("rep")
    item_id: str
    rep_type: RepresentationType         # raw_json, extracted_text, summary, chunk, transcript
    content_text: Optional[str]
    content_json: Optional[dict]
    source_rep_id: Optional[str]         # Parent representation
    processor: Optional[str]
    processor_version: Optional[str]
    content_hash: Optional[str]
    created_at: str                      # now_iso()
```

### Annotation

```python
class Annotation(BaseModel):
    id: str                              # generate_id("ann")
    item_id: str
    note_text: Optional[str]
    tags_json: Optional[list[str]]
    rating: Optional[int]                # Field(ge=1, le=5)
    stage: Stage = Stage.INBOX           # inbox, reviewed, exploring, reference, archived
    created_at: str                      # now_iso()
    updated_at: str                      # now_iso()
    obsidian_path: Optional[str]         # Relative path in vault
    obsidian_hash: Optional[str]         # Hash of exported markdown
    exported_at: Optional[str]           # Last export time
```

### Topic

```python
class Topic(BaseModel):
    id: str                              # generate_id("topic")
    name: str
    slug: str                            # URL-safe identifier
    parent_id: Optional[str]
    patterns_json: Optional[list[str]]   # Matching patterns
    accounts_json: Optional[list[str]]   # Associated accounts
    color: Optional[str]
    created_at: str                      # now_iso()
```

### ItemTopic

```python
class ItemTopic(BaseModel):
    item_id: str
    topic_id: str
    confidence: float = 1.0
    source: str = "pattern"
    created_at: str                      # now_iso()
```

### Conversation

```python
class Conversation(BaseModel):
    id: str                              # generate_id("conv")
    item_id: str
    platform: str                        # chatgpt, claude, gemini
    model: Optional[str]
    title: Optional[str]
    started_at: Optional[str]
    ended_at: Optional[str]
    summary_text: Optional[str]
    key_insights_json: Optional[list[str]]
```

### Message

```python
class Message(BaseModel):
    id: str                              # generate_id("msg")
    conversation_id: str
    role: str                            # user, assistant, system
    content_text: Optional[str]
    content_json: Optional[dict]
    message_index: int
    created_at: str                      # now_iso()
```

### SourceState

```python
class SourceState(BaseModel):
    source: str                          # Primary key
    last_checked_at: Optional[str]
    last_ingested_at: Optional[str]
    watermark_occurred_at: Optional[str]
    last_file_hash: Optional[str]
    state_json: Optional[dict]
```

### RawIngestion

```python
class RawIngestion(BaseModel):
    id: str                              # generate_id("ing")
    source: str
    file_path: str
    file_hash: str                       # SHA256
    record_count: Optional[int]
    schema_version: Optional[str]
    imported_at: str                     # now_iso()
```

### LinkedContent

```python
class LinkedContent(BaseModel):
    id: str                              # generate_id("lc")
    source_item_id: str                  # Parent item
    url: str                             # Original URL
    canonical_url: str                   # Resolved URL
    domain: Optional[str]
    content_type: Optional[str]          # article, transcript, readme, abstract
    title: Optional[str]
    extracted_text: Optional[str]
    word_count: int = 0
    extractor: Optional[str]             # trafilatura, youtube_transcript, github_api, arxiv_api
    status: ExtractionStatus = PENDING   # pending, success, failed, skipped
    error_message: Optional[str]
    content_hash: Optional[str]
    created_at: str                      # now_iso()
    updated_at: str                      # now_iso()
```

### Classification

```python
class Classification(BaseModel):
    id: str                              # generate_id("cls")
    item_id: str
    domain: DomainTag                    # ai-ml, software-eng, finance-quant, ...
    domain_secondary: Optional[str]
    content_type: ContentType            # paper, repo, video, article, thread, ...
    summary: Optional[str]               # One-sentence summary
    tags_json: Optional[list[str]]       # Fine-grained tags
    confidence: float = 1.0              # LLM=1.0, heuristic=0.5
    model_name: Optional[str]            # gpt-4.1-mini
    content_hash: Optional[str]          # Hash of classified text
    created_at: str                      # now_iso()
    updated_at: str                      # now_iso()
```

### Embedding

```python
class Embedding(BaseModel):
    id: str                              # generate_id("emb")
    item_id: str
    embedding_model: str = "text-embedding-3-small"
    dimensions: int = 1536
    embedding_json: Optional[list[float]]  # 1536 floats
    source_text_hash: Optional[str]        # Skip re-embedding if unchanged
    token_count: Optional[int]
    created_at: str                        # now_iso()
```

---

## Enums

All enums are `str` enums (inherit from both `str` and `Enum`), so their `.value` is the string itself.

### ItemKind
| Value | String |
|-------|--------|
| `TWEET` | `"tweet"` |
| `VIDEO` | `"video"` |
| `ARTICLE` | `"article"` |
| `PAGE` | `"page"` |
| `CONVERSATION` | `"conversation"` |

### EventType
| Value | String |
|-------|--------|
| `BOOKMARKED` | `"bookmarked"` |
| `VISITED` | `"visited"` |
| `LIKED` | `"liked"` |
| `SAVED` | `"saved"` |
| `ANNOTATED` | `"annotated"` |
| `REVIEWED` | `"reviewed"` |
| `STAGE_SET` | `"stage_set"` |
| `TAG_ADDED` | `"tag_added"` |
| `TAG_REMOVED` | `"tag_removed"` |

### Stage
| Value | String | Description |
|-------|--------|-------------|
| `INBOX` | `"inbox"` | Newly ingested, unreviewed |
| `REVIEWED` | `"reviewed"` | Seen but not deeply explored |
| `EXPLORING` | `"exploring"` | Actively studying |
| `REFERENCE` | `"reference"` | Kept as long-term reference |
| `ARCHIVED` | `"archived"` | No longer actively useful |

### RepresentationType
| Value | String |
|-------|--------|
| `RAW_JSON` | `"raw_json"` |
| `EXTRACTED_TEXT` | `"extracted_text"` |
| `SUMMARY` | `"summary"` |
| `CHUNK` | `"chunk"` |
| `TRANSCRIPT` | `"transcript"` |

### ExtractionStatus
| Value | String | Description |
|-------|--------|-------------|
| `PENDING` | `"pending"` | Not yet attempted |
| `SUCCESS` | `"success"` | Extraction succeeded |
| `FAILED` | `"failed"` | Extraction failed (error stored) |
| `SKIPPED` | `"skipped"` | Deliberately skipped (e.g., social media URL) |

### DomainTag
| Value | String | Description |
|-------|--------|-------------|
| `AI_ML` | `"ai-ml"` | AI, machine learning, deep learning, NLP, LLMs |
| `SOFTWARE_ENG` | `"software-eng"` | Programming, DevOps, architecture, tools |
| `FINANCE_QUANT` | `"finance-quant"` | Quantitative finance, trading, portfolio theory |
| `RESEARCH_ACADEMIC` | `"research-academic"` | Academic papers, research methodology |
| `MATH_STATS` | `"math-stats"` | Mathematics, statistics, probability |
| `CAREER` | `"career"` | Jobs, career advice, networking |
| `GENERAL` | `"general"` | Everything else |

### ContentType
| Value | String | Description |
|-------|--------|-------------|
| `PAPER` | `"paper"` | Academic paper or preprint |
| `REPO` | `"repo"` | GitHub/GitLab repository |
| `VIDEO` | `"video"` | YouTube or other video |
| `ARTICLE` | `"article"` | Blog post or news article |
| `THREAD` | `"thread"` | Multi-tweet thread (>800 chars) |
| `TOOL` | `"tool"` | Software tool or library |
| `INSIGHT` | `"insight"` | Short standalone insight (<=280 chars, no URLs) |
| `TWEET` | `"tweet"` | Single tweet |

---

## Configuration

Config file: `~/.ideabank/config.yaml`

### Full Config Structure

```yaml
db_path: ~/.ideabank/db/ideabank.db
raw_path: ~/.ideabank/raw
cache_path: ~/.ideabank/cache
vault_path: ~/IdeaBank

extraction:
  concurrency: 3              # Max concurrent HTTP requests
  timeout_seconds: 15          # Per-request timeout
  max_text_length: 50000       # Max extracted text length (chars)
  rate_limit_delay: 1.0        # Seconds between requests

classification:
  model: gpt-4.1-mini          # OpenAI model for classification
  max_context_chars: 4000      # Max chars sent to LLM per item
  batch_size: 20               # Items per batch

embedding:
  model: text-embedding-3-small  # OpenAI embedding model
  dimensions: 1536               # Vector dimensions
  batch_size: 500                # Items per API batch
  max_text_chars: 8000           # Max chars for embedding input
```

### Config Classes (Pydantic)

```python
class ExtractionConfig(BaseModel):
    concurrency: int = 3
    timeout_seconds: int = 15
    max_text_length: int = 50000
    rate_limit_delay: float = 1.0

class ClassificationConfig(BaseModel):
    model: str = "gpt-4.1-mini"
    max_context_chars: int = 4000
    batch_size: int = 20

class EmbeddingConfig(BaseModel):
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    batch_size: int = 500
    max_text_chars: int = 8000

class IdeaBankConfig(BaseModel):
    db_path: Path = Path("~/.ideabank/db/ideabank.db")
    raw_path: Path = Path("~/.ideabank/raw")
    cache_path: Path = Path("~/.ideabank/cache")
    vault_path: Optional[Path] = Path("~/IdeaBank")
    extraction: ExtractionConfig = ExtractionConfig()
    classification: ClassificationConfig = ClassificationConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
```

### Config Functions

| Function | Description |
|----------|-------------|
| `get_config_path() -> Path` | Returns `~/.ideabank/config.yaml` |
| `load_config() -> IdeaBankConfig` | Loads config from file or returns defaults |
| `save_config(config) -> None` | Saves config to YAML |
| `ensure_directories(config) -> None` | Creates all required directories |

---

## Module: core/database.py

### Constants

- `SCHEMA_VERSION = "4.0"`
- `PRAGMAS`: WAL mode, NORMAL sync, foreign_keys ON, 5000ms busy_timeout

### Class: Database

```python
class Database:
    def __init__(self, db_path: Path): ...

    # Connection
    async def connect() -> None
    async def close() -> None

    # Execution
    async def execute(sql: str, params: tuple = ()) -> aiosqlite.Cursor
    async def executemany(sql: str, params: list) -> aiosqlite.Cursor
    async def executescript(sql: str) -> None
    async def fetch_one(sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]
    async def fetch_all(sql: str, params: tuple = ()) -> list[aiosqlite.Row]
    async def commit() -> None

    # Schema
    async def init_schema() -> None          # Creates all tables, FTS, triggers, vec
    async def get_schema_version() -> Optional[str]

    # sqlite-vec
    async def _try_init_vec() -> None        # Attempts vec extension load
    @property
    def has_vec -> bool                      # True if sqlite-vec available
```

### Module Functions

```python
async def get_database(db_path: Path) -> Database    # Connect to existing DB
async def init_database(db_path: Path) -> Database   # Create + initialize new DB
```

---

## Module: core/repository.py

### Class: Repository

All methods are `async`. The Repository wraps the Database and handles Pydantic model ↔ SQLite row conversion.

#### Items

```python
async def insert_item(item: Item) -> Item
async def get_item_by_uri(canonical_uri: str) -> Optional[Item]
async def get_item_by_id(item_id: str) -> Optional[Item]
async def item_exists_by_uri(canonical_uri: str) -> bool
async def count_items(kind: Optional[str] = None) -> int
async def get_all_items(kind: Optional[str] = None, limit: Optional[int] = None) -> list[Item]
```

#### Events

```python
async def insert_event(event: Event) -> Event
async def event_exists_by_dedupe_key(source: str, event_type: str, dedupe_key: str) -> bool
async def count_events(source: Optional[str] = None) -> int
```

#### Representations

```python
async def insert_representation(rep: Representation) -> Representation
async def get_representation_text(item_id: str, rep_type: str = "extracted_text") -> Optional[str]
```

#### Annotations

```python
async def insert_annotation(ann: Annotation) -> Annotation
async def get_annotation_by_item(item_id: str) -> Optional[Annotation]
async def update_annotation(ann: Annotation) -> Annotation
async def get_or_create_annotation(item_id: str) -> Annotation
```

#### Source State

```python
async def get_source_state(source: str) -> Optional[SourceState]
async def upsert_source_state(state: SourceState) -> SourceState
```

#### Raw Ingestions

```python
async def insert_raw_ingestion(ing: RawIngestion) -> RawIngestion
async def ingestion_exists_by_hash(file_hash: str) -> bool
```

#### Conversations & Messages

```python
async def insert_conversation(conv: Conversation) -> Conversation
async def insert_message(msg: Message) -> Message
```

#### Topics

```python
async def insert_topic(topic: Topic) -> Topic
async def get_topic_by_slug(slug: str) -> Optional[Topic]
async def get_all_topics() -> list[Topic]
async def add_item_topic(item_id: str, topic_id: str, confidence: float = 1.0, source: str = "pattern")
async def get_topics_for_item(item_id: str) -> list[str]   # Returns topic slugs
```

#### Export Queries

```python
async def get_items_for_export(
    only_annotated: bool = True,
    only_changed: bool = False,
    kind: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[tuple[Item, Optional[Annotation]]]

async def get_first_event_date(item_id: str) -> Optional[str]
```

#### Linked Content

```python
async def insert_linked_content(lc: LinkedContent) -> LinkedContent
async def update_linked_content(lc: LinkedContent) -> LinkedContent
async def get_linked_content_for_item(item_id: str) -> list[LinkedContent]
async def get_items_needing_extraction(limit: int = 100) -> list[Item]
async def count_linked_content(status: Optional[str] = None) -> int
async def linked_content_exists(source_item_id: str, canonical_url: str) -> bool
```

#### Classifications

```python
async def insert_classification(cls: Classification) -> Classification
async def upsert_classification(cls: Classification) -> Classification
async def get_classification_for_item(item_id: str) -> Optional[Classification]
async def get_items_needing_classification(limit: int = 100) -> list[Item]
async def count_classifications(domain: Optional[str] = None) -> int
```

#### Embeddings

```python
async def insert_embedding(emb: Embedding) -> Embedding
async def upsert_embedding(emb: Embedding) -> Embedding
async def get_embedding_for_item(item_id: str, model: str = "text-embedding-3-small") -> Optional[Embedding]
async def get_all_embeddings(model: str = "text-embedding-3-small") -> list[Embedding]
async def get_items_needing_embedding(model: str = "text-embedding-3-small", limit: int = 500) -> list[Item]
async def count_embeddings(model: Optional[str] = None) -> int
```

### Utility Functions

```python
def _json_dumps(obj) -> Optional[str]           # JSON serialize or None
def compute_file_hash(file_path: str) -> str     # SHA256 of file
def compute_content_hash(content: str) -> str    # SHA256 of string
```

---

## Module: extraction/

Extracts content from URLs found in items. Supports articles (trafilatura), YouTube transcripts, GitHub READMEs, and ArXiv abstracts.

### extraction/base.py

```python
@dataclass
class ExtractionResult:
    url: str
    canonical_url: str
    title: Optional[str] = None
    text: Optional[str] = None
    word_count: int = 0
    content_type: Optional[str] = None    # article, transcript, readme, abstract
    extractor: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool             # True if text is non-empty

class BaseExtractor(ABC):
    name: str = "base"
    async def extract(self, url: str) -> ExtractionResult    # Abstract
    def can_handle(self, url: str, domain: str) -> bool      # Abstract
```

### extraction/router.py

```python
def route_url(url: str) -> Optional[BaseExtractor]
```

**Routing order** (first match wins):
1. `ArxivExtractor` — arxiv.org domains
2. `YouTubeExtractor` — youtube.com, youtu.be
3. `GitHubExtractor` — github.com
4. `ArticleExtractor` — any HTTP(S) URL not in SKIP_DOMAINS

### extraction/article.py — ArticleExtractor

- **Extractor name:** `trafilatura`
- **Content type:** `article`
- **Library:** trafilatura for main text extraction, httpx for async HTTP
- **Timeout:** 15 seconds
- **Max text:** 50,000 chars
- **Title extraction:** og:title → twitter:title → `<title>` tag
- **Skipped domains:** twitter.com, x.com, t.co, instagram.com, facebook.com, tiktok.com

### extraction/youtube.py — YouTubeExtractor

- **Extractor name:** `youtube_transcript`
- **Content type:** `transcript`
- **Library:** youtube-transcript-api
- **Handles:** youtube.com/watch, youtu.be/, youtube.com/shorts/
- **Title:** Via oEmbed API (`https://www.youtube.com/oembed?url=...&format=json`)
- **Graceful degradation:** Returns error result if youtube-transcript-api not installed

### extraction/github.py — GitHubExtractor

- **Extractor name:** `github_api`
- **Content type:** `readme`
- **Library:** httpx + GitHub REST API
- **Handles:** github.com/{owner}/{repo} URLs
- **Extracts:** Repo description, stars, language, README content (raw)
- **Combined text format:** `"Description: ... | Stars: ... | Language: ... | README: ..."`

### extraction/arxiv.py — ArxivExtractor

- **Extractor name:** `arxiv_api`
- **Content type:** `abstract`
- **Library:** httpx + ArXiv Atom API (`http://export.arxiv.org/api/query?id_list=...`)
- **Handles:** arxiv.org/abs/, arxiv.org/pdf/ URLs
- **Extracts:** Title, authors, abstract, categories
- **Combined text format:** `"Title: ... | Authors: ... | Abstract: ... | Categories: ..."`

### extraction/batch.py

```python
# URL extraction
URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+')

def extract_urls_from_item(item) -> list[str]
    # Extracts URLs from metadata_json and text fields
    # Filters out: twitter.com, x.com, t.co, instagram.com, facebook.com, tiktok.com

# Single extraction with rate limiting
async def extract_single(
    repo: Repository,
    item_id: str,
    url: str,
    semaphore: asyncio.Semaphore,
    rate_limit_delay: float = 1.0,
) -> Optional[LinkedContent]

# Batch orchestration
async def extract_batch(
    repo: Repository,
    items: list,
    concurrency: int = 3,
    rate_limit_delay: float = 1.0,
) -> dict    # Returns: {processed, extracted, skipped, failed, no_urls}
```

---

## Module: classification/

LLM-powered classification of items into domain, content_type, summary, and tags.

### classification/taxonomy.py

**Domain definitions** with keywords and URL patterns:

| Domain | Keywords (sample) | URL Patterns |
|--------|-------------------|-------------|
| ai-ml | llm, transformer, neural, pytorch, gpt | arxiv.org, huggingface.co |
| software-eng | api, docker, kubernetes, git, devops | github.com, stackoverflow.com |
| finance-quant | portfolio, trading, alpha, risk, hedge | ssrn.com, quantopian.com |
| research-academic | paper, methodology, hypothesis, peer-review | scholar.google.com, doi.org |
| math-stats | theorem, probability, bayesian, regression | mathworld.wolfram.com |
| career | interview, resume, salary, recruiter | linkedin.com, levels.fyi |

```python
def detect_domain_from_text(text: str, url: Optional[str] = None) -> Optional[str]
def detect_content_type_from_url(url: str) -> Optional[str]
def detect_content_type_from_text(text: str, has_urls: bool = True) -> str
    # >800 chars → "thread", <=280 chars no urls → "insight", else → "tweet"
```

### classification/prompts.py

```python
VALID_DOMAINS = ["ai-ml", "software-eng", "finance-quant", "research-academic", "math-stats", "career", "general"]
VALID_CONTENT_TYPES = ["paper", "repo", "video", "article", "thread", "tool", "insight", "tweet"]

SYSTEM_PROMPT = """..."""    # Instructs LLM to return JSON: {domain, content_type, summary, tags}

def build_user_prompt(
    text: str,
    author: str | None = None,
    url: str | None = None,
    linked_content: str | None = None,
) -> str
    # Builds prompt: author + URL + content (4000 chars) + linked content (2000 chars)
```

### classification/classifier.py

```python
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0  # seconds

async def classify_item(
    repo: Repository,
    item_id: str,
    text: str,
    author: Optional[str] = None,
    url: Optional[str] = None,
    linked_content_text: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[Classification]
    # OpenAI chat.completions with response_format={"type": "json_object"}
    # Validates domain/content_type against VALID_DOMAINS/VALID_CONTENT_TYPES
    # Retries with exponential backoff on failure
    # Falls back to heuristics if all retries fail

def _fallback_classification(
    item_id: str,
    text: str,
    url: Optional[str],
    model: str,
) -> Classification
    # Uses taxonomy.py heuristic functions
    # Sets confidence=0.5 to distinguish from LLM classifications

async def classify_batch(
    repo: Repository,
    limit: int = 100,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    dry_run: bool = False,
) -> dict
    # Returns: {classified, skipped, errors, fallback, estimated_tokens, estimated_cost}
    # Includes linked content text as additional context
    # Cost estimate: ~200 tokens/item at $0.80/1M tokens for gpt-4.1-mini
```

---

## Module: embeddings/

Vector embeddings for semantic and hybrid search.

### embeddings/generator.py

```python
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
) -> str
    # Combines: title + author + summary + content + linked_text (2000 chars)
    # Returns text capped at MAX_TEXT_CHARS (8000)

async def generate_embeddings(
    repo: Repository,
    model: str = DEFAULT_MODEL,
    dimensions: int = DEFAULT_DIMENSIONS,
    batch_size: int = BATCH_SIZE,
    limit: int = 500,
    force: bool = False,
    dry_run: bool = False,
) -> dict
    # Returns: {embedded, skipped, errors, total_tokens, estimated_cost}
    # Uses OpenAI client.embeddings.create() in batches
    # Hash-based skip: computes SHA256 of input text, skips if unchanged
    # Cost: ~$0.02/1M tokens for text-embedding-3-small
```

### embeddings/store.py

```python
@dataclass
class SimilarityResult:
    item_id: str
    score: float                          # 0.0–1.0
    title: Optional[str] = None
    kind: Optional[str] = None
    author: Optional[str] = None
    snippet: Optional[str] = None         # First 200 chars of content

def cosine_similarity(a: list[float], b: list[float]) -> float
    # Standard cosine similarity, returns 0.0 on zero vectors

class VectorStore:
    def __init__(self, db: Database, repo: Repository): ...

    async def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        kind: Optional[str] = None,
    ) -> list[SimilarityResult]
        # Dispatches to _search_vec or _search_json_fallback based on db.has_vec

    async def _search_vec(query_vector, limit, kind) -> list[SimilarityResult]
        # Uses: SELECT item_id, distance FROM embeddings_vec WHERE embedding MATCH ?
        # Converts distance to similarity score

    async def _search_json_fallback(query_vector, limit, kind) -> list[SimilarityResult]
        # Loads all embeddings into memory, computes cosine similarity
        # Sorts by score descending, returns top N
```

### embeddings/search.py

```python
async def semantic_search(
    db: Database,
    repo: Repository,
    query: str,
    limit: int = 20,
    kind: Optional[str] = None,
    model: str = "text-embedding-3-small",
    dimensions: int = 1536,
) -> list[SimilarityResult]
    # 1. Embeds query via OpenAI
    # 2. Searches via VectorStore
    # 3. Enriches results with content snippets (first 200 chars)

async def hybrid_search(
    db: Database,
    repo: Repository,
    query: str,
    limit: int = 20,
    kind: Optional[str] = None,
    fts_weight: float = 0.4,
    semantic_weight: float = 0.6,
    model: str = "text-embedding-3-small",
) -> list[SimilarityResult]
    # 1. Runs FTS5 search + semantic search in parallel (asyncio.gather)
    # 2. Computes RRF score: Σ (weight / (k + rank)) for each item
    # 3. k=60 (standard RRF constant)
    # 4. Merges and sorts by combined RRF score
    # 5. Enriches with snippets

async def _fts_search_wrapper(db, query, limit, kind) -> list[SimilarityResult]
    # Wraps FTS5 query results into SimilarityResult format
    # Searches items_fts + representations_fts
```

**Reciprocal Rank Fusion formula:**

```
For each item appearing in any result list:
  rrf_score = Σ_source (weight_source / (k + rank_in_source))

Where:
  k = 60 (constant)
  weight_source = fts_weight or semantic_weight
  rank_in_source = 1-based rank (or ∞ if not in that list)
```

---

## Module: export/obsidian.py

One-way export from SQLite to Obsidian vault. SQLite is authoritative — Obsidian files are read-only rendered views.

### Functions

```python
def _slugify(text: str, max_length: int = 50) -> str
    # Lowercase, alphanumeric + dashes, collapse multiple dashes

def _format_date(iso_date: Optional[str]) -> str
    # ISO 8601 → "YYYY-MM-DD"

def compute_content_hash(content: str) -> str
    # SHA256 → first 16 hex chars

def render_item_to_markdown(
    item: Item,
    annotation: Optional[Annotation],
    content_text: Optional[str],
    topics: list[str],
    classification: Optional[Classification] = None,
    linked_contents: Optional[list[LinkedContent]] = None,
) -> str

async def export_to_obsidian(
    db: Database,
    repo: Repository,
    vault_path: Path,
    *,
    only_changed: bool = True,
    kind: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict    # Returns: {exported, skipped, errors}

async def export_item(
    repo: Repository,
    item_id: str,
    vault_path: Path,
) -> Optional[Path]    # Returns file path or None
```

### Obsidian Markdown Format

Each exported file has this structure:

```markdown
---
id: item_01HXYZ...
kind: tweet
url: https://twitter.com/user/status/123
author: "@username"
date: 2024-03-15
stage: inbox
rating: 4
domain: ai-ml
content_type: thread
summary: "One-sentence LLM-generated summary"
fine_tags: ["llm-agents", "transformer", "attention"]
has_linked_content: true
linked_urls: 2
topics: [machine-learning, nlp]
tags: ["user-tag-1", "user-tag-2"]
exported: 2024-03-20T12:00:00Z
---

# Tweet Title or Content Preview

**Author:** [@username](https://twitter.com/username)
**Source:** [https://twitter.com/...](https://twitter.com/...)
**Date:** 2024-03-15

## Summary
> One-sentence LLM-generated summary

## Content

Full extracted text of the item...

## Linked Content

### [Article: Some Article Title](https://example.com/article)
> First 500 characters of extracted article text...

### [YouTube: Video Title](https://youtube.com/watch?v=abc)
> First 500 characters of transcript...

## Notes

User's personal notes about this item...
```

### Output Directory Structure

```
<vault>/IdeaBank/
  tweets/                    # ItemKind.TWEET
  conversations/             # ItemKind.CONVERSATION
  articles/                  # ItemKind.ARTICLE
  other/                     # ItemKind.VIDEO, PAGE, etc.
```

### Filename Format

```
YYYY-MM-DD-slug-shortid.md
```

- **Date prefix:** from `item.created_at` or `item.first_seen_at`
- **Slug:** `_slugify(item.title)`, max 50 chars
- **Short ID:** Last 8 chars of ULID portion of item ID

### Change Detection

Export uses content hashing to skip unchanged items:
1. Render markdown → compute SHA256 hash (16 hex chars)
2. Compare with `annotation.obsidian_hash`
3. Skip if identical; write + update hash if different

---

## Dependencies

### Core (always required)

| Package | Version | Purpose |
|---------|---------|---------|
| aiosqlite | >=0.19.0 | Async SQLite database access |
| pydantic | >=2.0.0 | Data models and validation |
| python-ulid | >=2.0.0 | ULID generation for IDs |
| typer | >=0.9.0 | CLI framework |
| rich | >=13.0.0 | Terminal formatting (tables, panels, progress) |
| pyyaml | >=6.0.0 | Config file parsing |

### Extraction (for `ib extract`)

| Package | Version | Purpose |
|---------|---------|---------|
| httpx | >=0.27.0 | Async HTTP client |
| trafilatura | >=1.8.0 | Article text extraction |
| youtube-transcript-api | >=0.6.0 | YouTube transcript fetching |

### Classification + Embeddings (for `ib classify`, `ib embed`, `ib semantic`, `ib hybrid`)

| Package | Version | Purpose |
|---------|---------|---------|
| openai | >=1.30.0 | OpenAI API client (chat + embeddings) |

### Optional

| Package | Version | Purpose |
|---------|---------|---------|
| sqlite-vec | >=0.1.0 | Fast vector similarity search (falls back to JSON cosine if unavailable) |

---

## Cost Estimates

For a corpus of ~3,894 items:

| Operation | Model | Est. Tokens | Est. Cost |
|-----------|-------|-------------|-----------|
| Classification | gpt-4.1-mini | ~780K | ~$0.62 |
| Embeddings | text-embedding-3-small | ~780K | ~$0.016 |
| Semantic query | text-embedding-3-small | ~50/query | ~$0.000001/query |
| **Total (full corpus)** | | | **~$0.64** |

Use `--dry-run` on `ib classify` and `ib embed` to get precise estimates before committing.

---

## File Map

```
src/ideabank/                          # Root package
  __init__.py
  core/                                # Core data layer
    __init__.py
    config.py                          # Configuration (YAML + Pydantic)
    database.py                        # SQLite schema + connection management
    models.py                          # All Pydantic models + enums
    repository.py                      # All CRUD operations (50+ async methods)
  cli/                                 # Command-line interface
    __init__.py
    main.py                            # All CLI commands (Typer + Rich)
  export/                              # Obsidian export
    __init__.py
    obsidian.py                        # Markdown rendering + vault export
  extraction/                          # URL content extraction
    __init__.py                        # Exports: route_url, extract_batch
    base.py                            # ExtractionResult + BaseExtractor ABC
    router.py                          # URL → extractor routing
    article.py                         # ArticleExtractor (trafilatura + httpx)
    youtube.py                         # YouTubeExtractor (transcript API)
    github.py                          # GitHubExtractor (REST API)
    arxiv.py                           # ArxivExtractor (Atom API)
    batch.py                           # Batch orchestration (semaphore, rate limit)
  classification/                      # LLM classification
    __init__.py                        # Exports: classify_item, classify_batch
    taxonomy.py                        # Domain + content_type definitions + heuristics
    prompts.py                         # System/user prompt templates
    classifier.py                      # OpenAI classifier + heuristic fallback
  embeddings/                          # Vector embeddings + search
    __init__.py                        # Exports: generate_embeddings, build_embedding_text, semantic_search, hybrid_search
    generator.py                       # OpenAI embedding generation + batching
    store.py                           # VectorStore (sqlite-vec + JSON fallback)
    search.py                          # Semantic search + hybrid RRF search
  ingest/                              # Data ingestion (existing)
    __init__.py
    twitter.py                         # Twitter bookmark ingestion
    conversations.py                   # AI conversation ingestion
  requirements.txt                     # All dependencies
  HELP.md                              # This file
```

### File Count

| Category | Files | Description |
|----------|-------|-------------|
| Core | 5 | models, database, repository, config, __init__ |
| CLI | 2 | main, __init__ |
| Export | 2 | obsidian, __init__ |
| Extraction | 8 | base, router, article, youtube, github, arxiv, batch, __init__ |
| Classification | 4 | taxonomy, prompts, classifier, __init__ |
| Embeddings | 4 | generator, store, search, __init__ |
| Ingest | 3 | twitter, conversations, __init__ |
| Other | 2 | requirements.txt, HELP.md |
| **Total** | **~30** | |

---

## ID Prefix Reference

| Prefix | Model | Example |
|--------|-------|---------|
| `item_` | Item | `item_01HXQ7K9N4BYCJR8W2F3M5G6T` |
| `evt_` | Event | `evt_01HXQ7K9N4...` |
| `rep_` | Representation | `rep_01HXQ7K9N4...` |
| `ann_` | Annotation | `ann_01HXQ7K9N4...` |
| `topic_` | Topic | `topic_01HXQ7K9N4...` |
| `conv_` | Conversation | `conv_01HXQ7K9N4...` |
| `msg_` | Message | `msg_01HXQ7K9N4...` |
| `ing_` | RawIngestion | `ing_01HXQ7K9N4...` |
| `lc_` | LinkedContent | `lc_01HXQ7K9N4...` |
| `cls_` | Classification | `cls_01HXQ7K9N4...` |
| `emb_` | Embedding | `emb_01HXQ7K9N4...` |

---

## Timestamp Format

All timestamps use ISO 8601 with UTC timezone:

```
2024-03-15T12:00:00Z
```

Generated by `now_iso()` in `core/models.py`.

---

## Error Handling Patterns

- **Extraction failures:** Stored in `linked_content.error_message` with `status='failed'`. Does not block other extractions.
- **Classification failures:** Falls back to heuristic classification with `confidence=0.5`. Retries LLM up to 2 times with exponential backoff.
- **Embedding failures:** Skipped items logged in stats. Does not block batch.
- **sqlite-vec unavailable:** Graceful fallback to in-memory JSON cosine similarity. Logged once at init.
- **Duplicate ingestion:** Deduplicated by `canonical_uri` (items), `dedupe_key` (events), `file_hash` (raw_ingestions), `(source_item_id, canonical_url)` (linked_content).
- **Export unchanged items:** Content hash comparison skips items that haven't changed since last export.
