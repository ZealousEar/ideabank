<!-- BANNER: Replace with ideabank-banner.png (Helvetica-style wordmark, transparent background) -->
<p align="center">
  <img src="assets/banner.png" alt="IdeaBank" width="600" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/async-first-purple?style=for-the-badge" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/search-FTS5%20%2B%20semantic%20%2B%20hybrid-orange?style=for-the-badge" />
</p>

<p align="center">
  <strong>Turn scattered bookmarks, AI chats, and articles into a searchable knowledge base.</strong>
  <br />
  <em>Ingest anything. Classify with AI. Search by meaning.</em>
</p>

<p align="center">
  <a href="#-quickstart">Quickstart</a> &bull;
  <a href="#-how-it-works">How It Works</a> &bull;
  <a href="#-search-modes">Search</a> &bull;
  <a href="#-cli-reference">CLI</a> &bull;
  <a href="docs/Home.md">Full Docs</a>
</p>

---

## The Problem

You bookmark tweets. You save ChatGPT conversations. You star GitHub repos. You highlight articles. Then... you never find any of it again.

IdeaBank fixes this. It pulls all your scattered content into **one local database**, enriches it with AI (summaries, tags, embeddings), and lets you search across everything — by keyword, by meaning, or both.

No cloud. No subscription. Just a SQLite file you own.

---

## Quickstart

```bash
# Install
git clone https://github.com/ZealousEar/ideabank.git
cd ideabank
pip install -e .

# Initialize your knowledge base
ib init

# Import your Twitter bookmarks (JSON export)
ib ingest twitter bookmarks.json

# Extract full article text from linked URLs
ib extract

# Classify everything with AI (needs OPENAI_API_KEY)
ib classify --dry-run        # see cost estimate first
ib classify                  # run it

# Generate embeddings for semantic search
ib embed

# Search!
ib search "transformer attention"     # keyword search
ib semantic "papers about reasoning"  # meaning-based search
ib hybrid "LLM agents"               # best of both worlds
```

> **Note:** Classification and embedding require an OpenAI API key. Set it with `export OPENAI_API_KEY=sk-...` in your shell. Ingestion, extraction, and keyword search work without it.

---

## How It Works

Every item flows through a six-stage pipeline:

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  Ingest  │───▶│ Extract  │───▶│ Classify │───▶│  Embed   │───▶│  Search  │───▶│  Export  │
  │          │    │          │    │          │    │          │    │          │    │          │
  │ Twitter  │    │ Articles │    │ LLM tags │    │ Vectors  │    │ FTS5     │    │ Obsidian │
  │ AI chats │    │ YouTube  │    │ Domains  │    │ 1536-dim │    │ Semantic │    │ Markdown │
  │ URLs     │    │ ArXiv    │    │ Summaries│    │          │    │ Hybrid   │    │          │
  └──────────┘    │ GitHub   │    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                  └──────────┘
                        │
                   Everything stored in one SQLite database
```

Each stage is independent — run them in any order, skip what you don't need, re-run with `--force` to update.

<details>
<summary><strong>What happens at each stage?</strong></summary>

| Stage | What it does | Tech | Needs API key? |
|:------|:-------------|:-----|:---------------|
| **Ingest** | Parses Twitter bookmark exports and AI conversation logs into normalized items | JSON parsing, SHA256 dedup | No |
| **Extract** | Fetches the full text behind URLs — routes to specialized extractors per domain | httpx, trafilatura, ArXiv API, YouTube transcripts | No |
| **Classify** | LLM labels each item with domain, content type, summary, and tags | GPT-4.1-mini with heuristic fallback | Yes |
| **Embed** | Creates 1536-dimensional vector representations for semantic similarity | text-embedding-3-small | Yes |
| **Search** | Three modes: keyword (FTS5), semantic (cosine similarity), hybrid (RRF fusion) | SQLite FTS5, numpy | Semantic/hybrid only |
| **Export** | Renders items as Obsidian-compatible Markdown with YAML frontmatter and wikilinks | Jinja-style templates | No |

</details>

---

## Search Modes

IdeaBank gives you three ways to find things:

### Keyword Search (FTS5)
Exact word matching with BM25 ranking. Fast, precise, great for known terms.
```bash
ib search "attention mechanism"
```

### Semantic Search
Finds content by *meaning*, not just words. "How do LLMs reason?" will find articles about chain-of-thought prompting even if they never use the word "reason."
```bash
ib semantic "how do LLMs reason"
```

### Hybrid Search
Combines both using [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf). This is usually the best option.
```bash
ib hybrid "reinforcement learning from human feedback"
```

---

## Supported Sources

| Source | Format | What gets captured |
|:-------|:-------|:-------------------|
| **Twitter/X** | JSON bookmark export | Tweet text, author, media, linked URLs, timestamps |
| **ChatGPT** | `conversations.json` export | All messages, model info, conversation metadata |
| **Claude** | JSON export | Messages with role attribution |
| **URLs** | Extracted via pipeline | Full article text, YouTube transcripts, ArXiv abstracts, GitHub READMEs |

More sources (Chrome bookmarks, Pocket, Readwise, RSS) are on the roadmap.

---

## CLI Reference

```
Usage: ib [COMMAND]

