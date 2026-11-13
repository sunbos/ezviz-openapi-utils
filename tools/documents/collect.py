"""Archive publicly linked EZVIZ documentation as inert source data.

This collector never calls device APIs or executes documentation HTML.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode, urlsplit, urljoin

import requests
from bs4 import BeautifulSoup


ORIGIN = "https://open.ys7.com"
PLATFORMS = {"domestic": "doc_open", "overseas": "doc_open_en"}
LIST_PATH = "/help/api/help_doc/doc/list"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def save_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def verified_bytes(path, digest):
    value = Path(path).read_bytes()
    if sha256(value) != digest:
        raise ValueError(f"Source hash mismatch: {path}")
    return value


def menu_memberships(tree, region, parents=()):
    rows = []
    for node in tree:
        path = (*parents, str(node.get("title", "")))
        doc_id = str(node.get("id", ""))
        if re.fullmatch(r"[0-9]+", doc_id):
            rows.append({"region": region, "doc_id": doc_id,
                         "category_path": list(path), "menu_title": node.get("title", "")})
        rows.extend(menu_memberships(node.get("children") or [], region, path))
    return rows


def listing_data(response):
    if str(response.get("meta", {}).get("code")) != "200":
        raise ValueError("Listing response did not report success")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise ValueError("Listing has no document records")
    total = data.get("total")
    if not isinstance(total, int) or total < len(data["list"]):
        raise ValueError("Invalid declared listing total")
    return total, data["list"]


def select_record(records, region, doc_id):
    matches = [r for r in records if str(r.get("docId")) == str(doc_id)
               and r.get("platformType") == PLATFORMS[region]]
    versions = {r.get("htmlContent") for r in matches}
    if len(versions) > 1:
        raise ValueError(f"Ambiguous source versions for {region}/{doc_id}")
    return matches[0] if matches else None


class PublicSources:
    def __init__(self, output, use_environment_proxy=False):
        self.output = Path(output)
        self.local = threading.local()
        self.use_environment_proxy = use_environment_proxy

    def session(self):
        if not hasattr(self.local, "session"):
            session = requests.Session()
            session.trust_env = self.use_environment_proxy
            session.headers["User-Agent"] = "Mozilla/5.0 (compatible; EZVIZDocumentationArchive/1.0)"
            self.local.session = session
        return self.local.session

    def capture(self, name, path, *, params=None, data=None, refresh=False):
        allowed = {LIST_PATH, "/help/api/help_doc/doc/menu/info",
                   "/web/console/doc/center/menu/raw/tree",
                   "/web/console/doc/center/menu/official/tree",
                   "/web/console/doc/center/doc/get"}
        if path not in allowed:
            raise ValueError("Only public documentation data endpoints are allowed")
        filename = self.output / "sources" / (name + ".json")
        receipt_path = self.output / "sources" / (name + ".receipt.json")
        url = ORIGIN + path
        signature = {"url": url, "method": "POST" if data is not None else "GET",
                     "params": params, "form": data}
        if not refresh and filename.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt["request"] == signature:
                return json.loads(verified_bytes(filename, receipt["sha256"])), receipt
        attempts = []
        for attempt in range(1, 5):
            started = utc_now()
            try:
                response = self.session().request(signature["method"], url,
                    params=params, data=data, timeout=(10, 35))
                response.raise_for_status()
                payload = response.json()
                if str(payload.get("meta", {}).get("code")) != "200":
                    raise ValueError("Source returned an unsuccessful documentation envelope")
                body = response.content
                receipt = {"request": signature, "request_url": response.request.url,
                    "final_url": response.url, "retrieved_at_utc": utc_now(),
                    "started_at_utc": started, "status_code": response.status_code,
                    "content_type": response.headers.get("Content-Type"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "bytes": len(body), "sha256": sha256(body),
                    "raw_file": str(filename.relative_to(self.output)),
                    "prior_attempts": attempts}
                atomic_write(filename, body)
                save_json(receipt_path, receipt)
                return payload, receipt
            except (requests.RequestException, ValueError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                attempts.append({"at_utc": started, "type": type(exc).__name__, "status": status})
                if status in (400, 401, 403, 404, 410) or attempt == 4:
                    save_json(filename.with_suffix(".failure.json"),
                              {"request": signature, "attempts": attempts})
                    raise
                time.sleep(min(attempt, 3))


def fetch_catalogs(sources, suffix="start", refresh=False):
    cn, cn_receipt = sources.capture("cn-menu-" + suffix,
        "/web/console/doc/center/menu/raw/tree", data={}, refresh=refresh)
    en, en_receipt = sources.capture("en-menu-" + suffix,
        "/help/api/help_doc/doc/menu/info", params={"pageStart": 1, "pageSize": 1,
            "platformType": "doc_open_en"}, refresh=refresh)
    if not isinstance(cn.get("data"), list) or not cn["data"]:
        raise ValueError("Domestic menu is empty or malformed")
    total, menus = listing_data(en)
    if total != 1 or len(menus) != 1:
        raise ValueError("Overseas menu identity is ambiguous")
    en_tree = json.loads(menus[0]["content"])
    if not isinstance(en_tree, list):
        raise ValueError("Overseas menu is not a tree array")
    trees = {"domestic": cn["data"], "overseas": en_tree}
    return trees, {"domestic": cn_receipt, "overseas": en_receipt}


def page_offsets(total, page_size):
    if page_size < 1 or total < 0:
        raise ValueError("Invalid pagination bounds")
    # The official frontend starts at 1. Live checks show starts 1 and 2
    # overlap by page_size-1 rows, while start 0 is rejected by the server.
    return list(range(1, total + 1, page_size))


def validate_bulk_records(records, total):
    identifiers = [r.get("id") for r in records]
    if len(records) != total or None in identifiers or len(set(identifiers)) != total:
        raise ValueError("Bulk listing is incomplete or contains overlapping pages")


def bulk_harvest(sources, workers=4, page_size=100):
    first, receipt = sources.capture("bulk-start-000001", LIST_PATH,
        params={"pageStart": 1, "pageSize": page_size, "tag": 1})
    total, first_rows = listing_data(first)
    if len(first_rows) != min(page_size, total):
        raise ValueError("Server page-size behavior differs from the requested pagination")
    offsets = page_offsets(total, page_size)
    pages = len(offsets)
    records = [(r, receipt) for r in first_rows]
    failures = []
    def page(offset):
        payload, proof = sources.capture(f"bulk-start-{offset:06d}", LIST_PATH,
            params={"pageStart": offset, "pageSize": page_size, "tag": 1})
        declared_total, rows = listing_data(payload)
        if declared_total != total or len(rows) != min(page_size, total-offset+1):
            raise ValueError("Listing changed or a page was truncated")
        return rows, proof
    print(f"Published listing: {total} records / {pages} pages", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(page, offset): offset for offset in offsets[1:]}
        for future in as_completed(futures):
            number = futures[future]
            try:
                rows, proof = future.result()
                records.extend((r, proof) for r in rows)
                print(f"bulk offset {number}/{total}: {len(rows)} records", flush=True)
            except Exception as exc:
                failures.append({"page": number, "error": type(exc).__name__})
                print(f"bulk page {number}: {type(exc).__name__}", flush=True)
    save_json(sources.output / "bulk-summary.json", {"expected_records": total,
        "acquired_records": len(records), "pages": pages, "failures": failures,
        "note": "Mixed-platform records are discovery transport, not the public document scope."})
    if failures:
        raise RuntimeError("Bulk pages remain missing; rerun to resume verified caches")
    validate_bulk_records([r for r, _ in records], total)
    return records


def help_references(html, base_url=ORIGIN + "/help/"):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    candidates = [urljoin(base_url, str(a["href"])) for a in soup.find_all("a", href=True)]
    candidates.extend(re.findall(
        r"(?<![\w./])(?:https?://|//|(?:open|wafopen)\.ys7\.com/|/help/)[^\s<>\"'()\[\]{}]+",
        soup.get_text(" ")))
    refs = set()
    for candidate in candidates:
        candidate = candidate.rstrip(".,;，。；")
        if candidate.startswith(("open.ys7.com/", "wafopen.ys7.com/")):
            candidate = "https://" + candidate
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        if candidate.startswith("/help/"):
            candidate = ORIGIN + candidate
        try:
            parsed = urlsplit(candidate)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
                "open.ys7.com", "wafopen.ys7.com"
            } or parsed.port not in (None, 80, 443):
                continue
        except ValueError:
            continue
        match = re.fullmatch(r"/help/(en/)?([0-9]+)/?", parsed.path)
        if match:
            refs.add((bool(match[1]), match[2]))
    return refs


def archive_pages(sources, trees, records):
    memberships = []
    for region, tree in trees.items():
        memberships.extend(menu_memberships(tree, region))
    # These links were found in the official support-center HTML, outside rawTree.
    for doc_id, title in [("452", "微信小程序开发方案"), ("5287", "新手地图")]:
        memberships.append({"region": "domestic", "doc_id": doc_id,
            "menu_title": title, "category_path": ["官方文档中心补充入口", title],
            "discovery_url": ORIGIN + "/cn/s/supportcenter"})
    paths = defaultdict(list)
    for member in memberships:
        paths[(member["region"], member["doc_id"])].append(member)
    raw_rows = [r for r, _ in records]
    indexed = defaultdict(list)
    proofs = {}
    for row, proof in records:
        key = (row.get("platformType"), str(row.get("docId")))
        indexed[key].append(row)
        proofs.setdefault(key, proof)
    queue = list(paths)
    completed = set()
    catalog = []
    while queue:
        region, doc_id = queue.pop(0)
        if (region, doc_id) in completed:
            continue
        completed.add((region, doc_id))
        row = select_record(indexed[(PLATFORMS[region], doc_id)], region, doc_id)
        proof = proofs.get((PLATFORMS[region], doc_id))
        status = "archived"
        missing_evidence = None
        if row is None:
            if region == "domestic":
                payload, proof = sources.capture(f"single-cn-{doc_id}",
                    "/web/console/doc/center/doc/get", params={"docId": doc_id})
                item = (payload.get("data") or {}).get("doc")
                if item and str(item.get("documentId")) == doc_id:
                    row = {"docId": doc_id, "fileName": item.get("title"),
                        "htmlContent": item.get("content"), "platformType": item.get("plateform"),
                        "createTime": item.get("createTime"), "updateTime": item.get("updateTime"),
                        "displayedModifyTime": item.get("modifyTime")}
            else:
                payload, proof = sources.capture(f"single-en-{doc_id}", LIST_PATH,
                    params={"pageStart": 1, "pageSize": 1, "tag": 1, "docId": doc_id})
                _, matches = listing_data(payload)
                row = select_record(matches, region, doc_id)
            if row is None:
                status = "source_missing"
                missing_evidence = "Official frontend data request returned no matching document"
        content = (row or {}).get("htmlContent")
        if row is not None and (not isinstance(content, str) or not content.strip()):
            status = "source_empty"
        if row is not None and row.get("platformType") not in (None, PLATFORMS[region]):
            status = "platform_mismatch"
        public_url = ORIGIN + "/help/" + ("en/" if region == "overseas" else "") + doc_id
        entry = {"region": region, "doc_id": doc_id, "source_url": public_url,
            "title": (row or {}).get("fileName") or paths[(region, doc_id)][0]["menu_title"],
            "memberships": paths[(region, doc_id)], "status": status,
            "source_receipt": proof, "source_record_platform": (row or {}).get("platformType"),
            "source_created_at": (row or {}).get("createTime"),
            "source_updated_at": (row or {}).get("updateTime"),
            "missing_evidence": missing_evidence}
        if status == "archived":
            raw_path = Path("pages") / region / (doc_id + ".source.json")
            # HTML remains inside JSON and is never executed or presented as a live page.
            save_json(sources.output / raw_path, {"doc_id": doc_id, "title": row.get("fileName"),
                "html_content": content, "platform": row.get("platformType")})
            entry.update({"raw_file": str(raw_path), "content_sha256": sha256(content.encode()),
                "raw_file_sha256": sha256((sources.output/raw_path).read_bytes()),
                "content_characters": len(content), "content_bytes": len(content.encode())})
            for is_en, linked_id in sorted(help_references(content, public_url)):
                linked_region = "overseas" if is_en else "domestic"
                linked_key = (linked_region, linked_id)
                if linked_key not in paths:
                    paths[linked_key].append({"region": linked_region, "doc_id": linked_id,
                        "menu_title": "正文引用文档", "category_path": ["正文引用补充"],
                        "discovery_url": public_url})
                    queue.append(linked_key)
        catalog.append(entry)
        if len(catalog) % 100 == 0:
            print(f"classified {len(catalog)} documents; pending {len(queue)}", flush=True)
        if len(catalog) % 100 == 0:
            save_json(sources.output / "catalog-checkpoint.json", catalog)
    # Attach all membership paths even when a duplicate was discovered later.
    for entry in catalog:
        entry["memberships"] = paths[(entry["region"], entry["doc_id"])]
    save_json(sources.output / "catalog.json", catalog)
    save_json(sources.output / "menu-memberships.json", memberships)
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--environment-proxy", action="store_true")
    args = parser.parse_args()
    sources = PublicSources(args.output, args.environment_proxy)
    trees, receipts = fetch_catalogs(sources)
    save_json(args.output / "menus.json", trees)
    records = bulk_harvest(sources, args.workers)
    catalog = archive_pages(sources, trees, records)
    final_trees, final_receipts = fetch_catalogs(sources, "end", refresh=True)
    save_json(args.output / "acquisition-summary.json", {"finished_at_utc": utc_now(),
        "catalog_entries": len(catalog),
        "by_status": {s: sum(e["status"] == s for e in catalog) for s in {e["status"] for e in catalog}},
        "menu_unchanged": trees == final_trees,
        "initial_receipts": receipts, "final_receipts": final_receipts})


if __name__ == "__main__":
    main()
