"""Base extractor interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionResult:
    """Result from content extraction."""
    url: str
    canonical_url: str
    title: Optional[str] = None
    text: Optional[str] = None
    word_count: int = 0
    content_type: Optional[str] = None  # article, transcript, readme, abstract
    extractor: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.text is not None and len(self.text.strip()) > 0


class BaseExtractor(ABC):
    """Abstract base for all content extractors."""

    name: str = "base"

    @abstractmethod
    async def extract(self, url: str) -> ExtractionResult:
        """Extract content from a URL."""
        ...

    @abstractmethod
    def can_handle(self, url: str, domain: str) -> bool:
        """Check if this extractor can handle the given URL."""
        ...
