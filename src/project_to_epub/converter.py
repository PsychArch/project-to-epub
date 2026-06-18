"""
Core functionality to convert a project directory to EPUB.
"""

import logging
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import markdown
import pathspec
import pygments
import typer
from pygments import lexers
from pygments.formatters import HtmlFormatter
from pygments.style import Style
from pygments.token import Comment, Generic, Keyword, Name, Operator

logger = logging.getLogger(__name__)


class EInkMonochromeStyle(Style):
    """Pygments style that preserves syntax cues without color."""

    background_color = "#FFFFFF"
    default_style = ""
    styles = {
        Comment: "italic",
        Generic.Deleted: "underline",
        Generic.Emph: "italic",
        Generic.Error: "bold underline",
        Generic.Heading: "bold",
        Generic.Inserted: "bold",
        Generic.Strong: "bold",
        Generic.Subheading: "bold",
        Keyword: "bold",
        Name.Class: "bold",
        Name.Function: "bold",
        Name.Namespace: "bold",
        Operator.Word: "bold",
    }


class Project:
    """Represents a project to be converted to EPUB."""

    def __init__(self, root_dir: Path, config: Dict[str, Any]):
        """
        Initialize a Project instance.

        Args:
            root_dir: Path to the project root directory
            config: Configuration dictionary
        """
        self.root_dir = root_dir
        self.config = config
        self.files = []  # Will contain FileEntry objects
        self.skipped_files = 0
        self.gitignore_specs = self._load_gitignore_specs()
        self.gitignore_spec = self.gitignore_specs[0][1]

    def _load_gitignore(self, gitignore_path: Path) -> pathspec.PathSpec:
        """
        Load a single .gitignore spec.

        Returns:
            pathspec.PathSpec: A compiled spec for matching paths
        """
        patterns = []

        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    patterns.extend(f.readlines())
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
        """
        Check if a path is ignored by gitignore rules.

        Args:
            path: Path to check (absolute)

        Returns:
            bool: True if the path is ignored
        """
        # Always ignore .git directory
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

    def _is_large_file(self, file_path: Path, threshold_bytes: float) -> bool:
        """Return True when a file exceeds the configured large-file threshold."""
        try:
            file_size = file_path.stat().st_size
        except Exception as e:
            logger.warning(f"Error checking file size for {file_path}: {e}")
            return True

        if file_size <= threshold_bytes:
            return False

        size_mb = file_size / 1024 / 1024
        if self.config.get("skip_large_files", True):
            logger.warning(f"Skipping large file ({size_mb:.2f} MB): {file_path}")
            self.skipped_files += 1
            return True

        logger.warning(f"Including large file ({size_mb:.2f} MB): {file_path}")
        return False

    def scan_files(self) -> List["FileEntry"]:
        """
        Scan the project directory for files to include in the EPUB.

        Returns:
            List[FileEntry]: List of file entries to include
        """
        self.files = []
        self.skipped_files = 0

        # Get the large file threshold in bytes
        large_file_threshold = (
            self.config.get("large_file_threshold_mb", 10) * 1024 * 1024
        )

        for root, dirs, files in os.walk(self.root_dir):
            # Convert to Path objects
            root_path = Path(root)

            # Filter out .git directory
            if ".git" in dirs:
                dirs.remove(".git")

            # Filter dirs in-place to avoid walking ignored directories.
            dirs[:] = [d for d in dirs if not self.is_ignored(root_path / d)]

            # Sort directories alphabetically
            dirs.sort()

            # Sort files alphabetically
            files.sort()

            # Process files
            for file in files:
                file_path = root_path / file

                # Skip ignored files
                if self.is_ignored(file_path):
                    logger.debug(f"Skipping ignored file: {file_path}")
                    continue

                # Get file extension and check if it's a recognized code file
                ext = file_path.suffix.lower()

                # Special handling for Markdown files
                if ext == ".md" or ext == ".markdown":
                    language = "markdown"
                else:
                    # Try to get lexer for code files
                    try:
                        language = lexers.get_lexer_for_filename(file_path).name
                    except pygments.util.ClassNotFound:
                        # Not a recognized code file
                        logger.debug(f"Skipping non-code file: {file_path}")
                        continue

                if self._is_large_file(file_path, large_file_threshold):
                    continue

                # Add to list of files to include
                relative_path = file_path.relative_to(self.root_dir)
                self.files.append(FileEntry(file_path, relative_path, language))

        logger.info(f"Found {len(self.files)} files to include in the EPUB")
        return self.files

    def get_file_content(self, file_entry: "FileEntry") -> Optional[str]:
        """
        Read the content of a file.

        Args:
            file_entry: FileEntry object representing the file

        Returns:
            Optional[str]: The file content, or None if reading failed
        """
        try:
            with open(
                file_entry.absolute_path, "r", encoding="utf-8", errors="replace"
            ) as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_entry.absolute_path}: {e}")
            return None


