"""
Integration tests for the project-to-epub converter.
"""

import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from ebooklib import epub

from project_to_epub.converter import convert_project_to_epub

EPUB_XML_SUFFIXES = (".opf", ".xhtml", ".ncx", ".xml")


def parse_epub_xml_documents(epub_path):
    """Parse all XML-based files in an EPUB and return parsed roots by path."""
    parsed = {}
    with zipfile.ZipFile(epub_path, "r") as zip_ref:
        for name in zip_ref.namelist():
            if name.endswith(EPUB_XML_SUFFIXES):
                parsed[name] = ET.fromstring(zip_ref.read(name))
    return parsed


def assert_epub_mimetype_is_first_and_uncompressed(epub_path):
    """Validate the required EPUB mimetype ZIP entry constraints."""
    with zipfile.ZipFile(epub_path, "r") as zip_ref:
        first_entry = zip_ref.infolist()[0]
        assert first_entry.filename == "mimetype"
        assert first_entry.compress_type == zipfile.ZIP_STORED
        assert first_entry.extra == b""
        assert zip_ref.read("mimetype") == b"application/epub+zip"


def test_convert_sample_project(sample_project_dir, temp_output_file):
    """Test converting a sample project to EPUB."""
    # Define config
    config = {
        "default_theme": "default_eink",
        "large_file_threshold_mb": 10,
        "skip_large_files": True,
        "log_level": "INFO",
        "epub_metadata": {
            "author": "Test Author",
            "language": "en",
            "publisher": "Test Publisher",
        },
    }

    # Convert the project
    result = convert_project_to_epub(sample_project_dir, temp_output_file, config)

    # Check that the EPUB file was created
    assert temp_output_file.exists()
    assert temp_output_file.stat().st_size > 0

    # Check that the result contains statistics
    assert "Processed" in result
    assert "Output:" in result
    assert str(temp_output_file) in result

    # Check that the file is a valid EPUB (zip archive)
    assert zipfile.is_zipfile(temp_output_file)
    assert_epub_mimetype_is_first_and_uncompressed(temp_output_file)
    parsed_documents = parse_epub_xml_documents(temp_output_file)
    assert "EPUB/content.opf" in parsed_documents

    content_opf = parsed_documents["EPUB/content.opf"]
    opf_namespace = {"opf": "http://www.idpf.org/2007/opf"}
    modified = content_opf.find(
        ".//opf:meta[@property='dcterms:modified']", opf_namespace
    )
    assert modified is not None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", modified.text)

    # Extract and check contents
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract EPUB (it's a zip file)
        with zipfile.ZipFile(temp_output_file, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        # Check for EPUB required files
        assert os.path.exists(os.path.join(temp_dir, "META-INF", "container.xml"))
        assert os.path.exists(os.path.join(temp_dir, "mimetype"))

        # Check for content files
        # We can't predict exact filenames, so just check directory structure
        content_opf = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".opf"):
                    content_opf = os.path.join(root, file)
                    break

        assert content_opf is not None, "content.opf not found"

        # Check for HTML files that should contain our content
        html_files = []
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".xhtml") or file.endswith(".html"):
                    html_files.append(os.path.join(root, file))

        # Verify we have HTML files
        assert len(html_files) > 0, "No HTML files found"

        # Check for CSS file
        css_files = []
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".css"):
                    css_files.append(os.path.join(root, file))

        assert len(css_files) > 0, "No CSS file found"

        # Check CSS content
        with open(css_files[0], "r", encoding="utf-8") as f:
            css_content = f.read()
            assert "background-color: #FFFFFF" in css_content
            assert "color: #000000" in css_content


def test_ignored_files(sample_project_dir, temp_output_file):
    """Test that ignored files are not included in the EPUB."""
    # Define config
    config = {
        "default_theme": "default_eink",
        "large_file_threshold_mb": 10,
        "skip_large_files": True,
        "log_level": "DEBUG",  # Use DEBUG to see all messages
        "epub_metadata": {
            "author": "Test Author",
            "language": "en",
            "publisher": "Test Publisher",
        },
    }

    # Convert the project
    convert_project_to_epub(sample_project_dir, temp_output_file, config)

    # Extract and check contents
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract EPUB (it's a zip file)
        with zipfile.ZipFile(temp_output_file, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        # Find all HTML files
        html_files = []
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".xhtml") or file.endswith(".html"):
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        content = f.read()
                        html_files.append((file, content))

        # Check that no ignored files are included
        for file, content in html_files:
            assert "app.log" not in content
            assert "node_modules" not in content
            assert "package.json" not in content


def test_custom_title_and_author(sample_project_dir, temp_output_file):
    """Test that custom title and author are used in the EPUB."""
    # Define config with custom title and author
    config = {
        "default_theme": "default_eink",
        "large_file_threshold_mb": 10,
        "skip_large_files": True,
        "log_level": "INFO",
        "title": "Custom Project Title",
        "author": "Custom Author Name",
        "epub_metadata": {"language": "en", "publisher": "Test Publisher"},
    }

    # Convert the project
    convert_project_to_epub(sample_project_dir, temp_output_file, config)

    # Open the EPUB and check metadata
    book = epub.read_epub(str(temp_output_file))

    # Check title and author
    assert book.get_metadata("DC", "title")[0][0] == "Custom Project Title"
    assert book.get_metadata("DC", "creator")[0][0] == "Custom Author Name"
    assert book.get_metadata("DC", "language")[0][0] == "en"

    # Check if publisher exists
    publisher_data = book.get_metadata("DC", "publisher")
    if publisher_data:
        assert publisher_data[0][0] == "Test Publisher"


def test_special_characters_generate_parseable_epub(tmp_path):
    """Special characters in metadata and paths must be escaped in EPUB XML."""
    project_dir = tmp_path / "A & B <Project>"
    source_dir = project_dir / "src & docs"
    source_dir.mkdir(parents=True)
    (source_dir / "a & b.py").write_text(
        'print("A & B < C")\n',
        encoding="utf-8",
    )
    (source_dir / "notes & refs.md").write_text(
        "# Notes & Refs\n\nUse `A < B && C > D` in examples.\n",
        encoding="utf-8",
    )

    output_file = tmp_path / "special.epub"
    convert_project_to_epub(
        project_dir,
        output_file,
        {
            "default_theme": "default_eink",
            "large_file_threshold_mb": 10,
            "skip_large_files": True,
            "title": 'A & B <Book> "Sample"',
            "author": 'C "D" & <E>',
            "epub_metadata": {
                "language": "en",
                "publisher": "P & Co <Test>",
            },
        },
    )

    parsed_documents = parse_epub_xml_documents(output_file)
    assert {
        "META-INF/container.xml",
        "EPUB/content.opf",
        "EPUB/nav.xhtml",
        "EPUB/toc.ncx",
        "EPUB/toc_page.xhtml",
        "EPUB/file_0.xhtml",
        "EPUB/file_1.xhtml",
    }.issubset(parsed_documents)

    book = epub.read_epub(str(output_file))
    assert book.get_metadata("DC", "title")[0][0] == 'A & B <Book> "Sample"'
    assert book.get_metadata("DC", "creator")[0][0] == 'C "D" & <E>'
    assert book.get_metadata("DC", "publisher")[0][0] == "P & Co <Test>"
