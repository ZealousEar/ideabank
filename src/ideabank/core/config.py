"""Configuration management for IdeaBank."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class ExtractionConfig(BaseModel):
    """Configuration for linked content extraction."""

    concurrency: int = 3
    timeout_seconds: int = 15
    max_text_length: int = 50000
    rate_limit_delay: float = 1.0


class ClassificationConfig(BaseModel):
    """Configuration for LLM classification."""

    model: str = "gpt-4.1-mini"
    max_context_chars: int = 4000
    batch_size: int = 20


class EmbeddingConfig(BaseModel):
    """Configuration for embedding generation."""

    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    batch_size: int = 500
    max_text_chars: int = 8000


class IdeaBankConfig(BaseModel):
    """IdeaBank configuration."""

    db_path: Path = Path("~/.ideabank/db/ideabank.db")
    raw_path: Path = Path("~/.ideabank/raw")
    cache_path: Path = Path("~/.ideabank/cache")
    vault_path: Optional[Path] = Path("~/IdeaBank")
    extraction: ExtractionConfig = ExtractionConfig()
    classification: ClassificationConfig = ClassificationConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()

    def expand_paths(self) -> "IdeaBankConfig":
        """Expand ~ in all paths."""
        return IdeaBankConfig(
            db_path=self.db_path.expanduser(),
            raw_path=self.raw_path.expanduser(),
            cache_path=self.cache_path.expanduser(),
            vault_path=self.vault_path.expanduser() if self.vault_path else None,
            extraction=self.extraction,
            classification=self.classification,
            embedding=self.embedding,
        )


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path("~/.ideabank/config.yaml").expanduser()


def load_config() -> IdeaBankConfig:
    """Load configuration from file or return defaults."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return IdeaBankConfig(**data).expand_paths()
    return IdeaBankConfig().expand_paths()


def save_config(config: IdeaBankConfig) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(mode="json"), f, default_flow_style=False)


def ensure_directories(config: IdeaBankConfig) -> None:
    """Create required directories if they don't exist."""
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    config.raw_path.mkdir(parents=True, exist_ok=True)
    config.cache_path.mkdir(parents=True, exist_ok=True)
    (config.raw_path / "twitter").mkdir(exist_ok=True)
    (config.raw_path / "chrome").mkdir(exist_ok=True)
    (config.raw_path / "youtube").mkdir(exist_ok=True)
    (config.raw_path / "conversations").mkdir(exist_ok=True)
    (config.raw_path / "brave").mkdir(exist_ok=True)
    if config.vault_path:
        config.vault_path.mkdir(parents=True, exist_ok=True)
