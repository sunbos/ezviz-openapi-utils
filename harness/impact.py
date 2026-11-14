"""Map a docdiff catalog report onto declared SDK bindings (stdlib only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

SCHEMA_VERSION = 1
EVIDENCE = "catalog_diff_and_declared_bindings_only"
REGIONS = ("domestic", "overseas")
CHANGE_ORDER = (
    "added",
    "removed",
    "content_changed",
    "status_changed",
    "source_changed",
    "title_changed",
    "navigation_changed",
)
CHANGE_SET = frozenset(CHANGE_ORDER)
REVIEW_CHANGES = CHANGE_SET - {"title_changed", "navigation_changed"}
UNRESOLVED = "unresolved_source_semantics"
MODULE_PREFIX = "src/ezviz_unified/"


class ImpactError(ValueError):
    pass


def _die(message: str) -> NoReturn:
    print(f"impact: error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _rows(value: object, name: str, field: str) -> list:
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != SCHEMA_VERSION
    ):
        raise ImpactError(f"{name}: expected a schema_version 1 object")
    rows = value.get(field)
    if not isinstance(rows, list):
        raise ImpactError(f"{name}: {field} must be a list")
    return rows


def _entry(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        raise ImpactError(f"{where}: expected a JSON object")
    return value


def _text(value: object, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImpactError(f"{where}: {field} must be a non-empty string")
    return value


def _region(value: object, where: str) -> str:
    if value not in REGIONS:
        raise ImpactError(f"{where}: region must be one of {REGIONS}")
    return value


def _module(value: object, where: str) -> str:
    module = _text(value, "module", where)
    parts = module.split("/")
    ok = (
        module.startswith(MODULE_PREFIX)
        and "\\" not in module
        and len(parts) >= 3
        and all(part not in ("", ".", "..") for part in parts)
        and parts[-1].endswith(".py")
        and parts[-1][:-3].isidentifier()
        and all(part.isidentifier() for part in parts[:-1])
    )
    if not ok:
        raise ImpactError(f"{where}: module must be a .py path under {MODULE_PREFIX}")
    return module


def _symbols(value: object, where: str) -> list:
    if not isinstance(value, list) or not value:
        raise ImpactError(f"{where}: symbols must be a non-empty list")
    for symbol in value:
        parts = symbol.split(".") if isinstance(symbol, str) else ()
        if len(parts) != 2 or not all(part.isidentifier() for part in parts):
            raise ImpactError(f"{where}: symbols items must be 'Class.method'")
    return list(value)


def _events(diff: object) -> list:
    seen, events = set(), []
    for i, raw in enumerate(_rows(diff, "diff", "events")):
        where = f"diff.events[{i}]"
        event = _entry(raw, where)
        changes = event.get("changes")
        if not (
            isinstance(changes, list)
            and changes
            and all(isinstance(c, str) and c in CHANGE_SET for c in changes)
        ):
            raise ImpactError(f"{where}: changes must be known change names")
        key = (_region(event.get("region"), where), _text(event.get("doc_id"), "doc_id", where))
        if key in seen:
            raise ImpactError(f"{where}: duplicate identity {key!r}")
        seen.add(key)
        events.append({"region": key[0], "doc_id": key[1], "changes": list(changes)})
    return events


def _bindings(bindings: object) -> list:
    seen, out = set(), []
    for i, raw in enumerate(_rows(bindings, "bindings", "bindings")):
        where = f"bindings.bindings[{i}]"
        entry = _entry(raw, where)
        op = _text(entry.get("operation_id"), "operation_id", where)
        if op in seen:
            raise ImpactError(f"{where}: duplicate operation_id {op!r}")
        seen.add(op)
        out.append(
            {
                "operation_id": op,
                "region": _region(entry.get("region"), where),
                "source_doc_id": _text(entry.get("source_doc_id"), "source_doc_id", where),
                "module": _module(entry.get("module"), where),
                "symbols": _symbols(entry.get("symbols"), where),
            }
        )
    return out


def _issues(issues: object) -> list:
    seen, out = set(), []
    for i, raw in enumerate(_rows(issues, "issues", "issues")):
        where = f"issues.issues[{i}]"
        entry = _entry(raw, where)
        issue_id = _text(entry.get("id"), "id", where)
        if issue_id in seen:
            raise ImpactError(f"{where}: duplicate id {issue_id!r}")
        seen.add(issue_id)
        out.append(
            {
                "id": issue_id,
                "region": _region(entry.get("region"), where),
                "source_doc_id": _text(entry.get("source_doc_id"), "source_doc_id", where),
                "pending": _text(entry.get("status"), "status", where) == UNRESOLVED,
            }
        )
    return out


def map_impact(diff: object, bindings: object, issues: object) -> dict[str, object]:
    events = _events(diff)
    by_doc: dict[tuple, list] = {}
    for entry in _bindings(bindings):
        by_doc.setdefault((entry["region"], entry["source_doc_id"]), []).append(entry)
    pending: dict[tuple, set] = {}
    for issue in _issues(issues):
        if issue["pending"]:
            pending.setdefault((issue["region"], issue["source_doc_id"]), set()).add(issue["id"])
    affected, unmapped, metadata_only, unresolved = [], [], [], set()
    for event in events:
        key = (event["region"], event["doc_id"])
        if not REVIEW_CHANGES & set(event["changes"]):
            metadata_only.append(event)
            continue
        unresolved |= pending.get(key, set())
        bound = by_doc.get(key)
        if not bound:
            unmapped.append(event)
            continue
        for entry in bound:
            affected.append(
                {
                    "operation_id": entry["operation_id"],
                    "region": event["region"],
                    "source_doc_id": event["doc_id"],
                    "module": entry["module"],
                    "symbols": entry["symbols"],
                    "changes": event["changes"],
                    "source_issue_ids": sorted(pending.get(key, ())),
                }
            )
    affected.sort(key=lambda item: item["operation_id"])
    unmapped.sort(key=lambda item: (item["region"], item["doc_id"]))
    metadata_only.sort(key=lambda item: (item["region"], item["doc_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": EVIDENCE,
        "needs_review": bool(affected or unmapped),
        "affected": affected,
        "unmapped": unmapped,
        "metadata_only": metadata_only,
        "summary": {
            "affected_operations": len(affected),
            "affected_modules": len({a["module"] for a in affected}),
            "unmapped_documents": len(unmapped),
            "metadata_only_documents": len(metadata_only),
        },
        "unresolved_issue_ids": sorted(unresolved),
    }


def _load(path: Path, label: str) -> tuple:
    try:
        raw = path.read_bytes()
    except OSError:
        _die(f"cannot read {label} file")
    try:
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (UnicodeError, json.JSONDecodeError):
        _die(f"invalid JSON or encoding in {label} file")


def _check_output(output: Path, inputs: tuple) -> None:
    resolved = output.resolve()
    for inp in inputs:
        if resolved == inp.resolve():
            _die("output must not overwrite an input file")
        try:
            if os.path.samefile(output, inp):
                _die("output must not overwrite an input file")
        except OSError:
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.impact",
        description="Map a docdiff report onto declared SDK bindings (no SDK code is run).",
    )
    parser.add_argument("--diff", required=True, type=Path, help="docdiff report JSON")
    parser.add_argument("--bindings", required=True, type=Path, help="bindings contract JSON")
    parser.add_argument("--issues", required=True, type=Path, help="source issues JSON")
    parser.add_argument("--output", type=Path, help="report path (default: stdout)")
    args = parser.parse_args(argv)
    diff, diff_sha = _load(args.diff, "--diff")
    bindings, bindings_sha = _load(args.bindings, "--bindings")
    issues, issues_sha = _load(args.issues, "--issues")
    try:
        report = map_impact(diff, bindings, issues)
    except ImpactError:
        _die("invalid input schema")
    report["inputs_sha256"] = {"diff": diff_sha, "bindings": bindings_sha, "issues": issues_sha}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
        return 0
    _check_output(args.output, (args.diff, args.bindings, args.issues))
    tmp: Path | None = None
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=args.output.parent,
            prefix=".impact-",
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
