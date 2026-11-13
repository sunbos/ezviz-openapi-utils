"""从官方 htmlContent 提取可复核结构，不推断接口业务契约。

原始 HTML 由调用方另行保存。本模块不执行脚本、不访问网络；提取出的 URL
也不代表允许下载，调用方应独立校验来源与协议。element_index 是原始 HTML
经 BeautifulSoup/html.parser 解析后，所有元素按文档顺序排列的零基下标。
普通文本会整理空白，代码块保留解析后的文本空白与 HTML entity 解码结果。
"""

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


def _text(element: Tag) -> str:
    return element.get_text(" ", strip=True)


def _span(cell: Tag, attribute: str) -> int | str:
    """保留 rowspan=0 与异常原值，不静默猜测上游表格布局。"""
    value = cell.get(attribute)
    if value is None:
        return 1
    try:
        return int(str(value))
    except ValueError:
        return str(value)


def _language(element: Tag) -> str:
    candidates = [element]
    if element.name == "pre":
        candidates = list(element.find_all("code")) + candidates
    for candidate in candidates:
        for attribute in ("data-language", "data-lang"):
            if candidate.get(attribute):
                return str(candidate[attribute])
        for css_class in candidate.get("class", []):
            for prefix in ("language-", "lang-"):
                if css_class.startswith(prefix):
                    return css_class[len(prefix):]
    return ""


def _srcset_urls(value: str) -> list[str]:
    """读取候选 URL，保留 data URL 内部逗号，不把描述符猜成 URL。"""
    urls = []
    position = 0
    whitespace = " \t\n\r\f"
    while position < len(value):
        while position < len(value) and value[position] in whitespace + ",":
            position += 1
        start = position
        while position < len(value) and value[position] not in whitespace:
            position += 1
        candidate = value[start:position]
        if not candidate:
            break
        urls.append(candidate.rstrip(","))
        if candidate.endswith(","):
            continue
        parentheses = 0
        while position < len(value):
            character = value[position]
            position += 1
            if character == "(":
                parentheses += 1
            elif character == ")" and parentheses:
                parentheses -= 1
            elif character == "," and not parentheses:
                break
    return urls


def extract_document(html: str, base_url: str) -> dict[str, Any]:
    """提取正文、标题、表格、代码和引用；不判断官方内容或真实 API 正确性。"""
    soup = BeautifulSoup(html, "html.parser")
    indices = {id(element): index for index, element in enumerate(soup.find_all(True))}
    for element in soup.find_all(["script", "style"]):
        element.decompose()
    for line_break in soup.find_all("br"):
        # 容错解析异常上游 HTML 时，br 可能带有恢复出来的子节点；不可删除子树。
        line_break.insert_before("\n")
        line_break.unwrap()

    headings = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        headings.append({
            "level": int(heading.name[1]),
            "text": _text(heading),
            "element_index": indices[id(heading)],
        })

    tables = []
    for table in soup.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            if row.find_parent("table") is not table:
                continue
            cells = []
            for cell in row.find_all(["th", "td"]):
                if cell.find_parent("tr") is not row:
                    continue
                cells.append({
                    "kind": cell.name,
                    "text": _text(cell),
                    "rowspan": _span(cell, "rowspan"),
                    "colspan": _span(cell, "colspan"),
                })
            rows.append(cells)
        heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
        tables.append({
            "rows": rows,
            "heading": _text(heading) if heading else "",
            "element_index": indices[id(table)],
        })

    code_blocks = []
    for block in soup.find_all(["pre", "code"]):
        if block.find_parent(["pre", "code"]) is not None:
            continue
        code_blocks.append({
            "language": _language(block),
            "text": block.get_text(),
            "element_index": indices[id(block)],
        })

    links = []
    for link in soup.find_all("a", href=True):
        links.append({
            "url": urljoin(base_url, str(link["href"])),
            "text": _text(link),
            "element_index": indices[id(link)],
        })

    images = []
    for image in soup.find_all(["img", "source", "image"]):
        if image.name == "source" and image.find_parent("picture") is None:
            continue
        seen = set()
        references = []
        for attribute in ("src", "data-src", "data-original", "href", "xlink:href"):
            reference = image.get(attribute)
            if reference:
                references.append(str(reference))
        for attribute in ("srcset", "data-srcset"):
            if image.get(attribute):
                references.extend(_srcset_urls(str(image[attribute])))
        for reference in references:
            url = urljoin(base_url, reference)
            if url in seen:
                continue
            seen.add(url)
            images.append({
                "url": url,
                "alt": str(image.get("alt", "")),
                "element_index": indices[id(image)],
            })

    embedded_resources = []
    embedded_attributes = {
        "frame": "src",
        "iframe": "src",
        "embed": "src",
        "object": "data",
        "audio": "src",
        "video": "src",
        "source": "src",
        "track": "src",
    }
    for resource in soup.find_all(list(embedded_attributes)):
        reference = resource.get(embedded_attributes[resource.name])
        if not reference:
            continue
        embedded_resources.append({
            "kind": resource.name,
            "url": urljoin(base_url, str(reference)),
            "element_index": indices[id(resource)],
        })

    return {
        "text": soup.get_text("\n", strip=True),
        "headings": headings,
        "tables": tables,
        "code_blocks": code_blocks,
        "links": links,
        "images": images,
        "embedded_resources": embedded_resources,
        "counts": {
            "headings": len(headings),
            "tables": len(tables),
            "table_rows": sum(len(table["rows"]) for table in tables),
            "table_cells": sum(len(row) for table in tables for row in table["rows"]),
            "code_blocks": len(code_blocks),
            "links": len(links),
            "images": len(images),
            "embedded_resources": len(embedded_resources),
        },
    }
