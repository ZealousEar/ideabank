# Search

IdeaBank supports three search modes, each with different strengths. In practice, hybrid search is the default for most use cases, but the other two modes are useful in specific situations.

## Comparison

| | FTS5 Full-Text | Semantic | Hybrid (RRF) |
|---|---|---|---|
| **Speed** | ~5ms | ~50ms | ~60ms |
| **Accuracy** | Good for exact terms | Good for concepts | Best overall |
| **Keyword matching** | Excellent | Poor | Good |
| **Conceptual matching** | Poor | Excellent | Good |
| **When to use** | Know the exact term | Exploring related ideas | Default; use this |

All three modes return results as a ranked list with scores. The CLI commands are `ib search`, `ib semantic`, and `ib hybrid` respectively (see [CLI Reference](CLI-Reference.md)).

## Full-Text Search (FTS5)

Uses SQLite's built-in FTS5 extension with BM25 ranking. This is traditional keyword search; if the query words appear in the item, it's a match.

### How it works

```sql
SELECT items.*, rank
FROM items_fts
JOIN items ON items.id = items_fts.rowid
WHERE items_fts MATCH ?
ORDER BY rank
LIMIT ?;
```

FTS5 supports several query syntaxes:

```bash
# Simple keyword search
ib search "attention mechanism"

# Phrase query (exact sequence)
ib search '"attention is all you need"'

# Prefix matching
ib search "transform*"

# Boolean operators
ib search "attention AND NOT rnn"
```

BM25 ranking considers:
- **Term frequency**: How often the query terms appear in the document
- **Inverse document frequency**: Terms that appear in fewer documents get higher weight
- **Document length**: Shorter documents with the same term count rank higher

### Strengths and Weaknesses

FTS5 is great when you know what you're looking for. Searching for "RLHF" will find items that literally contain "RLHF". But it won't find items about "reinforcement learning from human feedback" unless those exact words appear, and it won't find items about "reward modeling" even though that's conceptually related.

## Semantic Search

Embeds the query using the same model as the items (text-embedding-3-small, 1,536 dimensions), then computes cosine similarity against every stored embedding.

### How it works

```python
async def semantic_search(db: Database, query: str, limit: int = 20) -> list[SearchResult]:
    # Embed the query
    query_embedding = await embed_text(query)

    # Load all embeddings
    rows = await db.fetch_all("SELECT item_id, vector FROM embeddings WHERE model = ?",
                              ["text-embedding-3-small"])

    # Compute cosine similarity
    results = []
    for row in rows:
        stored = unpack_vector(row["vector"])
        similarity = cosine_similarity(query_embedding, stored)
        results.append(SearchResult(item_id=row["item_id"], score=similarity))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
```

Cosine similarity:

```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
```

### Performance

Computing cosine similarity against N vectors takes about 50ms in Python. That's fast enough for interactive use. If the collection grows to 100k+ items, an approximate nearest neighbor index (like FAISS or sqlite-vss) would likely make more sense, but for now brute force is fine.

### Strengths and Weaknesses

Semantic search finds conceptually similar items even when there's no keyword overlap. Searching for "how LLMs learn to follow instructions" will surface items about RLHF, instruction tuning, and alignment, even if they never use that exact phrase.

The downside: it can be too fuzzy. If you search for a specific paper title, FTS5 will nail it instantly. Semantic search might return the paper, but it'll also return ten vaguely related items with similar scores.

## Hybrid Search (RRF)

Reciprocal Rank Fusion combines FTS5 and semantic results into a single ranked list. This is the default search mode and gives the best overall results.

### How RRF Works

The idea is simple: run both searches, then merge the results based on their ranks (not their raw scores, which aren't comparable across search modes).

```python
def reciprocal_rank_fusion(
    fts_results: list[SearchResult],
    semantic_results: list[SearchResult],
    fts_weight: float = 0.4,
    semantic_weight: float = 0.6,
    k: int = 60,
) -> list[SearchResult]:
    scores: dict[int, float] = defaultdict(float)

    for rank, result in enumerate(fts_results, start=1):
        scores[result.item_id] += fts_weight / (k + rank)

    for rank, result in enumerate(semantic_results, start=1):
        scores[result.item_id] += semantic_weight / (k + rank)

    merged = [SearchResult(item_id=iid, score=score) for iid, score in scores.items()]
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged
```

The formula for each item's score:

```
score = sum(weight / (k + rank)) for each result list containing the item
```

Where:
- `k = 60` is a constant that prevents high-ranked items from dominating too much
- `fts_weight = 0.4`, keyword matching contributes 40%
- `semantic_weight = 0.6`, semantic similarity contributes 60%

### Why 0.4/0.6 weighting?

Different weightings were tested against a set of ~50 queries with known expected answers. Equal weighting (0.5/0.5) was decent, but tilting toward semantic gave better results for exploratory queries without hurting exact-match queries much. The FTS5 component still rescues cases where semantic search gets confused by ambiguous terms.

### Example

Searching for "GPU memory optimization for training large models":

| Rank | FTS5 only | Semantic only | Hybrid (RRF) |
|---|---|---|---|
| 1 | "GPU Memory Usage Guide" | "Efficient Training of LLMs" | "Efficient Training of LLMs" |
| 2 | "CUDA Memory Allocator" | "ZeRO: Memory Optimization" | "GPU Memory Usage Guide" |
| 3 | "Training Large Models" | "Model Parallelism Survey" | "ZeRO: Memory Optimization" |

The hybrid result combines the keyword precision of FTS5 (catching "GPU" and "memory") with the conceptual reach of semantic search (finding ZeRO and model parallelism papers).

## Implementation Notes

All three search functions return the same `SearchResult` dataclass:

```python
@dataclass
class SearchResult:
    item_id: int
    score: float
    title: str | None = None
    snippet: str | None = None
```

Results are enriched with titles and snippets before display. Snippets for FTS5 results use SQLite's `snippet()` function to highlight matching terms. Semantic results use the first 200 characters of the item text.

## Navigation

- [Home](Home.md), back to main page
- [Architecture](Architecture.md), where search fits in the pipeline
- [Database Schema](Database-Schema.md), tables that power search (items_fts, embeddings)
- [CLI Reference](CLI-Reference.md), the search commands
