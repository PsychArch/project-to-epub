"""
Test fixtures for pytest.
"""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_project_dir():
    """
    Create a temporary directory with a sample project structure.

    Returns:
        Path: Path to the temporary directory
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)

        # Create .gitignore
        with open(project_dir / ".gitignore", "w") as f:
            f.write("*.log\nnode_modules/\ndist/\n*.pyc\n__pycache__/\n")

        # Create a src directory with Python files
        src_dir = project_dir / "src"
        src_dir.mkdir()

        # Create a main.py file
        with open(src_dir / "main.py", "w") as f:
            f.write(
                """
def main():
    \"\"\"Main entry point.\"\"\"
    print("Hello, world!")

if __name__ == "__main__":
    main()
"""
            )

        # Create a utils.py file
        with open(src_dir / "utils.py", "w") as f:
            f.write(
                """
def greet(name):
    \"\"\"Greet a user.\"\"\"
    return f"Hello, {name}!"

def calculate_sum(a, b):
    \"\"\"Calculate the sum of two numbers.\"\"\"
    return a + b
"""
            )

        # Create a tests directory
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()

        # Create a test file
        with open(tests_dir / "test_utils.py", "w") as f:
            f.write(
                """
import pytest
from src.utils import greet, calculate_sum

def test_greet():
    \"\"\"Test the greet function.\"\"\"
    assert greet("Alice") == "Hello, Alice!"

def test_calculate_sum():
    \"\"\"Test the calculate_sum function.\"\"\"
    assert calculate_sum(1, 2) == 3
    assert calculate_sum(-1, 1) == 0
"""
            )

        # Create a docs directory with a markdown file
        docs_dir = project_dir / "docs"
        docs_dir.mkdir()

        # Create a README.md file
        with open(project_dir / "README.md", "w") as f:
            f.write(
                """
# Sample Project

This is a sample project for testing the project-to-epub converter.

## Features

- Sample Python code
- Tests
- Documentation
"""
            )

        # Create a log file that should be ignored
        with open(project_dir / "app.log", "w") as f:
            f.write("This is a log file that should be ignored.\n")

        # Create a node_modules directory that should be ignored
        node_modules_dir = project_dir / "node_modules"
        node_modules_dir.mkdir()
        with open(node_modules_dir / "package.json", "w") as f:
            f.write("{}")

        yield project_dir


@pytest.fixture
def temp_output_file():
    """
    Create a temporary file for testing EPUB output.

    Returns:
        Path: Path to the temporary file
    """
    fd, temp_path = tempfile.mkstemp(suffix=".epub")
    os.close(fd)  # Close the file descriptor

    yield Path(temp_path)

    # Clean up the temporary file
    if os.path.exists(temp_path):
        os.unlink(temp_path)
