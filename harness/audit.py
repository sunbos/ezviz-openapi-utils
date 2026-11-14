"""Read-only registry/AST audit CLI; never imports SDK implementation modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .code_audit import CodeAuditError, audit_code
from .registry import RegistryError, audit_registry

_INPUTS = (
    "contracts/reviewed-transport-contracts.json",
    "contracts/sdk-bindings.json",
    "contracts/source-issues.json",
    "contracts/legacy-migration.json",
    "docs/research/legacy-audit/legacy-method-inventory.json",
)
_COVERAGE = "contracts/coverage.json"


class AuditInputError(ValueError):
    pass


def _load(root: Path, relative: str) -> tuple[object, str]:
    raw = None
    try:
        target = (root / relative).resolve(strict=True)
        if target.is_relative_to(root) and target.is_file():
            raw = target.read_bytes()
    except (OSError, RuntimeError):
        pass
    if raw is None:
        raise AuditInputError("input is missing, unreadable, or outside the repository")
    parsed = None
    valid = False
    try:
        parsed = json.loads(raw)
        valid = True
    except (UnicodeError, ValueError):
        pass
    if not valid:
        raise AuditInputError("invalid input JSON or encoding")
    return parsed, hashlib.sha256(raw).hexdigest()


def audit_repository(repo_root: Path) -> dict:
    root = None
    try:
        root = repo_root.resolve()
    except (OSError, RuntimeError):
        pass
    if root is None:
        raise AuditInputError("repository root cannot be resolved")
    values = []
    hashes = {}
    for relative in _INPUTS:
        data, digest = _load(root, relative)
        values.append(data)
        hashes[relative] = digest
    registry = audit_registry(*values)
    code = audit_code(root, values[1], values[3])
    return {
        "schema_version": 1,
        "evidence": "registry_and_static_ast_only",
        "registry": registry,
        "code": code,
        "inputs_sha256": hashes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--summary-only", action="store_true")
    mode.add_argument("--check-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit_repository(args.repo)
        if args.check_summary:
            existing, _ = _load(args.repo.resolve(), _COVERAGE)
            if existing != report["registry"]:
                raise AuditInputError("coverage summary is stale; regenerate from current inputs")
    except (AuditInputError, RegistryError, CodeAuditError) as exc:
        sys.stderr.write(f"audit: {exc}\n")
        return 2
    output = report["registry"] if args.summary_only else report
    sys.stdout.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
