"""Tests for the command-line interface."""

from typer.main import get_command

from project_to_epub.cli import app


def test_help_uses_intended_boolean_flag_names():
    """Boolean flags should not expose double-negative option names."""
    command = get_command(app)
    option_names = {
        option_name
        for parameter in command.params
        for option_name in [*parameter.opts, *parameter.secondary_opts]
    }

    assert "--no-skip-large" in option_names
    assert "--no-no-skip-large" not in option_names
    assert "--hierarchical-toc" in option_names
    assert "--no-hierarchical-toc" not in option_names
