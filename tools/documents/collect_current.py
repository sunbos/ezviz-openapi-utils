"""Capture every current frontend document by its authoritative menu identity."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import (ORIGIN, LIST_PATH, PLATFORMS, PublicSources, atomic_write,
                     fetch_catalogs, help_references, listing_data, menu_memberships,
                     save_json, select_record, sha256, utc_now, verified_bytes)


def current_doc(payload, expected_id):
    doc = (payload.get("data") or {}).get("doc")
    if doc is None:
        return None
    if not isinstance(doc, dict) or str(doc.get("documentId")) != str(expected_id):
        raise ValueError("Current frontend returned a different document identity")
    return doc


def import_english_cache(directory, sources):
    manifest_path = Path(directory) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["entries"]:
        doc_id = entry["doc_id"]
        body = verified_bytes(Path(directory)/entry["raw_file"], entry["raw_sha256"])
        name = "current/overseas-" + doc_id
        filename = sources.output / "sources" / (name + ".json")
        signature = {"url": ORIGIN+LIST_PATH, "method": "GET", "params": {
            "pageStart": 1, "pageSize": 1, "tag": 1, "docId": doc_id}, "form": None}
        receipt = {"request": signature, "request_url": entry["request_url"],
            "final_url": entry.get("final_url"), "status_code": entry.get("http_status"),
            "retrieved_at_utc": entry.get("fetched_at_utc"),
            "started_at_utc": entry.get("requested_at_utc"),
            "content_type": entry.get("content_type"), "etag": entry.get("etag"),
            "last_modified": entry.get("last_modified"), "bytes": len(body),
            "sha256": sha256(body), "raw_file": str(filename.relative_to(sources.output)),
            "imported_from_independent_manifest_sha256": sha256(manifest_path.read_bytes())}
        atomic_write(filename, body)
        save_json(filename.with_suffix(".receipt.json"), receipt)
    save_json(sources.output/"sources/independent-english-manifest.json", manifest)


def capture_page(sources, region, doc_id):
    public_url = ORIGIN + "/help/" + ("en/" if region == "overseas" else "") + doc_id
    entry = {"region": region, "doc_id": doc_id, "source_url": public_url}
    try:
        if region == "domestic":
            payload, proof = sources.capture("current/domestic-"+doc_id,
                "/web/console/doc/center/doc/get", params={"docId": doc_id})
            doc = current_doc(payload, doc_id)
            content = doc.get("content") if doc else None
            platform = doc.get("plateform") if doc else None
            title = doc.get("title") if doc else None
        else:
            payload, proof = sources.capture("current/overseas-"+doc_id, LIST_PATH,
                params={"pageStart": 1, "pageSize": 1, "tag": 1, "docId": doc_id})
            _, rows = listing_data(payload)
            doc = select_record(rows, region, doc_id)
            content = doc.get("htmlContent") if doc else None
            platform = doc.get("platformType") if doc else None
            title = doc.get("fileName") if doc else None
        entry.update({"source_receipt": proof, "title": title,
            "source_record_platform": platform,
            "source_created_at": (doc or {}).get("createTime"),
            "source_updated_at": (doc or {}).get("updateTime"),
            "source_displayed_modified_at": (doc or {}).get("modifyTime")})
        if doc is None:
            entry.update(status="source_missing", missing_evidence="Current frontend request returned no document")
        elif platform not in (None, PLATFORMS[region]):
            entry.update(status="platform_mismatch", missing_evidence="Document platform differs from menu region")
        elif not isinstance(content, str) or not content.strip():
            entry.update(status="source_empty", missing_evidence="Current frontend returned an empty body")
        else:
            raw_path = Path("pages")/region/(doc_id+".source.json")
            save_json(sources.output/raw_path, {"doc_id": doc_id, "title": title,
                "html_content": content, "platform": platform})
            entry.update(status="archived", raw_file=str(raw_path),
                raw_file_sha256=sha256((sources.output/raw_path).read_bytes()),
                content_sha256=sha256(content.encode()), content_characters=len(content),
                content_bytes=len(content.encode()), missing_evidence=None)
        return entry, help_references(content, public_url) if entry["status"] == "archived" else set()
    except Exception as exc:
        entry.update(status="acquisition_failed", error_type=type(exc).__name__)
        return entry, set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--english-cache", type=Path)
    parser.add_argument("--environment-proxy", action="store_true")
    args = parser.parse_args()
    sources = PublicSources(args.output, args.environment_proxy)
    trees, initial_receipts = fetch_catalogs(sources)
    save_json(args.output/"menus.json", trees)
    if args.english_cache:
        import_english_cache(args.english_cache, sources)
    members = []
    for region, tree in trees.items():
        members.extend(menu_memberships(tree, region))
    for doc_id, title in [("452", "微信小程序开发方案"), ("5287", "新手地图")]:
        members.append({"region": "domestic", "doc_id": doc_id, "menu_title": title,
            "category_path": ["官方文档中心补充入口", title],
            "discovery_url": ORIGIN+"/cn/s/supportcenter"})
    memberships = defaultdict(list)
    for member in members:
        memberships[(member["region"], member["doc_id"])].append(member)
    save_json(args.output/"menu-memberships.json", members)
    pending = set(memberships)
    completed = {}
    edges = []
    round_number = 0
    while pending:
        round_number += 1
        batch = sorted(pending)
        pending = set()
        print(f"Current-frontend round {round_number}: {len(batch)} documents", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            jobs = {executor.submit(capture_page, sources, region, doc_id): (region, doc_id)
                    for region, doc_id in batch}
            for job in as_completed(jobs):
                key = jobs[job]
                entry, references = job.result()
                entry["memberships"] = memberships[key]
                entry["title"] = entry.get("title") or memberships[key][0]["menu_title"]
                completed[key] = entry
                for is_en, linked_id in references:
                    target = ("overseas" if is_en else "domestic", linked_id)
                    edges.append({"from_region": key[0], "from_doc_id": key[1],
                                  "to_region": target[0], "to_doc_id": target[1]})
                    if target not in memberships:
                        memberships[target].append({"region": target[0], "doc_id": linked_id,
                            "menu_title": "正文引用文档", "category_path": ["正文引用补充"],
                            "discovery_url": entry["source_url"]})
                        pending.add(target)
                if len(completed) % 100 == 0 or len(completed) == len(batch):
                    counts = dict(Counter(e["status"] for e in completed.values()))
                    print(f"captured {len(completed)}: {counts}", flush=True)
                    save_json(args.output/"catalog-checkpoint.json", list(completed.values()))
    catalog = sorted(completed.values(), key=lambda e: (e["region"], int(e["doc_id"])))
    save_json(args.output/"catalog.json", catalog)
    save_json(args.output/"document-reference-edges.json", edges)
    final_trees, final_receipts = fetch_catalogs(sources, "end", refresh=True)
    summary = {"finished_at_utc": utc_now(), "acquisition_method": "current frontend per-document requests",
        "catalog_entries": len(catalog), "initial_unique_menu_and_entry_documents": len({
            (m["region"], m["doc_id"]) for m in members}),
        "by_status": dict(Counter(e["status"] for e in catalog)),
        "menu_unchanged": trees == final_trees,
        "reference_queue_exhausted": not pending,
        "initial_receipts": initial_receipts, "final_receipts": final_receipts,
        "note": "Document observations span a collection window; the website provides no atomic snapshot."}
    save_json(args.output/"acquisition-summary.json", summary)
    print(json.dumps({k:v for k,v in summary.items() if not k.endswith("receipts")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
