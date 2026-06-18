"""Table-of-contents organization and document rendering."""

from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Union

from project_to_epub.models import TocItem

TocInput = Union[TocItem, Mapping[str, Any]]


def xml_escape(value: object) -> str:
    """Escape text or attribute values for generated EPUB XML documents."""
    return escape(str(value), quote=True)


def _coerce_toc_items(toc_items: Sequence[TocInput]) -> List[TocItem]:
    return [TocItem.from_any(item) for item in toc_items]


def flatten_toc_items(toc_items: Sequence[TocInput]) -> List[TocItem]:
    """
    Flatten TOC items while preserving hierarchical naming.

    This creates a flat (non-nested) TOC structure but keeps the directory names
    as part of the file names in the TOC entries.
    """
    items = _coerce_toc_items(toc_items)
    result = [item for item in items if not item.is_directory]

    def process_items(children: Sequence[TocItem], parent_path: str = "") -> None:
        for item in children:
            if item.is_directory and item.children:
                current_path = (
                    f"{parent_path}/{item.title}" if parent_path else item.title
                )
                process_items(item.children, current_path)
            elif item.href:
                if parent_path and "/" not in item.title:
                    result.append(item.with_title(f"{parent_path}/{item.title}"))
                else:
                    result.append(item)

    for item in items:
        if item.is_directory and item.children:
            process_items([item])

    return result


def organize_toc_items_by_directory(toc_items: Sequence[TocInput]) -> List[TocItem]:
    """Organize flat TOC items hierarchically based on directory structure."""
    items = _coerce_toc_items(toc_items)
    result = [item for item in items if not (item.path or "").strip()]
    directory_structure: Dict[str, Dict[str, Any]] = {}

    for item in items:
        if not (item.path or "").strip():
            continue

        parts = Path(item.path or "").parts
        if len(parts) <= 1:
            result.append(item)
            continue

        current_level = directory_structure
        for index, part in enumerate(parts[:-1]):
            if part not in current_level:
                current_level[part] = {"files": [], "dirs": {}}

            if index == len(parts) - 2:
                current_level[part]["files"].append(item)
            else:
                current_level = current_level[part]["dirs"]

    dir_id_counter = 0

    def process_directory(dir_name: str, dir_content: Dict[str, Any]) -> TocItem:
        nonlocal dir_id_counter
        dir_item = TocItem(
            id=f"dir_{dir_id_counter}",
            title=dir_name,
            is_directory=True,
        )
        dir_id_counter += 1

        dir_item.children.extend(dir_content["files"])
        for subdir_name, subdir_content in dir_content["dirs"].items():
            dir_item.children.append(process_directory(subdir_name, subdir_content))

        return dir_item

    for dir_name, dir_content in directory_structure.items():
        result.append(process_directory(dir_name, dir_content))

    return result


def select_toc_items_for_display(
    toc_items: Sequence[TocInput],
    flat_toc: bool,
) -> List[TocItem]:
    """Return either flattened or hierarchical TOC items for display."""
    hierarchical_toc_items = organize_toc_items_by_directory(toc_items)
    if flat_toc:
        return flatten_toc_items(hierarchical_toc_items)
    return hierarchical_toc_items


