import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def event(doc="1", changes=None):
    return {"region": "domestic", "doc_id": doc, "changes": changes or ["content_changed"]}


def binding(op="cn.test", doc="1", module="src/ezviz_unified/devices.py"):
    return {
        "operation_id": op,
        "region": "domestic",
        "source_doc_id": doc,
        "module": module,
        "symbols": ["Devices.get"],
    }


def issue(identifier="conflict", doc="1", status="unresolved_source_semantics"):
    return {"id": identifier, "region": "domestic", "source_doc_id": doc, "status": status}


def impact(events, bindings, issues=()):
    assert Path("harness/impact.py").exists(), "Impact mapper missing"
    return importlib.import_module("harness.impact").map_impact(
        {"schema_version": 1, "needs_review": False, "events": list(events)},
        {"schema_version": 1, "bindings": list(bindings)},
        {"schema_version": 1, "issues": list(issues)},
    )


def test_source_change_maps_all_operations_and_does_not_trust_review_flag():
    result = impact(
        [event(), event("2"), event("3", ["title_changed"])],
        [binding("cn.z"), binding("cn.a")],
        [issue(), issue("resolved", status="resolved")],
    )
    assert [x["operation_id"] for x in result["affected"]] == ["cn.a", "cn.z"]
    assert result["affected"][0]["source_issue_ids"] == ["conflict"]
    assert result["unmapped"] == [event("2")]
    assert result["metadata_only"] == [event("3", ["title_changed"])]
    assert result["needs_review"] and result["unresolved_issue_ids"] == ["conflict"]
    assert result["summary"] == {
        "affected_operations": 2,
        "affected_modules": 1,
        "unmapped_documents": 1,
        "metadata_only_documents": 1,
    }
    assert (
        result["evidence"] == "catalog_diff_and_declared_bindings_only"
        and "safe_to_publish" not in result
    )


def test_metadata_only_is_not_a_code_change():
    result = impact([event(changes=["navigation_changed"])], [binding()], [issue()])
    assert (
        not result["needs_review"] and not result["affected"] and not result["unresolved_issue_ids"]
    )


@pytest.mark.parametrize(
    "bad_module",
    [
        "/etc/passwd",
        "src/ezviz_unified/../../secret.py",
        "src\\ezviz_unified\\x.py",
        "harness/impact.py",
    ],
)
def test_mapping_paths_are_data_and_must_stay_inside_sdk(bad_module):
    with pytest.raises(ValueError):
        impact([event()], [binding(module=bad_module)])


@pytest.mark.parametrize(
    "events,bindings,issues",
    [
        ([event(), event()], [binding()], []),
        ([event()], [binding(), binding()], []),
        ([event()], [binding()], [issue(), issue()]),
        ([event(changes=["publish_now"])], [binding()], []),
    ],
)
def test_ambiguous_or_unknown_inputs_are_rejected(events, bindings, issues):
    with pytest.raises(ValueError):
        impact(events, bindings, issues)


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_cli_cannot_overwrite_inputs(tmp_path, alias):
    inputs = {
        "diff": {"schema_version": 1, "events": [event()]},
        "bindings": {"schema_version": 1, "bindings": [binding()]},
        "issues": {"schema_version": 1, "issues": []},
    }
    for name, value in inputs.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    original = tmp_path / "bindings.json"
    before = original.read_bytes()
    output = original if alias == "same" else tmp_path / "out.json"
    if alias == "symlink":
        output.symlink_to(original)
    if alias == "hardlink":
        output.hardlink_to(original)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.impact",
            "--diff",
            str(tmp_path / "diff.json"),
            "--bindings",
            str(original),
            "--issues",
            str(tmp_path / "issues.json"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and original.read_bytes() == before


@pytest.mark.parametrize("which", [0, 1, 2])
def test_schema_version_boolean_is_not_integer_one(which):
    values = [
        {"schema_version": 1, "events": [event()]},
        {"schema_version": 1, "bindings": [binding()]},
        {"schema_version": 1, "issues": []},
    ]
    values[which]["schema_version"] = True
    with pytest.raises(ValueError):
        importlib.import_module("harness.impact").map_impact(*values)


def test_unknown_issue_region_is_not_silently_ignored():
    bad = issue()
    bad["region"] = "unknown"
    with pytest.raises(ValueError):
        impact([event()], [binding()], [bad])


def test_whitespace_identity_is_not_valid():
    with pytest.raises(ValueError):
        impact([event(" ")], [binding()])


def test_windows_drive_component_is_not_sdk_relative():
    with pytest.raises(ValueError):
        impact([event()], [binding(module="src/ezviz_unified/C:/outside.py")])
