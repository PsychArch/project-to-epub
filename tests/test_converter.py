"""
Tests for the converter module.
"""

import tempfile
from pathlib import Path

import pytest
from pygments.formatters import HtmlFormatter

from project_to_epub.converter import (
    Project,
    create_highlight_formatter,
    get_css_for_epub,
    highlight_code,
)


def test_create_highlight_formatter():
    """Test creating formatter with various themes."""
    # Test default e-ink theme
    formatter = create_highlight_formatter("default_eink")
    assert isinstance(formatter, HtmlFormatter)
    # In newer Pygments versions, formatter.style is now the actual Style class
    assert formatter.style.__name__ == "DefaultStyle" or formatter.style == "default"
    assert formatter.noclasses is True
    assert formatter.nobackground is True

    # Test standard theme
    formatter = create_highlight_formatter("monokai")
    assert isinstance(formatter, HtmlFormatter)
    # In newer Pygments versions, the style is a class
    assert "monokai" in str(formatter.style).lower() or formatter.style == "monokai"

    # Test non-existent theme falls back to default
    formatter = create_highlight_formatter("non_existent_theme")
    assert isinstance(formatter, HtmlFormatter)
    assert formatter.style.__name__ == "DefaultStyle" or formatter.style == "default"


def test_get_epub_css():
    """Test CSS generation."""
    css = get_css_for_epub()

    # CSS should include basic styles
    assert "body" in css
    assert "background-color: #FFFFFF" in css
    assert "color: #000000" in css
    assert "pre" in css
    assert ".markdown-content" in css


def test_highlight_code():
    """Test code highlighting."""
    from pygments.lexers import PythonLexer

    # Create a formatter
    formatter = create_highlight_formatter("default_eink")

    # Sample Python code
    code = "def hello_world():\n    print('Hello, world!')"

    # Highlight the code
    html = highlight_code(code, PythonLexer(), formatter)

    # Check that it contains expected HTML
    assert "<pre" in html
    assert "def" in html
    assert "hello_world" in html
    assert "print" in html


def test_project_init():
    """Test initializing a Project instance."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a test .gitignore file
        gitignore_path = temp_path / ".gitignore"
        with open(gitignore_path, "w") as f:
            f.write("*.log\nnode_modules/\n.DS_Store\n")

        # Create a Project instance
        project = Project(temp_path, {"large_file_threshold_mb": 5})

        # Check initialization
        assert project.root_dir == temp_path
        assert project.config["large_file_threshold_mb"] == 5
        assert project.files == []

        # Check gitignore spec loaded
        assert project.gitignore_spec is not None

        # Test is_ignored method
        assert project.is_ignored(temp_path / "test.log") is True
        assert project.is_ignored(temp_path / "node_modules" / "package.json") is True
        assert project.is_ignored(temp_path / "code.py") is False


@pytest.mark.parametrize(
    "filename,should_be_ignored",
    [
        (".git/config", True),  # .git is always ignored
        ("node_modules/package.json", True),  # from gitignore
        ("logs/app.log", True),  # from gitignore
        ("src/main.py", False),  # regular file
    ],
)
def test_project_is_ignored(filename, should_be_ignored):
    """Test the is_ignored method with various paths."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create directories
        (temp_path / ".git").mkdir(exist_ok=True)
        (temp_path / "node_modules").mkdir(exist_ok=True)
        (temp_path / "logs").mkdir(exist_ok=True)
        (temp_path / "src").mkdir(exist_ok=True)

        # Create a test .gitignore file
        gitignore_path = temp_path / ".gitignore"
        with open(gitignore_path, "w") as f:
            f.write("*.log\nnode_modules/\n")

        # Create test files
        for path in [
            ".git/config",
            "node_modules/package.json",
            "logs/app.log",
            "src/main.py",
        ]:
            file_path = temp_path / path
            file_path.parent.mkdir(exist_ok=True)
            with open(file_path, "w") as f:
                f.write("Test content")

        # Create a Project instance
        project = Project(temp_path, {})

        # Test the path
        assert project.is_ignored(temp_path / filename) is should_be_ignored
