"""
Core functionality to convert a project directory to EPUB.
"""

import logging
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import markdown  # Add markdown import
import pathspec
import pygments
from pygments import lexers
from pygments.formatters import HtmlFormatter

logger = logging.getLogger(__name__)


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
        self.gitignore_spec = self._load_gitignore()

    def _load_gitignore(self) -> pathspec.PathSpec:
        """
        Load .gitignore specs from project files.

        Returns:
            pathspec.PathSpec: A compiled spec for matching paths
        """
        patterns = []

        # Start with .gitignore at the root
        gitignore_path = self.root_dir / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    patterns.extend(f.readlines())
            except Exception as e:
                logger.warning(f"Could not read .gitignore at {gitignore_path}: {e}")

        # TODO: Add support for scanning nested .gitignore files

        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, patterns
        )

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

        # Convert absolute path to relative path from project root
        relative_path = path.relative_to(self.root_dir)
        # Check if the path matches any gitignore pattern
        return self.gitignore_spec.match_file(str(relative_path))

    def scan_files(self) -> List["FileEntry"]:
        """
        Scan the project directory for files to include in the EPUB.

        Returns:
            List[FileEntry]: List of file entries to include
        """
        self.files = []

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

            # Filter dirs based on gitignore (modify dirs in-place to skip walking ignored dirs)
            dirs[:] = [d for d in dirs if not self.is_ignored(root_path / d)]

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
                    relative_path = file_path.relative_to(self.root_dir)
                    self.files.append(FileEntry(file_path, relative_path, "markdown"))
                    continue

                # Try to get lexer for code files
                try:
                    lexer = lexers.get_lexer_for_filename(file_path)

                    # Check file size
                    try:
                        file_size = file_path.stat().st_size
                        if file_size > large_file_threshold:
                            if self.config.get("skip_large_files", True):
                                logger.warning(
                                    f"Skipping large file ({file_size / 1024 / 1024:.2f} MB): {file_path}"
                                )
                                continue
                            else:
                                logger.warning(
                                    f"Including large file ({file_size / 1024 / 1024:.2f} MB): {file_path}"
                                )
                    except Exception as e:
                        logger.warning(f"Error checking file size for {file_path}: {e}")
                        continue

                    # Add to list of files to include
                    relative_path = file_path.relative_to(self.root_dir)
                    self.files.append(FileEntry(file_path, relative_path, lexer.name))

                except pygments.util.ClassNotFound:
                    # Not a recognized code file
                    logger.debug(f"Skipping non-code file: {file_path}")
                    continue

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
        # Create a high-contrast formatter for e-ink
        return HtmlFormatter(
            style="default",
            cssclass="highlight",
            linenos=False,  # Remove line numbers for better e-ink display
            full=False,
            noclasses=True,
            nobackground=True,
        )

    # Use a standard theme
    try:
        return HtmlFormatter(
            style=theme_name,
            cssclass="highlight",
            linenos=False,  # Remove line numbers for better e-ink display
            full=False,
            noclasses=True,  # Inline styles for better compatibility
        )
    except pygments.util.ClassNotFound:
        logger.warning(f"Theme '{theme_name}' not found, falling back to 'default'")
        return HtmlFormatter(
            style="default",
            cssclass="highlight",
            linenos=False,  # Remove line numbers for better e-ink display
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
        font-family: monospace;
        font-size: 0.9em;
        line-height: 1.5;
        overflow-x: auto;
        background-color: #f8f8f8;
        border: 1px solid #e1e1e8;
        border-radius: 3px;
    }

    .filepath {
        font-weight: bold;
        padding: 0.5em;
        margin-bottom: 0.5em;
        border-bottom: 1px solid #ccc;
    }

    .highlight {
        background-color: #FFFFFF;
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
        color: #333;
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
        background-color: #f0f0f0;
        padding: 0.2em 0.4em;
        border-radius: 3px;
        font-family: monospace;
    }

    .markdown-content pre {
        background-color: #f8f8f8;
        padding: 1em;
        border-radius: 5px;
        overflow-x: auto;
        margin-bottom: 1em;
    }

    .markdown-content blockquote {
        border-left: 4px solid #ccc;
        padding-left: 1em;
        margin-left: 0;
        color: #555;
    }

    .markdown-content table {
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 1em;
    }

    .markdown-content th,
    .markdown-content td {
        border: 1px solid #ccc;
        padding: 0.5em;
        text-align: left;
    }

    .markdown-content img {
        max-width: 100%;
        height: auto;
    }
    """


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
            highlighted = f"<pre class='highlight'>{content}</pre>"
        return highlighted
    except Exception as e:
        logger.error(f"Error highlighting code with {lexer.name}: {e}")
        # Provide a fallback on exception
        return f"<pre class='highlight'>{content}</pre>"


def render_markdown(content: str) -> str:
    """
    Render Markdown content to HTML.

    Args:
        content: Markdown content

    Returns:
        str: HTML content
    """
    try:
        # Use the Python Markdown library to convert markdown to HTML
        html = markdown.markdown(
            content,
            extensions=["tables", "fenced_code", "codehilite"],
            output_format="html",
        )
        return f"<div class='markdown-content'>{html}</div>"
    except Exception as e:
        logger.error(f"Error rendering Markdown: {e}")
        # Provide a fallback on exception
        return f"<pre class='markdown-error'>{content}</pre>"


def organize_toc_items_by_directory(toc_items: List[Dict[str, str]]) -> List[Dict]:
    """
    Organize TOC items hierarchically based on directory structure.

    Args:
        toc_items: Flat list of TOC items

    Returns:
        List[Dict]: Hierarchical TOC items with children for subdirectories
    """
    # Start with intro and other non-file items
    result = [
        item for item in toc_items if not item.get("href", "").startswith("file_")
    ]

    # Group file items by directory
    directory_structure = {}

    for item in toc_items:
        if not item.get("href", "").startswith("file_"):
            continue

        title = item.get("title", "")
        parts = Path(title).parts

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
    Generate the NCX file content for EPUB Table of Contents with hierarchical structure.

    Args:
        toc_items: List of dictionaries with hierarchical TOC structure
        title: Title of the EPUB
        identifier: Unique identifier for the EPUB

    Returns:
        str: NCX file content
    """
    ncx_content = [
        f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="{identifier}"/>
        <meta name="dtb:depth" content="3"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle>
        <text>{title}</text>
    </docTitle>
    <navMap>"""
    ]

    play_order = 1

    # Recursive function to process hierarchical items
    def add_nav_point(item, level=0):
        nonlocal play_order
        current_play_order = play_order
        play_order += 1

        indent = "    " * (level + 2)

        # If it's a directory (has children)
        if item.get("is_directory", False):
            # For directories without direct content link
            nav_content = f"""{indent}<navPoint id="{item['id']}" playOrder="{current_play_order}">
{indent}    <navLabel>
{indent}        <text>{item['title']}</text>
{indent}    </navLabel>
{indent}    <content src="{item['children'][0].get('href', '#')}"/>
"""
            ncx_content.append(nav_content)

            # Process children
            for child in item.get("children", []):
                add_nav_point(child, level + 1)

            ncx_content.append(f"{indent}</navPoint>")
        else:
            # For regular file items
            if "href" in item:
                nav_content = f"""{indent}<navPoint id="{item['id']}" playOrder="{current_play_order}">
{indent}    <navLabel>
{indent}        <text>{item['title']}</text>
{indent}    </navLabel>
{indent}    <content src="{item['href']}"/>
{indent}</navPoint>"""
                ncx_content.append(nav_content)

    # Process all items
    for item in toc_items:
        add_nav_point(item)

    ncx_content.append(
        """    </navMap>
</ncx>"""
    )

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
    nav_content = [
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1 class="toc-title">Table of Contents</h1>
        <ol class="toc-list">"""
    ]

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
                    f"{indent}<li><span class='toc-directory'>{item['title']}</span>"
                )
                nav_content.append(f"{indent}    <ol>")
                add_toc_items(item["children"], level + 1)
                nav_content.append(f"{indent}    </ol>")
                nav_content.append(f"{indent}</li>")
            # Regular file item
            elif "href" in item:
                nav_content.append(
                    f'{indent}<li><a href="{item["href"]}">{item["title"]}</a></li>'
                )

    # Process all items
    add_toc_items(toc_items)

    nav_content.append(
        """        </ol>
    </nav>
</body>
</html>"""
    )

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

    # Get metadata
    metadata = config.get("epub_metadata", {})
    title = config.get("title") or metadata.get("title") or input_dir.name
    author = config.get("author") or metadata.get("author") or "Project-to-EPUB Tool"
    language = metadata.get("language", "en")

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
            f.write(
                """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
            )

        # Add CSS file
        css_content = get_css_for_epub()
        with open(epub_dir / "style.css", "w", encoding="utf-8") as f:
            f.write(css_content)

        # Process each file and create HTML files
        html_files = []
        toc_items = []

        # Create intro page
        intro_file = "intro.xhtml"
        with open(epub_dir / intro_file, "w", encoding="utf-8") as f:
            f.write(
                f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Introduction</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <h1>{title}</h1>
    <p>This EPUB was generated from project directory: {input_dir}</p>
    <p>Contains {len(project.files)} files.</p>
</body>
</html>"""
            )
        html_files.append({"id": "intro", "file": intro_file, "title": "Introduction"})
        toc_items.append({"id": "intro", "title": "Introduction", "href": intro_file})

        # Process files
        for i, file_entry in enumerate(project.files):
            try:
                # Read file content
                content = project.get_file_content(file_entry)
                if content is None:
                    logger.warning(
                        f"Skipping file due to read error: {file_entry.relative_path}"
                    )
                    error_files += 1
                    continue

                # Create HTML content based on file type
                if file_entry.language == "markdown":
                    # Process markdown files
                    html_content = render_markdown(content)
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

                with open(epub_dir / file_name, "w", encoding="utf-8") as f:
                    f.write(
                        f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{file_entry.relative_path}</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <h1>{file_entry.relative_path}</h1>
    {html_content}
</body>
</html>"""
                    )

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
                    }
                )

                processed_files += 1
                logger.debug(f"Processed file: {file_entry.relative_path}")

            except Exception as e:
                logger.error(f"Error processing file {file_entry.relative_path}: {e}")
                error_files += 1
                continue

        # Organize TOC items hierarchically based on directory structure
        hierarchical_toc_items = organize_toc_items_by_directory(toc_items)

        # Create EPUB 3 navigation document (nav.xhtml)
        nav_file = "nav.xhtml"
        nav_content = generate_nav_xhtml(hierarchical_toc_items, title)
        with open(epub_dir / nav_file, "w", encoding="utf-8") as f:
            f.write(nav_content)

        # Create NCX file for backwards compatibility with EPUB 2 readers
        ncx_file = "toc.ncx"
        ncx_content = generate_toc_ncx(hierarchical_toc_items, title, identifier)
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
                f'<item id="ncx" href="{ncx_file}" media-type="application/x-dtbncx+xml"/>'
            )
            manifest_items.append(
                f'<item id="nav" href="{nav_file}" media-type="application/xhtml+xml" properties="nav"/>'
            )

            # Add HTML files
            for html_file in html_files:
                manifest_items.append(
                    f'<item id="{html_file["id"]}" href="{html_file["file"]}" '
                    f'media-type="application/xhtml+xml"/>'
                )
                spine_items.append(f'<itemref idref="{html_file["id"]}"/>')

            opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="uid">{identifier}</dc:identifier>
        <dc:title>{title}</dc:title>
        <dc:creator>{author}</dc:creator>
        <dc:language>{language}</dc:language>
        <meta property="dcterms:modified">{os.urandom(4).hex()}</meta>
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
                    temp_path / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED
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
