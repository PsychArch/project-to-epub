"""Project filesystem scanning and ignore handling."""

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import pathspec
import pygments
from pygments import lexers

from project_to_epub.config import ConversionConfig
from project_to_epub.models import FileEntry

logger = logging.getLogger(__name__)


def detect_language(file_path: Path) -> Optional[str]:
    """Return the language for a file that should be included, if recognized."""
    ext = file_path.suffix.lower()
    if ext in {".md", ".markdown"}:
        return "markdown"

    try:
        return lexers.get_lexer_for_filename(file_path).name
    except pygments.util.ClassNotFound:
        return None


class ProjectScanner:
    """Scans a project directory for EPUB-eligible files."""

    def __init__(self, root_dir: Path, config: ConversionConfig):
        self.root_dir = root_dir
        self.config = config
        self.skipped_files = 0
        self.gitignore_specs = self._load_gitignore_specs()
        self.gitignore_spec = self.gitignore_specs[0][1]

    def _load_gitignore(self, gitignore_path: Path) -> pathspec.PathSpec:
        """Load a single .gitignore spec."""
        patterns = []

        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as file:
                    patterns.extend(file.readlines())
            except Exception as e:
                logger.warning(f"Could not read .gitignore at {gitignore_path}: {e}")

        return pathspec.GitIgnoreSpec.from_lines(patterns)

    def _load_gitignore_specs(self) -> List[Tuple[Path, pathspec.PathSpec]]:
        """Load root and nested .gitignore specs with their base directories."""
        specs = [(self.root_dir, self._load_gitignore(self.root_dir / ".gitignore"))]

        for root, dirs, files in os.walk(self.root_dir):
            if ".git" in dirs:
                dirs.remove(".git")

            root_path = Path(root)
            if root_path == self.root_dir or ".gitignore" not in files:
                continue

            specs.append((root_path, self._load_gitignore(root_path / ".gitignore")))

        return specs

    def is_ignored(self, path: Path) -> bool:
        """Return True if a path is ignored by gitignore rules."""
        if ".git" in path.parts:
            return True

        for base_dir, spec in self.gitignore_specs:
            try:
                relative_path = path.relative_to(base_dir)
            except ValueError:
                continue

            if spec.match_file(str(relative_path)):
                return True

        return False

    def _is_large_file(self, file_path: Path) -> bool:
        """Return True when a file exceeds the configured large-file threshold."""
        try:
            file_size = file_path.stat().st_size
        except Exception as e:
            logger.warning(f"Error checking file size for {file_path}: {e}")
            return True

        if file_size <= self.config.large_file_threshold_bytes:
            return False

        size_mb = file_size / 1024 / 1024
        if self.config.skip_large_files:
            logger.warning(f"Skipping large file ({size_mb:.2f} MB): {file_path}")
            self.skipped_files += 1
            return True

        logger.warning(f"Including large file ({size_mb:.2f} MB): {file_path}")
        return False

    def scan_files(self) -> List[FileEntry]:
        """Scan the project directory for files to include in the EPUB."""
        files_to_include: List[FileEntry] = []
        self.skipped_files = 0

        for root, dirs, files in os.walk(self.root_dir):
            root_path = Path(root)

            if ".git" in dirs:
                dirs.remove(".git")

            dirs[:] = [d for d in dirs if not self.is_ignored(root_path / d)]
            dirs.sort()
            files.sort()

            for file in files:
                file_path = root_path / file

                if self.is_ignored(file_path):
                    logger.debug(f"Skipping ignored file: {file_path}")
                    continue

                language = detect_language(file_path)
                if language is None:
                    logger.debug(f"Skipping non-code file: {file_path}")
                    continue

                if self._is_large_file(file_path):
                    continue

                files_to_include.append(
                    FileEntry(
                        absolute_path=file_path,
                        relative_path=file_path.relative_to(self.root_dir),
                        language=language,
                    )
                )

        logger.info(f"Found {len(files_to_include)} files to include in the EPUB")
        return files_to_include
