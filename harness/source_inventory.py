"""Link portal catalog documents to audited transport contracts.

Evidence is limited to catalog-declared fields and registry-audited
contract source references. The tool never fetches URLs, reads raw
source files, or imports SDK modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import docdiff
from .audit import audit_repository

SCHEMA_VERSION = 1
EVIDENCE = "document_contract_links_only"
REGIONS = ("domestic", "overseas")
CONTRACTS_INPUT = "contracts/reviewed-transport-contracts.json"
UNCATEGORIZED = "未分类"

DISCLAIMER = (
    "Document-to-contract link evidence only; not an API inventory, "
    "support level, or release-readiness statement."
)
LIMITATIONS = [
    "raw source files and their hashes are not re-verified",
    "counts are document/contract link counts, not API totals or support rates",
    "documents without contract links include guides, SDK pages, and other non-endpoint content",
    "linked documents may still contain endpoints that have not been reviewed",
    "links do not prove real API support or permission to publish",
]

_E_CATALOG = "invalid catalog"
_E_MEMBERSHIP = "invalid catalog membership"
_E_CONTRACTS = "invalid contracts"
_E_LINK = "contract does not match an archived catalog document"
_E_INPUT = "invalid input"

_SUMMARY_KEYS = (
    "documents",
    "archived_documents",
    "source_unavailable_documents",
    "documents_with_contract_links",
    "documents_without_contract_links",
    "registered_contracts",
)


def _blank() -> dict:
    return dict.fromkeys(_SUMMARY_KEYS, 0)


def _paths(rec: dict) -> list:
    paths = set()
    for raw in rec["memberships"]:
        try:
            item = json.loads(raw)
        except ValueError:
            raise ValueError(_E_MEMBERSHIP) from None
        if not isinstance(item, dict):
            raise ValueError(_E_MEMBERSHIP)
        path = item.get("category_path")
        if not isinstance(path, list) or not all(isinstance(part, str) and part for part in path):
            raise ValueError(_E_MEMBERSHIP)
        paths.add(tuple(path))
    return sorted(paths)


def _contracts(data: dict) -> list:
    if not isinstance(data, dict):
        raise ValueError(_E_CONTRACTS)
    rows = data.get("contracts")
    if not isinstance(rows, list):
        raise ValueError(_E_CONTRACTS)
    seen = set()
    contracts = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(_E_CONTRACTS)
        op = row.get("operation_id")
        if not isinstance(op, str) or not op or op in seen:
            raise ValueError(_E_CONTRACTS)
        seen.add(op)
        region = row.get("region")
        doc_id = row.get("source_doc_id")
        url = row.get("source_url")
        sha = row.get("source_content_sha256")
        if not all(isinstance(v, str) and v for v in (region, doc_id, url, sha)):
            raise ValueError(_E_CONTRACTS)
        contracts.append(
            {
                "operation_id": op,
                "region": region,
                "doc_id": doc_id,
                "source_url": url,
                "source_content_sha256": sha,
            }
        )
    return contracts


def _count(bucket: dict, rec: dict, linked: list) -> None:
    bucket["documents"] += 1
    if rec["status"] == "archived":
        bucket["archived_documents"] += 1
    else:
        bucket["source_unavailable_documents"] += 1
    if linked:
        bucket["documents_with_contract_links"] += 1
    elif rec["status"] == "archived":
        bucket["documents_without_contract_links"] += 1
    bucket["registered_contracts"] += len(linked)


def inventory(catalog: object, contracts: dict) -> dict:
    try:
        records = docdiff._index(catalog, "catalog")
    except docdiff.CatalogError:
        raise ValueError(_E_CATALOG) from None
    paths = {key: _paths(rec) for key, rec in records.items()}
    linked = {key: [] for key in records}
    for contract in _contracts(contracts):
        key = (contract["region"], contract["doc_id"])
        rec = records.get(key)
        if (
            rec is None
            or rec["status"] != "archived"
            or rec["source_url"] != contract["source_url"]
            or rec["content_sha256"] != contract["source_content_sha256"]
        ):
            raise ValueError(_E_LINK)
        linked[key].append(contract["operation_id"])

    summary = _blank()
    regions = {region: _blank() for region in REGIONS}
    grouped = {}
    documents = []
    for key in sorted(records):
        rec = records[key]
        ops = sorted(linked[key])
        if rec["status"] != "archived":
            link_status = "source_unavailable"
        elif ops:
            link_status = "contracts_linked_partial"
        else:
            link_status = "no_contracts_linked"
        documents.append(
            {
                "region": rec["region"],
                "doc_id": rec["doc_id"],
                "title": rec["title"],
                "source_url": rec["source_url"],
                "status": rec["status"],
                "content_sha256": rec["content_sha256"],
                "category_paths": [list(p) for p in paths[key]],
                "linked_operation_ids": ops,
                "link_status": link_status,
            }
        )
        _count(summary, rec, ops)
        _count(regions[rec["region"]], rec, ops)
        tops = {p[0] if p else UNCATEGORIZED for p in paths[key]} or {UNCATEGORIZED}
        for top in tops:
            _count(grouped.setdefault((rec["region"], top), _blank()), rec, ops)
    categories = [
        {"region": region, "top_category": top, "summary": grouped[(region, top)]}
        for region, top in sorted(grouped)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": EVIDENCE,
        "summary": summary,
        "regions": regions,
        "categories": categories,
        "category_totals_are_non_additive": True,
        "documents": documents,
        "disclaimer": DISCLAIMER,
        "limitations": LIMITATIONS,
    }


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise ValueError(_E_INPUT) from None


def _repo_bytes(root: Path, relative: str) -> bytes:
    try:
        target = (root / relative).resolve(strict=True)
        if target.is_relative_to(root) and target.is_file():
            return target.read_bytes()
    except (OSError, RuntimeError):
        pass
    raise ValueError(_E_INPUT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="harness.source_inventory", description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        catalog_raw = _read_bytes(args.catalog)
        catalog = json.loads(catalog_raw.decode("utf-8"))
        try:
            root = args.repo.resolve()
        except (OSError, RuntimeError):
            raise ValueError(_E_INPUT) from None
        report = audit_repository(root)
        contracts_raw = _repo_bytes(root, CONTRACTS_INPUT)
        declared = report.get("inputs_sha256", {}).get(CONTRACTS_INPUT)
        if hashlib.sha256(contracts_raw).hexdigest() != declared:
            raise ValueError(_E_INPUT)
        contracts = json.loads(contracts_raw.decode("utf-8"))
        result = inventory(catalog, contracts)
        result["inputs_sha256"] = {
            "catalog": hashlib.sha256(catalog_raw).hexdigest(),
            "contracts": hashlib.sha256(contracts_raw).hexdigest(),
        }
    except (ValueError, OSError, RuntimeError):
        sys.stderr.write("source_inventory: error: invalid input\n")
        return 2
    if args.summary_only:
        result = {
            key: result[key]
            for key in (
                "schema_version",
                "evidence",
                "summary",
                "regions",
                "categories",
                "category_totals_are_non_additive",
                "disclaimer",
                "limitations",
                "inputs_sha256",
            )
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
