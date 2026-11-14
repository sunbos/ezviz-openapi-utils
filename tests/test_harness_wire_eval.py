import copy
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def inputs(operation_id="cn.devices.get"):
    contracts = json.loads((ROOT / "contracts/reviewed-transport-contracts.json").read_text())
    bindings = json.loads((ROOT / "contracts/sdk-bindings.json").read_text())
    cases = {
        "schema_version": 1,
        "cases": [
            {
                "operation_id": operation_id,
                "args": [{"$ref": "device_serial"}],
                "kwargs": {},
                "fields": {"deviceSerial": {"$ref": "device_serial"}},
                "data": {"marker": "fixture", "isChecked": 0},
            }
        ],
    }
    return contracts, bindings, cases


def evaluate(data):
    assert (ROOT / "harness/wire_eval.py").exists(), "Wire evaluator missing"
    return importlib.import_module("harness.wire_eval").evaluate(*data, ROOT)


def test_one_case_exercises_real_wire_and_all_fault_scenarios():
    data = inputs()
    original = copy.deepcopy(data)
    report = evaluate(data)
    assert data == original
    assert report["passed"] and not report["coverage_complete"]
    assert report["covered_operation_ids"] == ["cn.devices.get"]
    assert report["summary"]["executions"] == 8
    assert report["summary"]["failed_executions"] == 0
    assert {r["scenario"] for r in report["results"]} == {
        "success",
        "auth_fault",
        "permission_fault",
        "http_fault",
    }
    assert report["evidence"] == "offline_contract_conformance_only"
    assert "safe_to_publish" not in report


def test_wrong_expected_fields_fail_without_echoing_values():
    data = inputs()
    data[2]["cases"][0]["fields"]["deviceSerial"] = "PRIVATE_VALUE_MUST_NOT_APPEAR"
    report = evaluate(data)
    assert not report["passed"] and not report["covered_operation_ids"]
    assert "PRIVATE_VALUE_MUST_NOT_APPEAR" not in json.dumps(report)


def test_contract_method_is_not_taken_from_sdk_output():
    data = inputs()
    next(r for r in data[0]["contracts"] if r["operation_id"] == "cn.devices.get")["method"] = "GET"
    report = evaluate(data)
    assert not report["passed"]


def test_auth_origin_is_checked_against_contract_not_the_sdk_factory():
    data = inputs()
    next(r for r in data[0]["contracts"] if r["operation_id"] == "cn.token.get")["base_url"] = (
        "https://different.example.invalid"
    )
    assert not evaluate(data)["passed"]


def test_fake_success_without_any_http_request_is_not_coverage(monkeypatch):
    from ezviz_unified import ApiResponse
    from ezviz_unified.devices import Devices

    monkeypatch.setattr(
        Devices,
        "get",
        lambda self, serial: ApiResponse(200, "200", data={"marker": "fixture", "isChecked": 0}),
    )
    report = evaluate(inputs())
    assert not report["passed"] and "cn.devices.get" not in report["covered_operation_ids"]


def test_write_replay_is_detected_even_if_declared_operation_looks_correct(monkeypatch):
    from dataclasses import replace

    from ezviz_unified import Client

    original = Client.request

    def incorrectly_replay(self, operation, **kwargs):
        return original(self, replace(operation, read_only=True), **kwargs)

    monkeypatch.setattr(Client, "request", incorrectly_replay)
    report = evaluate(inputs("cn.security.enable_encryption"))
    assert not report["passed"]
    assert any(not r["passed"] and r["scenario"] == "auth_fault" for r in report["results"])


@pytest.mark.parametrize(
    "edit",
    [
        "unknown_operation",
        "private_entry",
        "unknown_dto",
        "format_attribute",
        "duplicate_case",
        "reserved_token",
    ],
)
def test_malformed_or_unsafe_case_data_is_rejected(edit):
    data = inputs()
    case = data[2]["cases"][0]
    if edit == "unknown_operation":
        case["operation_id"] = "not.registered"
    elif edit == "private_entry":
        next(b for b in data[1]["bindings"] if b["operation_id"] == case["operation_id"])[
            "public_entry"
        ] = "_manager.get_token"
    elif edit == "unknown_dto":
        case["args"] = [{"$type": "Client", "kwargs": {}}]
    elif edit == "format_attribute":
        case["args"] = [{"$format": "{device_serial.__class__}"}]
    elif edit == "duplicate_case":
        data[2]["cases"].append(copy.deepcopy(case))
    else:
        case["fields"]["accessToken"] = "PRIVATE_TOKEN"
    try:
        report = evaluate(data)
    except ValueError as exc:
        assert "PRIVATE_TOKEN" not in str(exc)
    else:
        assert not report["passed"] and not report["covered_operation_ids"]
