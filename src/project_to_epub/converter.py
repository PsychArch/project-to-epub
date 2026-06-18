"""
Core functionality to convert a project directory to EPUB.
"""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple, Union

import typer

from project_to_epub.config import ConversionConfig
from project_to_epub.epub import (
    NAV_FILE,
    NCX_FILE,
    TOC_PAGE_FILE,
    create_epub_workspace,
    write_content_opf,
    write_epub_zip,
    write_text_file,
)
from project_to_epub.models import (
    BuildStats,
    FileEntry,
    HtmlFile,
    RenderedFile,
    TocItem,
)
from project_to_epub.rendering import (
    EInkMonochromeStyle,
    create_highlight_formatter,
    get_css_for_epub,
    highlight_code,
    render_file_xhtml,
    render_markdown,
    render_source_content,
)
from project_to_epub.scanner import ProjectScanner, detect_language
from project_to_epub.toc import (
    flatten_toc_items,
    generate_nav_xhtml,
    generate_toc_ncx,
    generate_toc_page_xhtml,
    organize_toc_items_by_directory,
    select_toc_items_for_display,
    xml_escape,
)

logger = logging.getLogger(__name__)


class Project:
    """Represents a project to be converted to EPUB."""

    def __init__(
        self,
        root_dir: Path,
        config: Union[ConversionConfig, Mapping[str, Any]],
    ):
        """
        Initialize a Project instance.

        Args:
            root_dir: Path to the project root directory
            config: Conversion configuration
        """
        self.root_dir = root_dir
        self.config = ConversionConfig.from_mapping(config)
        self.scanner = ProjectScanner(root_dir, self.config)
        self.files: List[FileEntry] = []
        self.skipped_files = 0
        self.gitignore_specs = self.scanner.gitignore_specs
        self.gitignore_spec = self.scanner.gitignore_spec

    def is_ignored(self, path: Path) -> bool:
        """
        Check if a path is ignored by gitignore rules.

        Args:
            path: Path to check (absolute)

        Returns:
            bool: True if the path is ignored
        """
        return self.scanner.is_ignored(path)

    def scan_files(self) -> List[FileEntry]:
        """
        Scan the project directory for files to include in the EPUB.

        Returns:
            List[FileEntry]: List of file entries to include
        """
        self.files = self.scanner.scan_files()
        self.skipped_files = self.scanner.skipped_files
        return self.files

    def get_file_content(self, file_entry: FileEntry) -> Optional[str]:
        """
        Read the content of a file.

        Args:
            file_entry: FileEntry object representing the file

        Returns:
            Optional[str]: The file content, or None if reading failed
        """
        try:
            with open(
                file_entry.absolute_path,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_entry.absolute_path}: {e}")
            return None


def render_project_file(
    file_entry: FileEntry,
    file_index: int,
    project: Project,
    epub_dir: Path,
    formatter,
) -> Optional[RenderedFile]:
    """Render one scanned file into the EPUB workspace."""
    content = project.get_file_content(file_entry)
    if content is None:
        logger.warning(f"Skipping file due to read error: {file_entry.relative_path}")
        return None

    html_content = render_source_content(file_entry, content, formatter)
    file_id = f"file_{file_index}"
    file_name = f"{file_id}.xhtml"
    write_text_file(
        epub_dir / file_name,
        render_file_xhtml(file_entry.relative_path, html_content),
    )

    return RenderedFile(
        html_file=HtmlFile(
            id=file_id,
            file=file_name,
            title=str(file_entry.relative_path),
        ),
        toc_item=TocItem(
            id=file_id,
            title=str(file_entry.relative_path),
            href=file_name,
            path=str(file_entry.relative_path),
        ),
    )


def render_project_files(
    project: Project,
    epub_dir: Path,
    formatter,
    progress,
) -> Tuple[List[HtmlFile], List[TocItem], BuildStats]:
    """Render all project files into XHTML pages."""
    html_files: List[HtmlFile] = []
    toc_items: List[TocItem] = []
    stats = BuildStats(skipped_files=project.skipped_files)

    for index, file_entry in enumerate(project.files):
        try:
            rendered_file = render_project_file(
                file_entry,
                index,
                project,
                epub_dir,
                formatter,
            )
            if rendered_file is None:
                stats.error_files += 1
                progress.update(1)
                continue

            html_files.append(rendered_file.html_file)
            toc_items.append(rendered_file.toc_item)
            stats.processed_files += 1
            logger.debug(f"Processed file: {file_entry.relative_path}")
            progress.update(1)
        except Exception as e:
            logger.error(f"Error processing file {file_entry.relative_path}: {e}")
            stats.error_files += 1
            progress.update(1)

    return html_files, toc_items, stats


def write_toc_documents(
    epub_dir: Path,
    toc_items_for_display: List[TocItem],
    title: str,
    identifier: str,
) -> HtmlFile:
    """Write TOC page, nav.xhtml, and toc.ncx."""
    write_text_file(
        epub_dir / TOC_PAGE_FILE, generate_toc_page_xhtml(toc_items_for_display)
    )
    write_text_file(
        epub_dir / NAV_FILE, generate_nav_xhtml(toc_items_for_display, title)
    )
    write_text_file(
        epub_dir / NCX_FILE,
        generate_toc_ncx(toc_items_for_display, title, identifier),
    )
    return HtmlFile(id="toc_page", file=TOC_PAGE_FILE, title="Table of Contents")


def convert_project_to_epub(
    input_dir: Path,
    output_path: Path,
    config: Union[ConversionConfig, Mapping[str, Any]],
) -> str:
    """
    Convert a project directory to EPUB.

    Args:
        input_dir: Path to the project directory
        output_path: Path where to save the EPUB file
        config: Configuration dictionary or ConversionConfig

    Returns:
        str: Summary message of the conversion

    Raises:
        Exception: If conversion fails
    """
    settings = ConversionConfig.from_mapping(config)
    metadata = settings.metadata_for_project(input_dir.name)
    identifier = f"urn:uuid:{uuid.uuid4()}"

    project = Project(input_dir, settings)
    project.scan_files()

    with typer.progressbar(
        length=len(project.files),
        label="Converting project to EPUB",
        show_eta=True,
        show_pos=True,
    ) as progress:
        formatter = create_highlight_formatter(settings.theme)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            epub_dir = create_epub_workspace(temp_path, get_css_for_epub())
            html_files, toc_items, stats = render_project_files(
                project,
                epub_dir,
                formatter,
                progress,
            )
            toc_items_for_display = select_toc_items_for_display(
                toc_items,
                settings.flat_toc,
            )
            toc_page = write_toc_documents(
                epub_dir,
                toc_items_for_display,
                metadata.title or input_dir.name,
                identifier,
            )
            write_content_opf(
                epub_dir,
                metadata,
                identifier,
                [toc_page] + html_files,
            )

            try:
                write_epub_zip(temp_path, output_path)
                logger.info(f"EPUB created successfully at {output_path}")
            except Exception as e:
                logger.error(f"Error creating EPUB file: {e}")
                raise

    return stats.summary(output_path)


__all__ = [
    "ConversionConfig",
    "EInkMonochromeStyle",
    "FileEntry",
    "Project",
    "TocItem",
    "convert_project_to_epub",
    "create_highlight_formatter",
    "detect_language",
    "flatten_toc_items",
    "generate_nav_xhtml",
    "generate_toc_ncx",
    "get_css_for_epub",
    "highlight_code",
    "organize_toc_items_by_directory",
    "render_markdown",
    "xml_escape",
]
