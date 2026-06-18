"""Source rendering and EPUB page styling."""

import logging
from html import escape
from pathlib import Path
from typing import Optional

try:
    from importlib.resources import files
except ImportError:  # pragma: no cover - Python 3.8 fallback
    from importlib.resources import read_text

    files = None

import markdown
import pygments
from pygments import lexers
from pygments.formatters import HtmlFormatter
from pygments.style import Style
from pygments.token import Comment, Generic, Keyword, Name, Operator

from project_to_epub.models import FileEntry

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


def create_highlight_formatter(theme_name: str) -> HtmlFormatter:
    """
    Create a Pygments HTML formatter with the specified theme.

    Args:
        theme_name: Name of the syntax highlighting theme

    Returns:
        HtmlFormatter: Pygments HTML formatter
    """
    if theme_name == "default_eink":
        return HtmlFormatter(
            style=EInkMonochromeStyle,
            cssclass="highlight",
            linenos=True,
            full=False,
            noclasses=True,
            nobackground=True,
        )

    try:
        return HtmlFormatter(
            style=theme_name,
            cssclass="highlight",
            linenos=True,
            full=False,
            noclasses=True,
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
    if files is not None:
        return (files("project_to_epub") / "style.css").read_text(encoding="utf-8")

    return read_text("project_to_epub", "style.css", encoding="utf-8")


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
            highlighted = f'<pre class="highlight">{escape(content)}</pre>'
        return highlighted
    except Exception as e:
        logger.error(f"Error highlighting code with {lexer.name}: {e}")
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
        return f'<pre class="markdown-error">{escape(content)}</pre>'


def render_source_content(
    file_entry: FileEntry,
    content: str,
    formatter: HtmlFormatter,
) -> str:
    """Render a source file as an HTML fragment."""
    if file_entry.language == "markdown":
        return render_markdown(content, formatter)

    try:
        lexer = lexers.get_lexer_for_filename(str(file_entry.absolute_path))
    except pygments.util.ClassNotFound:
        lexer = lexers.get_lexer_by_name("text")

    return highlight_code(content, lexer, formatter)


def render_file_xhtml(relative_path: Path, html_content: str) -> str:
    """Render a complete XHTML page for one project file."""
    escaped_relative_path = escape(str(relative_path), quote=True)
    return f"""<?xml version="1.0" encoding="utf-8"?>
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
</html>"""