class FileEntry:
    """Represents a file to be included in the EPUB."""

    def __init__(self, absolute_path: Path, relative_path: Path, language: str):
        """
        Initialize a FileEntry instance.

        Args:
            absolute_path: Absolute path to the file
            relative_path: Path relative to the project root
            language: Detected language name for syntax highlighting
        """
        self.absolute_path = absolute_path
        self.relative_path = relative_path
        self.language = language
        self.content = None
        self.highlighted_content = None

    def __str__(self) -> str:
        return f"{self.relative_path} ({self.language})"


def create_highlight_formatter(theme_name: str) -> HtmlFormatter:
    """
    Create a Pygments HTML formatter with the specified theme.

    Args:
        theme_name: Name of the syntax highlighting theme

    Returns:
        HtmlFormatter: Pygments HTML formatter
    """
    # Handle the special default_eink theme
    if theme_name == "default_eink":
        return HtmlFormatter(
            style=EInkMonochromeStyle,
            cssclass="highlight",
            linenos=True,
            full=False,
            noclasses=True,
            nobackground=True,
        )

    # Use a standard theme
    try:
        return HtmlFormatter(
            style=theme_name,
            cssclass="highlight",
            linenos=True,
            full=False,
            noclasses=True,  # Inline styles for better compatibility
        )
    except pygments.util.ClassNotFound:
        logger.warning(f"Theme '{theme_name}' not found, falling back to 'default'")
        return HtmlFormatter(
            style="default",
            cssclass="highlight",
            linenos=True,
            full=False,
            noclasses=True,
        )


def get_css_for_epub() -> str:
    """
    Get base CSS for EPUB styling.

    Returns:
        str: CSS content
    """
    return """
    body {
        margin: 0;
        padding: 1em;
        background-color: #FFFFFF;
        color: #000000;
        font-family: monospace;
    }

    h1 {
        font-size: 1.5em;
        margin: 0.5em 0;
    }

    pre {
        margin: 0;
        padding: 0.5em;
        white-space: pre-wrap;
        word-wrap: break-word;
        overflow-wrap: anywhere;
        font-family: monospace;
        font-size: 0.9em;
        line-height: 1.5;
        tab-size: 4;
        background-color: #FFFFFF;
        color: #000000;
        border: 1px solid #000000;
        border-radius: 0;
    }

    .filepath {
        font-weight: bold;
        padding: 0.5em;
        margin-bottom: 0.5em;
        border-bottom: 1px solid #000000;
    }

    .highlight,
    .codehilite {
        background-color: #FFFFFF;
        color: #000000;
    }

    .highlighttable,
    .codehilitetable {
        border: 1px solid #000000;
        border-collapse: collapse;
        width: 100%;
    }

    .highlighttable td,
    .codehilitetable td {
        padding: 0;
        vertical-align: top;
    }

    .highlighttable pre,
    .codehilitetable pre {
        border: none;
        margin: 0;
    }

    .linenos {
        border-right: 1px solid #000000;
        user-select: none;
        white-space: nowrap;
        width: auto;
    }

    .linenodiv {
        white-space: nowrap;
    }

    .linenos pre {
        overflow-wrap: normal;
        padding: 0.5em 0;
        text-align: right;
        white-space: pre;
        word-wrap: normal;
    }

    .linenos span {
        padding-left: 0.2em !important;
        padding-right: 0.35em !important;
    }

    .toc-title {
        font-size: 2em;
        margin-bottom: 1em;
    }

    .toc-list {
        list-style-type: none;
        padding-left: 1em;
    }

    .toc-list li {
        margin-bottom: 0.5em;
    }

    .toc-section {
        font-weight: bold;
        margin-top: 1em;
    }

    .toc-directory {
        font-weight: bold;
        color: inherit;
    }

    /* Markdown specific styles */
    .markdown-content {
        font-family: serif;
        line-height: 1.6;
    }

    .markdown-content h1,
    .markdown-content h2,
    .markdown-content h3,
    .markdown-content h4,
    .markdown-content h5,
    .markdown-content h6 {
        margin-top: 1em;
        margin-bottom: 0.5em;
    }

    .markdown-content p {
        margin-bottom: 1em;
    }

    .markdown-content ul,
    .markdown-content ol {
        padding-left: 2em;
        margin-bottom: 1em;
    }

    .markdown-content li {
        margin-bottom: 0.5em;
    }

    .markdown-content code {
        background-color: #FFFFFF;
        padding: 0.2em 0.4em;
        border: 1px solid #000000;
        border-radius: 0;
        font-family: monospace;
    }

    .markdown-content pre {
        background-color: #FFFFFF;
        color: #000000;
        padding: 1em;
        border-radius: 0;
        margin-bottom: 1em;
        border: 1px solid #000000;
    }

    .markdown-content blockquote {
        border-left: 4px solid #000000;
        padding-left: 1em;
        margin-left: 0;
        color: inherit;
    }

    .markdown-content table {
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 1em;
    }

    .markdown-content th,
    .markdown-content td {
        border: 1px solid #000000;
        padding: 0.5em;
        text-align: left;
    }

    .markdown-content img {
        max-width: 100%;
        height: auto;
    }
    """


