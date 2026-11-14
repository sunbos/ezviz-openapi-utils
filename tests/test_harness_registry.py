import copy
import importlib
from pathlib import Path

import pytest


def module():
    assert Path("harness/registry.py").exists(), "Registry auditor missing"
    return importlib.import_module("harness.registry")


def fixtures():
    return [
        {
            "schema_version": 1,
            "contracts": [
                {
                    "operation_id": "cn.feature.get",
                    "region": "domestic",
                    "source_doc_id": "1",
                    "source_url": "https://open.ys7.com/help/1",
                    "source_content_sha256": "a" * 64,
                    "method": "POST",
                    "path": "/api/feature/get",
                    "read_only": True,
                    "body_encoding": "form_urlencoded",
                    "token_location": "form",
                    "parameters": [
                        {
                            "name": "accessToken",
                            "location": "body",
                            "type": "String",
                            "required": True,
                        }
                    ],
                    "success": {"code_path": "meta.code", "values": [200]},
                }
            ],
        },
        {
            "schema_version": 1,
            "bindings": [
                {
                    "operation_id": "cn.feature.get",
                    "region": "domestic",
                    "source_doc_id": "1",
                    "module": "src/ezviz_unified/feature.py",
                    "symbols": ["Feature.get", "AsyncFeature.get"],
                    "offline_status": "passed",
                    "live_status": "not_verified",
                }
            ],
        },
        {
            "schema_version": 1,
            "issues": [
                {
                    "id": "source_conflict",
                    "region": "domestic",
                    "source_doc_id": "1",
                    "source_url": "https://open.ys7.com/help/1",
                    "source_content_sha256": "a" * 64,
                    "description": "source conflict",
                    "status": "unresolved_source_semantics",
                    "sdk_handling": "preserve raw",
                }
            ],
        },
        {
            "schema_version": 1,
            "source_commit": "b" * 40,
            "compatibility_shim": False,
            "mapped_count": 1,
            "pending_count": 0,
            "methods": [
                {
                    "legacy_method": "old_get",
                    "source_line": 7,
                    "status": "mapped_with_breaking_changes",
                    "target": "client.feature.get",
                    "argument_map": {"old_arg": "new_arg"},
                    "notes": "breaking change",
                }
            ],
        },
        {
            "source_commit": "b" * 40,
            "public_method_count": 1,
            "operations": [{"name": "old_get", "source_line": 7}],
        },
    ]


def test_registry_cross_references_and_counts_without_mutation():
    data = fixtures()
    before = copy.deepcopy(data)
    result = module().audit_registry(*data)
    assert data == before
    assert result["evidence"] == "registry_structure_only"
    assert result["summary"] == {
        "contracts": 1,
        "bindings": 1,
        "source_documents": 1,
        "source_issues": 1,
        "legacy_methods": 1,
        "mapped_legacy_methods": 1,
        "pending_legacy_methods": 0,
    }
    assert result["regions"] == {"domestic": 1}
    assert result["live_status_counts"] == {"not_verified": 1}
    assert not ({"safe_to_publish", "approved"} & result.keys())


