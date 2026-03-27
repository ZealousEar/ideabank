# CLI Reference

IdeaBank is driven by the `ib` CLI, built with Typer and rendered with Rich. The console entry point is `ib = ideabank.cli.main:main`, and the current CLI exposes 16 commands. By default, the database lives at `~/.ideabank/db/ideabank.db`, and runtime settings such as the database path, raw import directories, extraction defaults, and vault path are loaded from `~/.ideabank/config.yaml`.

## Commands

### ib init

Initialize the database, configuration file, and working directories.

```bash
ib init [--vault DIR]
```

Creates `~/.ideabank/`, writes `~/.ideabank/config.yaml`, initializes the SQLite database, and ensures the raw, cache, and vault directories exist. Safe to run multiple times because it is idempotent.

```
$ ib init --vault ~/IdeaBank
+---------------- Setup Complete ----------------+
| IdeaBank initialized!                          |
|                                                |
| Database: /Users/demo/.ideabank/db/ideabank.db |
| Raw data: /Users/demo/.ideabank/raw            |
| Vault: /Users/demo/IdeaBank                    |
+------------------------------------------------+
```

---

### ib check

Auto-detect and ingest new files from a raw source directory.

```bash
ib check <source>
```

Scans `~/.ideabank/raw/<source>/` for new files and ingests anything not seen before. Supported sources currently are `twitter` and `conversations`.

```
$ ib check twitter
Ingesting: bookmarks-2026-03-25.json
  Created: 41, Skipped: 3
Ingesting: bookmarks-2026-03-26.json
  Created: 28, Skipped: 2
+---------------- Twitter Bookmarks ----------------+
| Ingestion complete!                               |
|                                                   |
| Items created: 69                                 |
| Items skipped (duplicates): 5                     |
+---------------------------------------------------+
```

| Argument | Required | Description |
|---|---|---|
| `source` | Yes | Source directory to scan, currently `twitter` or `conversations` |

---

### ib status

Show counts and source checkpoints for the current database.

```bash
ib status
```

```
$ ib status

                IdeaBank Status
+----------------------+----------------------+
| Metric               | Value                |
+----------------------+----------------------+
| Total items          | 134                  |
| Tweets               | 72                   |
| Events               | 211                  |
|                      |                      |
| Twitter last checked | 2026-03-27T09:14:22Z |
| Twitter watermark    | 2026-03-26T21:40:03Z |
+----------------------+----------------------+
```

---

### ib ingest

Ingest a specific source file.

```bash
ib ingest <source> <file> [--force]
```

Parses a single file, canonicalizes content where needed, deduplicates against existing data, and records the resulting items and events. The supported sources are `twitter` and `conversation`.

```
$ ib ingest twitter bookmarks-2026-03-27.json
+---------------- Twitter Bookmarks ----------------+
| Ingestion complete!                               |
|                                                   |
| Total records: 64                                 |
| Items created: 58                                 |
| Items skipped: 6                                  |
| Events created: 58                                |
+---------------------------------------------------+
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `source` | Yes | n/a | Source type, currently `twitter` or `conversation` |
| `file` | Yes | n/a | Path to the file to ingest |
| `--force` | No | `False` | Re-import a file that has already been ingested |

---

### ib extract

Fetch linked URL content for items that need extraction.

```bash
ib extract [--limit N] [--concurrency N] [--force]
```

Routes each URL to the appropriate domain extractor (see [Extractors](Extractors.md)), fetches content asynchronously, and stores it in `linked_content`. Use `--force` to re-extract existing linked content.

```
$ ib extract --limit 80 --concurrency 3
Processing 80 items with concurrency=3...

