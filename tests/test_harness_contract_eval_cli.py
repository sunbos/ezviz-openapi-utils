import importlib
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def copied_repo(tmp_path):
    root = tmp_path / "repo"
    for directory in (
        "src/ezviz_unified",
        "contracts",
        "docs/validation/live",
    ):
        shutil.copytree(ROOT / directory, root / directory)
    case = {
        "schema_version": 1,
        "cases": [
            {
                "operation_id": "cn.devices.get",
                "args": [{"$ref": "device_serial"}],
                "kwargs": {},
                "fields": {"deviceSerial": {"$ref": "device_serial"}},
                "data": {"marker": "fixture"},
            }
        ],
    }
    (root / "cases.json").write_text(json.dumps(case))
    return root


def run(root, timeout=30):
    return importlib.import_module("harness.contract_eval").run_evaluation(
        root, Path("cases.json"), timeout=timeout
    )


def test_child_uses_selected_sdk_source_and_synthetic_credentials(tmp_path):
    root = copied_repo(tmp_path)
    result = run(root)
    assert result["passed"] and not result["coverage_complete"]
    assert result["real_api_used"] is False
    assert len(result["inputs_sha256"]) == 3


def test_unexpected_sdk_output_is_suppressed_and_fails(tmp_path):
    root = copied_repo(tmp_path)
    with (root / "src/ezviz_unified/__init__.py").open("a") as handle:
        handle.write('\nprint("PRIVATE_OUTPUT_MUST_NOT_APPEAR")\n')
    result = run(root)
    assert not result["passed"] and result["guard_failure"] == "unexpected_sdk_output"
    assert "PRIVATE_OUTPUT_MUST_NOT_APPEAR" not in json.dumps(result)


def test_network_attempt_is_blocked_even_if_sdk_swallows_exception(tmp_path):
    root = copied_repo(tmp_path)
    with (root / "src/ezviz_unified/__init__.py").open("a") as handle:
        handle.write(
            '\nimport socket\ntry:\n    socket.getaddrinfo("blocked.invalid", 443)\nexcept Exception:\n    pass\n'
        )
    result = run(root)
    assert not result["passed"] and result["guard_failure"] == "network_attempt"


def test_worker_deadline_prevents_a_hanging_sdk_from_blocking_the_suite(tmp_path):
    root = copied_repo(tmp_path)
    with (root / "src/ezviz_unified/__init__.py").open("a") as handle:
        handle.write("\nwhile True:\n    pass\n")
    with pytest.raises(
        importlib.import_module("harness.contract_eval").EvaluationError, match="timed out"
    ):
        run(root, timeout=0.5)


def test_worker_receives_no_parent_credentials(tmp_path, monkeypatch):
    root = copied_repo(tmp_path)
    monkeypatch.setenv("EZVIZ_APP_SECRET", "PRIVATE_PARENT_CREDENTIAL")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "PRIVATE_PARENT_CREDENTIAL")
    with (root / "src/ezviz_unified/__init__.py").open("a") as handle:
        handle.write(
            '\nimport os\nif "EZVIZ_APP_SECRET" in os.environ or "ANTHROPIC_AUTH_TOKEN" in os.environ:\n    print("unexpected inherited credentials")\n'
        )
    assert run(root)["passed"]


def test_sdk_source_mutation_is_not_reported_as_matching_input(tmp_path):
    root = copied_repo(tmp_path)
    with (root / "src/ezviz_unified/__init__.py").open("a") as handle:
        handle.write(
            '\nfrom pathlib import Path\nPath(__file__).with_name("unexpected.py").write_text("# changed")\n'
        )
    with pytest.raises(
        importlib.import_module("harness.contract_eval").EvaluationError, match="source changed"
    ):
        run(root)


def complete_report():
    rows = [
        {
            "operation_id": "cn.example",
            "mode": mode,
            "layout": layout,
            "scenario": scenario,
            "passed": True,
            "problem": None,
        }
        for mode in ("sync", "async")
        for layout in ("", "body")
        for scenario in ("success", "auth_fault", "permission_fault", "http_fault")
    ]
    return {
        "schema_version": 1,
        "evidence": "offline_contract_conformance_only",
        "passed": True,
        "coverage_complete": True,
        "summary": {
            "contracts": 1,
            "cases": 1,
            "executions": 16,
            "passed_executions": 16,
            "failed_executions": 0,
        },
        "results": rows,
        "covered_operation_ids": ["cn.example"],
        "missing_operation_ids": [],
    }


def validate_report(report):
    module = importlib.import_module("harness.contract_eval")
    contracts = {
        "contracts": [{"operation_id": "cn.example", "success": {"envelope_paths": ["", "body"]}}]
    }
    cases = {"schema_version": 1, "cases": [{"operation_id": "cn.example"}]}
    module._validate_report(report, contracts, cases)


def test_parent_accepts_all_declared_layouts_and_fault_scenarios():
    validate_report(complete_report())


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_cell",
        "duplicate_cell",
        "unknown_scenario",
        "false_counts",
        "false_coverage",
        "non_boolean_pass",
        "unknown_problem",
        "raw_output",
        "false_guard_pass",
    ],
)
def test_parent_rejects_incomplete_or_forged_reports_without_echoing_values(tamper):
    report = complete_report()
    if tamper == "missing_cell":
        report["results"].pop()
    elif tamper == "duplicate_cell":
        report["results"][-1] = report["results"][0].copy()
    elif tamper == "unknown_scenario":
        report["results"][0]["scenario"] = "PRIVATE_REPORT_VALUE"
    elif tamper == "false_counts":
        report["summary"]["executions"] = 15
    elif tamper == "false_coverage":
        report["covered_operation_ids"] = []
    elif tamper == "non_boolean_pass":
        report["results"][0]["passed"] = 1
    elif tamper == "unknown_problem":
        report["results"][0].update(passed=False, problem="PRIVATE_REPORT_VALUE")
    elif tamper == "raw_output":
        report["debug"] = "PRIVATE_REPORT_VALUE"
    else:
        report["guard_failure"] = "network_attempt"
    with pytest.raises(importlib.import_module("harness.contract_eval").EvaluationError) as exc:
        validate_report(report)
    assert "PRIVATE_REPORT_VALUE" not in str(exc.value)
