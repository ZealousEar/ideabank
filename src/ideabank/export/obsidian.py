"""One-way export to Obsidian vault.

SQLite is authoritative. Obsidian is a read-only rendered view.
Don't try to sync back - edit via CLI, export to Obsidian.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.database import Database
from ..core.models import Item, Annotation, Classification, LinkedContent, now_iso
from ..core.repository import Repository


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a safe filename slug."""
    if not text:
        return "untitled"
    # Remove/replace unsafe chars
    safe = ""
    for c in text.lower():
        if c.isalnum():
            safe += c
        elif c in " -_":
            safe += "-"
    # Collapse multiple dashes
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:max_length] or "untitled"


def _format_date(iso_date: Optional[str]) -> str:
    """Format ISO date to YYYY-MM-DD."""
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return ""


def render_item_to_markdown(
    item: Item,
    annotation: Optional[Annotation],
    content_text: Optional[str],
    topics: list[str],
    classification: Optional[Classification] = None,
    linked_contents: Optional[list[LinkedContent]] = None,
) -> str:
    """Render an item to Obsidian-compatible markdown."""
    lines = []

    # Frontmatter
    lines.append("---")
    lines.append(f"id: {item.id}")
    lines.append(f"kind: {item.kind}")
    if item.canonical_uri:
        lines.append(f"url: {item.canonical_uri}")
    if item.author_handle:
        lines.append(f"author: \"{item.author_handle}\"")
    if item.created_at:
        lines.append(f"date: {_format_date(item.created_at)}")
    if annotation and annotation.stage:
        stage = annotation.stage.value if hasattr(annotation.stage, "value") else annotation.stage
        lines.append(f"stage: {stage}")
    if annotation and annotation.rating:
        lines.append(f"rating: {annotation.rating}")
    # Classification frontmatter
    if classification:
        domain = classification.domain.value if hasattr(classification.domain, "value") else classification.domain
        lines.append(f"domain: {domain}")
        ct = classification.content_type.value if hasattr(classification.content_type, "value") else classification.content_type
        lines.append(f"content_type: {ct}")
        if classification.summary:
            safe_summary = classification.summary.replace('"', '\\"')
            lines.append(f'summary: "{safe_summary}"')
        if classification.tags_json:
            fine_tags = ", ".join(f'"{t}"' for t in classification.tags_json)
            lines.append(f"fine_tags: [{fine_tags}]")
    # Linked content frontmatter
    if linked_contents:
        success_lc = [lc for lc in linked_contents if lc.extracted_text]
        if success_lc:
            lines.append("has_linked_content: true")
            lines.append(f"linked_urls: {len(success_lc)}")
    if topics:
        lines.append(f"topics: [{', '.join(topics)}]")
    if annotation and annotation.tags_json:
        tags = ", ".join(f'"{t}"' for t in annotation.tags_json)
        lines.append(f"tags: [{tags}]")
    lines.append(f"exported: {now_iso()}")
    lines.append("---")
    lines.append("")

    # Title
    title = item.title or "Untitled"
    lines.append(f"# {title}")
    lines.append("")

    # Metadata section
    if item.author_name or item.author_handle:
        author = item.author_name or item.author_handle
        if item.author_uri:
            lines.append(f"**Author:** [{author}]({item.author_uri})")
        else:
            lines.append(f"**Author:** {author}")

    if item.canonical_uri:
        lines.append(f"**Source:** [{item.canonical_uri}]({item.canonical_uri})")

    if item.created_at:
        lines.append(f"**Date:** {_format_date(item.created_at)}")

    lines.append("")

    # Summary (from classification)
    if classification and classification.summary:
        lines.append("## Summary")
        lines.append(f"> {classification.summary}")
        lines.append("")

    # Content
    if content_text:
        lines.append("## Content")
        lines.append("")
        lines.append(content_text)
        lines.append("")

    # Linked Content
    if linked_contents:
        success_lc = [lc for lc in linked_contents if lc.extracted_text]
        if success_lc:
            lines.append("## Linked Content")
            lines.append("")
            for lc in success_lc:
                lc_title = lc.title or lc.canonical_url
                ct_label = f"{lc.content_type}: " if lc.content_type else ""
                lines.append(f"### [{ct_label}{lc_title}]({lc.canonical_url})")
                # Show first 500 chars as blockquote
                preview = lc.extracted_text[:500]
                if len(lc.extracted_text) > 500:
                    preview += "..."
                lines.append(f"> {preview}")
                lines.append("")

    # Notes (if any)
    if annotation and annotation.note_text:
        lines.append("## Notes")
        lines.append("")
        lines.append(annotation.note_text)
        lines.append("")

    return "\n".join(lines)