+----------- Linked Content Extraction ------------+
| Extraction complete!                             |
|                                                  |
| Items processed: 80                              |
| URLs extracted: 64                               |
| Skipped: 9                                       |
| Failed: 5                                        |
| No URLs: 2                                       |
+--------------------------------------------------+
```

| Option | Default | Description |
|---|---|---|
| `--limit` | 100 | Max items to process |
| `--concurrency` | 3 | Concurrent requests |
| `--force` | `False` | Re-extract items that already have linked content |

---

### ib classify

Run LLM classification on items that have not been classified yet.

```bash
ib classify [--limit N] [--model MODEL] [--force] [--dry-run]
```

Sends item text to the selected model and stores domain, content type, summary, and tags. Use `--dry-run` to preview token usage and estimated cost without writing classifications.

```
$ ib classify --limit 80 --dry-run
+--------------- Classification Estimate ----------+
| Dry run - no changes made                        |
|                                                  |
| Would classify: 80                               |
| Estimated tokens: 96,400                         |
| Estimated cost: $0.0286                          |
+--------------------------------------------------+
```

| Option | Default | Description |
|---|---|---|
| `--limit` | 100 | Max items to classify |
| `--model` | `gpt-4.1-mini` | OpenAI model to use |
| `--force` | `False` | Re-classify items that already have classifications |
| `--dry-run` | `False` | Show a cost estimate without writing results |

---

### ib embed

Generate vector embeddings for items that do not have them yet.

```bash
ib embed [--limit N] [--force] [--dry-run]
```

Uses the embedding model configured in `~/.ideabank/config.yaml`. Batch size, dimensions, and model are read from config rather than passed as CLI flags.

```
$ ib embed --limit 120 --dry-run
+---------------- Embedding Estimate --------------+
| Dry run - no changes made                        |
|                                                  |
| Would embed: 120                                 |
| Estimated tokens: 148,200                        |
| Estimated cost: $0.0030                          |
+--------------------------------------------------+
```

| Option | Default | Description |
|---|---|---|
| `--limit` | 500 | Max items to embed |
| `--force` | `False` | Re-embed items that already have embeddings |
| `--dry-run` | `False` | Show a cost estimate without writing embeddings |

---

### ib search

Full-text search using FTS5 with BM25 ranking.

```bash
ib search <query> [--limit N] [--kind KIND]
```

Supports prefix matching (`transform*`), phrase queries (`"exact phrase"`), and boolean operators (`attention AND NOT rnn`). See [Search](Search.md) for details.

```
$ ib search "attention mechanism" --limit 3

                         Search: attention mechanism
+----------+--------------------------------------+-------------+------------------------------------------+
| Kind     | Title                                | Author      | Snippet                                  |
+----------+--------------------------------------+-------------+------------------------------------------+
| article  | Attention Is All You Need            | A. Vaswani  | Introduces transformer attention for...  |
| page     | Multi-head attention walkthrough     |             | Step-by-step guide to scaled dot...      |
| tweet    | FlashAttention notes                 | gpu_dave    | CUDA benchmarks for attention kernels    |
+----------+--------------------------------------+-------------+------------------------------------------+

Showing 3 of 3 max results
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | n/a | Search query string |
| `--limit` | No | 20 | Max results |
| `--kind` | No | All kinds | Filter by item kind |

---

### ib semantic

Semantic search using vector embeddings and cosine similarity.

```bash
ib semantic <query> [--limit N] [--kind KIND]
```

Embeds the query with the configured embedding model and finds the most similar items by score.

```
$ ib semantic "how do language models learn instructions" --limit 3

                    Semantic: how do language models learn instructions
+-------+--------------+--------------------------------------+-------------+------------------------------------------+
| Score | Kind         | Title                                | Author      | Snippet                                  |
+-------+--------------+--------------------------------------+-------------+------------------------------------------+
| 0.913 | article      | Training Language Models to Follow   | OpenAI      | Instruction tuning and preference data   |
| 0.884 | conversation | Notes on RLHF training loops         |             | Reward models, ranking data, and evals   |
| 0.861 | page         | Constitutional AI overview           | Anthropic   | Supervision through critique and revise  |
+-------+--------------+--------------------------------------+-------------+------------------------------------------+

3 results
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | n/a | Natural language query |
| `--limit` | No | 20 | Max results |
| `--kind` | No | All kinds | Filter by item kind |

---

### ib hybrid

Hybrid search combining FTS5 and semantic results via Reciprocal Rank Fusion.

```bash
ib hybrid <query> [--limit N] [--fts-weight F]
```

This is the recommended search mode for most queries. `--fts-weight` controls the text-search contribution, and the semantic weight is derived automatically as `1.0 - fts_weight`.

```
$ ib hybrid "gpu memory optimization for training" --limit 3

                    Hybrid: gpu memory optimization for training
+---------+---------+--------------------------------------+-------------+------------------------------------------+
| RRF     | Kind    | Title                                | Author      | Snippet                                  |
+---------+---------+--------------------------------------+-------------+------------------------------------------+
| 0.03077 | article | Efficient Training of Large Models   |             | Activation checkpointing and offloading  |
| 0.02941 | page    | GPU memory usage guide               |             | Profiling, caching, and allocator tips   |
| 0.02857 | article | ZeRO memory optimizations            | DeepSpeed   | Partitioning optimizer and gradient data |
+---------+---------+--------------------------------------+-------------+------------------------------------------+

3 results (FTS weight: 0.4, Semantic weight: 0.6)
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | n/a | Search query |
| `--limit` | No | 20 | Max results |
| `--fts-weight` | No | 0.4 | Weight for FTS5 results |

---

### ib export

Render items to Obsidian Markdown files with frontmatter and wiki-links.

