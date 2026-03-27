"""IdeaBank CLI - Personal knowledge base management."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..core.config import IdeaBankConfig, load_config, save_config, ensure_directories
from ..core.database import init_database, get_database
from ..core.repository import Repository
from ..ingestors.twitter import ingest_twitter_bookmarks, check_twitter_source, SOURCE_NAME as TWITTER_SOURCE
from ..ingestors.conversation import ingest_conversation_file, check_conversation_source, SOURCE_NAME as CONV_SOURCE
from ..search.fulltext import search_all
from ..processing.categorizer import ensure_topics_exist, categorize_item


app = typer.Typer(
    name="ib",
    help="IdeaBank - Personal knowledge base for intellectual fascinations",
    no_args_is_help=True,
)
console = Console()


def run_async(coro):
    """Run async function in sync context."""
    return asyncio.run(coro)


@app.command()
def init(
    vault_path: Optional[Path] = typer.Option(
        None, "--vault", "-v", help="Path to Obsidian vault"
    ),
):
    """Initialize IdeaBank database and directories."""
    config = load_config()
    if vault_path:
        config.vault_path = vault_path.expanduser()

    ensure_directories(config)
    save_config(config)

    async def _init():
        db = await init_database(config.db_path)
        await db.close()

    run_async(_init())

    console.print(Panel.fit(
        f"[green]IdeaBank initialized![/green]\n\n"
        f"Database: {config.db_path}\n"
        f"Raw data: {config.raw_path}\n"
        f"Vault: {config.vault_path or 'Not configured'}",
        title="Setup Complete",
    ))


@app.command()
def check(
    source: str = typer.Argument(..., help="Source to check: twitter, conversations"),
):
    """Check for new data from a source and ingest it."""
    config = load_config()

    async def _check():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            if source == "twitter":
                files = await check_twitter_source(repo, config.raw_path)
                if not files:
                    console.print("[yellow]No new Twitter bookmark files found.[/yellow]")
                    console.print(f"Place JSON files in: {config.raw_path / 'twitter'}")
                    return

                total_created = 0
                total_skipped = 0

                for file_path in files:
                    console.print(f"Ingesting: {file_path.name}")
                    result = await ingest_twitter_bookmarks(repo, file_path)
                    total_created += result.items_created
                    total_skipped += result.items_skipped
                    console.print(
                        f"  Created: {result.items_created}, Skipped: {result.items_skipped}"
                    )

                console.print(Panel.fit(
                    f"[green]Ingestion complete![/green]\n\n"
                    f"Items created: {total_created}\n"
                    f"Items skipped (duplicates): {total_skipped}",
                    title="Twitter Bookmarks",
                ))

            elif source == "conversations":
                files = await check_conversation_source(repo, config.raw_path)
                if not files:
                    console.print("[yellow]No new conversation files found.[/yellow]")
                    console.print(f"Place JSON/JSONL files in: {config.raw_path / 'conversations'}")
                    return

                total_created = 0
                total_skipped = 0
                total_messages = 0

                for file_path in files:
                    console.print(f"Ingesting: {file_path.name}")
                    result = await ingest_conversation_file(repo, file_path)
                    total_created += result.conversations_created
                    total_skipped += result.conversations_skipped
                    total_messages += result.messages_created
                    console.print(
                        f"  Conversations: {result.conversations_created}, "
                        f"Messages: {result.messages_created}, "
                        f"Platform: {result.platform}"
                    )

                console.print(Panel.fit(
                    f"[green]Ingestion complete![/green]\n\n"
                    f"Conversations created: {total_created}\n"
                    f"Messages created: {total_messages}\n"
                    f"Skipped (duplicates): {total_skipped}",
                    title="Conversations",
                ))

            else:
                console.print(f"[red]Unknown source: {source}[/red]")
                console.print("Supported sources: twitter, conversations")
        finally:
            await db.close()

    run_async(_check())


@app.command()
def status():
    """Show status of all data sources."""
    config = load_config()

    async def _status():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            # Get counts
            total_items = await repo.count_items()
            tweet_count = await repo.count_items("tweet")
            event_count = await repo.count_events()

            # Get source states
            twitter_state = await repo.get_source_state(TWITTER_SOURCE)

            table = Table(title="IdeaBank Status")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total items", f"{total_items:,}")
            table.add_row("Tweets", f"{tweet_count:,}")
            table.add_row("Events", f"{event_count:,}")
            table.add_row("", "")

            if twitter_state:
                table.add_row(
                    "Twitter last checked",
                    twitter_state.last_checked_at or "Never",
                )
                table.add_row(
                    "Twitter watermark",
                    twitter_state.watermark_occurred_at or "None",
                )

            console.print(table)
        finally:
            await db.close()

    run_async(_status())


@app.command()
def ingest(
    source: str = typer.Argument(..., help="Source type: twitter, conversation"),
    file_path: Path = typer.Argument(..., help="Path to file to ingest"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-import"),
):
    """Ingest a specific file."""
    config = load_config()

    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    async def _ingest():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            if source == "twitter":
                result = await ingest_twitter_bookmarks(repo, file_path, force=force)

                if result.items_created == 0 and result.items_skipped == 0:
                    console.print("[yellow]File already ingested. Use --force to re-import.[/yellow]")
                else:
                    console.print(Panel.fit(
                        f"[green]Ingestion complete![/green]\n\n"
                        f"Total records: {result.total_records:,}\n"
                        f"Items created: {result.items_created:,}\n"
                        f"Items skipped: {result.items_skipped:,}\n"
                        f"Events created: {result.events_created:,}",
                        title="Twitter Bookmarks",
                    ))

            elif source == "conversation":
                result = await ingest_conversation_file(repo, file_path, force=force)

                if result.conversations_created == 0 and result.conversations_skipped == 0:
                    console.print("[yellow]File already ingested. Use --force to re-import.[/yellow]")
                else:
                    console.print(Panel.fit(
                        f"[green]Ingestion complete![/green]\n\n"
                        f"Platform: {result.platform}\n"
                        f"Conversations: {result.conversations_created:,}\n"
                        f"Messages: {result.messages_created:,}\n"
                        f"Skipped: {result.conversations_skipped:,}",
                        title="Conversations",
                    ))

            else:
                console.print(f"[red]Unknown source: {source}[/red]")
                console.print("Supported sources: twitter, conversation")
        finally:
            await db.close()

    run_async(_ingest())


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Filter by item kind"),
):
    """Search across all content."""
    config = load_config()

    async def _search():
        db = await get_database(config.db_path)

        try:
            results = await search_all(db, query, limit=limit, kind=kind)

            if not results:
                console.print("[yellow]No results found.[/yellow]")
                return

            table = Table(title=f"Search: {query}")
            table.add_column("Kind", style="cyan", width=10)
            table.add_column("Title", style="white", width=40)
            table.add_column("Author", style="dim", width=15)
            table.add_column("Snippet", style="dim", width=50)

            for r in results:
                title = (r.item_title or "")[:40]
                snippet = (r.snippet or "").replace("<b>", "[bold]").replace("</b>", "[/bold]")[:50]
                table.add_row(
                    r.item_kind or "",
                    title,
                    r.item_author or "",
                    snippet,
                )

            console.print(table)
            console.print(f"\n[dim]Showing {len(results)} of {limit} max results[/dim]")
        finally:
            await db.close()

    run_async(_search())


@app.command()
def inbox(
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """Show items in inbox (not yet reviewed)."""
    config = load_config()

    async def _inbox():
        db = await get_database(config.db_path)

        try:
            # Get items without annotations or with stage='inbox'
            rows = await db.fetch_all(
                """
                SELECT i.id, i.kind, i.title, i.author_name, i.canonical_uri, i.created_at
                FROM items i
                LEFT JOIN annotations a ON i.id = a.item_id
                WHERE a.id IS NULL OR a.stage = 'inbox'
                ORDER BY i.first_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            if not rows:
                console.print("[green]Inbox is empty! All items reviewed.[/green]")
                return

            table = Table(title="Inbox")
            table.add_column("ID", style="dim", width=20)
            table.add_column("Kind", style="cyan", width=10)
            table.add_column("Title", style="white", width=40)
            table.add_column("Author", style="dim", width=15)

            for row in rows:
                title = (row["title"] or "")[:40]
                table.add_row(
                    row["id"][:20],
                    row["kind"],
                    title,
                    row["author_name"] or "",
                )

            console.print(table)
            console.print(f"\n[dim]{len(rows)} items in inbox[/dim]")
        finally:
            await db.close()

    run_async(_inbox())


