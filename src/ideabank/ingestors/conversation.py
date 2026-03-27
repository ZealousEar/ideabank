"""Conversation ingestor for Claude Code, ChatGPT, and other AI chat exports."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.models import (
    Conversation,
    Event,
    EventType,
    Item,
    ItemKind,
    Message,
    RawIngestion,
    Representation,
    RepresentationType,
    SourceState,
    generate_id,
    now_iso,
)
from ..core.repository import Repository, compute_content_hash, compute_file_hash


SOURCE_NAME = "conversations"


@dataclass
class ConversationIngestResult:
    """Result of conversation ingestion."""

    conversations_created: int = 0
    conversations_skipped: int = 0
    messages_created: int = 0
    file_hash: str = ""
    platform: str = ""


def detect_format(file_path: Path) -> str:
    """Detect the format of a conversation export file."""
    suffix = file_path.suffix.lower()

    if suffix == ".jsonl":
        # Check if it's Claude Code format by looking at first few lines
        with open(file_path, "r", encoding="utf-8") as f:
            for _ in range(10):  # Check first 10 lines
                line = f.readline()
                if not line:
                    break
                try:
                    data = json.loads(line)
                    # Claude Code format indicators
                    if "sessionId" in data:
                        return "claude_code"
                    if data.get("type") in ("user", "assistant"):
                        return "claude_code"
                    if data.get("type") == "file-history-snapshot":
                        return "claude_code"  # Claude Code snapshot
                except json.JSONDecodeError:
                    pass
        return "jsonl_generic"

    elif suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                # ChatGPT export format
                if isinstance(data, list) and data and "mapping" in data[0]:
                    return "chatgpt"
                # Generic conversations array
                if isinstance(data, list) and data and "messages" in data[0]:
                    return "generic_array"
                # Single conversation with messages
                if isinstance(data, dict) and "messages" in data:
                    return "generic_single"
            except json.JSONDecodeError:
                pass

    return "unknown"


async def ingest_conversation_file(
    repo: Repository,
    file_path: Path,
    *,
    force: bool = False,
    platform_override: Optional[str] = None,
) -> ConversationIngestResult:
    """
    Ingest conversations from a file.

    Supports:
    - Claude Code JSONL (.jsonl)
    - ChatGPT export (.json)
    - Generic JSON format

    Args:
        repo: Repository for database operations
        file_path: Path to the conversation file
        force: If True, re-ingest even if file was already processed
        platform_override: Override detected platform

    Returns:
        ConversationIngestResult with counts
    """
    result = ConversationIngestResult()

    # Check if file was already ingested
    file_hash = compute_file_hash(str(file_path))
    result.file_hash = file_hash

    if not force and await repo.ingestion_exists_by_hash(file_hash):
        return result

    # Detect format
    fmt = detect_format(file_path)

    if fmt == "claude_code":
        result = await _ingest_claude_code(repo, file_path, file_hash)
    elif fmt == "chatgpt":
        result = await _ingest_chatgpt(repo, file_path, file_hash)
    elif fmt in ("generic_single", "generic_array"):
        result = await _ingest_generic(repo, file_path, file_hash, fmt)
    else:
        raise ValueError(f"Unknown conversation format: {fmt}")

    if platform_override:
        result.platform = platform_override

    # Record raw ingestion
    ingestion = RawIngestion(
        source=SOURCE_NAME,
        file_path=str(file_path),
        file_hash=file_hash,
        record_count=result.conversations_created,
        schema_version="1",
    )
    await repo.insert_raw_ingestion(ingestion)

    return result


async def _ingest_claude_code(
    repo: Repository,
    file_path: Path,
    file_hash: str,
) -> ConversationIngestResult:
    """Ingest Claude Code JSONL format."""
    result = ConversationIngestResult(platform="claude_code")

    # Group messages by session
    sessions: dict[str, list[dict]] = {}

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type")
                if msg_type in ("user", "assistant"):
                    session_id = data.get("sessionId", "unknown")
                    if session_id not in sessions:
                        sessions[session_id] = []
                    sessions[session_id].append(data)
            except json.JSONDecodeError:
                continue

    # Process each session as a conversation
    for session_id, messages in sessions.items():
        if not messages:
            continue

        # Sort by timestamp
        messages.sort(key=lambda m: m.get("timestamp", ""))

        # Extract metadata
        first_msg = messages[0]
        last_msg = messages[-1]
        slug = first_msg.get("slug", "conversation")
        model = None

        # Find model from first assistant message
        for msg in messages:
            if msg.get("type") == "assistant":
                model = msg.get("message", {}).get("model")
                if model:
                    break

        # Create canonical URI for deduplication
        canonical_uri = f"claude-code://{session_id}"

        # Check if conversation already exists
        if await repo.item_exists_by_uri(canonical_uri):
            result.conversations_skipped += 1
            continue

        # Extract title from first user message or slug
        title = _extract_title_from_messages(messages) or slug

        # Create item
        item = Item(
            kind=ItemKind.CONVERSATION,
            canonical_uri=canonical_uri,
            title=title,
            created_at=first_msg.get("timestamp"),
        )
        await repo.insert_item(item)

        # Create conversation
        conv = Conversation(
            item_id=item.id,
            platform="claude",
            model=model,
            title=title,
            started_at=first_msg.get("timestamp"),
            ended_at=last_msg.get("timestamp"),
        )
        await repo.insert_conversation(conv)

        # Create messages
        for idx, msg_data in enumerate(messages):
            role = msg_data.get("type")  # "user" or "assistant"
            message_obj = msg_data.get("message", {})

            # Extract text content
            content = message_obj.get("content")
            if isinstance(content, str):
                content_text = content
            elif isinstance(content, list):
                # Extract text from content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            # Optionally include thinking
                            pass
                    elif isinstance(block, str):
                        text_parts.append(block)
                content_text = "\n".join(text_parts)
            else:
                content_text = str(content) if content else ""

            msg = Message(
                conversation_id=conv.id,
                role=role,
                content_text=content_text,
                content_json=message_obj if isinstance(content, list) else None,
                message_index=idx,
                created_at=msg_data.get("timestamp", now_iso()),
            )
            await repo.insert_message(msg)
            result.messages_created += 1

        # Create extracted_text representation (full conversation)
        full_text = _format_conversation_text(messages)
        if full_text:
            rep = Representation(
                item_id=item.id,
                rep_type=RepresentationType.EXTRACTED_TEXT,
                content_text=full_text,
                processor="conversation_ingestor",
                processor_version="1",
                content_hash=compute_content_hash(full_text),
            )
            await repo.insert_representation(rep)

        # Create event
        event = Event(
            event_type=EventType.SAVED,
            item_id=item.id,
            occurred_at=first_msg.get("timestamp", now_iso()),
            source=SOURCE_NAME,
            dedupe_key=canonical_uri,
        )
        await repo.insert_event(event)

        result.conversations_created += 1

    return result


async def _ingest_chatgpt(
    repo: Repository,
    file_path: Path,
    file_hash: str,
) -> ConversationIngestResult:
    """Ingest ChatGPT JSON export format."""
    result = ConversationIngestResult(platform="chatgpt")

    with open(file_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    for conv_data in conversations:
        conv_id = conv_data.get("id", generate_id("chatgpt"))
        title = conv_data.get("title", "ChatGPT Conversation")
        create_time = conv_data.get("create_time")
        update_time = conv_data.get("update_time")

        # Create canonical URI
        canonical_uri = f"chatgpt://{conv_id}"

        if await repo.item_exists_by_uri(canonical_uri):
            result.conversations_skipped += 1
            continue

        # Convert timestamps
        started_at = None
        ended_at = None
        if create_time:
            started_at = datetime.fromtimestamp(create_time).isoformat() + "Z"
        if update_time:
            ended_at = datetime.fromtimestamp(update_time).isoformat() + "Z"

        # Create item
        item = Item(
            kind=ItemKind.CONVERSATION,
            canonical_uri=canonical_uri,
            title=title,
            created_at=started_at,
        )
        await repo.insert_item(item)

        # Create conversation
        conv = Conversation(
            item_id=item.id,
            platform="chatgpt",
            model=conv_data.get("model"),
            title=title,
            started_at=started_at,
            ended_at=ended_at,
        )
        await repo.insert_conversation(conv)

        # Extract messages from mapping
        mapping = conv_data.get("mapping", {})
        messages = []

        for node_id, node in mapping.items():
            message = node.get("message")
            if not message:
                continue

            role = message.get("author", {}).get("role")
            if role not in ("user", "assistant", "system"):
                continue

            content = message.get("content", {})
            parts = content.get("parts", [])
            content_text = "\n".join(str(p) for p in parts if p)

            create_time = message.get("create_time")
            timestamp = None
            if create_time:
                timestamp = datetime.fromtimestamp(create_time).isoformat() + "Z"

            messages.append({
                "role": role,
                "content_text": content_text,
                "timestamp": timestamp,
                "weight": message.get("weight", 0),
            })

        # Sort by timestamp or weight
        messages.sort(key=lambda m: m.get("timestamp") or "")

        # Insert messages
        for idx, msg_data in enumerate(messages):
            msg = Message(
                conversation_id=conv.id,
                role=msg_data["role"],
                content_text=msg_data["content_text"],
                message_index=idx,
                created_at=msg_data.get("timestamp") or now_iso(),
            )
            await repo.insert_message(msg)
            result.messages_created += 1

        # Create extracted_text representation
        full_text = "\n\n".join(
            f"**{m['role'].upper()}**: {m['content_text']}"
            for m in messages if m["content_text"]
        )
        if full_text:
            rep = Representation(
                item_id=item.id,
                rep_type=RepresentationType.EXTRACTED_TEXT,
                content_text=full_text,
                processor="conversation_ingestor",
                processor_version="1",
                content_hash=compute_content_hash(full_text),
            )
            await repo.insert_representation(rep)

        # Create event
        event = Event(
            event_type=EventType.SAVED,
            item_id=item.id,
            occurred_at=started_at or now_iso(),
            source=SOURCE_NAME,
            dedupe_key=canonical_uri,
        )
        await repo.insert_event(event)

        result.conversations_created += 1

    return result


async def _ingest_generic(
    repo: Repository,
    file_path: Path,
    file_hash: str,
    fmt: str,
) -> ConversationIngestResult:
    """Ingest generic JSON format."""
    result = ConversationIngestResult(platform="generic")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Normalize to list of conversations
    if fmt == "generic_single":
        conversations = [data]
    else:
        conversations = data

    for conv_data in conversations:
        conv_id = conv_data.get("id", generate_id("conv"))
        title = conv_data.get("title", "Conversation")
        platform = conv_data.get("platform", "unknown")
        model = conv_data.get("model")

        canonical_uri = f"{platform}://{conv_id}"

        if await repo.item_exists_by_uri(canonical_uri):
            result.conversations_skipped += 1
            continue

        # Create item
        item = Item(
            kind=ItemKind.CONVERSATION,
            canonical_uri=canonical_uri,
            title=title,
            created_at=conv_data.get("created_at"),
        )
        await repo.insert_item(item)

        # Create conversation
        conv = Conversation(
            item_id=item.id,
            platform=platform,
            model=model,
            title=title,
            started_at=conv_data.get("started_at") or conv_data.get("created_at"),
            ended_at=conv_data.get("ended_at"),
        )
        await repo.insert_conversation(conv)

        # Insert messages
        messages = conv_data.get("messages", [])
        for idx, msg_data in enumerate(messages):
            role = msg_data.get("role", "user")
            content = msg_data.get("content", "")

            if isinstance(content, list):
                content_text = "\n".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            else:
                content_text = str(content)

            msg = Message(
                conversation_id=conv.id,
                role=role,
                content_text=content_text,
                message_index=idx,
                created_at=msg_data.get("created_at") or now_iso(),
            )
            await repo.insert_message(msg)
            result.messages_created += 1

        # Create extracted_text representation
        full_text = "\n\n".join(
            f"**{m.get('role', 'user').upper()}**: {m.get('content', '')}"
            for m in messages
        )
        if full_text:
            rep = Representation(
                item_id=item.id,
                rep_type=RepresentationType.EXTRACTED_TEXT,
                content_text=full_text,
                processor="conversation_ingestor",
                processor_version="1",
                content_hash=compute_content_hash(full_text),
            )
            await repo.insert_representation(rep)

        # Create event
        event = Event(
            event_type=EventType.SAVED,
            item_id=item.id,
            occurred_at=conv_data.get("created_at") or now_iso(),
            source=SOURCE_NAME,
            dedupe_key=canonical_uri,
        )
        await repo.insert_event(event)

        result.conversations_created += 1
        result.platform = platform

    return result


def _extract_title_from_messages(messages: list[dict]) -> str:
    """Extract a title from the first user message."""
    for msg in messages:
        if msg.get("type") == "user":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content:
                # Take first line, truncate
                first_line = content.split("\n")[0].strip()
                if len(first_line) > 60:
                    return first_line[:57] + "..."
                return first_line
    return ""


def _format_conversation_text(messages: list[dict]) -> str:
    """Format messages as searchable text."""
    parts = []
    for msg in messages:
        role = msg.get("type", "unknown").upper()
        content = msg.get("message", {}).get("content", "")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            text = "\n".join(text_parts)
        else:
            text = str(content) if content else ""

        if text:
            parts.append(f"**{role}**: {text}")

    return "\n\n".join(parts)


async def check_conversation_source(repo: Repository, raw_path: Path) -> list[Path]:
    """
    Check for new conversation files to ingest.

    Args:
        repo: Repository for database operations
        raw_path: Path to raw data directory

    Returns:
        List of files that need ingestion
    """
    conv_path = raw_path / "conversations"
    if not conv_path.exists():
        return []

    files_to_ingest = []
    for pattern in ("*.json", "*.jsonl"):
        for file_path in conv_path.glob(pattern):
            file_hash = compute_file_hash(str(file_path))
            if not await repo.ingestion_exists_by_hash(file_hash):
                files_to_ingest.append(file_path)

    return sorted(files_to_ingest)