@pytest.mark.parametrize(
    "index,path,value",
    [
        (0, ("schema_version",), True),
        (1, ("schema_version",), 2),
        (2, ("issues",), {}),
        (3, ("schema_version",), "1"),
        (0, ("contracts", 0, "source_content_sha256"), None),
        (0, ("contracts", 0, "source_content_sha256"), "A" * 64),
        (0, ("contracts", 0, "read_only"), 1),
        (0, ("contracts", 0, "method"), "post"),
        (0, ("contracts", 0, "path"), "//outside.invalid/x"),
        (0, ("contracts", 0, "path"), "/api/x?password=PRIVATE_VALUE"),
        (0, ("contracts", 0, "path"), "/api/x\\y"),
        (0, ("contracts", 0, "region"), "global"),
        (0, ("contracts", 0, "source_doc_id"), "1 "),
        (0, ("contracts", 0, "operation_id"), " cn.feature.get"),
        (0, ("contracts", 0, "token_location"), "body"),
        (0, ("contracts", 0, "token_location"), "header"),
        (0, ("contracts", 0, "token_location"), "none"),
        (0, ("contracts", 0, "body_encoding"), "json"),
        (0, ("contracts", 0, "parameters", 0, "required"), 1),
        (0, ("contracts", 0, "parameters", 0, "required"), False),
        (0, ("contracts", 0, "parameters", 0, "location"), "cookie"),
        (0, ("contracts", 0, "parameters", 0, "type"), ""),
        (0, ("contracts", 0, "success", "values"), [True]),
        (0, ("contracts", 0, "success", "values"), []),
        (0, ("contracts", 0, "success", "code_path"), "meta..code"),
        (0, ("contracts", 0, "success", "message_path"), ".message"),
        (0, ("contracts", 0, "success", "require_device_code"), True),
        (0, ("contracts", 0, "success", "require_device_code"), 1),
        (0, ("contracts", 0, "success", "device_success_values"), [False]),
        (1, ("bindings", 0, "source_doc_id"), "2"),
        (1, ("bindings", 0, "operation_id"), "unknown"),
        (1, ("bindings", 0, "symbols"), []),
        (1, ("bindings", 0, "argument_constants"), {"setting": []}),
        (1, ("bindings", 0, "argument_constants"), {"bad-key": 1}),
        (1, ("bindings", 0, "live_status"), "empty_list_succeeded"),
        (2, ("issues", 0, "source_content_sha256"), "c" * 64),
        (2, ("issues", 0, "source_url"), "https://open.ys7.com/help/2"),
        (3, ("mapped_count",), 0),
        (3, ("pending_count",), True),
        (3, ("compatibility_shim",), "false"),
        (3, ("methods", 0, "source_line"), 8),
        (3, ("methods", 0, "source_line"), True),
        (3, ("methods", 0, "legacy_method"), "other"),
        (3, ("methods", 0, "status"), "verified"),
        (3, ("methods", 0, "argument_map"), {"x": None}),
        (3, ("methods", 0, "target"), None),
        (4, ("public_method_count",), True),
        (4, ("source_commit",), "different"),
    ],
)
def test_registry_rejects_corruption_without_echoing_input(index, path, value):
    data = fixtures()
    target = data[index]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(module().RegistryError) as caught:
        module().audit_registry(*data)
    assert "PRIVATE_VALUE" not in str(caught.value)


@pytest.mark.parametrize(
    "index,key",
    [(0, "contracts"), (1, "bindings"), (2, "issues"), (3, "methods"), (4, "operations")],
)
def test_duplicate_identities_are_never_silently_collapsed(index, key):
    data = fixtures()
    data[index][key].append(copy.deepcopy(data[index][key][0]))
    with pytest.raises(module().RegistryError):
        module().audit_registry(*data)


def test_unmapped_source_issue_and_reported_live_failure_remain_distinct():
    data = fixtures()
    data[2]["issues"][0].update(
        source_doc_id="99",
        source_url="https://open.ys7.com/help/99",
        source_content_sha256="c" * 64,
    )
    data[1]["bindings"][0].update(
        live_status="request_failed_http_500", live_evidence="docs/report.json"
    )
    data[3]["methods"][0].update(status="not_migrated", target=None, argument_map=None)
    data[3].update(mapped_count=0, pending_count=1)
    result = module().audit_registry(*data)
    assert result["live_status_counts"] == {"request_failed_http_500": 1}
    assert result["summary"]["mapped_legacy_methods"] == 0
    assert result["summary"]["source_documents"] == 1


def test_duplicate_parameters_and_incomplete_binding_set_fail():
    data = fixtures()
    data[0]["contracts"][0]["parameters"] *= 2
    with pytest.raises(module().RegistryError):
        module().audit_registry(*data)
    data = fixtures()
    data[1]["bindings"] = []
    with pytest.raises(module().RegistryError):
        module().audit_registry(*data)