def compute_content_hash(content: str) -> str:
    """Compute hash of markdown content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


async def export_to_obsidian(
    db: Database,
    repo: Repository,
    vault_path: Path,
    *,
    only_changed: bool = True,
    kind: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict:
    """
    Export items to Obsidian vault as markdown files.
    
    Args:
        db: Database connection
        repo: Repository instance
        vault_path: Path to Obsidian vault
        only_changed: Only export items changed since last export
        kind: Filter by item kind (tweet, conversation, etc.)
        limit: Maximum items to export
        
    Returns:
        Dict with export statistics
    """
    stats = {
        "exported": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    # Create export directory
    export_dir = vault_path / "IdeaBank"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories by kind
    (export_dir / "tweets").mkdir(exist_ok=True)
    (export_dir / "conversations").mkdir(exist_ok=True)
    (export_dir / "articles").mkdir(exist_ok=True)
    (export_dir / "other").mkdir(exist_ok=True)
    
    # Get items to export
    items_with_annotations = await repo.get_items_for_export(
        only_annotated=False,
        only_changed=only_changed,
        kind=kind,
        limit=limit,
    )
    
    for item, annotation in items_with_annotations:
        try:
            # Get content text
            content_text = await repo.get_representation_text(item.id, "extracted_text")

            # Get topics
            topics = await repo.get_topics_for_item(item.id)

            # Get classification
            classification = await repo.get_classification_for_item(item.id)

            # Get linked content
            linked_contents = await repo.get_linked_content_for_item(item.id)

            # Render markdown
            markdown = render_item_to_markdown(
                item, annotation, content_text, topics,
                classification=classification,
                linked_contents=linked_contents or None,
            )
            content_hash = compute_content_hash(markdown)
            
            # Check if content changed (skip if same hash)
            if annotation and annotation.obsidian_hash == content_hash:
                stats["skipped"] += 1
                continue
            
            # Determine output path
            item_kind = item.kind.value if hasattr(item.kind, "value") else item.kind
            if item_kind == "tweet":
                subdir = "tweets"
            elif item_kind == "conversation":
                subdir = "conversations"
            elif item_kind == "article":
                subdir = "articles"
            else:
                subdir = "other"
            
            # Generate filename: date-slug-id.md
            date_prefix = _format_date(item.created_at) or _format_date(item.first_seen_at)
            slug = _slugify(item.title or "")
            short_id = item.id.split("_")[-1][:8] if "_" in item.id else item.id[:8]
            filename = f"{date_prefix}-{slug}-{short_id}.md" if date_prefix else f"{slug}-{short_id}.md"
            
            file_path = export_dir / subdir / filename
            
            # Write file
            file_path.write_text(markdown, encoding="utf-8")
            
            # Update annotation with export info
            if annotation:
                annotation.obsidian_path = str(file_path.relative_to(vault_path))
                annotation.obsidian_hash = content_hash
                annotation.exported_at = now_iso()
                await repo.update_annotation(annotation)
            else:
                # Create annotation to track export
                from ..core.models import Annotation
                new_ann = Annotation(
                    item_id=item.id,
                    obsidian_path=str(file_path.relative_to(vault_path)),
                    obsidian_hash=content_hash,
                    exported_at=now_iso(),
                )
                await repo.insert_annotation(new_ann)
            
            stats["exported"] += 1
            
        except Exception as e:
            stats["errors"] += 1
            # Could log error here if needed
    
    return stats


async def export_item(
    repo: Repository,
    item_id: str,
    vault_path: Path,
) -> Optional[Path]:
    """Export a single item to Obsidian."""
    item = await repo.get_item_by_id(item_id)
    if not item:
        return None
    
    annotation = await repo.get_annotation_by_item(item_id)
    content_text = await repo.get_representation_text(item_id, "extracted_text")
    topics = await repo.get_topics_for_item(item_id)
    classification = await repo.get_classification_for_item(item_id)
    linked_contents = await repo.get_linked_content_for_item(item_id)

    markdown = render_item_to_markdown(
        item, annotation, content_text, topics,
        classification=classification,
        linked_contents=linked_contents or None,
    )
    
    # Determine path
    export_dir = vault_path / "IdeaBank"
    item_kind = item.kind.value if hasattr(item.kind, "value") else item.kind
    subdir = {"tweet": "tweets", "conversation": "conversations", "article": "articles"}.get(item_kind, "other")
    
    date_prefix = _format_date(item.created_at) or _format_date(item.first_seen_at)
    slug = _slugify(item.title or "")
    short_id = item.id.split("_")[-1][:8] if "_" in item.id else item.id[:8]
    filename = f"{date_prefix}-{slug}-{short_id}.md" if date_prefix else f"{slug}-{short_id}.md"
    
    file_path = export_dir / subdir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(markdown, encoding="utf-8")
    
    # Update annotation
    content_hash = compute_content_hash(markdown)
    if annotation:
        annotation.obsidian_path = str(file_path.relative_to(vault_path))
        annotation.obsidian_hash = content_hash
        annotation.exported_at = now_iso()
        await repo.update_annotation(annotation)
    else:
        from ..core.models import Annotation
        new_ann = Annotation(
            item_id=item_id,
            obsidian_path=str(file_path.relative_to(vault_path)),
            obsidian_hash=content_hash,
            exported_at=now_iso(),
        )
        await repo.insert_annotation(new_ann)
    
    return file_path