def flatten_toc_items(toc_items: List[Dict[str, str]]) -> List[Dict]:
    """
    Flatten TOC items while preserving hierarchical naming.

    This creates a flat (non-nested) TOC structure but keeps the directory names
    as part of the file names in the TOC entries.

    Args:
        toc_items: List of dictionaries with hierarchical TOC structure

    Returns:
        List[Dict]: Flattened TOC items
    """
    # Start with non-file items (like TOC page)
    result = [item for item in toc_items if not item.get("is_directory", False)]

    # Recursive function to flatten the hierarchy
    def process_items(items, parent_path=""):
        for item in items:
            if item.get("is_directory", False) and "children" in item:
                # For directories, process their children
                current_path = (
                    f"{parent_path}/{item['title']}" if parent_path else item["title"]
                )
                process_items(item["children"], current_path)
            elif "href" in item and not item.get("is_directory", False):
                # For files, add them to the result with the parent path in the title
                # Only modify the title if it's not already a path (like TOC page)
                if parent_path and "/" not in item["title"]:
                    # Create a copy of the item to avoid modifying the original
                    flat_item = item.copy()
                    flat_item["title"] = f"{parent_path}/{item['title']}"
                    result.append(flat_item)
                else:
                    result.append(item)

    # Process all hierarchical items
    for item in toc_items:
        if item.get("is_directory", False) and "children" in item:
            process_items([item])

    return result


def highlight_code(content: str, lexer, formatter: HtmlFormatter) -> str:
    """
    Apply syntax highlighting to code content.

    Args:
        content: Source code content
        lexer: Pygments lexer for the language
        formatter: Pygments HTML formatter

    Returns:
        str: HTML content with syntax highlighting
    """
    try:
        highlighted = pygments.highlight(content, lexer, formatter)
        if not highlighted.strip():
            logger.warning(
                f"Pygments returned empty highlighted content for {lexer.name}"
            )
            # Provide a fallback if highlighting fails
            highlighted = f'<pre class="highlight">{escape(content)}</pre>'
        return highlighted
    except Exception as e:
        logger.error(f"Error highlighting code with {lexer.name}: {e}")
        # Provide a fallback on exception
        return f'<pre class="highlight">{escape(content)}</pre>'


