"""Configuration models and defaults for project-to-epub."""

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

DEFAULT_AUTHOR = "Project-to-EPUB Tool"
DEFAULT_LANGUAGE = "en"
DEFAULT_THEME = "default_eink"
DEFAULT_PUBLISHER = "Project-to-EPUB v1.0"
DEFAULT_LARGE_FILE_THRESHOLD_MB = 10.0

DEFAULT_CONFIG: Dict[str, Any] = {
    "output_directory": ".",
    "default_theme": DEFAULT_THEME,
    "large_file_threshold_mb": DEFAULT_LARGE_FILE_THRESHOLD_MB,
    "skip_large_files": True,
    "log_level": "INFO",
    "epub_metadata": {
        "author": DEFAULT_AUTHOR,
        "language": DEFAULT_LANGUAGE,
        "publisher": DEFAULT_PUBLISHER,
    },
}


@dataclass(frozen=True)
class EpubMetadata:
    """Resolved EPUB metadata."""

    title: Optional[str] = None
    author: str = DEFAULT_AUTHOR
    language: str = DEFAULT_LANGUAGE
    publisher: Optional[str] = DEFAULT_PUBLISHER

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "EpubMetadata":
        """Resolve metadata from legacy nested and top-level config keys."""
        metadata = config.get("epub_metadata", {}) or {}
        return cls(
            title=config.get("title") or metadata.get("title"),
            author=config.get("author") or metadata.get("author") or DEFAULT_AUTHOR,
            language=metadata.get("language") or DEFAULT_LANGUAGE,
            publisher=metadata.get("publisher"),
        )

    def for_title(self, fallback_title: str) -> "EpubMetadata":
        """Return metadata with a concrete title."""
        if self.title:
            return self
        return EpubMetadata(
            title=fallback_title,
            author=self.author,
            language=self.language,
            publisher=self.publisher,
        )

    def as_dict(self) -> Dict[str, Optional[str]]:
        """Return a legacy metadata dictionary."""
        return {
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "publisher": self.publisher,
        }


@dataclass(frozen=True)
class ConversionConfig:
    """Typed conversion configuration."""

    theme: str = DEFAULT_THEME
    large_file_threshold_mb: float = DEFAULT_LARGE_FILE_THRESHOLD_MB
    skip_large_files: bool = True
    flat_toc: bool = True
    metadata: EpubMetadata = field(default_factory=EpubMetadata)

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "ConversionConfig":
        """Create typed config from the existing dictionary API."""
        if isinstance(config, cls):
            return config

        theme = config.get("theme") or config.get("default_theme") or DEFAULT_THEME
        return cls(
            theme=str(theme),
            large_file_threshold_mb=float(
                config.get(
                    "large_file_threshold_mb",
                    DEFAULT_LARGE_FILE_THRESHOLD_MB,
                )
            ),
            skip_large_files=bool(config.get("skip_large_files", True)),
            flat_toc=bool(config.get("flat_toc", True)),
            metadata=EpubMetadata.from_mapping(config),
        )

    @property
    def large_file_threshold_bytes(self) -> float:
        """Configured large-file threshold in bytes."""
        return self.large_file_threshold_mb * 1024 * 1024

    def metadata_for_project(self, project_name: str) -> EpubMetadata:
        """Return metadata with project-name fallback applied."""
        return self.metadata.for_title(project_name)

    def get(self, key: str, default: Any = None) -> Any:
        """Small compatibility shim for older dict-style callers/tests."""
        values = {
            "theme": self.theme,
            "default_theme": self.theme,
            "large_file_threshold_mb": self.large_file_threshold_mb,
            "skip_large_files": self.skip_large_files,
            "flat_toc": self.flat_toc,
            "title": self.metadata.title,
            "author": self.metadata.author,
            "epub_metadata": self.metadata.as_dict(),
        }
        return values.get(key, default)

    def __getitem__(self, key: str) -> Any:
        value = self.get(key, None)
        if value is None and key not in {
            "title",
            "publisher",
            "epub_metadata",
            "theme",
            "default_theme",
            "large_file_threshold_mb",
            "skip_large_files",
            "flat_toc",
            "author",
        }:
            raise KeyError(key)
        return value
