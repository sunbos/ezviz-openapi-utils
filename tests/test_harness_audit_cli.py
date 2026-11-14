import json
import subprocess
import sys
from pathlib import Path


def test_repository_audit_and_summary_are_machine_generated():
    assert Path("harness/audit.py").exists(), "Audit CLI missing"
    result = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", "."], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["evidence"] == "registry_and_static_ast_only"
    assert len(report["inputs_sha256"]) == 3
    summary = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", ".", "--summary-only"],
        capture_output=True,
        text=True,
    )
    assert summary.returncode == 0, summary.stderr
    assert json.loads(summary.stdout) == report["registry"]
    checked = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", ".", "--check-summary"],
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_missing_repo_and_malformed_json_fail_without_printing_contents(tmp_path):
    root = tmp_path / "repo"
    (root / "contracts").mkdir(parents=True)
    (root / "contracts/reviewed-transport-contracts.json").write_text('{"PRIVATE_CONTENT":')
    result = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", str(root)], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "PRIVATE_CONTENT" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_stale_summary_is_rejected(tmp_path):
    import shutil

    root = tmp_path / "repo"
    # Copy only the owning sources and referenced evidence; no raw corpus or credentials.
    for folder in (
        "contracts",
        "src/ezviz_unified",
        "docs/validation/live",
    ):
        shutil.copytree(Path(folder), root / folder)
    summary = json.loads((root / "contracts/coverage.json").read_text())
    summary["summary"]["contracts"] += 1
    (root / "contracts/coverage.json").write_text(json.dumps(summary))
    result = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", str(root), "--check-summary"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "summary" in result.stderr.lower()


def test_audit_passes_without_legacy_migration_or_inventory(tmp_path):
    import shutil

    root = tmp_path / "repo"
    shutil.copytree(Path("src/ezviz_unified"), root / "src/ezviz_unified")
    shutil.copytree(Path("docs/validation/live"), root / "docs/validation/live")
    (root / "contracts").mkdir(parents=True)
    official = (
        "reviewed-transport-contracts.json",
        "sdk-bindings.json",
        "source-issues.json",
    )
    for name in official:
        shutil.copy(Path("contracts") / name, root / "contracts" / name)
    assert not (root / "contracts/legacy-migration.json").exists()
    assert not (root / "docs/research/legacy-audit").exists()
    result = subprocess.run(
        [sys.executable, "-m", "harness.audit", "--repo", str(root)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["evidence"] == "registry_and_static_ast_only"
    assert len(report["inputs_sha256"]) == 3
