"""独立离线验收目录、原始证据链、派生 hash 和 HTML 结构计数。

不调用采集器或 BeautifulSoup；passed 仅表示归档一致性检查通过，正文缺项、
编码告警与未验证的业务语义仍单独报告。验证过程不联网，不修改原始或派生数据。
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, urlunsplit


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr", "frame"}
EMBEDDED = {tag: "src" for tag in ("iframe", "frame", "embed", "audio", "video", "source", "track")}
EMBEDDED["object"] = "data"
COUNT_KEYS = ("headings", "tables", "table_rows", "table_cells", "code_blocks", "links", "embedded_resources")


class IndependentHTMLInventory(HTMLParser):
    """按源标签计数；每个嵌套表格中的行/单元格只累计一次。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.counts = Counter()
        self.raw_tags = Counter()
        self.nested_tables = 0
        self.candidates = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        ignored = any(name in {"script", "style"} for name in self.stack)
        if not ignored and tag not in {"script", "style"}:
            self.raw_tags[tag] += 1
            if tag == "table":
                self.counts["tables"] += 1
                self.nested_tables += "table" in self.stack
            elif tag == "tr" and "table" in self.stack:
                self.counts["table_rows"] += 1
            elif tag in {"th", "td"} and "table" in self.stack and "tr" in self.stack:
                self.counts["table_cells"] += 1
                self.counts["table_" + tag] += 1
            elif re.fullmatch(r"h[1-6]", tag):
                self.counts["headings"] += 1
            elif tag in {"pre", "code"} and not any(name in {"pre", "code"} for name in self.stack):
                self.counts["code_blocks"] += 1
            if tag == "a" and "href" in attributes:
                self.counts["links"] += 1
                self.candidates.append(attributes["href"] or "")
            if tag in EMBEDDED and attributes.get(EMBEDDED[tag]):
                self.counts["embedded_resources"] += 1
                self.candidates.append(attributes[EMBEDDED[tag]])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            offset = len(self.stack) - self.stack[::-1].index(tag) - 1
            del self.stack[offset:]

    def handle_data(self, data):
        if not any(name in {"script", "style"} for name in self.stack):
            self.text.append(data)

    def reference_candidates(self):
        tokens = re.findall(
            r"(?<![\w./])(?:https?://|//|(?:open|wafopen)\.ys7\.com/|/help/)[^\s<>\"'()\[\]{}]+",
            " ".join(self.text),
        )
        return self.candidates + tokens