@app.command()
def stage(
    item_id: str = typer.Argument(..., help="Item ID"),
    new_stage: str = typer.Argument(..., help="New stage: inbox, reviewed, exploring, reference, archived"),
):
    """Change an item's stage."""
    config = load_config()

    valid_stages = {"inbox", "reviewed", "exploring", "reference", "archived"}
    if new_stage not in valid_stages:
        console.print(f"[red]Invalid stage: {new_stage}[/red]")
        console.print(f"Valid stages: {', '.join(valid_stages)}")
        raise typer.Exit(1)

    async def _stage():
        from ..core.models import Annotation, Event, EventType, now_iso

        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            # Find item by prefix
            row = await db.fetch_one(
                "SELECT id FROM items WHERE id LIKE ?", (f"{item_id}%",)
            )
            if not row:
                console.print(f"[red]Item not found: {item_id}[/red]")
                return

            full_id = row["id"]

            # Get or create annotation
            ann = await repo.get_annotation_by_item(full_id)
            old_stage = ann.stage if ann else "inbox"

            if ann:
                ann.stage = new_stage
                await repo.update_annotation(ann)
            else:
                ann = Annotation(item_id=full_id, stage=new_stage)
                await repo.insert_annotation(ann)

            # Create event
            event = Event(
                event_type=EventType.STAGE_SET,
                item_id=full_id,
                source="manual",
                context_json={"from_stage": old_stage, "to_stage": new_stage},
            )
            await repo.insert_event(event)

            console.print(f"[green]Stage updated: {old_stage} -> {new_stage}[/green]")
        finally:
            await db.close()

    run_async(_stage())


