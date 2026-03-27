# CLI Reference

IdeaBank is driven by the `ib` CLI, built with Click. All commands operate on the database at `~/.ideabank/ideabank.db` (configurable via `IDEABANK_DB` env var).

## Commands

### ib init

Initialize the database and working directories.

```bash
ib init
```

Creates `~/.ideabank/` with the SQLite database, runs all pending migrations, and sets up the export directory. Safe to run multiple times — it's idempotent.

```
$ ib init
Created database at /Users/me/.ideabank/ideabank.db
Applied 12 migrations
Ready.
```

---

### ib check twitter

Validate a Twitter bookmark export JSON file without importing anything.

```bash
ib check twitter <file>
```

Checks that the JSON structure matches what the ingester expects, counts bookmarks, and reports any issues. Run this before `ib ingest twitter` to catch problems early.

```
$ ib check twitter bookmarks-2024-03.json
Valid Twitter bookmark export
  Bookmarks found: 847
  With URLs: 831
  Duplicates (within file): 3
  Ready to ingest: 828
```

---

### ib ingest twitter

Import Twitter bookmarks from a JSON export file.

```bash
ib ingest twitter <file>
```

Parses the export, canonicalizes URLs, deduplicates against existing items, and creates new items + events. The raw file is fingerprinted — importing the same file twice is a no-op.

```
$ ib ingest twitter bookmarks-2024-03.json
Ingesting bookmarks-2024-03.json...
  Parsed: 828 bookmarks
  New items: 743
  Duplicates skipped: 85
  Events created: 743
Done in 2.1s
```

| Argument | Required | Description |
|---|---|---|
| `file` | Yes | Path to Twitter bookmark JSON export |

---

### ib extract

Fetch linked URL content for items that haven't been extracted yet.

```bash
ib extract [--limit N] [--concurrency N]
```

Routes each URL to the appropriate domain extractor (see [Extractors](Extractors.md)), fetches content asynchronously, and stores it in `linked_content`.

```
$ ib extract --limit 100 --concurrency 10
Extracting linked content...
  Queued: 100 items
  article: 72 | arxiv: 12 | github: 9 | youtube: 7
  Success: 94 | Failed: 6
  Avg time: 1.2s per item
Done in 14.3s
```

| Option | Default | Description |
|---|---|---|
| `--limit` | All pending | Max items to process |
| `--concurrency` | 10 | Simultaneous HTTP requests |

---

### ib classify

Run LLM classification on items that haven't been classified yet.

```bash
ib classify [--limit N] [--model MODEL]
```

Sends item text to GPT-4.1-mini (by default) and stores domain labels, summaries, tags, and confidence scores. See [Architecture](Architecture.md) for the classification prompt.

```
$ ib classify --limit 200
Classifying items...
  Queued: 200 items
  Classified: 200
  Avg confidence: 0.87
  Top domains: machine-learning (43), web-dev (31), systems (28)
  Cost: ~$0.21
Done in 38.4s
```

| Option | Default | Description |
|---|---|---|
| `--limit` | All pending | Max items to classify |
| `--model` | gpt-4.1-mini | OpenAI model to use |

---

### ib embed

Generate vector embeddings for items that don't have them yet.

```bash
ib embed [--limit N] [--batch-size N]
```

Processes items in batches through OpenAI's text-embedding-3-small API. Embeddings are stored as binary blobs in the `embeddings` table.

```
$ ib embed
Embedding items...
  Queued: 5808 items
  Batch size: 500
  Batches: 12
  Processed: 5808
  Cost: ~$0.42
Done in 2m 14s
```

| Option | Default | Description |
|---|---|---|
| `--limit` | All pending | Max items to embed |
| `--batch-size` | 500 | Items per API call |

---

### ib search

Full-text search using FTS5 with BM25 ranking.

```bash
ib search <query> [--limit N]
```

Supports prefix matching (`transform*`), phrase queries (`"exact phrase"`), and boolean operators (`attention AND NOT rnn`). See [Search](Search.md) for details.

```
$ ib search "attention mechanism" --limit 5
 1. [0.92] Attention Is All You Need
    arxiv.org/abs/1706.03762 — 2024-01-15
 2. [0.87] Multi-Head Attention Explained
    blog.example.com/mha — 2024-02-03
 3. [0.81] FlashAttention: Fast and Memory-Efficient
    arxiv.org/abs/2205.14135 — 2024-03-12
5 results (4ms)
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | — | Search query string |
| `--limit` | No | 20 | Max results |

---

### ib semantic

Semantic search using vector embeddings and cosine similarity.

```bash
ib semantic <query> [--limit N]
```

Embeds the query with text-embedding-3-small and finds the most similar items by cosine distance.

```
$ ib semantic "how do language models learn to follow instructions" --limit 5
 1. [0.89] Training Language Models to Follow Instructions with Human Feedback
    arxiv.org/abs/2203.02155 — 2024-01-20
 2. [0.86] RLHF: A Brief Overview
    blog.example.com/rlhf — 2024-04-11
 3. [0.84] Constitutional AI: Harmlessness from AI Feedback
    arxiv.org/abs/2212.08073 — 2024-02-08
