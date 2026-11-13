"""Deterministic diff between two portal catalog.json snapshots.

The tool compares content hashes declared by the catalogs themselves; it
never re-fetches or re-verifies the source files or URLs they reference.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

SCHEMA_VERSION = 1
EVIDENCE = "catalog_declared_hashes_only"
REGIONS = ("domestic", "overseas")
STATUSES = ("archived", "source_missing")
CHANGE_ORDER = (
    "added",
    "removed",
    "content_changed",
    "status_changed",
    "source_changed",
    "title_changed",
    "navigation_changed",
)
REVIEW_CHANGES = CHANGE_ORDER[:5]
_HEX_DIGITS = frozenset("0123456789abcdef")


class CatalogError(ValueError):
    """Raised when a catalog row is malformed."""


def _die(message: str) -> NoReturn:
    print(f"docdiff: error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _canon_memberships(memberships: list, where: str) -> list:
    # sort_keys normalizes dict key order only; nested list order such as
    # category_path stays significant. Exact duplicates collapse via the set.
    canon = set()
    for item in memberships:
        try:
            canon.add(
                json.dumps(
                    item, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
                )
            )
        except (TypeError, ValueError) as exc:
            raise CatalogError(f"{where}: membership is not JSON serializable: {exc}") from exc
    return sorted(canon)


def _validate_row(row: object, index: int, label: str) -> dict:
    where = f"{label} row {index}"
    if not isinstance(row, dict):
        raise CatalogError(f"{where}: expected a JSON object")
    doc_id = row.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id:
        raise CatalogError(f"{where}: doc_id must be a non-empty string")
    where = f"{where} ({doc_id!r})"
    region = row.get("region")
    if region not in REGIONS:
        raise CatalogError(f"{where}: region must be one of {REGIONS}")
    status = row.get("status")
    if status not in STATUSES:
        raise CatalogError(f"{where}: status must be one of {STATUSES}")
    sha = row.get("content_sha256")
    if sha is not None and not (
        isinstance(sha, str) and len(sha) == 64 and set(sha) <= _HEX_DIGITS
    ):
        raise CatalogError(f"{where}: content_sha256 must be 64 lowercase hex chars or null")
    if status == "archived" and sha is None:
        raise CatalogError(f"{where}: archived rows must declare content_sha256")
    if status == "source_missing" and sha is not None:
        raise CatalogError(f"{where}: source_missing rows must not declare content_sha256")
    source_url = row.get("source_url")
    if not isinstance(source_url, str) or not source_url:
        raise CatalogError(f"{where}: source_url must be a non-empty string")
    title = row.get("title", "")
    if not isinstance(title, str):
        raise CatalogError(f"{where}: title must be a string")
    memberships = row.get("memberships", [])
    if not isinstance(memberships, list) or not all(isinstance(m, dict) for m in memberships):
        raise CatalogError(f"{where}: memberships must be a list of objects")
    return {
        "region": region,
        "doc_id": doc_id,
        "status": status,
        "content_sha256": sha,
        "source_url": source_url,
        "title": title,
        "memberships": _canon_memberships(memberships, where),
    }


def _index(catalog: object, label: str) -> dict:
    if not isinstance(catalog, list):
        raise CatalogError(f"{label}: catalog must be a JSON array")
    records = {}
    for i, row in enumerate(catalog):
        rec = _validate_row(row, i, label)
        key = (rec["region"], rec["doc_id"])
        if key in records:
            raise CatalogError(f"{label} row {i}: duplicate identity {key!r}")
        records[key] = rec
    return records


def _project(rec: dict | None) -> dict | None:
    if rec is None:
        return None
    return {
        "status": rec["status"],
        "content_sha256": rec["content_sha256"],
        "source_url": rec["source_url"],
    }


def compare_catalogs(before: object, after: object) -> dict[str, object]:
    before_map = _index(before, "before")
    after_map = _index(after, "after")
    counts = dict.fromkeys(CHANGE_ORDER, 0)
    unchanged = 0
    events = []
    for key in sorted(before_map.keys() | after_map.keys()):
        old = before_map.get(key)
        new = after_map.get(key)
        if old is None:
            changes = ["added"]
        elif new is None:
            changes = ["removed"]
        else:
            changes = []
            if old["content_sha256"] != new["content_sha256"]:
                changes.append("content_changed")
            if old["status"] != new["status"]:
                changes.append("status_changed")
            if old["source_url"] != new["source_url"]:
                changes.append("source_changed")
            if old["title"] != new["title"]:
                changes.append("title_changed")
            if old["memberships"] != new["memberships"]:
                changes.append("navigation_changed")
        if not changes:
            unchanged += 1
            continue
        for name in changes:
            counts[name] += 1
        region, doc_id = key
        events.append(
            {
                "region": region,
                "doc_id": doc_id,
                "changes": changes,
                "before": _project(old),
                "after": _project(new),
            }
        )
    summary = {name: counts[name] for name in CHANGE_ORDER}
    summary["unchanged"] = unchanged
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": EVIDENCE,
        "summary": summary,
        "needs_review": any(counts[name] for name in REVIEW_CHANGES),
        "events": events,
    }


def _load(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        _die(f"cannot read {label} catalog")
    except (UnicodeError, json.JSONDecodeError):
        _die(f"invalid JSON or encoding in {label} catalog")


def _check_output(output: Path, inputs: tuple) -> None:
    resolved = output.resolve()
    for inp in inputs:
        if resolved == inp.resolve():
            _die("output must not overwrite an input catalog")
        try:
            if os.path.samefile(output, inp):
                _die("output must not overwrite an input catalog")
        except OSError:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.docdiff",
        description="Diff two portal catalog.json snapshots (declared hashes only).",
    )
    parser.add_argument("--before", required=True, type=Path, help="older catalog.json")
    parser.add_argument("--after", required=True, type=Path, help="newer catalog.json")
    parser.add_argument("--output", type=Path, help="report path (default: stdout)")
    args = parser.parse_args(argv)

    before = _load(args.before, "--before")
    after = _load(args.after, "--after")
    try:
        report = compare_catalogs(before, after)
    except CatalogError:
        _die("invalid catalog schema")
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
        return 0
    _check_output(args.output, (args.before, args.after))
    tmp: Path | None = None
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=args.output.parent,
            prefix=".docdiff-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp = Path(handle.name)
            handle.write(text)
        os.replace(tmp, args.output)
    except OSError:
        _die("cannot write report")
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