```bash
ib export [--vault DIR] [--kind KIND] [--limit N] [--all]
```

Writes one `.md` file per exported item into the configured vault, or the path supplied with `--vault`. Files include YAML frontmatter, tags, and cross-references as wiki-links.

```
$ ib export --vault ~/IdeaBank --kind article --limit 60
Exporting to: /Users/demo/IdeaBank

+----------------- Obsidian Export ----------------+
| Export complete!                                 |
|                                                  |
| Exported: 54                                     |
| Skipped (unchanged): 6                           |
| Errors: 0                                        |
+--------------------------------------------------+
```

| Option | Default | Description |
|---|---|---|
| `--vault` | Config value | Path to Obsidian vault |
| `--kind` | All kinds | Filter by item kind |
| `--limit` | No limit | Max items to export |
| `--all` | `False` | Export all items, not only changed ones |

---

### ib stats

Show detailed statistics across items, workflow stages, topics, linked content, classifications, and embeddings.

```bash
ib stats
```

```
$ ib stats

          Items by Kind
+--------------+-------+
| Kind         | Count |
+--------------+-------+
| tweet        |    72 |
| article      |    41 |
| conversation |    21 |
| Total        |   134 |
+--------------+-------+

         Items by Stage
+------------+-------+
| Stage      | Count |
+------------+-------+
| reviewed   |    52 |
| inbox      |    38 |
| exploring  |    24 |
| reference  |    16 |
| archived   |     4 |
+------------+-------+

           Top Topics
+----------------+-------+
| Topic          | Count |
+----------------+-------+
| ai-ml          |    31 |
| software-eng   |    24 |
| productivity   |    18 |
+----------------+-------+

Embeddings: 96 items embedded
```

---

### ib inbox

List items that have not been reviewed yet.

```bash
ib inbox [--limit N]
```

Shows items with no annotation record or items whose annotation stage is still `inbox`.

```
$ ib inbox --limit 3

                                  Inbox
+----------------------+--------------+--------------------------------------+-------------+
| ID                   | Kind         | Title                                | Author      |
+----------------------+--------------+--------------------------------------+-------------+
| item_01HYX7K2R4D1G9  | tweet        | Thread on CUDA optimization tricks   | gpu_dave    |
| item_01HYX7M7V8B2P1  | article      | Building a compact RAG pipeline      |             |
| item_01HYX7Q3C9P4T6  | page         | Mixture-of-experts implementation... |             |
+----------------------+--------------+--------------------------------------+-------------+

3 items in inbox
```

| Option | Default | Description |
|---|---|---|
| `--limit` | 20 | Max items to show |

---

### ib stage

Move an item to a workflow stage.

```bash
ib stage <item_id> <stage>
```

Valid stages are `inbox`, `reviewed`, `exploring`, `reference`, and `archived`.

```
$ ib stage item_01HYX7K2R4D1G9PMM9Q2V6B9Q reviewed
Stage updated: inbox -> reviewed
```

| Argument | Required | Description |
|---|---|---|
| `item_id` | Yes | Item ID or unique prefix, typically `item_01...` |
| `stage` | Yes | Workflow stage: `inbox`, `reviewed`, `exploring`, `reference`, or `archived` |

---

### ib tag

Add tags to an item manually.

```bash
ib tag <item_id> <tags...>
```

```
$ ib tag item_01HYX7K2R4D1G9PMM9Q2V6B9Q transformers attention optimization
Tags added: transformers, attention, optimization
All tags: attention, optimization, transformers
```

| Argument | Required | Description |
|---|---|---|
| `item_id` | Yes | Item ID or unique prefix, typically `item_01...` |
| `tags` | Yes | One or more tag strings |

---

### ib categorize

Run pattern-based topic categorization on uncategorized items. This is different from LLM classification; it applies regex and keyword patterns to assign items to topics.

```bash
ib categorize [--limit N]
```

```
$ ib categorize --limit 60
Loaded 18 topics
Categorized 37 items
```

| Option | Default | Description |
|---|---|---|
| `--limit` | 100 | Max items to process |

## Environment Variables

Most CLI settings are stored in `~/.ideabank/config.yaml`. This includes `db_path`, `raw_path`, `cache_path`, `vault_path`, and the extraction, classification, and embedding defaults.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | Required | Used by `ib classify`, `ib embed`, `ib semantic`, and `ib hybrid` |

## Navigation

- [Home](Home.md) - Back to main page
- [Architecture](Architecture.md) - Pipeline overview
- [Search](Search.md) - Search mode details
- [Database Schema](Database-Schema.md) - What the commands read and write
- [Extractors](Extractors.md) - What `ib extract` calls under the hood