@app.command()
def tag(
    item_id: str = typer.Argument(..., help="Item ID"),
    tags: list[str] = typer.Argument(..., help="Tags to add"),
):
    """Add tags to an item."""
    config = load_config()

    async def _tag():
        from ..core.models import Annotation, Event, EventType

        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            # Find item by prefix
            row = await db.fetch_one(
                "SELECT id FROM items WHERE id LIKE ?", (f"{item_id}%",)
            )
            if not row:
                console.print(f"[red]Item not found: {item_id}[/red]")
                return

            full_id = row["id"]

            # Get or create annotation
            ann = await repo.get_annotation_by_item(full_id)

            if ann:
                existing_tags = set(ann.tags_json or [])
                new_tags = existing_tags | set(tags)
                ann.tags_json = sorted(new_tags)
                await repo.update_annotation(ann)
            else:
                ann = Annotation(item_id=full_id, tags_json=sorted(tags))
                await repo.insert_annotation(ann)

            # Create events for new tags
            for tag in tags:
                event = Event(
                    event_type=EventType.TAG_ADDED,
                    item_id=full_id,
                    source="manual",
                    context_json={"tag": tag},
                )
                await repo.insert_event(event)

            console.print(f"[green]Tags added: {', '.join(tags)}[/green]")
            console.print(f"All tags: {', '.join(ann.tags_json)}")
        finally:
            await db.close()

    run_async(_tag())


