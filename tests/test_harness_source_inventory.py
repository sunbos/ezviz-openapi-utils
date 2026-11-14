import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest


def module():
    assert Path("harness/source_inventory.py").exists(), "Official source inventory missing"
    return importlib.import_module("harness.source_inventory")


def inputs():
    catalog = []
    contracts = []
    for region in ("domestic", "overseas"):
        row = {
            "region": region,
            "doc_id": "1",
            "title": "source",
            "status": "archived",
            "source_url": f"https://example.invalid/{region}/1",
            "content_sha256": "a" * 64,
            "memberships": [
                {"category_path": ["API", "one"]},
                {"category_path": ["API", "two"]},
                {"category_path": ["Guide"]},
            ],
        }
        catalog.append(row)
        for op in ("read", "write") if region == "domestic" else ("read",):
            contracts.append(
                {
                    "operation_id": f"{region}.{op}",
                    "region": region,
                    "source_doc_id": "1",
                    "source_url": row["source_url"],
                    "source_content_sha256": row["content_sha256"],
                }
            )
    unlinked = copy.deepcopy(catalog[0])
    unlinked.update(doc_id="2", memberships=[])
    catalog.append(unlinked)
    missing = copy.deepcopy(unlinked)
    missing.update(doc_id="3", status="source_missing", content_sha256=None)
    catalog.append(missing)
    return catalog, {"contracts": contracts}


def test_all_documents_are_accounted_without_claiming_api_support():
    data = inputs()
    before = copy.deepcopy(data)
    report = module().inventory(*data)
    assert data == before
    assert report["evidence"] == "document_contract_links_only"
    assert report["summary"] == {
        "documents": 4,
        "archived_documents": 3,
        "source_unavailable_documents": 1,
        "documents_with_contract_links": 2,
        "documents_without_contract_links": 1,
        "registered_contracts": 3,
    }
    assert report["category_totals_are_non_additive"] is True
    domestic_api = next(
        x for x in report["categories"] if x["region"] == "domestic" and x["top_category"] == "API"
    )
    assert domestic_api["summary"]["documents"] == 1
    assert domestic_api["summary"]["registered_contracts"] == 2
    assert {x["link_status"] for x in report["documents"]} == {
        "contracts_linked_partial",
        "no_contracts_linked",
        "source_unavailable",
    }
    assert len(report["documents"]) == 4
    assert not ({"coverage_percent", "safe_to_publish", "all_supported"} & report.keys())


@pytest.mark.parametrize(
    "change",
    ["duplicate_doc", "duplicate_op", "missing_doc", "hash", "url", "unavailable", "bad_path"],
)
def test_inconsistent_links_are_rejected(change):
    catalog, contracts = inputs()
    if change == "duplicate_doc":
        catalog.append(copy.deepcopy(catalog[0]))
    elif change == "duplicate_op":
        contracts["contracts"].append(copy.deepcopy(contracts["contracts"][0]))
    elif change == "missing_doc":
        contracts["contracts"][0]["source_doc_id"] = "404"
    elif change == "hash":
        contracts["contracts"][0]["source_content_sha256"] = "b" * 64
    elif change == "url":
        contracts["contracts"][0]["source_url"] = "https://wrong.invalid/"
    elif change == "unavailable":
        catalog[0].update(status="source_missing", content_sha256=None)
    else:
        catalog[0]["memberships"][0]["category_path"] = ["API", None]
    with pytest.raises(ValueError):
        module().inventory(catalog, contracts)


def test_permutation_and_duplicate_membership_do_not_change_report():
    catalog, contracts = inputs()
    expected = module().inventory(catalog, contracts)
    catalog[0]["memberships"].append(copy.deepcopy(catalog[0]["memberships"][0]))
    catalog.reverse()
    contracts["contracts"].reverse()
    assert module().inventory(catalog, contracts) == expected


def test_empty_category_path_is_explicitly_uncategorized():
    catalog, contracts = inputs()
    catalog[2]["memberships"] = [{"category_path": []}]
    report = module().inventory(catalog, contracts)
    group = next(
        c
        for c in report["categories"]
        if c["region"] == "domestic" and c["top_category"] == "未分类"
    )
    assert group["summary"]["documents"] == 2


def test_alternate_source_fields_cannot_hide_missing_canonical_fields():
    catalog, contracts = inputs()
    row = contracts["contracts"][0]
    row["source"] = {"doc_id": row.pop("source_doc_id")}
    with pytest.raises(ValueError):
        module().inventory(catalog, contracts)


def test_cli_records_exact_inputs_and_never_opens_catalog_raw_file(tmp_path, monkeypatch, capsys):
    mod = module()
    catalog, contracts = inputs()
    catalog[0]["raw_file"] = "/must/not/read/this"
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps(catalog))
    target = tmp_path / "contracts/reviewed-transport-contracts.json"
    target.parent.mkdir()
    target.write_text(json.dumps(contracts))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(
        mod,
        "audit_repository",
        lambda root: {"inputs_sha256": {"contracts/reviewed-transport-contracts.json": digest}},
    )
    assert mod.main(["--catalog", str(source), "--repo", str(tmp_path), "--summary-only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "documents" not in report
    assert set(report["inputs_sha256"].values()) == {
        digest,
        hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        mod,
        "audit_repository",
        lambda root: {"inputs_sha256": {"contracts/reviewed-transport-contracts.json": "b" * 64}},
    )
    assert mod.main(["--catalog", str(source), "--repo", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert not captured.out and "/must/not/read" not in captured.err
