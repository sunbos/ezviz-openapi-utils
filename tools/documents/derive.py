"""离线校验官方原文并生成派生索引，不推断接口业务语义。

运行：python3 tools/documents/derive.py --input data/official-docs/2026-11-14
以 documents.jsonl 为本次派生文件清单；目录中未被引用的旧文件不属于本次结果。
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import tempfile

if __package__:
    from .parse_html import extract_document
else:
    from parse_html import extract_document


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _verify_sources(root, catalog):
    """在写输出前验证所有 archived 原文，并固定本次使用的正文字符串。"""
    if not isinstance(catalog, list):
        raise ValueError("catalog.json must contain a list")
    seen = set()
    contents = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            raise ValueError("Each catalog entry must be an object")
        for required in ("region", "doc_id", "title", "source_url", "status", "memberships"):
            if required not in entry:
                raise ValueError(f"Catalog entry is missing {required}")
        key = (entry["region"], str(entry["doc_id"]))
        if key[0] not in ("domestic", "overseas") or not re.fullmatch(r"[0-9]+", key[1]):
            raise ValueError(f"Invalid document identity: {key}")
        if key in seen:
            raise ValueError(f"Duplicate document identity in catalog: {key}")
        seen.add(key)
        if not isinstance(entry["memberships"], list):
            raise ValueError(f"memberships must be a list for {key}")
        for membership in entry["memberships"]:
            if not isinstance(membership, dict) or not isinstance(membership.get("category_path"), list):
                raise ValueError(f"Invalid category_path for {key}")
        if entry["status"] != "archived":
            continue
        for required in ("raw_file", "raw_file_sha256", "content_sha256"):
            if not entry.get(required):
                raise ValueError(f"Archived entry {key} is missing {required}")
        relative = Path(entry["raw_file"])
        raw_path = (root / relative).resolve()
        if relative.is_absolute() or not raw_path.is_relative_to(root):
            raise ValueError(f"Raw source path escapes input directory: {key}")
        raw = raw_path.read_bytes()
        if _sha256(raw) != entry["raw_file_sha256"]:
            raise ValueError(f"raw_file_sha256 mismatch for {key}")
        source = json.loads(raw)
        html = source.get("html_content") if isinstance(source, dict) else None
        if not isinstance(html, str):
            raise ValueError(f"Archived source has no string html_content: {key}")
        if _sha256(html.encode("utf-8")) != entry["content_sha256"]:
            raise ValueError(f"content_sha256 mismatch for {key}")
        contents[key] = html
    return contents


def _category_statistics(documents):
    categories = {}
    counted = set()
    for document in documents:
        memberships = document["memberships"] or [{"category_path": []}]
        for membership in memberships:
            path = membership["category_path"]
            top = str(path[0]) if path else "未分类"
            kind = "body_reference_supplement" if top == "正文引用补充" else "official_navigation"
            if not path:
                kind = "uncategorized"
            key = (document["region"], kind, top)
            item = categories.setdefault(key, {
                "region": key[0], "category_kind": kind, "top_category": top,
                "documents": 0, "derived_documents": 0, "membership_relations": 0,
                "by_status": Counter(), "counts": Counter(),
            })
            item["membership_relations"] += bool(document["memberships"])
            identity = (*key, str(document["doc_id"]))
            if identity in counted:
                continue
            counted.add(identity)
            item["documents"] += 1
            item["by_status"][document["status"]] += 1
            if document["derivation_status"] == "derived":
                item["derived_documents"] += 1
                item["counts"].update(document["counts"])
    return [categories[key] for key in sorted(categories)]


def derive(input_directory):
    """验证输入后离线派生；校验或解析失败时不发布本次临时输出。"""
    root = Path(input_directory).resolve()
    catalog_bytes = (root / "catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    contents = _verify_sources(root, catalog)
    documents = []
    row_counts = Counter()
    region_stats = defaultdict(lambda: {
        "documents": 0, "derived_documents": 0, "by_status": Counter(), "counts": Counter()
    })
    totals = Counter()
    index_names = ("documents.jsonl", "tables.jsonl", "code-blocks.jsonl", "references.jsonl")
    with tempfile.TemporaryDirectory(prefix=".derive-", dir=root) as temporary:
        staging = Path(temporary)
        with ExitStack() as stack:
            streams = {name: stack.enter_context((staging / name).open("w", encoding="utf-8"))
                       for name in index_names}

            def emit(name, row):
                streams[name].write(json.dumps(row, ensure_ascii=False) + "\n")
                row_counts[name] += 1

            for entry in catalog:
                document = dict(entry)
                document.update({
                    "derivation_status": "not_archived", "counts": None,
                    "structure_file": None, "structure_sha256": None,
                    "plain_text_file": None, "plain_text_sha256": None,
                })
                region = entry["region"]
                doc_id = str(entry["doc_id"])
                stats = region_stats[region]
                stats["documents"] += 1
                stats["by_status"][entry["status"]] += 1
                if entry["status"] == "archived":
                    structure = extract_document(contents[(region, doc_id)], entry["source_url"])
                    structure_path = Path("derived") / region / f"{doc_id}.structure.json"
                    text_path = Path("derived") / region / f"{doc_id}.plain.txt"
                    structure_bytes = _json_bytes(structure)
                    text_bytes = (structure["text"] + "\n").encode("utf-8")
                    _write(staging / structure_path, structure_bytes)
                    _write(staging / text_path, text_bytes)
                    document.update({
                        "derivation_status": "derived", "counts": structure["counts"],
                        "structure_file": str(structure_path),
                        "structure_sha256": _sha256(structure_bytes),
                        "plain_text_file": str(text_path), "plain_text_sha256": _sha256(text_bytes),
                    })
                    stats["derived_documents"] += 1
                    stats["counts"].update(structure["counts"])
                    totals.update(structure["counts"])
                    provenance = {
                        "region": region, "doc_id": doc_id, "source_url": entry["source_url"],
                        "raw_file": entry["raw_file"], "structure_file": str(structure_path),
                    }
                    for name, field, index_field in (
                        ("tables.jsonl", "tables", "table_index"),
                        ("code-blocks.jsonl", "code_blocks", "code_block_index"),
                    ):
                        for index, block in enumerate(structure[field]):
                            row = {key: value for key, value in block.items() if key != "element_index"}
                            row.update(provenance)
                            row.update({index_field: index, "source_element_index": block["element_index"]})
                            emit(name, row)
                    for field, reference_type in (
                        ("links", "link"), ("images", "image"),
                        ("embedded_resources", "embedded_resource"),
                    ):
                        for reference in structure[field]:
                            row = {key: value for key, value in reference.items() if key != "element_index"}
                            row.update(provenance)
                            row.update({"reference_type": reference_type,
                                        "source_element_index": reference["element_index"]})
                            emit("references.jsonl", row)
                documents.append(document)
                emit("documents.jsonl", document)

        summary = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_catalog": "catalog.json", "input_catalog_sha256": _sha256(catalog_bytes),
            "documents": len(documents), "derived_documents": len(contents),
            "membership_relations": sum(len(document["memberships"]) for document in documents),
            "by_status": Counter(document["status"] for document in documents),
            "by_region": dict(region_stats), "by_top_category": _category_statistics(documents),
            "counts": totals,
            "indexes": {name: {"rows": row_counts[name], "sha256": _sha256((staging / name).read_bytes())}
                        for name in index_names},
            "parser": {"path": "tools/documents/parse_html.py",
                       "sha256": _sha256(Path(__file__).with_name("parse_html.py").read_bytes()),
                       "beautifulsoup4_version": version("beautifulsoup4"),
                       "python_version": platform.python_version()},
            "semantic_schema_review": "not_performed",
            "notes": [
                "counts.images 是图片 URL 引用数，不是 img 元素数；一个元素可引用多个 URL。",
                "正文只按 region/doc_id 派生一次，memberships 保留全部分类关系，包括重复关系。",
                "分类内 documents 去重；同篇可计入多个主分类，各分类数量之和不等于文档总数。",
                "正文引用补充通过 category_kind=body_reference_supplement 单列，不冒充官方导航主分类。",
                "未归档条目保留状态，counts=null 表示未提取，不代表正文没有表格或代码。",
                "派生结果未推断接口业务语义，未人工核实业务 schema，未调用真实 API。",
                "原文与派生结果通过 hash 关联；hash 一致不证明官方文档内容正确。",
            ],
        }
        _write(staging / "derivation-summary.json", _json_bytes(summary))
        # 所有源校验及结构解析成功后才发布；汇总最后更新，供消费方校验索引 hash。
        for path in sorted(staging.rglob("*")):
            if path.is_file() and path.name != "derivation-summary.json":
                destination = root / path.relative_to(staging)
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
        (staging / "derivation-summary.json").replace(root / "derivation-summary.json")
    return summary


def main():
    parser = argparse.ArgumentParser(description="离线校验官方文档并生成派生索引")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = derive(args.input)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"documents": summary["documents"],
                      "derived_documents": summary["derived_documents"],
                      "by_status": summary["by_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