@app.command()
def categorize(
    limit: int = typer.Option(100, "--limit", "-n", help="Max items to categorize"),
):
    """Auto-categorize uncategorized items."""
    config = load_config()

    async def _categorize():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            # Ensure topics exist
            topics = await ensure_topics_exist(repo)
            console.print(f"[dim]Loaded {len(topics)} topics[/dim]")

            # Get items without topic associations
            rows = await db.fetch_all(
                """
                SELECT i.id, i.author_handle, i.metadata_json, r.content_text
                FROM items i
                LEFT JOIN item_topics it ON i.id = it.item_id
                LEFT JOIN representations r ON i.id = r.item_id AND r.rep_type = 'extracted_text'
                WHERE it.item_id IS NULL
                LIMIT ?
                """,
                (limit,),
            )

            if not rows:
                console.print("[green]All items are categorized![/green]")
                return

            categorized = 0
            for row in rows:
                text = row["content_text"] or ""
                author = row["author_handle"]
                has_media = False
                if row["metadata_json"]:
                    import json
                    meta = json.loads(row["metadata_json"])
                    has_media = meta.get("has_media", False)

                matched = await categorize_item(
                    repo, row["id"], text, author, has_media, topics
                )
                if matched:
                    categorized += 1

            console.print(f"[green]Categorized {categorized} items[/green]")
        finally:
            await db.close()

    run_async(_categorize())


@app.command()
def stats():
    """Show detailed statistics."""
    config = load_config()

    async def _stats():
        db = await get_database(config.db_path)

        try:
            # Items by kind
            rows = await db.fetch_all(
                "SELECT kind, COUNT(*) as cnt FROM items GROUP BY kind ORDER BY cnt DESC"
            )

            table = Table(title="Items by Kind")
            table.add_column("Kind", style="cyan")
            table.add_column("Count", style="green", justify="right")

            total = 0
            for row in rows:
                table.add_row(row["kind"], f"{row['cnt']:,}")
                total += row["cnt"]
            table.add_row("[bold]Total[/bold]", f"[bold]{total:,}[/bold]")

            console.print(table)

            # Items by stage
            rows = await db.fetch_all(
                """
                SELECT COALESCE(a.stage, 'inbox') as stage, COUNT(*) as cnt
                FROM items i
                LEFT JOIN annotations a ON i.id = a.item_id
                GROUP BY stage
                ORDER BY cnt DESC
                """
            )

            table = Table(title="Items by Stage")
            table.add_column("Stage", style="cyan")
            table.add_column("Count", style="green", justify="right")

            for row in rows:
                table.add_row(row["stage"], f"{row['cnt']:,}")

            console.print(table)

            # Top topics
            rows = await db.fetch_all(
                """
                SELECT t.name, COUNT(it.item_id) as cnt
                FROM topics t
                LEFT JOIN item_topics it ON t.id = it.topic_id
                GROUP BY t.id
                HAVING cnt > 0
                ORDER BY cnt DESC
                LIMIT 10
                """
            )

            if rows:
                table = Table(title="Top Topics")
                table.add_column("Topic", style="cyan")
                table.add_column("Count", style="green", justify="right")

                for row in rows:
                    table.add_row(row["name"], f"{row['cnt']:,}")

                console.print(table)

            # Linked content stats
            repo = Repository(db)
            lc_total = await repo.count_linked_content()
            if lc_total > 0:
                lc_success = await repo.count_linked_content("success")
                lc_failed = await repo.count_linked_content("failed")
                lc_pending = await repo.count_linked_content("pending")

                table = Table(title="Linked Content")
                table.add_column("Status", style="cyan")
                table.add_column("Count", style="green", justify="right")
                table.add_row("Success", f"{lc_success:,}")
                table.add_row("Failed", f"{lc_failed:,}")
                table.add_row("Pending", f"{lc_pending:,}")
                table.add_row("[bold]Total[/bold]", f"[bold]{lc_total:,}[/bold]")
                console.print(table)

            # Classification stats
            cls_total = await repo.count_classifications()
            if cls_total > 0:
                cls_rows = await db.fetch_all(
                    "SELECT domain, COUNT(*) as cnt FROM classifications GROUP BY domain ORDER BY cnt DESC"
                )
                table = Table(title="Classifications by Domain")
                table.add_column("Domain", style="cyan")
                table.add_column("Count", style="green", justify="right")
                for row in cls_rows:
                    table.add_row(row["domain"], f"{row['cnt']:,}")
                table.add_row("[bold]Total[/bold]", f"[bold]{cls_total:,}[/bold]")
                console.print(table)

            # Embedding stats
            emb_total = await repo.count_embeddings()
            if emb_total > 0:
                console.print(f"\n[cyan]Embeddings:[/cyan] {emb_total:,} items embedded")

        finally:
            await db.close()

    run_async(_stats())


