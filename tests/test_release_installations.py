import importlib
import os
import subprocess
from pathlib import Path

import pytest
from test_release_artifacts import artifacts


def module():
    assert Path("tools/release/verify_installations.py").exists(), "Install verifier missing"
    return importlib.import_module("tools.release.verify_installations")


@pytest.fixture
def isolated_commands(tmp_path, monkeypatch):
    # Assertions must never include the host's credential-bearing environment.
    monkeypatch.setattr(os, "environ", {"PATH": os.environ.get("PATH", "")})
    dist, project = artifacts(tmp_path)
    smoke = tmp_path / "tools/release/smoke_installed.py"
    smoke.parent.mkdir(parents=True)
    smoke.write_text("pass\n")
    calls = []

    def run(args, **kwargs):
        calls.append((list(map(str, args)), kwargs))
        if "-m" in args and "venv" in args:
            target = Path(args[-1])
            folder = target / ("Scripts" if os.name == "nt" else "bin")
            folder.mkdir(parents=True, exist_ok=True)
            (folder / ("python.exe" if os.name == "nt" else "python")).touch()
        output = (
            "12 passed in 0.1s\n"
            if "pytest" in args
            else "Installed SDK sync/async mock smoke passed\n"
        )
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected real subprocess")
    )
    return dist, project, calls


def test_install_workflow_is_isolated_offline_and_binds_artifact_hashes(
    isolated_commands, monkeypatch
):
    dist, project, calls = isolated_commands
    monkeypatch.setenv("ANTHROPIC_API_KEY", "PRIVATE")
    monkeypatch.setenv("EZVIZ_APP_SECRET", "PRIVATE")
    monkeypatch.setenv("PYTHONPATH", "PRIVATE")
    monkeypatch.setenv("PYTHONHOME", "PRIVATE_HOME")
    monkeypatch.setenv("PIP_TARGET", "PRIVATE_TARGET")
    result = module().verify_installations(dist, project, installer="uv", offline=True)
    assert (
        result["validation"] == "clean_install_and_offline_smoke"
        and result["real_api_used"] is False
    )
    assert {r["kind"] for r in result["results"]} == {"wheel", "sdist"}
    assert all(len(r["artifact_sha256"]) == 64 for r in result["results"])
    assert any("pytest" in args for args, _ in calls)
    installs = [args for args, _ in calls if "install" in args]
    assert len(installs) == 2 and all("--offline" in args for args in installs)
    for args, kw in calls:
        assert not kw.get("shell", False) and kw.get("timeout") == 300
        assert not any(
            k in kw["env"]
            for k in (
                "ANTHROPIC_API_KEY",
                "EZVIZ_APP_SECRET",
                "PYTHONPATH",
                "PYTHONHOME",
                "PIP_TARGET",
            )
        )
    assert os.environ["ANTHROPIC_API_KEY"] == "PRIVATE"


@pytest.mark.parametrize("installer,offline", [("pip", True), ("unknown", False)])
def test_bad_installer_mode_never_runs_commands(isolated_commands, installer, offline):
    dist, project, calls = isolated_commands
    with pytest.raises(ValueError):
        module().verify_installations(dist, project, installer=installer, offline=offline)
    assert not calls


def test_command_failure_stops_without_echoing_subprocess_logs(isolated_commands, monkeypatch):
    dist, project, calls = isolated_commands

    def fail(args, **kwargs):
        calls.append((args, kwargs))
        raise subprocess.CalledProcessError(
            1, args, output="PRIVATE_OUTPUT", stderr="PRIVATE_SECRET"
        )

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises((ValueError, RuntimeError)) as caught:
        module().verify_installations(dist, project)
    assert "PRIVATE" not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("alias", ["same", "symlink"])
def test_cli_rejects_output_alias_before_installing(isolated_commands, alias, monkeypatch):
    dist, project, calls = isolated_commands
    before = project.read_bytes()
    output = project
    if alias == "symlink":
        output = project.with_name("alias.json")
        output.symlink_to(project)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_installations",
            "--dist",
            str(dist),
            "--pyproject",
            str(project),
            "--output",
            str(output),
        ],
    )
    try:
        code = module().main()
    except SystemExit as exc:
        code = exc.code
    assert code == 1 and not calls and project.read_bytes() == before


def test_invalid_archive_is_rejected_before_installing(isolated_commands):
    dist, project, calls = isolated_commands
    next(dist.glob("*.whl")).write_bytes(b"bad archive")
    with pytest.raises(ValueError):
        module().verify_installations(dist, project)
    assert not calls


def test_source_tests_can_be_explicitly_skipped_without_claiming_them(isolated_commands):
    dist, project, calls = isolated_commands
    result = module().verify_installations(dist, project, source_tests=False)
    assert not any("pytest" in args for args, _ in calls)
    assert not any("source_archive_tests" in r for r in result["results"])


def test_changed_artifact_is_rejected_before_commands(isolated_commands, monkeypatch):
    dist, project, calls = isolated_commands
    mod = module()
    original = mod.check_artifacts.check_artifacts

    def changed(*args, **kwargs):
        report = original(*args, **kwargs)
        next(dist.glob("*.whl")).write_bytes(b"changed after check")
        return report

    monkeypatch.setattr(mod.check_artifacts, "check_artifacts", changed)
    with pytest.raises(ValueError):
        mod.verify_installations(dist, project)
    assert not calls


def test_smoke_output_must_confirm_execution(isolated_commands, monkeypatch):
    dist, project, calls = isolated_commands
    previous = subprocess.run

    def empty(args, **kwargs):
        result = previous(args, **kwargs)
        if any(str(a).endswith("smoke_installed.py") for a in args):
            result.stdout = ""
        return result

    monkeypatch.setattr(subprocess, "run", empty)
    with pytest.raises(ValueError):
        module().verify_installations(dist, project)


def test_test_summary_cannot_echo_unexpected_subprocess_content(isolated_commands, monkeypatch):
    dist, project, calls = isolated_commands
    previous = subprocess.run

    def unsafe(args, **kwargs):
        result = previous(args, **kwargs)
        if "pytest" in args:
            result.stdout = "PRIVATE_VALUE 12 passed in 0.1s\n"
        return result

    monkeypatch.setattr(subprocess, "run", unsafe)
    with pytest.raises(ValueError) as caught:
        module().verify_installations(dist, project)
    assert "PRIVATE" not in str(caught.value)
