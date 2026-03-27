"""Route URLs to the correct extractor."""

from urllib.parse import urlparse
from typing import Optional

from .base import BaseExtractor
from .article import ArticleExtractor
from .youtube import YouTubeExtractor
from .github import GitHubExtractor
from .arxiv import ArxivExtractor

# Instantiate extractors (stateless, reusable)
_EXTRACTORS: list[BaseExtractor] = [
    ArxivExtractor(),
    YouTubeExtractor(),
    GitHubExtractor(),
    ArticleExtractor(),  # Fallback — must be last
]


def route_url(url: str) -> Optional[BaseExtractor]:
    """Route a URL to the appropriate extractor."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return None

    for extractor in _EXTRACTORS:
        if extractor.can_handle(url, domain):
            return extractor

    return None