def generate_toc_ncx(
    toc_items: Sequence[TocInput],
    title: str,
    identifier: str,
) -> str:
    """Generate the EPUB 2 NCX table-of-contents document."""
    items = _coerce_toc_items(toc_items)
    ncx_content = [f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="{xml_escape(identifier)}"/>
        <meta name="dtb:depth" content="3"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle>
        <text>{xml_escape(title)}</text>
    </docTitle>
    <navMap>"""]

    play_order = 1
    play_order_by_href: Dict[str, int] = {}

    def play_order_for_href(href: str) -> int:
        nonlocal play_order

        if href not in play_order_by_href:
            play_order_by_href[href] = play_order
            play_order += 1

        return play_order_by_href[href]

    def add_nav_point(item: TocItem, level: int = 0) -> None:
        indent = "    " * (level + 2)

        if item.is_directory:
            first_child_href = item.first_descendant_href()
            current_play_order = play_order_for_href(first_child_href)
            nav_point_open = (
                f'{indent}<navPoint id="{xml_escape(item.id)}" '
                f'playOrder="{current_play_order}">'
            )
            ncx_content.append(f"""{nav_point_open}
{indent}    <navLabel>
{indent}        <text>{xml_escape(item.title)}</text>
{indent}    </navLabel>
{indent}    <content src="{xml_escape(first_child_href)}"/>
""")

            for child in item.children:
                add_nav_point(child, level + 1)

            ncx_content.append(f"{indent}</navPoint>")
        elif item.href:
            current_play_order = play_order_for_href(item.href)
            nav_point_open = (
                f'{indent}<navPoint id="{xml_escape(item.id)}" '
                f'playOrder="{current_play_order}">'
            )
            ncx_content.append(f"""{nav_point_open}
{indent}    <navLabel>
{indent}        <text>{xml_escape(item.title)}</text>
{indent}    </navLabel>
{indent}    <content src="{xml_escape(item.href)}"/>
{indent}</navPoint>""")

    for item in items:
        add_nav_point(item)

    ncx_content.append("""    </navMap>
</ncx>""")
    return "\n".join(ncx_content)


def generate_nav_xhtml(toc_items: Sequence[TocInput], title: str) -> str:
    """Generate EPUB 3 Navigation Document (nav.xhtml)."""
    del title
    items = _coerce_toc_items(toc_items)
    nav_content = ["""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1 class="toc-title">Table of Contents</h1>
        <ol class="toc-list">"""]

    def add_toc_items(children: Sequence[TocItem], level: int = 0) -> None:
        indent = "    " * (level + 3)

        for item in children:
            if item.is_directory and item.children:
                nav_content.append(
                    f"{indent}<li><span class='toc-directory'>"
                    f"{xml_escape(item.title)}</span>"
                )
                nav_content.append(f"{indent}    <ol>")
                add_toc_items(item.children, level + 1)
                nav_content.append(f"{indent}    </ol>")
                nav_content.append(f"{indent}</li>")
            elif item.href:
                nav_content.append(
                    f'{indent}<li><a href="{xml_escape(item.href)}">'
                    f"{xml_escape(item.title)}</a></li>"
                )

    add_toc_items(items)
    nav_content.append("""        </ol>
    </nav>
</body>
</html>""")
    return "\n".join(nav_content)


def generate_toc_html(toc_items: Sequence[TocInput], level: int = 0) -> str:
    """Generate the body list for the human-readable TOC page."""
    items = _coerce_toc_items(toc_items)
    indent = "    " * level
    html: List[str] = []

    for item in items:
        if item.is_directory and item.children:
            html.append(
                f"{indent}<li><span class='toc-directory'>"
                f"{xml_escape(item.title)}</span>"
            )
            html.append(f"{indent}    <ul>")
            html.append(generate_toc_html(item.children, level + 1))
            html.append(f"{indent}    </ul>")
            html.append(f"{indent}</li>")
        elif item.href:
            html.append(
                f'{indent}<li><a href="{xml_escape(item.href)}">'
                f"{xml_escape(item.title)}</a></li>"
            )

    return "\n".join(html)


def generate_toc_page_xhtml(toc_items: Sequence[TocInput]) -> str:
    """Generate the readable table-of-contents XHTML page."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="style.css" />
    <style>
        .toc-directory {{
            font-weight: bold;
        }}
        ul {{
            margin-top: 0.5em;
            margin-bottom: 0.5em;
        }}
        li {{
            margin-bottom: 0.5em;
        }}
    </style>
</head>
<body>
    <h1>Table of Contents</h1>
    <ul class="toc-list">
{generate_toc_html(toc_items)}
    </ul>
</body>
</html>"""
