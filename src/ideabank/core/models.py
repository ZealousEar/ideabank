"""Core data models for IdeaBank."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from ulid import ULID


def generate_id(prefix: str = "") -> str:
    """Generate a ULID-based ID with optional prefix."""
    ulid = str(ULID())
    return f"{prefix}_{ulid}" if prefix else ulid


def now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


class ItemKind(str, Enum):
    """Types of items."""

    TWEET = "tweet"
    VIDEO = "video"
    ARTICLE = "article"
    PAGE = "page"
    CONVERSATION = "conversation"


class EventType(str, Enum):
    """Types of events."""

    BOOKMARKED = "bookmarked"
    VISITED = "visited"
    LIKED = "liked"
    SAVED = "saved"
    ANNOTATED = "annotated"
    REVIEWED = "reviewed"
    STAGE_SET = "stage_set"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"


class Stage(str, Enum):
    """Processing stages for items."""

    INBOX = "inbox"
    REVIEWED = "reviewed"
    EXPLORING = "exploring"
    REFERENCE = "reference"
    ARCHIVED = "archived"


class RepresentationType(str, Enum):
    """Types of representations."""

    RAW_JSON = "raw_json"
    EXTRACTED_TEXT = "extracted_text"
    SUMMARY = "summary"
    CHUNK = "chunk"
    TRANSCRIPT = "transcript"


class ExtractionStatus(str, Enum):
    """Status of linked content extraction."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class DomainTag(str, Enum):
    """Domain classification tags."""

    AI_ML = "ai-ml"
    SOFTWARE_ENG = "software-eng"
    FINANCE_QUANT = "finance-quant"
    RESEARCH_ACADEMIC = "research-academic"
    MATH_STATS = "math-stats"
    CAREER = "career"
    SPORTS_FOOTBALL = "sports-football"
    MEMES_ENTERTAINMENT = "memes-entertainment"
    HEALTH_BIOHACKING = "health-biohacking"
    SELF_IMPROVEMENT = "self-improvement"
    LIFESTYLE_DESIGN = "lifestyle-design"
    CRYPTO_WEB3 = "crypto-web3"
    POLITICS_NEWS = "politics-news"
    GAMING = "gaming"
    TECH_HARDWARE = "tech-hardware"
    COURSES_LEARNING = "courses-learning"
    GENERAL = "general"


class ContentType(str, Enum):
    """Content type classification."""

    PAPER = "paper"
    REPO = "repo"
    VIDEO = "video"
    ARTICLE = "article"
    THREAD = "thread"
    TOOL = "tool"
    INSIGHT = "insight"
    TWEET = "tweet"


class Item(BaseModel):
    """A canonical item in the knowledge base."""

    id: str = Field(default_factory=lambda: generate_id("item"))
    kind: ItemKind
    canonical_uri: Optional[str] = None
    canonicalizer_version: str = "1"

    title: Optional[str] = None
    author_name: Optional[str] = None
    author_handle: Optional[str] = None
    author_uri: Optional[str] = None

    created_at: Optional[str] = None
    first_seen_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    metadata_json: Optional[dict[str, Any]] = None


class Event(BaseModel):
    """An activity event on an item."""

    id: str = Field(default_factory=lambda: generate_id("evt"))
    event_type: EventType
    item_id: str
    occurred_at: str = Field(default_factory=now_iso)
    source: str
    context_json: Optional[dict[str, Any]] = None
    dedupe_key: Optional[str] = None


class Representation(BaseModel):
    """A representation of an item's content."""

    id: str = Field(default_factory=lambda: generate_id("rep"))
    item_id: str
    rep_type: RepresentationType

    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None

    source_rep_id: Optional[str] = None
    processor: Optional[str] = None
    processor_version: Optional[str] = None

    content_hash: Optional[str] = None

    created_at: str = Field(default_factory=now_iso)


class Annotation(BaseModel):
    """User annotations on an item."""

    id: str = Field(default_factory=lambda: generate_id("ann"))
    item_id: str

    note_text: Optional[str] = None
    tags_json: Optional[list[str]] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    stage: Stage = Stage.INBOX

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    obsidian_path: Optional[str] = None
    obsidian_hash: Optional[str] = None
    exported_at: Optional[str] = None


class Topic(BaseModel):
    """A category/topic with detection patterns."""

    id: str = Field(default_factory=lambda: generate_id("topic"))
    name: str
    slug: str
    parent_id: Optional[str] = None

    patterns_json: Optional[list[str]] = None
    accounts_json: Optional[list[str]] = None

    color: Optional[str] = None

    created_at: str = Field(default_factory=now_iso)


class ItemTopic(BaseModel):
    """Association between item and topic."""

    item_id: str
    topic_id: str
    confidence: float = 1.0
    source: str = "pattern"
    created_at: str = Field(default_factory=now_iso)


class Conversation(BaseModel):
    """A conversation with an AI system."""

    id: str = Field(default_factory=lambda: generate_id("conv"))
    item_id: str
    platform: str
    model: Optional[str] = None
    title: Optional[str] = None

    started_at: Optional[str] = None
    ended_at: Optional[str] = None

    summary_text: Optional[str] = None
    key_insights_json: Optional[list[str]] = None


class Message(BaseModel):
    """A message in a conversation."""

    id: str = Field(default_factory=lambda: generate_id("msg"))
    conversation_id: str
    role: str
    content_text: Optional[str] = None
    content_json: Optional[dict[str, Any]] = None
    message_index: int
    created_at: str = Field(default_factory=now_iso)


class SourceState(BaseModel):
    """Watermark state for a data source."""

    source: str
    last_checked_at: Optional[str] = None
    last_ingested_at: Optional[str] = None
    watermark_occurred_at: Optional[str] = None
    last_file_hash: Optional[str] = None
    state_json: Optional[dict[str, Any]] = None


class RawIngestion(BaseModel):
    """Record of a raw file import."""

    id: str = Field(default_factory=lambda: generate_id("ing"))
    source: str
    file_path: str
    file_hash: str
    record_count: Optional[int] = None
    schema_version: Optional[str] = None
    imported_at: str = Field(default_factory=now_iso)


class LinkedContent(BaseModel):
    """Extracted content from a URL linked in an item."""

    id: str = Field(default_factory=lambda: generate_id("lc"))
    source_item_id: str
    url: str
    canonical_url: str
    domain: Optional[str] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    extracted_text: Optional[str] = None
    word_count: int = 0
    extractor: Optional[str] = None
    status: ExtractionStatus = ExtractionStatus.PENDING
    error_message: Optional[str] = None
    content_hash: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Classification(BaseModel):
    """LLM classification of an item."""

    id: str = Field(default_factory=lambda: generate_id("cls"))
    item_id: str
    domain: DomainTag
    domain_secondary: Optional[str] = None
    content_type: ContentType
    summary: Optional[str] = None
    tags_json: Optional[list[str]] = None
    confidence: float = 1.0
    model_name: Optional[str] = None
    content_hash: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class Embedding(BaseModel):
    """Vector embedding for an item."""

    id: str = Field(default_factory=lambda: generate_id("emb"))
    item_id: str
    embedding_model: str = "text-embedding-3-small"
    dimensions: int = 1536
    embedding_json: Optional[list[float]] = None
    source_text_hash: Optional[str] = None
    token_count: Optional[int] = None
    created_at: str = Field(default_factory=now_iso)