@app.command()
def export(
    vault: Optional[Path] = typer.Option(
        None, "--vault", "-v", help="Path to Obsidian vault (uses config default if not specified)"
    ),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Filter by item kind"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max items to export"),
    all_items: bool = typer.Option(False, "--all", "-a", help="Export all items, not just changed ones"),
):
    """Export items to Obsidian vault as markdown files."""
    from ..export.obsidian import export_to_obsidian
    
    config = load_config()
    vault_path = vault.expanduser() if vault else config.vault_path
    
    if not vault_path:
        console.print("[red]No vault path configured. Use --vault or run 'ib init --vault /path/to/vault'[/red]")
        raise typer.Exit(1)
    
    vault_path = Path(vault_path).expanduser()
    if not vault_path.exists():
        console.print(f"[yellow]Creating vault directory: {vault_path}[/yellow]")
        vault_path.mkdir(parents=True, exist_ok=True)

    async def _export():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            console.print(f"[dim]Exporting to: {vault_path}[/dim]")
            
            stats = await export_to_obsidian(
                db=db,
                repo=repo,
                vault_path=vault_path,
                only_changed=not all_items,
                kind=kind,
                limit=limit,
            )
            
            console.print(Panel.fit(
                f"[green]Export complete![/green]\n\n"
                f"Exported: {stats['exported']:,}\n"
                f"Skipped (unchanged): {stats['skipped']:,}\n"
                f"Errors: {stats['errors']:,}",
                title="Obsidian Export",
            ))
        finally:
            await db.close()

    run_async(_export())


@app.command()
def extract(
    limit: int = typer.Option(100, "--limit", "-n", help="Max items to process"),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="Concurrent requests"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-extract existing content"),
):
    """Extract linked content from item URLs."""
    from ..extraction.batch import extract_batch

    config = load_config()

    async def _extract():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            if force:
                items = await repo.get_all_items(limit=limit)
            else:
                items = await repo.get_items_needing_extraction(limit=limit)

            if not items:
                console.print("[yellow]No items need extraction.[/yellow]")
                return

            console.print(f"[dim]Processing {len(items)} items with concurrency={concurrency}...[/dim]")

            result = await extract_batch(
                repo=repo,
                items=items,
                concurrency=concurrency,
                rate_limit_delay=config.extraction.rate_limit_delay,
            )

            console.print(Panel.fit(
                f"[green]Extraction complete![/green]\n\n"
                f"Items processed: {result['processed']:,}\n"
                f"URLs extracted: {result['extracted']:,}\n"
                f"Skipped: {result['skipped']:,}\n"
                f"Failed: {result['failed']:,}\n"
                f"No URLs: {result['no_urls']:,}",
                title="Linked Content Extraction",
            ))
        finally:
            await db.close()

    run_async(_extract())


@app.command()
def classify(
    limit: int = typer.Option(100, "--limit", "-n", help="Max items to classify"),
    model: str = typer.Option("gpt-4.1-mini", "--model", "-m", help="LLM model"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-classify existing items"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Estimate cost without classifying"),
):
    """Classify items using LLM (domain, content_type, summary, tags)."""
    from ..classification.classifier import classify_batch

    config = load_config()

    async def _classify():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            result = await classify_batch(
                repo=repo,
                limit=limit,
                model=model,
                force=force,
                dry_run=dry_run,
            )

            if dry_run:
                console.print(Panel.fit(
                    f"[yellow]Dry run - no changes made[/yellow]\n\n"
                    f"Would classify: {result.get('would_classify', 0):,}\n"
                    f"Estimated tokens: {result['estimated_tokens']:,}\n"
                    f"Estimated cost: ${result['estimated_cost']:.4f}",
                    title="Classification Estimate",
                ))
            else:
                console.print(Panel.fit(
                    f"[green]Classification complete![/green]\n\n"
                    f"Classified: {result['classified']:,}\n"
                    f"Fallback (heuristic): {result['fallback']:,}\n"
                    f"Skipped: {result['skipped']:,}\n"
                    f"Errors: {result['errors']:,}",
                    title="LLM Classification",
                ))
        finally:
            await db.close()

    run_async(_classify())


