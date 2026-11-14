"""Run synthetic SDK contract evaluations in a bounded, credential-free child."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .audit import AuditInputError, _load, audit_repository
from .code_audit import CodeAuditError
from .registry import RegistryError

_WORKER = Path(__file__).with_name("_contract_worker.py")
_SCENARIOS = {"success", "auth_fault", "permission_fault", "http_fault"}
_PROBLEMS = {
    "case_invalid",
    "contract_invalid",
    "binding_invalid",
    "unknown_operation_id",
    "managed_token_field",
    "missing_required_field",
    "unknown_field",
    "ambiguous_field_location",
    "sdk_import_failed",
    "auth_contract_missing",
    "auth_request_mismatch",
    "request_mismatch",
    "response_mismatch",
    "wrong_exception_type",
    "wrong_exception_status",
    "cleanup_failed",
    "harness_error",
    "request_limit_exceeded",
    "operation_dispatch",
    "operation_mismatch",
    "unexpected_exception",
    "expected_exception_absent",
    "request_count_mismatch",
    "auth_count_mismatch",
    "token_mismatch",
    "cases_invalid",
    "duplicate_operation_id",
}


class EvaluationError(ValueError):
    pass


def _source_snapshot(root: Path) -> dict[str, str]:
    sdk_root = (root / "src/ezviz_unified").resolve()
    if not sdk_root.is_relative_to(root):
        raise EvaluationError("SDK source escapes repository")
    snapshots = {}
    for path in sorted(sdk_root.rglob("*.py")):
        if not path.resolve().is_relative_to(sdk_root):
            raise EvaluationError("SDK source escapes repository")
        snapshots[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshots


def _validate_report(report: dict, contracts: dict, cases: dict) -> None:
    """Recompute coverage and cell counts instead of trusting child summary flags."""
    allowed = {
        "schema_version",
        "evidence",
        "passed",
        "coverage_complete",
        "summary",
        "results",
        "covered_operation_ids",
        "missing_operation_ids",
        "guard_failure",
    }
    if (
        set(report) - allowed
        or type(report.get("schema_version")) is not int
        or report["schema_version"] != 1
    ):
        raise EvaluationError("invalid worker report schema")
    if report.get("evidence") != "offline_contract_conformance_only":
        raise EvaluationError("invalid worker report evidence")
    contract_map = {r["operation_id"]: r for r in contracts["contracts"]}
    if (
        not isinstance(cases, dict)
        or type(cases.get("schema_version")) is not int
        or cases["schema_version"] != 1
        or not isinstance(cases.get("cases"), list)
    ):
        raise EvaluationError("invalid case schema")
    selected = []
    for case in cases["cases"]:
        op = case.get("operation_id") if isinstance(case, dict) else None
        if not isinstance(op, str) or op not in contract_map or op in selected:
            raise EvaluationError("unknown or duplicate evaluation operation")
        selected.append(op)
    expected = {
        (op, mode, layout, scenario)
        for op in selected
        for mode in ("sync", "async")
        for layout in contract_map[op]["success"].get("envelope_paths", [""])
        for scenario in _SCENARIOS
    }
    results = report.get("results")
    if not isinstance(results, list):
        raise EvaluationError("invalid worker results")
    seen = set()
    passed_count = 0
    successful = {op: True for op in selected}
    for row in results:
        if not isinstance(row, dict) or set(row) != {
            "operation_id",
            "mode",
            "layout",
            "scenario",
            "passed",
            "problem",
        }:
            raise EvaluationError("invalid worker result row")
        values = [row[k] for k in ("operation_id", "mode", "layout", "scenario")]
        if not all(isinstance(v, str) for v in values):
            raise EvaluationError("invalid worker result identity")
        cell = tuple(values)
        if cell not in expected or cell in seen or type(row["passed"]) is not bool:
            raise EvaluationError("missing, duplicate or unexpected evaluation cell")
        if row["passed"]:
            if row["problem"] is not None:
                raise EvaluationError("invalid passing result")
            passed_count += 1
        else:
            if not isinstance(row["problem"], str) or row["problem"] not in _PROBLEMS:
                raise EvaluationError("unrecognized worker problem code")
            successful[row["operation_id"]] = False
        seen.add(cell)
    if seen != expected:
        raise EvaluationError("incomplete evaluation result cells")
    covered = sorted(op for op, passed in successful.items() if passed)
    missing = sorted(set(contract_map) - set(covered))
    summary = {
        "contracts": len(contract_map),
        "cases": len(selected),
        "executions": len(results),
        "passed_executions": passed_count,
        "failed_executions": len(results) - passed_count,
    }
    actual_summary = report.get("summary")
    if (
        not isinstance(actual_summary, dict)
        or any(type(v) is not int for v in actual_summary.values())
        or actual_summary != summary
    ):
        raise EvaluationError("inconsistent evaluation summary")
    guard = report.get("guard_failure")
    if guard is not None and guard not in {"network_attempt", "unexpected_sdk_output"}:
        raise EvaluationError("invalid guard result")
    if (
        report.get("covered_operation_ids") != covered
        or report.get("missing_operation_ids") != missing
    ):
        raise EvaluationError("inconsistent operation coverage")
    if report.get("passed") is not (
        bool(results) and passed_count == len(results) and guard is None
    ):
        raise EvaluationError("inconsistent evaluation outcome")
    if report.get("coverage_complete") is not (not missing and guard is None):
        raise EvaluationError("inconsistent complete-coverage claim")


def run_evaluation(repo_root: Path, cases_path: Path, *, timeout: float = 90.0) -> dict:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 300
    ):
        raise EvaluationError("timeout must be finite and between 0 and 300 seconds")
    root = repo_root.resolve()
    source = cases_path if cases_path.is_absolute() else root / cases_path
    source = source.resolve()
    if not source.is_relative_to(root):
        raise EvaluationError("cases must be inside the repository")
    audited = audit_repository(root)
    contracts, contract_hash = _load(root, "contracts/reviewed-transport-contracts.json")
    bindings, binding_hash = _load(root, "contracts/sdk-bindings.json")
    cases, case_hash = _load(root, source.relative_to(root).as_posix())
    if (
        contract_hash != audited["inputs_sha256"]["contracts/reviewed-transport-contracts.json"]
        or binding_hash != audited["inputs_sha256"]["contracts/sdk-bindings.json"]
    ):
        raise EvaluationError("registry changed during evaluation setup")
    inputs = {"repo_root": str(root), "contracts": contracts, "bindings": bindings, "cases": cases}
    source_hashes = _source_snapshot(root)
    env = {"PATH": os.defpath, "LANG": "C.UTF-8"}
    with tempfile.TemporaryDirectory(prefix="ezviz-eval-") as temp:
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-X", f"pycache_prefix={temp}", str(_WORKER)],
                input=json.dumps(inputs, ensure_ascii=True),
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=root,
                env=env,
            )
        except subprocess.TimeoutExpired:
            result = None
    if result is None:
        raise EvaluationError("evaluation worker timed out")
    if result.returncode != 0 or result.stderr:
        raise EvaluationError("evaluation worker failed; output suppressed")
    report = None
    try:
        report = json.loads(result.stdout)
    except (UnicodeError, ValueError):
        pass
    if (
        not isinstance(report, dict)
        or report.get("evidence") != "offline_contract_conformance_only"
    ):
        raise EvaluationError("unexpected evaluation worker output")
    _validate_report(report, contracts, cases)
    if _source_snapshot(root) != source_hashes:
        raise EvaluationError("SDK source changed during evaluation")
    report["inputs_sha256"] = {
        "contracts": contract_hash,
        "bindings": binding_hash,
        "cases": case_hash,
    }
    report["source_files_sha256"] = source_hashes
    report["real_api_used"] = False
    report["network_guard"] = "Python socket operations blocked; not an OS security sandbox"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--cases", type=Path, default=Path("evals/contracts/cases.json"))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_evaluation(args.repo, args.cases, timeout=args.timeout)
    except (EvaluationError, AuditInputError, RegistryError, CodeAuditError, OSError, RuntimeError):
        sys.stderr.write("contract-eval: input, worker, timeout or source consistency failure\n")
        return 2
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return (
        0
        if report.get("passed") is True
        and (not args.require_all or report.get("coverage_complete") is True)
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