Pipeline:
  init                    Set up database and directories
  ingest SOURCE FILE      Import a file (twitter, conversation)
  check SOURCE            Auto-detect and ingest new files
  extract                 Fetch linked URL content
  classify                LLM classification (domain, tags, summary)
  embed                   Generate vector embeddings
  export                  Render to Obsidian Markdown

Search:
  search QUERY            Full-text search (FTS5 + BM25)
  semantic QUERY          Semantic search (cosine similarity)
  hybrid QUERY            Hybrid search (RRF fusion)

Management:
  status                  Show source sync status
  stats                   Detailed statistics (items, stages, topics, embeddings)
  inbox                   Items not yet reviewed
  stage ITEM_ID STAGE     Move item through workflow (inbox → reviewed → exploring → reference → archived)
  tag ITEM_ID TAG [TAG]   Add tags to an item
  categorize              Auto-categorize items by pattern matching
```

Every command that hits the API supports `--dry-run` to preview costs before spending money.

---

## Project Structure

```
ideabank/
├── pyproject.toml              # Package config, dependencies, entry points
├── src/ideabank/
│   ├── core/                   # Database, models, config, repository pattern
│   ├── ingestors/              # Source-specific parsers (Twitter, conversations)
│   ├── extraction/             # URL content fetchers (article, ArXiv, GitHub, YouTube)
│   ├── classification/         # LLM labeling with taxonomy + fallback heuristics
│   ├── embeddings/             # Vector generation, storage, and similarity search
│   ├── search/                 # FTS5 full-text search
│   ├── processing/             # Pattern-based categorization
│   ├── export/                 # Obsidian Markdown renderer
│   └── cli/                    # Typer CLI (16 commands)
├── docs/                       # Architecture, schema, search, CLI, extractor docs
└── tests/                      # (coming soon)
```

---

## Tech Stack

| Layer | Technology | Why |
|:------|:-----------|:----|
| **Database** | SQLite + WAL mode + FTS5 | Single-file, zero-config, full-text search built in |
| **Models** | Pydantic v2 | Validation, serialization, type safety |
| **Async** | aiosqlite + httpx | Non-blocking I/O for batch extraction and embedding |
| **Classification** | OpenAI GPT-4.1-mini | Cheap, fast, good enough for tagging |
| **Embeddings** | text-embedding-3-small (1536d) | Best price/quality ratio for personal-scale search |
| **Vector search** | sqlite-vec (optional) | Native SQLite extension; falls back to JSON + numpy |
| **Extraction** | trafilatura | Best Python library for article text extraction |
| **CLI** | Typer + Rich | Type-driven argument parsing, pretty terminal output |
| **IDs** | ULID | Sortable by time, globally unique, URL-safe |

---

## Configuration

IdeaBank stores everything under `~/.ideabank/`:

```
~/.ideabank/
├── config.yaml          # Settings (auto-created on first run)
├── db/ideabank.db       # Your knowledge base
├── raw/                 # Drop files here for ingestion
│   ├── twitter/
│   ├── conversations/
│   └── youtube/
└── cache/               # Extraction cache
```

Override defaults in `config.yaml`:

```yaml
db_path: ~/.ideabank/db/ideabank.db
vault_path: ~/my-obsidian-vault
extraction:
  concurrency: 5
  timeout_seconds: 20
classification:
  model: gpt-4.1-mini
embedding:
  model: text-embedding-3-small
  dimensions: 1536
```

---

## FAQ

<details>
<summary><strong>How much does it cost to run?</strong></summary>

Ingestion, extraction, and keyword search are **free** (no API calls). Classification with GPT-4.1-mini costs roughly **$0.01 per 100 items**. Embedding costs about **$0.002 per 100 items**. Use `--dry-run` on any command to see the estimate before committing.

</details>

<details>
<summary><strong>Do I need Obsidian?</strong></summary>

No. IdeaBank works as a standalone CLI + SQLite database. The Obsidian export (`ib export`) is optional — it renders your items as Markdown files with frontmatter and wikilinks, which Obsidian can display as a connected knowledge graph. But you can use the search commands without ever touching Obsidian.

</details>

<details>
<summary><strong>Can I use a different LLM?</strong></summary>

The classification and embedding modules use the OpenAI SDK. Any OpenAI-compatible API (Ollama, LiteLLM, Azure OpenAI) should work by setting the `OPENAI_BASE_URL` environment variable. We haven't tested every provider, but the interface is standard.

</details>

<details>
<summary><strong>How do I export my Twitter bookmarks?</strong></summary>

Use your Twitter/X data export (Settings → Your Account → Download an archive), or a tool like [twitter-bookmarks-export](https://github.com/search?q=twitter+bookmarks+export) to get a JSON file. Drop it into `~/.ideabank/raw/twitter/` and run `ib check twitter`.

</details>

<details>
<summary><strong>Is my data private?</strong></summary>

Yes. Everything stays on your machine in a local SQLite file. The only external calls are to the OpenAI API for classification and embedding — and only when you explicitly run those commands.

</details>

---

## Roadmap

- [ ] Chrome / Brave bookmark ingestion
- [ ] Pocket and Readwise import
- [ ] RSS feed monitoring
- [ ] Local embedding models (no API key needed)
- [ ] Web UI for browsing and search
- [ ] Plugin system for custom extractors

---

## License

MIT — do whatever you want with it.