5 results (52ms)
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | — | Natural language query |
| `--limit` | No | 20 | Max results |

---

### ib hybrid

Hybrid search combining FTS5 and semantic results via Reciprocal Rank Fusion.

```bash
ib hybrid <query> [--limit N] [--fts-weight F] [--semantic-weight F]
```

This is the recommended search mode for most queries. See [Search](Search.md) for how RRF works.

```
$ ib hybrid "GPU memory optimization for training" --limit 5
 1. [0.024] Efficient Training of Large Language Models
    blog.example.com/efficient-training — 2024-05-02
 2. [0.021] GPU Memory Usage Guide
    docs.example.com/gpu-memory — 2024-03-18
 3. [0.019] ZeRO: Memory Optimizations Toward Training Trillion Parameter Models
    arxiv.org/abs/1910.02054 — 2024-01-30
5 results (58ms)
```

| Argument/Option | Required | Default | Description |
|---|---|---|---|
| `query` | Yes | — | Search query |
| `--limit` | No | 20 | Max results |
| `--fts-weight` | No | 0.4 | Weight for FTS5 results |
| `--semantic-weight` | No | 0.6 | Weight for semantic results |

---

### ib export

Render items to Obsidian Markdown files with frontmatter and wiki-links.

```bash
ib export [--output DIR] [--limit N] [--domain DOMAIN]
```

Creates one `.md` file per item in the output directory, organized by domain. Files include YAML frontmatter, tags, and cross-references as wiki-links.

```
$ ib export --output ~/vault/IdeaBank/
Exporting to /Users/me/vault/IdeaBank/...
  Items: 5808
  Domains: 23 folders
  Files written: 5808
  Skipped (unchanged): 0
Done in 8.7s
```

| Option | Default | Description |
|---|---|---|
| `--output` | `~/.ideabank/export/` | Output directory |
| `--limit` | All | Max items to export |
| `--domain` | All | Filter to specific domain |

---

### ib stats

Show pipeline statistics — how many items are at each stage.

```bash
ib stats
```

```
$ ib stats
IdeaBank Statistics
  Total items:      5,808
  Extracted:        5,214 (89.8%)
  Classified:       5,106 (87.9%)
  Embedded:         5,808 (100.0%)
  With topics:      4,892 (84.2%)
  Exported:         5,808 (100.0%)

  Sources:
    twitter:        4,231
    chatgpt:          892
    claude:           437
    manual:           248

  Top domains:
    machine-learning:   1,247
    web-dev:              831
    systems:              694
    finance:              512
    career:               389
```

---

### ib inbox

List items that haven't been fully processed yet (missing extraction, classification, or embedding).

```bash
ib inbox [--stage STAGE] [--limit N]
```

```
$ ib inbox --limit 5
Unprocessed items (594 total):
 1. [needs-extract] "Thread on CUDA optimization tricks"
    twitter.com/user/status/123 — ingested 2024-06-01
 2. [needs-classify] "Building a RAG pipeline"
    blog.example.com/rag — ingested 2024-05-28
 3. [needs-extract] "New paper on mixture of experts"
    arxiv.org/abs/2401.xxxxx — ingested 2024-06-02
```

| Option | Default | Description |
|---|---|---|
| `--stage` | All | Filter: "extract", "classify", "embed" |
| `--limit` | 20 | Max items to show |

---

### ib stage

Manually move an item to a specific processing stage. Useful for re-processing or skipping stages.

```bash
ib stage <item_id> <stage>
```

```
$ ib stage 4521 classify
Item 4521 marked for re-classification.
Previous classification cleared.
```

| Argument | Required | Description |
|---|---|---|
| `item_id` | Yes | Item ID (integer) |
| `stage` | Yes | "extract", "classify", "embed", "export" |

---

### ib tag

Add tags to an item manually.

```bash
ib tag <item_id> <tags...>
```

```
$ ib tag 4521 transformers attention optimization
Added 3 tags to item 4521:
  + transformers
  + attention
  + optimization
```

| Argument | Required | Description |
|---|---|---|
| `item_id` | Yes | Item ID (integer) |
| `tags` | Yes | One or more tag strings |

---

### ib categorize

Run pattern-based topic categorization on all items. This is different from LLM classification — it applies regex and keyword patterns to assign items to topics.

```bash
ib categorize [--limit N]
```

```
$ ib categorize
Categorizing items...
  Processed: 5,808
  Topics assigned: 14,231 (avg 2.4 per item)
  New topic assignments: 342
Done in 3.2s
```

| Option | Default | Description |
|---|---|---|
| `--limit` | All | Max items to process |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `IDEABANK_DB` | `~/.ideabank/ideabank.db` | Database path |
| `OPENAI_API_KEY` | — | Required for classify, embed, semantic search |
| `IDEABANK_EXPORT_DIR` | `~/.ideabank/export/` | Default export directory |

## Navigation

- [Home](Home.md) — Back to main page
- [Architecture](Architecture.md) — Pipeline overview
- [Search](Search.md) — Search mode details
- [Database Schema](Database-Schema.md) — What the commands read/write
- [Extractors](Extractors.md) — What `ib extract` calls under the hood