def render_markdown(content: str, formatter: Optional[HtmlFormatter] = None) -> str:
    """
    Render Markdown content to HTML.

    Args:
        content: Markdown content
        formatter: Pygments formatter to use for fenced code blocks

    Returns:
        str: HTML content
    """
    if formatter is None:
        formatter = create_highlight_formatter("default_eink")

    try:
        # Use the Python Markdown library to convert markdown to HTML
        html = markdown.markdown(
            content,
            extensions=["tables", "fenced_code", "codehilite"],
            extension_configs={
                "codehilite": {
                    "linenums": formatter.linenos,
                    "noclasses": formatter.noclasses,
                    "pygments_style": formatter.style,
                }
            },
            output_format="xhtml",
        )
        return f"<div class='markdown-content'>{html}</div>"
    except Exception as e:
        logger.error(f"Error rendering Markdown: {e}")
        # Provide a fallback on exception
        return f'<pre class="markdown-error">{escape(content)}</pre>'


def epub_timestamp() -> str:
    """Return the current UTC timestamp in EPUB metadata format."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def xml_escape(value: object) -> str:
    """Escape text or attribute values for generated EPUB XML documents."""
    return escape(str(value), quote=True)


def organize_toc_items_by_directory(toc_items: List[Dict[str, str]]) -> List[Dict]:
    """
    Organize TOC items hierarchically based on directory structure.

    Args:
        toc_items: Flat list of TOC items

    Returns:
        List[Dict]: Hierarchical TOC items with children for subdirectories
    """
    # Start with non-file items (like TOC page)
    result = [item for item in toc_items if not item.get("path", "").strip()]

    # Group file items by directory
    directory_structure = {}

    for item in toc_items:
        # Skip items without path (like TOC page)
        if not item.get("path", "").strip():
            continue

        path = item.get("path", "")
        parts = Path(path).parts

        # Process only file items with path information
        if len(parts) <= 1:
            # Root level file
            result.append(item)
            continue

        # Build directory structure
        current_level = directory_structure
        for i, part in enumerate(parts[:-1]):  # All parts except the filename
            if part not in current_level:
                current_level[part] = {"files": [], "dirs": {}}

            if i == len(parts) - 2:  # Last directory before filename
                current_level[part]["files"].append(item)
            else:
                current_level = current_level[part]["dirs"]

    # Convert directory structure to hierarchical items
    dir_id_counter = 0

    def process_directory(dir_name, dir_content, parent_path=""):
        nonlocal dir_id_counter
        current_path = f"{parent_path}/{dir_name}" if parent_path else dir_name
        dir_id = f"dir_{dir_id_counter}"
        dir_id_counter += 1

        # Create directory item
        dir_item = {
            "id": dir_id,
            "title": dir_name,
            "is_directory": True,
            "children": [],
        }

        # Add files in this directory
        for file_item in dir_content["files"]:
            dir_item["children"].append(file_item)

        # Process subdirectories
        for subdir_name, subdir_content in dir_content["dirs"].items():
            subdir_item = process_directory(subdir_name, subdir_content, current_path)
            dir_item["children"].append(subdir_item)

        return dir_item

    # Process top-level directories
    for dir_name, dir_content in directory_structure.items():
        dir_item = process_directory(dir_name, dir_content)
        result.append(dir_item)

    return result


def generate_toc_ncx(toc_items: List[Dict], title: str, identifier: str) -> str:
    """
    Generate the NCX file content for EPUB Table of Contents with
    hierarchical structure.

    Args:
        toc_items: List of dictionaries with hierarchical TOC structure
        title: Title of the EPUB
        identifier: Unique identifier for the EPUB

    Returns:
        str: NCX file content
    """
    ncx_content = [f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="{xml_escape(identifier)}"/>
        <meta name="dtb:depth" content="3"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle>
        <text>{xml_escape(title)}</text>
    </docTitle>
    <navMap>"""]

    def first_descendant_href(item) -> str:
        if item.get("href"):
            return item["href"]

        for child in item.get("children", []):
            href = first_descendant_href(child)
            if href:
                return href

        return "#"

    play_order = 1
    play_order_by_href = {}

    def play_order_for_href(href: str) -> int:
        nonlocal play_order

        if href not in play_order_by_href:
            play_order_by_href[href] = play_order
            play_order += 1

        return play_order_by_href[href]

    # Recursive function to process hierarchical items
    def add_nav_point(item, level=0):
        indent = "    " * (level + 2)

        # If it's a directory (has children)
        if item.get("is_directory", False):
            first_child_href = first_descendant_href(item)
            current_play_order = play_order_for_href(first_child_href)

            nav_point_open = (
                f'{indent}<navPoint id="{item["id"]}" '
                f'playOrder="{current_play_order}">'
            )
            nav_content = f"""{nav_point_open}
{indent}    <navLabel>
{indent}        <text>{xml_escape(item['title'])}</text>
{indent}    </navLabel>
{indent}    <content src="{xml_escape(first_child_href)}"/>
"""
            ncx_content.append(nav_content)

            # Process children
            for child in item.get("children", []):
                add_nav_point(child, level + 1)

            ncx_content.append(f"{indent}</navPoint>")
        else:
            # For regular file items
            if "href" in item:
                current_play_order = play_order_for_href(item["href"])
                nav_point_open = (
                    f'{indent}<navPoint id="{item["id"]}" '
                    f'playOrder="{current_play_order}">'
                )
                nav_content = f"""{nav_point_open}
{indent}    <navLabel>
{indent}        <text>{xml_escape(item['title'])}</text>
{indent}    </navLabel>
{indent}    <content src="{xml_escape(item['href'])}"/>
{indent}</navPoint>"""
                ncx_content.append(nav_content)

    # Process all items
    for item in toc_items:
        add_nav_point(item)

    ncx_content.append("""    </navMap>
</ncx>""")

    return "\n".join(ncx_content)


