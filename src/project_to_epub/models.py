"""Shared data models for project scanning and EPUB generation."""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, List, Mapping, Optional


@dataclass
class FileEntry:
    """Represents a file to be included in the EPUB."""

    absolute_path: Path
    relative_path: Path
    language: str
    content: Optional[str] = None
    highlighted_content: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.relative_path} ({self.language})"


@dataclass(frozen=True)
class HtmlFile:
    """An XHTML file written into the EPUB spine."""

    id: str
    file: str
    title: str


@dataclass
class TocItem:
    """A table-of-contents entry, either a file link or a directory group."""

    id: str
    title: str
    href: Optional[str] = None
    path: Optional[str] = None
    is_directory: bool = False
    children: List["TocItem"] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "TocItem":
        """Create a TOC item from the legacy dictionary representation."""
        children = [cls.from_any(child) for child in item.get("children", [])]
        return cls(
            id=str(item["id"]),
            title=str(item["title"]),
            href=item.get("href"),
            path=item.get("path"),
            is_directory=bool(item.get("is_directory", False)),
            children=children,
        )

    @classmethod
    def from_any(cls, item: Any) -> "TocItem":
        """Accept either a TocItem or a legacy mapping."""
        if isinstance(item, cls):
            return item
        if isinstance(item, Mapping):
            return cls.from_mapping(item)
        raise TypeError(f"Unsupported TOC item type: {type(item)!r}")

    def with_title(self, title: str) -> "TocItem":
        """Return a shallow copy with a different display title."""
        return replace(self, title=title)

    def first_descendant_href(self) -> str:
        """Return the first link target below this item, if any."""
        if self.href:
            return self.href

        for child in self.children:
            href = child.first_descendant_href()
            if href:
                return href

        return "#"


@dataclass(frozen=True)
class RenderedFile:
    """A source file rendered as an EPUB XHTML page and TOC entry."""

    html_file: HtmlFile
    toc_item: TocItem


@dataclass
class BuildStats:
    """Counters collected during conversion."""

    processed_files: int = 0
    skipped_files: int = 0
    error_files: int = 0

    def summary(self, output_path: Path) -> str:
        """Return the user-facing conversion summary."""
        return (
            "Project conversion complete:\n"
            f"- Processed {self.processed_files} files\n"
            f"- Skipped {self.skipped_files} files\n"
            f"- Errors in {self.error_files} files\n"
            f"- Output: {output_path}"
        )
