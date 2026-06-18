"""EPUB workspace and packaging helpers."""

import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from project_to_epub.config import EpubMetadata
from project_to_epub.models import HtmlFile
from project_to_epub.toc import xml_escape

MIMETYPE = "application/epub+zip"
EPUB_DIR_NAME = "EPUB"
META_INF_DIR_NAME = "META-INF"
TOC_PAGE_FILE = "toc_page.xhtml"
NAV_FILE = "nav.xhtml"
NCX_FILE = "toc.ncx"


def epub_timestamp() -> str:
    """Return the current UTC timestamp in EPUB metadata format."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text to a file."""
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def create_epub_workspace(temp_path: Path, css_content: str) -> Path:
    """Create required EPUB directories and static files."""
    epub_dir = temp_path / EPUB_DIR_NAME
    meta_inf_dir = temp_path / META_INF_DIR_NAME
    epub_dir.mkdir()
    meta_inf_dir.mkdir()

    write_text_file(temp_path / "mimetype", MIMETYPE)
    write_text_file(
        meta_inf_dir / "container.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="EPUB/content.opf"
            media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>""",
    )
    write_text_file(epub_dir / "style.css", css_content)
    return epub_dir


def generate_content_opf(
    metadata: EpubMetadata,
    identifier: str,
    html_files: List[HtmlFile],
    nav_file: str = NAV_FILE,
    ncx_file: str = NCX_FILE,
) -> str:
    """Generate the EPUB package document."""
    manifest_items = [
        '<item id="style" href="style.css" media-type="text/css"/>',
        (
            f'<item id="ncx" href="{xml_escape(ncx_file)}" '
            'media-type="application/x-dtbncx+xml"/>'
        ),
        (
            f'<item id="nav" href="{xml_escape(nav_file)}" '
            'media-type="application/xhtml+xml" properties="nav"/>'
        ),
    ]
    spine_items = []

    for html_file in html_files:
        manifest_items.append(
            f'<item id="{xml_escape(html_file.id)}" '
            f'href="{xml_escape(html_file.file)}" '
            'media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{xml_escape(html_file.id)}"/>')

    publisher_metadata = ""
    if metadata.publisher:
        publisher_metadata = (
            "\n        <dc:publisher>"
            f"{xml_escape(metadata.publisher)}</dc:publisher>"
        )

    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="uid">{xml_escape(identifier)}</dc:identifier>
        <dc:title>{xml_escape(metadata.title or '')}</dc:title>
        <dc:creator>{xml_escape(metadata.author)}</dc:creator>
        <dc:language>{xml_escape(metadata.language)}</dc:language>{publisher_metadata}
        <meta property="dcterms:modified">{epub_timestamp()}</meta>
    </metadata>
    <manifest>
        {chr(10).join(manifest_items)}
    </manifest>
    <spine toc="ncx">
        {chr(10).join(spine_items)}
    </spine>
</package>"""


def write_content_opf(
    epub_dir: Path,
    metadata: EpubMetadata,
    identifier: str,
    html_files: List[HtmlFile],
) -> None:
    """Write the package document to the EPUB workspace."""
    write_text_file(
        epub_dir / "content.opf",
        generate_content_opf(metadata, identifier, html_files),
    )


def write_epub_zip(temp_path: Path, output_path: Path) -> None:
    """Zip the EPUB workspace into a final EPUB file."""
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w") as epub_zip:
        epub_zip.write(
            temp_path / "mimetype",
            "mimetype",
            compress_type=zipfile.ZIP_STORED,
        )

        for root, _dirs, files in os.walk(temp_path):
            for file in files:
                if file == "mimetype":
                    continue

                file_path = Path(root) / file
                arc_name = str(file_path.relative_to(temp_path))
                epub_zip.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)