@app.command()
def embed(
    limit: int = typer.Option(500, "--limit", "-n", help="Max items to embed"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-embed existing items"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Estimate cost without embedding"),
):
    """Generate embeddings for items."""
    from ..embeddings.generator import generate_embeddings

    config = load_config()

    async def _embed():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            result = await generate_embeddings(
                repo=repo,
                model=config.embedding.model,
                dimensions=config.embedding.dimensions,
                batch_size=config.embedding.batch_size,
                limit=limit,
                force=force,
                dry_run=dry_run,
            )

            if dry_run:
                console.print(Panel.fit(
                    f"[yellow]Dry run - no changes made[/yellow]\n\n"
                    f"Would embed: {result.get('would_embed', 0):,}\n"
                    f"Estimated tokens: {result['total_tokens']:,}\n"
                    f"Estimated cost: ${result['estimated_cost']:.4f}",
                    title="Embedding Estimate",
                ))
            else:
                console.print(Panel.fit(
                    f"[green]Embedding complete![/green]\n\n"
                    f"Embedded: {result['embedded']:,}\n"
                    f"Skipped: {result['skipped']:,}\n"
                    f"Errors: {result['errors']:,}\n"
                    f"Total tokens: {result['total_tokens']:,}",
                    title="Embeddings",
                ))
        finally:
            await db.close()

    run_async(_embed())


@app.command()
def semantic(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Filter by item kind"),
):
    """Semantic search using embeddings."""
    from ..embeddings.search import semantic_search as _semantic_search

    config = load_config()

    async def _search():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            results = await _semantic_search(db, repo, query, limit=limit, kind=kind)

            if not results:
                console.print("[yellow]No results found. Have you run 'ib embed' first?[/yellow]")
                return

            table = Table(title=f"Semantic: {query}")
            table.add_column("Score", style="yellow", width=6)
            table.add_column("Kind", style="cyan", width=10)
            table.add_column("Title", style="white", width=40)
            table.add_column("Author", style="dim", width=15)
            table.add_column("Snippet", style="dim", width=40)

            for r in results:
                table.add_row(
                    f"{r.score:.3f}",
                    r.kind or "",
                    (r.title or "")[:40],
                    r.author or "",
                    (r.snippet or "")[:40],
                )

            console.print(table)
            console.print(f"\n[dim]{len(results)} results[/dim]")
        finally:
            await db.close()

    run_async(_search())


@app.command()
def hybrid(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    fts_weight: float = typer.Option(0.4, "--fts-weight", help="FTS5 weight (0-1)"),
):
    """Hybrid search combining FTS5 + semantic (RRF)."""
    from ..embeddings.search import hybrid_search as _hybrid_search

    config = load_config()

    async def _search():
        db = await get_database(config.db_path)
        repo = Repository(db)

        try:
            results = await _hybrid_search(
                db, repo, query,
                limit=limit,
                fts_weight=fts_weight,
                semantic_weight=1.0 - fts_weight,
            )

            if not results:
                console.print("[yellow]No results found.[/yellow]")
                return

            table = Table(title=f"Hybrid: {query}")
            table.add_column("RRF", style="yellow", width=8)
            table.add_column("Kind", style="cyan", width=10)
            table.add_column("Title", style="white", width=40)
            table.add_column("Author", style="dim", width=15)
            table.add_column("Snippet", style="dim", width=40)

            for r in results:
                table.add_row(
                    f"{r.score:.5f}",
                    r.kind or "",
                    (r.title or "")[:40],
                    r.author or "",
                    (r.snippet or "")[:40],
                )

            console.print(table)
            console.print(f"\n[dim]{len(results)} results (FTS weight: {fts_weight}, Semantic weight: {1.0 - fts_weight})[/dim]")
        finally:
            await db.close()

    run_async(_search())


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
