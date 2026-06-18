"""
Command-line interface for project-to-epub.
"""

import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from project_to_epub import __version__
from project_to_epub.config import DEFAULT_CONFIG, ConversionConfig
from project_to_epub.converter import convert_project_to_epub

app = typer.Typer(
    help=(
        "Convert a software project directory into an EPUB file for offline "
        "code reading."
    )
)


def version_callback(value: bool):
    """Print the version and exit."""
    if value:
        typer.echo(f"project-to-epub version: {__version__}")
        raise typer.Exit()


def configure_logging(log_level: str) -> None:
    """Configure logging from a CLI log-level value."""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        typer.echo(f"Invalid log level: {log_level}", err=True)
        raise typer.Exit(code=1)
    logging.basicConfig(level=numeric_level, format="%(levelname)s: %(message)s")


def resolve_input_directory(input_directory: Optional[Path]) -> Path:
    """Resolve and validate the input directory."""
    if input_directory is None:
        input_directory = Path.cwd()
        logging.info(
            f"No input directory specified, using current directory: {input_directory}"
        )

    resolved_directory = input_directory.resolve()
    if not resolved_directory.exists() or not resolved_directory.is_dir():
        error_message = (
            f"Error: Input directory '{resolved_directory}' does not exist or "
            "is not a directory"
        )
        typer.echo(error_message, err=True)
        raise typer.Exit(code=1)

    return resolved_directory


def resolve_output_path(input_directory: Path, output: Optional[Path]) -> Path:
    """Resolve the final EPUB output path."""
    folder_name = input_directory.name
    if output is None:
        return Path.cwd() / f"{folder_name}.epub"
    if output.is_dir():
        return output / f"{folder_name}.epub"
    return output


def build_config_from_cli(
    theme: Optional[str],
    title: Optional[str],
    author: Optional[str],
    limit_mb: Optional[float],
    no_skip_large: bool,
    hierarchical_toc: bool,
) -> ConversionConfig:
    """Build conversion config from CLI options."""
    config = {
        **DEFAULT_CONFIG,
        "epub_metadata": dict(DEFAULT_CONFIG["epub_metadata"]),
        "theme": theme,
        "title": title,
        "author": author,
        "large_file_threshold_mb": (
            limit_mb
            if limit_mb is not None
            else DEFAULT_CONFIG["large_file_threshold_mb"]
        ),
        "skip_large_files": not no_skip_large,
        "flat_toc": not hierarchical_toc,
    }
    return ConversionConfig.from_mapping(config)


@app.command()
def main(
    input_directory: Annotated[
        Optional[Path], typer.Argument(help="Path to the project directory to convert")
    ] = None,
    output: Annotated[
        Optional[Path], typer.Option("-o", "--output", help="Output EPUB file path")
    ] = None,
    theme: Annotated[
        Optional[str],
        typer.Option(help="Syntax highlighting theme (e.g., default_eink, monokai)"),
    ] = None,
    log_level: Annotated[
        str, typer.Option(help="Log level (DEBUG, INFO, WARNING, ERROR)")
    ] = "INFO",
    title: Annotated[
        Optional[str],
        typer.Option(help="Set EPUB title (defaults to project directory name)"),
    ] = None,
    author: Annotated[Optional[str], typer.Option(help="Set EPUB author")] = None,
    limit_mb: Annotated[
        Optional[float], typer.Option(help="Set large file threshold in MB")
    ] = None,
    no_skip_large: Annotated[
        bool,
        typer.Option("--no-skip-large", help="Include large files instead of skipping"),
    ] = False,
    hierarchical_toc: Annotated[
        bool,
        typer.Option(
            "--hierarchical-toc", help="Use hierarchical TOC instead of flat TOC"
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=version_callback, help="Show version and exit"
        ),
    ] = False,
):
    """
    Convert a software project directory into an EPUB file for offline code reading.

    This tool creates an EPUB that preserves your project structure in the
    table of contents, applies syntax highlighting to code files, and respects
    .gitignore rules.
    """
    configure_logging(log_level)
    input_directory = resolve_input_directory(input_directory)
    output = resolve_output_path(input_directory, output)
    config = build_config_from_cli(
        theme,
        title,
        author,
        limit_mb,
        no_skip_large,
        hierarchical_toc,
    )

    try:
        result = convert_project_to_epub(input_directory, output, config)
        typer.echo(result)
    except Exception as e:
        typer.echo(f"Error during conversion: {e}", err=True)
        logging.error(f"Conversion failed: {e}", exc_info=True)
        raise typer.Exit(code=1)


# Entry point for the command-line script
def run_cli():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    app()
