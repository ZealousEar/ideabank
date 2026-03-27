# IdeaBank

IdeaBank is a private, async Python knowledge base that ingests Twitter bookmarks and AI conversation exports from ChatGPT and Claude, then enriches, classifies, embeds, and makes them searchable. Linked URLs are extracted into structured content during the pipeline.

The pipeline turns raw saves into structured, searchable, exportable knowledge.

## At a Glance

| Capability | Value |
|---|---|
| Ingestion sources | Twitter bookmarks, ChatGPT exports, Claude exports |
| Database tables | 14 |
| Search modes | 3 (full-text, semantic, hybrid) |
| URL extractors | 4 (article, arXiv, GitHub, YouTube) |
| CLI commands | 16 |
| Embedding dimensions | 1,536 |

## How It Works

```
Twitter Bookmarks / ChatGPT / Claude Exports
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

Everything runs through a SQLite database with WAL mode, so reads never block writes. The CLI (`ib`) drives each stage independently. Ingestion, extraction, classification, embedding, search, and export can run separately.

## Pages

- [Architecture](Architecture.md) - System design, pipeline stages, data flow
- [Database Schema](Database-Schema.md) - All 14 tables, relationships, SQLite pragmas
- [Search](Search.md) - Full-text, semantic, and hybrid search explained
- [CLI Reference](CLI-Reference.md) - All 16 commands with examples
- [Extractors](Extractors.md) - The 4 domain-specific content extractors

## Quick Start

```bash
# Initialize
ib init

# Ingest Twitter bookmarks
ib ingest twitter bookmarks.json

# Run extraction
ib extract

# Requires OPENAI_API_KEY
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
- **OpenAI API** - GPT-4.1-mini for classification, text-embedding-3-small for vectors
- **httpx** - async HTTP client for extraction
- **Typer + Rich** - CLI framework and terminal output
- **Obsidian** - export target with frontmatter + wiki-links