def generate_nav_xhtml(toc_items: List[Dict], title: str) -> str:
    """
    Generate EPUB3 Navigation Document (nav.xhtml) with hierarchical structure.

    Args:
        toc_items: List of dictionaries with hierarchical TOC structure
        title: Title of the EPUB

    Returns:
        str: nav.xhtml content
    """
    nav_content = ["""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1 class="toc-title">Table of Contents</h1>
        <ol class="toc-list">"""]

    # Recursive function to build nested lists
    def add_toc_items(items, level=0):
        indent = "    " * (level + 3)

        for item in items:
            # If it's a directory with children
            if (
                item.get("is_directory", False)
                and "children" in item
                and item["children"]
            ):
                nav_content.append(
                    f"{indent}<li><span class='toc-directory'>"
                    f"{xml_escape(item['title'])}</span>"
                )
                nav_content.append(f"{indent}    <ol>")
                add_toc_items(item["children"], level + 1)
                nav_content.append(f"{indent}    </ol>")
                nav_content.append(f"{indent}</li>")
            # Regular file item
            elif "href" in item:
                nav_content.append(
                    f'{indent}<li><a href="{xml_escape(item["href"])}">'
                    f'{xml_escape(item["title"])}</a></li>'
                )

    # Process all items
    add_toc_items(toc_items)

    nav_content.append("""        </ol>
    </nav>
</body>
</html>""")

    return "\n".join(nav_content)