def help_identity(candidate, base_url="https://open.ys7.com"):
    candidate = candidate.strip().rstrip(".,;，。；")
    if candidate.startswith(("open.ys7.com/", "wafopen.ys7.com/")):
        candidate = "https://" + candidate
    try:
        parsed = urlsplit(urljoin(base_url, candidate))
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"open.ys7.com", "wafopen.ys7.com"}:
            return None
        if parsed.port not in (None, 80, 443):
            return None
        match = re.fullmatch(r"/help/(en/)?([0-9]+)/?", parsed.path)
    except ValueError:
        return None
    return ("overseas" if match[1] else "domestic", match[2]) if match else None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class Audit:
    def __init__(self, root):
        self.root = root
        self.errors = []
        self.warnings = []
        self.checks = Counter()

    def expect(self, condition, code, detail):
        self.checks[code] += 1
        if not condition:
            self.errors.append({"code": code, "detail": detail})
        return condition

    def read(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Path escapes corpus: " + str(relative))
        return path.read_bytes()

    def json(self, relative):
        return json.loads(self.read(relative))

    def checked(self, relative, digest, code):
        data = self.read(relative)
        self.expect(_sha(data) == digest, code, str(relative))
        return data

    def receipt(self, receipt):
        raw = self.checked(receipt["raw_file"], receipt["sha256"], "receipt_sha256_mismatch")
        if receipt.get("bytes") is not None:
            self.expect(len(raw) == receipt["bytes"], "receipt_byte_count_mismatch", receipt["raw_file"])
        return json.loads(raw)


def _menu_nodes(tree, region, result):
    for node in tree:
        doc_id = str(node.get("id", ""))
        children = node.get("children") or []
        if doc_id.isdigit():
            result[(region, doc_id)].append({"title": node.get("title"), "has_children": bool(children)})
        _menu_nodes(children, region, result)


def _check_scope(audit, catalog):
    identities = {(entry["region"], str(entry["doc_id"])) for entry in catalog}
    nodes = defaultdict(list)
    manifest = None
    if (audit.root / "menus.json").exists():
        menus = audit.json("menus.json")
        for region, tree in menus.items():
            _menu_nodes(tree, region, nodes)
        required = set(nodes) | {("domestic", "452"), ("domestic", "5287")}
        for member in audit.json("menu-memberships.json"):
            required.add((member["region"], str(member["doc_id"])))
        for identity in sorted(required - identities):
            audit.expect(False, "menu_catalog_missing", list(identity))
        acquisition = audit.json("acquisition-summary.json")
        observed = {}
        for phase in ("initial_receipts", "final_receipts"):
            observed[phase] = {}
            for region, receipt in acquisition[phase].items():
                payload = audit.receipt(receipt)
                tree = payload["data"] if region == "domestic" else json.loads(payload["data"]["list"][0]["content"])
                observed[phase][region] = tree
        audit.expect(observed["initial_receipts"] == menus, "menu_snapshot_mismatch", "menus.json versus initial receipts")
        audit.expect(observed["initial_receipts"] == observed["final_receipts"], "menu_changed_during_capture", "initial versus final raw menu evidence")
        return nodes, {"kind": "official_help", "required_documents": len(required),
                       "present_documents": len(required & identities), "supplemental_entry_ids": ["452", "5287"]}, manifest
    manifest = audit.json("manifest.json")
    expected_urls = {entry["url"] for entry in manifest["entries"]}
    present_urls = {entry["source_url"] for entry in catalog}
    audit.expect(expected_urls == present_urls, "sdk_manifest_catalog_mismatch", {
        "missing": sorted(expected_urls - present_urls), "extra": sorted(present_urls - expected_urls)})
    return nodes, {"kind": "static_sdk_reference", "required_documents": len(expected_urls),
                   "present_documents": len(expected_urls & present_urls)}, manifest


def _api_body(audit, entry):
    payload = audit.receipt(entry["source_receipt"])
    identity = [entry["region"], str(entry["doc_id"])]
    audit.expect(str(payload.get("meta", {}).get("code")) == "200", "api_envelope_not_success", identity)
    if entry["region"] == "domestic":
        item = (payload.get("data") or {}).get("doc")
        if item:
            audit.expect(str(item.get("documentId")) == identity[1], "api_document_identity_mismatch", identity)
            audit.expect(item.get("plateform") in (None, "doc_open"), "api_platform_mismatch", identity)
        body = item.get("content") if item else None
    else:
        items = (payload.get("data") or {}).get("list") or []
        matches = [item for item in items if str(item.get("docId")) == identity[1] and item.get("platformType") == "doc_open_en"]
        audit.expect(len(matches) <= 1, "ambiguous_api_document", identity)
        item = matches[0] if matches else None
        body = item.get("htmlContent") if item else None
    if entry["status"] == "source_missing":
        audit.expect(item is None, "source_missing_has_api_record", identity)
    elif entry["status"] == "source_empty":
        audit.expect(not isinstance(body, str) or not body.strip(), "source_empty_has_body", identity)
    return body


def _sdk_body(audit, entry):
    receipt = entry["source_receipt"]
    if entry["status"] != "archived":
        audit.expect(receipt.get("status") != "ok", "unavailable_sdk_has_success_receipt", entry["source_url"])
        return None
    raw = audit.checked(receipt["local_path"], receipt["sha256"], "sdk_raw_sha256_mismatch")
    audit.expect(len(raw) == receipt["bytes"], "sdk_raw_byte_count_mismatch", receipt["local_path"])
    warning = entry.get("encoding_warning")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        audit.expect(bool(warning), "undeclared_source_encoding_loss", entry["source_url"])
        text = raw.decode("utf-8", errors="replace")
    if warning:
        audit.expect(warning.get("canonical_raw_file") == receipt["local_path"] and
                     warning.get("canonical_raw_sha256") == _sha(raw), "encoding_warning_raw_mismatch", entry["source_url"])
        audit.expect(text.count("\ufffd") == warning.get("replacement_characters"), "encoding_replacement_count_mismatch", entry["source_url"])
        audit.warnings.append({"code": "encoding_warning", "source_url": entry["source_url"],
                               "details": warning, "original_character_accuracy_verified": False})
    return text


def _sdk_reference(candidate, base, roots):
    try:
        parsed = urlsplit(urljoin(base, candidate))
        if parsed.scheme not in {"http", "https"} or parsed.hostname != "open.ys7.com":
            return None
        if parsed.port not in (None, 80, 443) or not parsed.path.lower().endswith(".html"):
            return None
        if not any(parsed.path.startswith(root) for root in roots):
            return None
        return urlunsplit(("https", "open.ys7.com", parsed.path, "", ""))
    except ValueError:
        return None


def verify(input_directory):
    root = Path(input_directory).resolve()
    audit = Audit(root)
    catalog = audit.json("catalog.json")
    identities = {(entry["region"], str(entry["doc_id"])) for entry in catalog}
    audit.expect(len(identities) == len(catalog), "duplicate_catalog_identity", len(catalog))
    menu_nodes, scope, manifest = _check_scope(audit, catalog)
    summary = audit.json("derivation-summary.json")
    audit.expect(summary["input_catalog_sha256"] == _sha(audit.read("catalog.json")), "derivation_catalog_sha256_mismatch", "catalog.json")
    audit.expect(summary["parser"]["sha256"] == _sha(Path(__file__).with_name("parse_html.py").read_bytes()),
                 "parser_source_sha256_mismatch", "derivation-summary.json parser provenance")
    indexes = {}
    for name, metadata in summary["indexes"].items():
        raw = audit.checked(name, metadata["sha256"], "index_sha256_mismatch")
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        audit.expect(len(rows) == metadata["rows"], "index_row_count_mismatch", name)
        indexes[name] = rows
    documents = {(entry["region"], str(entry["doc_id"])): entry for entry in indexes["documents.jsonl"]}
    audit.expect(set(documents) == identities and len(documents) == len(indexes["documents.jsonl"]), "document_index_identity_mismatch", "documents.jsonl")
    all_counts = Counter()
    independent_counts = Counter()
    raw_tags = Counter()
    status_stats = Counter()
    group_stats = defaultdict(Counter)
    missing = []
    edges = set()
    nested_pages = []
    urls = {entry["source_url"] for entry in catalog}
    roots = (manifest or {}).get("scope_roots") or sorted({
        match[0] for url in urls for match in [re.findall(r"^https?://open\.ys7\.com(/doc/(?:en|zh)/(?:android|ios|pc)/)", url)] if match})
    expected_index_rows = Counter({"documents.jsonl": len(catalog)})
    for entry in catalog:
        identity = (entry["region"], str(entry["doc_id"]))
        kind = entry.get("source_kind", "official_help")
        group_stats[(entry["region"], kind)][entry["status"]] += 1
        status_stats[entry["status"]] += 1
        doc = documents.get(identity)
        if doc is None:
            continue
        audit.expect(all(doc.get(key) == value for key, value in entry.items()), "document_index_metadata_mismatch", list(identity))
        body = _sdk_body(audit, entry) if kind == "static_sdk_reference" else _api_body(audit, entry)
        if entry["status"] != "archived":
            roles = menu_nodes.get(identity, [])
            if roles and all(role["has_children"] for role in roles):
                classification = "numeric_branch_with_no_body"
            elif roles:
                classification = "menu_leaf_with_no_body"
            elif kind == "static_sdk_reference":
                classification = "sdk_reference_unavailable"
            else:
                classification = "supplement_or_body_reference_with_no_body"
            missing.append({"region": identity[0], "doc_id": identity[1], "source_type": kind,
                            "source_url": entry["source_url"], "status": entry["status"],
                            "classification": classification, "menu_roles": roles,
                            "memberships": entry.get("memberships", [])})
            audit.expect(doc.get("counts") is None and doc.get("derivation_status") == "not_archived", "missing_body_falsely_derived", list(identity))
            continue
        raw = audit.checked(entry["raw_file"], entry["raw_file_sha256"], "source_sha256_mismatch")
        html = json.loads(raw)["html_content"]
        audit.expect(_sha(html.encode()) == entry["content_sha256"], "content_sha256_mismatch", list(identity))
        audit.expect(html == body, "source_body_differs_from_receipt", list(identity))
        structure = json.loads(audit.checked(doc["structure_file"], doc["structure_sha256"], "derived_sha256_mismatch"))
        text = audit.checked(doc["plain_text_file"], doc["plain_text_sha256"], "derived_sha256_mismatch")
        audit.expect(text == (structure["text"] + "\n").encode(), "plain_text_structure_mismatch", list(identity))
        audit.expect(doc["counts"] == structure["counts"], "document_structure_counts_mismatch", list(identity))
        inventory = IndependentHTMLInventory()
        inventory.feed(html)
        inventory.close()
        for key in COUNT_KEYS:
            audit.expect(inventory.counts[key] == structure["counts"].get(key, 0), "independent_html_count_mismatch",
                         {"document": list(identity), "field": key, "source": inventory.counts[key], "derived": structure["counts"].get(key, 0)})
        actual_cells = Counter(cell["kind"] for table in structure["tables"] for row in table["rows"] for cell in row)
        for cell_kind in ("th", "td"):
            audit.expect(actual_cells[cell_kind] == inventory.counts["table_" + cell_kind], "table_cell_kind_mismatch", {"document": list(identity), "kind": cell_kind})
        for field in ("headings", "tables", "code_blocks", "links", "images", "embedded_resources"):
            audit.expect(len(structure[field]) == structure["counts"][field], "structure_collection_count_mismatch", {"document": list(identity), "field": field})
        audit.expect(sum(len(table["rows"]) for table in structure["tables"]) == structure["counts"]["table_rows"], "structure_row_count_mismatch", list(identity))
        audit.expect(sum(actual_cells.values()) == structure["counts"]["table_cells"], "structure_cell_count_mismatch", list(identity))
        all_counts.update(structure["counts"])
        independent_counts.update(inventory.counts)
        raw_tags.update(inventory.raw_tags)
        if inventory.nested_tables:
            nested_pages.append({"region": identity[0], "doc_id": identity[1], "nested_tables": inventory.nested_tables})
        expected_index_rows["tables.jsonl"] += len(structure["tables"])
        expected_index_rows["code-blocks.jsonl"] += len(structure["code_blocks"])
        expected_index_rows["references.jsonl"] += sum(len(structure[field]) for field in ("links", "images", "embedded_resources"))
        for candidate in inventory.reference_candidates():
            target = _sdk_reference(candidate, entry["source_url"], roots) if manifest else help_identity(candidate, entry["source_url"])
            if target:
                edges.add((identity, target))
                present = target in urls if manifest else target in identities
                audit.expect(present, "reference_catalog_missing", {"from": list(identity), "target": target})
    for name, rows in indexes.items():
        audit.expect(len(rows) == expected_index_rows[name], "index_structure_row_count_mismatch", name)
        if name != "documents.jsonl":
            for row in rows:
                key = (row["region"], str(row["doc_id"]))
                audit.expect(key in identities and isinstance(row.get("source_element_index"), int), "index_source_identity_invalid", {"index": name, "document": key})
    audit.expect(dict(all_counts) == summary["counts"], "summary_counts_mismatch", "derivation-summary.json")
    audit.expect(dict(status_stats) == summary["by_status"], "summary_status_mismatch", "derivation-summary.json")
    audit.expect(len(catalog) == summary["documents"] and status_stats["archived"] == summary["derived_documents"], "summary_documents_mismatch", "derivation-summary.json")
    # 包括当前 catalog 之外的历史采集缓存：只核验其字节，不计入正文覆盖分母。
    for path in sorted((root / "sources").rglob("*.receipt.json")) if (root / "sources").exists() else []:
        receipt = json.loads(path.read_bytes())
        if receipt.get("raw_file") and receipt.get("sha256"):
            audit.receipt(receipt)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "offline_full_corpus_integrity_and_discovered_scope_closure",
        "passed": not audit.errors, "errors": audit.errors, "warnings": audit.warnings,
        "documents": len(catalog), "archived_bodies": status_stats["archived"],
        "all_discovered_bodies_available": not missing,
        "encoding_warning_count": len(audit.warnings),
        "scope_coverage": scope, "reference_edges_checked": len(edges),
        "by_status": status_stats,
        "by_region_source_type": [{"region": key[0], "source_type": key[1], "by_status": value}
                                  for key, value in sorted(group_stats.items())],
        "missing_body_classifications": Counter(item["classification"] for item in missing),
        "missing_bodies": missing, "checks": audit.checks,
        "structure_counts": all_counts, "independent_html_counts": independent_counts,
        "raw_html_tag_counts": raw_tags, "nested_table_pages": nested_pages,
        "input_catalog_sha256": _sha(audit.read("catalog.json")),
        "derivation_summary_sha256": _sha(audit.read("derivation-summary.json")),
        "limitations": [
            "passed 表示离线证据一致性和可发现范围闭包通过，不表示所有正文均可获取。",
            "数字父分类无正文单列为 numeric_branch_with_no_body，不能直接断言文章丢失。",
            "闭包限已归档正文与官方目录可发现的链接；不可用页面可能隐藏进一步资源。",
            "独立 HTMLParser 核验结构数量，不替代逐字人工校对、业务 schema 核实或真实 API 验证。",
            "counts.images 是 URL 引用数；编码替换告警页面不宣称原字符准确。",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="独立离线验证官方文档归档")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.input)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {"passed": False, "errors": [{"code": "verification_input_error", "detail": str(exc)}]}
    target = args.input / "verification-report.json"
    temporary = target.with_suffix(".json.partial")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"passed": report["passed"], "errors": len(report["errors"]),
                      "documents": report.get("documents"), "archived_bodies": report.get("archived_bodies"),
                      "missing_body_classifications": report.get("missing_body_classifications"),
                      "encoding_warning_count": report.get("encoding_warning_count")}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
