"""Tests for the command-line interface."""

from typer.testing import CliRunner

from project_to_epub.cli import app


def test_help_uses_intended_boolean_flag_names():
    """Boolean flags should not expose double-negative option names."""
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--no-skip-large" in result.stdout
    assert "--no-no-skip-large" not in result.stdout
    assert "--hierarchical-toc" in result.stdout
    assert "--no-hierarchical-toc" not in result.stdout