def convert_project_to_epub(
    input_dir: Path, output_path: Path, config: Dict[str, Any]
) -> str:
    """
    Convert a project directory to EPUB.

    Args:
        input_dir: Path to the project directory
        output_path: Path where to save the EPUB file
        config: Configuration dictionary

    Returns:
        str: Summary message of the conversion

    Raises:
        Exception: If conversion fails
    """
    # Initialize counters
    processed_files = 0
    skipped_files = 0
    error_files = 0

    # Initialize the project
    project = Project(input_dir, config)

    # Scan for files
    project.scan_files()
    skipped_files = project.skipped_files

    # Get total number of files for progress bar
    total_files = len(project.files)

    # Create a progress bar
    with typer.progressbar(
        length=total_files,
        label="Converting project to EPUB",
        show_eta=True,
        show_pos=True,
    ) as progress:

        # Get metadata
        metadata = config.get("epub_metadata", {})
        title = config.get("title") or metadata.get("title") or input_dir.name
        author = (
            config.get("author") or metadata.get("author") or "Project-to-EPUB Tool"
        )
        language = metadata.get("language", "en")
        publisher = metadata.get("publisher")

        # Generate a unique identifier for the EPUB
        identifier = f"urn:uuid:{uuid.uuid4()}"

        # Set up the highlight formatter
        theme = config.get("theme") or config.get("default_theme", "default_eink")
        formatter = create_highlight_formatter(theme)

        # Create a temporary directory to build the EPUB
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            epub_dir = temp_path / "EPUB"
            meta_inf_dir = temp_path / "META-INF"

            # Create directories
            epub_dir.mkdir()
            meta_inf_dir.mkdir()

            # Add mimetype file (must be first in the ZIP and uncompressed)
            with open(temp_path / "mimetype", "w", encoding="utf-8") as f:
                f.write("application/epub+zip")

            # Add container.xml
            with open(meta_inf_dir / "container.xml", "w", encoding="utf-8") as f:
                f.write("""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="EPUB/content.opf"
            media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>""")

            # Add CSS file
            css_content = get_css_for_epub()
            with open(epub_dir / "style.css", "w", encoding="utf-8") as f:
                f.write(css_content)

            # Process each file and create HTML files
            html_files = []
            toc_items = []

            # Create a dedicated TOC page as the first page
            toc_page_file = "toc_page.xhtml"

            # Process files first
            for i, file_entry in enumerate(project.files):
                try:
                    # Read file content
                    content = project.get_file_content(file_entry)
                    if content is None:
                        read_error_message = (
                            "Skipping file due to read error: "
                            f"{file_entry.relative_path}"
                        )
                        logger.warning(read_error_message)
                        error_files += 1
                        progress.update(1)  # Update progress bar even for skipped files
                        continue

                    # Create HTML content based on file type
                    if file_entry.language == "markdown":
                        # Process markdown files
                        html_content = render_markdown(content, formatter)
                    else:
                        # Process code files with syntax highlighting
                        try:
                            lexer = lexers.get_lexer_for_filename(
                                str(file_entry.absolute_path)
                            )
                        except pygments.util.ClassNotFound:
                            # Fallback to text
                            lexer = lexers.get_lexer_by_name("text")

                        # Apply syntax highlighting
                        html_content = highlight_code(content, lexer, formatter)

                    # Create HTML file
                    file_id = f"file_{i}"
                    file_name = f"{file_id}.xhtml"

                    escaped_relative_path = xml_escape(file_entry.relative_path)
                    with open(epub_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{escaped_relative_path}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <h1>{escaped_relative_path}</h1>
    {html_content}
</body>
</html>""")

                    html_files.append(
                        {
                            "id": file_id,
                            "file": file_name,
                            "title": str(file_entry.relative_path),
                        }
                    )
                    toc_items.append(
                        {
                            "id": file_id,
                            "title": str(file_entry.relative_path),
                            "href": file_name,
                            "path": str(file_entry.relative_path),
                        }
                    )

                    processed_files += 1
                    logger.debug(f"Processed file: {file_entry.relative_path}")

                    # Update progress bar
                    progress.update(1)

                except Exception as e:
                    logger.error(
                        f"Error processing file {file_entry.relative_path}: {e}"
                    )
                    error_files += 1
                    # Update progress bar even for error files
                    progress.update(1)
                    continue

            # Organize TOC items hierarchically based on directory structure
            hierarchical_toc_items = organize_toc_items_by_directory(toc_items)

            # If flat TOC is enabled, flatten the hierarchical TOC
            use_flat_toc = config.get("flat_toc", True)  # Default to True
            if use_flat_toc:
                toc_items_for_display = flatten_toc_items(hierarchical_toc_items)
            else:
                toc_items_for_display = hierarchical_toc_items

            # Function to generate TOC HTML content recursively
            def generate_toc_html(items, level=0):
                indent = "    " * level
                html = []

                for item in items:
                    # If it's a directory with children
                    if (
                        item.get("is_directory", False)
                        and "children" in item
                        and item["children"]
                    ):
                        html.append(
                            f"{indent}<li><span class='toc-directory'>"
                            f"{xml_escape(item['title'])}</span>"
                        )
                        html.append(f"{indent}    <ul>")
                        html.append(generate_toc_html(item["children"], level + 1))
                        html.append(f"{indent}    </ul>")
                        html.append(f"{indent}</li>")
                    # Regular file item
                    elif "href" in item:
                        html.append(
                            f'{indent}<li><a href="{xml_escape(item["href"])}">'
                            f'{xml_escape(item["title"])}</a></li>'
                        )

                return "\n".join(html)

            # Generate TOC HTML content
            toc_html_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <style>
        .toc-directory {{
            font-weight: bold;
        }}
        ul {{
            margin-top: 0.5em;
            margin-bottom: 0.5em;
        }}
        li {{
            margin-bottom: 0.5em;
        }}
    </style>
</head>
<body>
    <h1>Table of Contents</h1>
    <ul class="toc-list">
{generate_toc_html(toc_items_for_display)}
    </ul>
</body>
</html>"""

            with open(epub_dir / toc_page_file, "w", encoding="utf-8") as f:
                f.write(toc_html_content)

            # Add the TOC page to the list of HTML files and TOC items
            # Insert it as the first page
            html_files.insert(
                0,
                {"id": "toc_page", "file": toc_page_file, "title": "Table of Contents"},
            )
            toc_items.insert(
                0,
                {"id": "toc_page", "title": "Table of Contents", "href": toc_page_file},
            )

            # Create EPUB 3 navigation document (nav.xhtml)
            nav_file = "nav.xhtml"
            nav_content = generate_nav_xhtml(toc_items_for_display, title)
            with open(epub_dir / nav_file, "w", encoding="utf-8") as f:
                f.write(nav_content)

            # Create NCX file for backwards compatibility with EPUB 2 readers
            ncx_file = "toc.ncx"
            ncx_content = generate_toc_ncx(toc_items_for_display, title, identifier)
            with open(epub_dir / ncx_file, "w", encoding="utf-8") as f:
                f.write(ncx_content)

            # Create content.opf file
            with open(epub_dir / "content.opf", "w", encoding="utf-8") as f:
                manifest_items = []
                spine_items = []

                # Add CSS
                manifest_items.append(
                    '<item id="style" href="style.css" media-type="text/css"/>'
                )

                # Add NCX and NAV files to manifest
                manifest_items.append(
                    f'<item id="ncx" href="{ncx_file}" '
                    'media-type="application/x-dtbncx+xml"/>'
                )
                manifest_items.append(
                    f'<item id="nav" href="{nav_file}" '
                    'media-type="application/xhtml+xml" properties="nav"/>'
                )

                # Add HTML files
                for html_file in html_files:
                    manifest_items.append(
                        f'<item id="{xml_escape(html_file["id"])}" '
                        f'href="{xml_escape(html_file["file"])}" '
                        f'media-type="application/xhtml+xml"/>'
                    )
                    spine_items.append(
                        f'<itemref idref="{xml_escape(html_file["id"])}"/>'
                    )

                publisher_metadata = ""
                if publisher:
                    publisher_metadata = (
                        "\n        <dc:publisher>"
                        f"{xml_escape(publisher)}</dc:publisher>"
                    )

                opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="uid">{xml_escape(identifier)}</dc:identifier>
        <dc:title>{xml_escape(title)}</dc:title>
        <dc:creator>{xml_escape(author)}</dc:creator>
        <dc:language>{xml_escape(language)}</dc:language>{publisher_metadata}
        <meta property="dcterms:modified">{epub_timestamp()}</meta>
    </metadata>
    <manifest>
        {chr(10).join(manifest_items)}
    </manifest>
    <spine toc="ncx">
        {chr(10).join(spine_items)}
    </spine>
</package>"""

                f.write(opf_content)

            # Create the EPUB (ZIP) file
            try:
                if output_path.exists():
                    output_path.unlink()

                with zipfile.ZipFile(output_path, "w") as epub_zip:
                    # Add mimetype first (must be uncompressed)
                    epub_zip.write(
                        temp_path / "mimetype",
                        "mimetype",
                        compress_type=zipfile.ZIP_STORED,
                    )

                    # Add all other files (compressed)
                    for root, dirs, files in os.walk(temp_path):
                        for file in files:
                            if file == "mimetype":
                                continue  # Already added

                            file_path = Path(root) / file
                            arc_name = str(file_path.relative_to(temp_path))
                            epub_zip.write(
                                file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED
                            )

                logger.info(f"EPUB created successfully at {output_path}")
            except Exception as e:
                logger.error(f"Error creating EPUB file: {e}")
                raise

    # Generate summary message
    summary = (
        f"Project conversion complete:\n"
        f"- Processed {processed_files} files\n"
        f"- Skipped {skipped_files} files\n"
        f"- Errors in {error_files} files\n"
        f"- Output: {output_path}"
    )

    return summary
