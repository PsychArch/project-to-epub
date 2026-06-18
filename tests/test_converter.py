"""
Tests for the converter module.
"""

import re
import tempfile
from pathlib import Path

import pytest
from pygments.formatters import HtmlFormatter

from project_to_epub.converter import (
    Project,
    create_highlight_formatter,
    get_css_for_epub,
    highlight_code,
    render_markdown,
)


def assert_uses_only_black_white_hex_colors(html: str) -> None:
    hex_colors = set(re.findall(r"#[0-9a-fA-F]{3,6}", html))
    assert hex_colors <= {"#000000", "#FFFFFF", "#ffffff"}


def assert_has_no_colored_inline_styles(html: str) -> None:
    color_values = re.findall(r"(?<!-)color:\s*([^;\"']+)", html)
    assert all(
        value.strip() in {"inherit", "#000000", "#FFFFFF"} for value in color_values
    )


def test_create_highlight_formatter():
    """Test creating formatter with various themes."""
    # Test default e-ink theme
    formatter = create_highlight_formatter("default_eink")
    assert isinstance(formatter, HtmlFormatter)
    assert formatter.style.__name__ == "EInkMonochromeStyle"
    assert formatter.noclasses is True
    assert formatter.nobackground is True
    assert formatter.linenos

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
    assert "#f8f8f8" not in css
    assert "#f0f0f0" not in css
    assert "#ccc" not in css
    assert "#555" not in css
    assert "min-width: 4ch" not in css
    assert ".linenos span" in css


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


def test_default_eink_highlighting_uses_monochrome_styles():
    """Default e-ink highlighting should not emit color-token styling."""
    from pygments.lexers import PythonLexer

    code = "import os\n\ndef hello_world():\n    # greet\n    return 'Hello'\n"
    formatter = create_highlight_formatter("default_eink")
    html = highlight_code(code, PythonLexer(), formatter)

    assert_uses_only_black_white_hex_colors(html)
    assert_has_no_colored_inline_styles(html)
    assert "background:" not in html
    assert 'class="linenos"' in html
    assert 'class="highlighttable"' in html
    assert "font-weight: bold" in html
    assert "font-style: italic" in html


def test_markdown_fenced_code_uses_default_eink_formatter():
    """Markdown fenced code should use the same monochrome token style."""
    markdown = """# Notes

```python
def hello_world():
    # greet
    return "Hello"
```
"""
    formatter = create_highlight_formatter("default_eink")
    html = render_markdown(markdown, formatter)

    assert_uses_only_black_white_hex_colors(html)
    assert_has_no_colored_inline_styles(html)
    assert 'class="linenos"' in html
    assert 'class="codehilitetable"' in html
    assert "font-weight: bold" in html
    assert "font-style: italic" in html


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


def test_nested_gitignore_rules_are_respected():
    """Nested .gitignore files should apply relative to their own directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        subdir = temp_path / "sub"
        subdir.mkdir()

        (subdir / ".gitignore").write_text("secret.py\n", encoding="utf-8")
        (subdir / "secret.py").write_text("print('secret')\n", encoding="utf-8")
        (subdir / "keep.py").write_text("print('keep')\n", encoding="utf-8")

        project = Project(temp_path, {"large_file_threshold_mb": 10})

        assert project.is_ignored(subdir / "secret.py") is True
        assert project.is_ignored(subdir / "keep.py") is False
        assert [str(file.relative_path) for file in project.scan_files()] == [
            "sub/keep.py"
        ]


def test_large_markdown_and_code_files_are_skipped():
    """The large-file limit should apply before Markdown/code branching."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "big.md").write_text("# Big\n" + ("x" * 2048), encoding="utf-8")
        (temp_path / "big.py").write_text(
            "value = '" + ("x" * 2048) + "'\n", encoding="utf-8"
        )
        (temp_path / "big.bin").write_bytes(b"\x00" * 2048)
        (temp_path / "small.py").write_text("print('small')\n", encoding="utf-8")

        project = Project(
            temp_path,
            {"large_file_threshold_mb": 0.001, "skip_large_files": True},
        )

        assert [str(file.relative_path) for file in project.scan_files()] == [
            "small.py"
        ]
        assert project.skipped_files == 2
