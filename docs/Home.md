# IdeaBank

IdeaBank is a private async Python knowledge base that ingests bookmarks, conversations, and articles — then enriches, classifies, embeds, and makes them searchable. I built it because I was drowning in saved links and AI chat logs with no way to find anything again.

The pipeline turns raw saves into structured, searchable, exportable knowledge.

## At a Glance

| Metric | Count |
|---|---|
| Items indexed | 5,808 |
| Database tables | 14 |
| Search modes | 3 (full-text, semantic, hybrid) |
| Domain extractors | 6 |
| CLI commands | 15 |
| Embedding dimensions | 1,536 |

## How It Works

```
Bookmarks / Conversations / Articles
        ↓
    Ingest & Normalize
        ↓
    Extract Linked Content
        ↓
    Classify with LLM
        ↓
    Embed (vector)
        ↓
    Search (FTS5 / semantic / hybrid)
        ↓
    Export to Obsidian
```

Everything runs through a SQLite database with WAL mode, so reads never block writes. The CLI (`ib`) drives each stage independently — you can ingest without classifying, search without exporting, etc.

## Pages

- [Architecture](Architecture.md) — System design, pipeline stages, data flow
- [Database Schema](Database-Schema.md) — All 14 tables, relationships, SQLite pragmas
- [Search](Search.md) — Full-text, semantic, and hybrid search explained
- [CLI Reference](CLI-Reference.md) — All 15 commands with examples
- [Extractors](Extractors.md) — The 6 domain-specific content extractors

## Quick Start

```bash
# Initialize
ib init

# Ingest Twitter bookmarks
ib ingest twitter bookmarks.json

# Run the enrichment pipeline
ib extract
ib classify
ib embed

# Search
ib hybrid "transformer attention mechanisms"

# Export to Obsidian
ib export
```

## Tech Stack

- **Python 3.11+** with asyncio throughout
- **SQLite** with FTS5, WAL mode
- **OpenAI API** — GPT-4.1-mini for classification, text-embedding-3-small for vectors
- **httpx** — async HTTP client for extraction
- **Click** — CLI framework
- **Obsidian** — export target with frontmatter + wiki-links
