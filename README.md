# Project-to-EPUB

Convert a software project directory into an EPUB file for offline code reading and browsing on e-readers and tablets.

## Features

- Preserves your project's directory structure in the EPUB table of contents
- Applies syntax highlighting to recognized code files
- Respects `.gitignore` rules to exclude unwanted files
- Optimized for e-ink devices with high-contrast themes
- Configurable via command-line options

## Installation

```bash
pip install project-to-epub
```

Or install from source:

```bash
git clone https://github.com/PsychArch/project-to-epub.git
cd project-to-epub
pip install -e .
```

## Usage

Basic usage:

```bash
project-to-epub /path/to/your/project
```

This will create an EPUB file named after your project directory in the current working directory.

### Command-line options

```
Usage: project-to-epub [OPTIONS] INPUT_DIRECTORY

  Convert a software project directory into an EPUB file for offline code reading.

  This tool creates an EPUB that preserves your project structure in the table of
  contents, applies syntax highlighting to code files, and respects .gitignore rules.

Arguments:
  INPUT_DIRECTORY  Path to the project directory to convert  [required]

Options:
  -o, --output PATH               Output EPUB file path
  --theme TEXT                    Syntax highlighting theme (e.g., default_eink, 
                                 monokai)
  --log-level TEXT                Log level (DEBUG, INFO, WARNING, ERROR)
                                 [default: INFO]
  --title TEXT                    Set EPUB title (defaults to project directory name)
  --author TEXT                   Set EPUB author
  --limit-mb FLOAT                Set large file threshold in MB
  --no-skip-large                 Error out on large files instead of skipping
  --version                       Show version and exit
  --help                          Show this message and exit.
```

### Examples

Specify an output file:

```bash
project-to-epub /path/to/project -o ~/Documents/my-project.epub
```

Use a different syntax highlighting theme:

```bash
project-to-epub /path/to/project --theme monokai
```

Custom title and author:

```bash
project-to-epub /path/to/project --title "My Awesome Project" --author "Jane Developer"
```

## Configuration

The tool uses sensible defaults but can be customized using command-line options:

- **Theme**: Default is `default_eink`, a high-contrast theme optimized for e-ink displays.
- **Output File**: Defaults to `<project_name>.epub` in the current directory.
- **File Size Handling**: Files larger than 10MB are skipped by default.
- **Metadata**: Title defaults to the project directory name. Author defaults to "Project-to-EPUB Tool".

All settings can be customized via command-line options as shown in the usage section.

## Supported Code File Types

Project-to-EPUB supports all file types recognized by Pygments. This includes most popular programming languages like Python, JavaScript, Java, C/C++, Ruby, Go, Rust, and many more.

## Requirements

- Python 3.13+
- Pygments
- pathspec
- PyYAML
- typer
- Markdown

## License

MIT 