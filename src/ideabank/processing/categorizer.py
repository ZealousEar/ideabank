"""Content categorization using patterns and account matching.

Simplified to 7 high-value categories. Add more as needed.
"""

import re
from dataclasses import dataclass
from typing import Optional

from ..core.models import Topic
from ..core.repository import Repository

# Simplified category definitions - 7 high-value categories
CATEGORIES = {
    "ai-ml": {
        "name": "AI & Machine Learning",
        "patterns": [
            r"\b(ai|artificial intelligence|machine learning|deep learning|neural|gpt|llm|claude|openai|chatgpt|anthropic|gemini|llama|transformer|diffusion|embedding|fine.?tun|prompt|rag|vector|mistral|hugging\s?face|langchain|ollama|deepseek|perplexity|copilot|agent|multimodal)\b",
        ],
        "accounts": [
            "karpathy", "ylecun", "AndrewYNg", "swyx", "emollick",
            "DrJimFan", "sama", "_akhaliq",
        ],
        "color": "#8B5CF6",
    },
    "programming": {
        "name": "Programming & Dev",
        "patterns": [
            r"\b(python|javascript|typescript|rust|golang|java|swift|kotlin)\b",
            r"\b(react|nextjs|vue|svelte|node|deno|bun|fastapi|django|flask)\b",
            r"\b(coding|programming|developer|software|backend|frontend|api|library|framework)\b",
            r"\b(docker|kubernetes|k8s|aws|azure|gcp|devops|deploy|ci.?cd)\b",
            r"\b(database|sql|postgres|mongodb|redis)\b",
        ],
        "accounts": ["ThePrimeagen", "rauchg", "shadcn"],
        "color": "#3B82F6",
    },
    "finance": {
        "name": "Finance & Trading",
        "patterns": [
            r"\b(trading|stocks?|options?|investing|finance|market|quant|portfolio|etf)\b",
            r"\b(\$[A-Z]{1,5})\b",
        ],
        "accounts": ["unusual_whales", "pyquantnews"],
        "color": "#10B981",
    },
    "research": {
        "name": "Research & Papers",
        "patterns": [
            r"\b(paper|research|study|arxiv|journal|phd|academic|findings)\b",
            r"arxiv\.org",
        ],
        "accounts": ["_akhaliq"],
        "color": "#6366F1",
    },
    "github-oss": {
        "name": "GitHub & Open Source",
        "patterns": [
            r"github\.com",
            r"\b(open source|repo|repository|oss)\b",
        ],
        "accounts": [],
        "color": "#171717",
    },
    "tools": {
        "name": "Tools & Productivity",
        "patterns": [
            r"\b(tool|productivity|notion|obsidian|cursor|vscode|vim|neovim|raycast|automation|workflow|app)\b",
        ],
        "accounts": ["levelsio"],
        "color": "#F59E0B",
    },
    "media": {
        "name": "Media & Entertainment",
        "patterns": [
            r"\b(video|youtube|podcast|meme|funny|viral)\b",
            r"youtu\.?be",
        ],
        "accounts": [],
        "color": "#DC2626",
    },
}


@dataclass
class CategoryMatch:
    """A category match result."""

    slug: str
    name: str
    confidence: float
    source: str  # 'pattern' or 'account'


def categorize_content(
    text: str,
    author_handle: Optional[str] = None,
    has_media: bool = False,
) -> list[CategoryMatch]:
    """
    Categorize content based on text patterns and author.

    Args:
        text: The content text to categorize
        author_handle: The author's handle (without @)
        has_media: Whether the content has media attachments

    Returns:
        List of CategoryMatch objects, ordered by confidence
    """
    text_lower = text.lower()

    # Strip @ from handle if present
    if author_handle and author_handle.startswith("@"):
        author_handle = author_handle[1:]

    matches: list[CategoryMatch] = []

    # Pattern matching (higher confidence)
    for slug, config in CATEGORIES.items():
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower, re.IGNORECASE):
                matches.append(
                    CategoryMatch(
                        slug=slug,
                        name=config["name"],
                        confidence=0.9,
                        source="pattern",
                    )
                )
                break

    # Account-based matching (if no pattern match or as supplement)
    if author_handle:
        for slug, config in CATEGORIES.items():
            if author_handle in config.get("accounts", []):
                # Check if already matched by pattern
                existing = next((m for m in matches if m.slug == slug), None)
                if existing:
                    existing.confidence = min(1.0, existing.confidence + 0.1)
                else:
                    matches.append(
                        CategoryMatch(
                            slug=slug,
                            name=config["name"],
                            confidence=0.7,
                            source="account",
                        )
                    )

    # Fallback for media-heavy content with short text
    if not matches and has_media and len(text) < 100:
        matches.append(
            CategoryMatch(
                slug="media",
                name="Media & Entertainment",
                confidence=0.5,
                source="heuristic",
            )
        )

    # Sort by confidence
    matches.sort(key=lambda m: m.confidence, reverse=True)

    return matches


async def ensure_topics_exist(repo: Repository) -> dict[str, Topic]:
    """
    Ensure all category topics exist in the database.

    Returns:
        Dict mapping slug to Topic
    """
    topics = {}
    for slug, config in CATEGORIES.items():
        existing = await repo.get_topic_by_slug(slug)
        if existing:
            topics[slug] = existing
        else:
            topic = Topic(
                name=config["name"],
                slug=slug,
                patterns_json=config["patterns"],
                accounts_json=config.get("accounts", []),
                color=config.get("color"),
            )
            await repo.insert_topic(topic)
            topics[slug] = topic
    return topics


async def categorize_item(
    repo: Repository,
    item_id: str,
    text: str,
    author_handle: Optional[str] = None,
    has_media: bool = False,
    topics_cache: Optional[dict[str, Topic]] = None,
) -> list[str]:
    """
    Categorize an item and store topic associations.

    Args:
        repo: Repository for database operations
        item_id: ID of the item to categorize
        text: Content text
        author_handle: Author's handle
        has_media: Whether item has media
        topics_cache: Optional pre-loaded topics dict

    Returns:
        List of matched topic slugs
    """
    # Ensure topics exist
    if topics_cache is None:
        topics_cache = await ensure_topics_exist(repo)

    # Get matches
    matches = categorize_content(text, author_handle, has_media)

    # Store associations
    matched_slugs = []
    for match in matches:
        if match.slug in topics_cache:
            topic = topics_cache[match.slug]
            await repo.add_item_topic(
                item_id=item_id,
                topic_id=topic.id,
                confidence=match.confidence,
                source=match.source,
            )
            matched_slugs.append(match.slug)

    return matched_slugs
