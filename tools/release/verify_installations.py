"""Verify release artifacts through clean installs and mock-only smoke runs.

Creates an isolated virtual environment per artifact, installs the wheel and
sdist validated by ``check_artifacts``, and runs ``smoke_installed`` under
``python -I`` in each. This is dependency/import isolation, not a security
sandbox; no real API is contacted and no application configuration is read.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if __package__:  # python -m tools.release.verify_installations
    from . import check_artifacts
else:  # direct python tools/release/verify_installations.py
    import check_artifacts

_TIMEOUT = 300  # seconds; no child process may run longer
_DROP_PREFIXES = ("ANTHROPIC_", "OPENAI_", "EZVIZ_")
_DROP_NAMES = frozenset(
    {
        "CLAUDE_CODE_OAUTH_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
        "PIP_CONFIG_FILE",
        "UV_SYSTEM_PYTHON",
    }
)
_PASSED = re.compile(r"[1-9]\d* passed")
_SMOKE_SUCCESS = "Installed SDK sync/async mock smoke passed"
_SUMMARY = re.compile(
    r"\d+ (?:passed|skipped|xfailed|xpassed|warnings?|subtests passed)(?:, \d+ (?:passed|skipped|xfailed|xpassed|warnings?|subtests passed))* in \d+(?:\.\d+)?s(?: \([0-9:]+\))?"
)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _child_env() -> dict[str, str]:
    cleaned = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(_DROP_PREFIXES) and key not in _DROP_NAMES
    }
    cleaned["PIP_CONFIG_FILE"] = os.devnull
    return cleaned


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    # Child output is captured but never surfaced: it may be sensitive.
    failure = None
    done = None
    try:
        done = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        failure = "verification step timed out"
    except (OSError, subprocess.SubprocessError):
        failure = "verification step could not complete"
    if failure is not None:
        raise ValueError(failure)
    assert done is not None
    if done.returncode != 0:
        raise ValueError("verification step failed")
    return done


def _last_line(text: str, fallback: str = "") -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else fallback


def _install(
    python: Path,
    artifact: Path,
    kind: str,
    source_tests: bool,
    installer: str,
    offline: bool,
    cwd: Path,
    env: dict[str, str],
) -> None:
    target = f"{artifact}[dev]" if kind == "sdist" and source_tests else str(artifact)
    if installer == "uv":
        argv = ["uv", "--no-config", "pip", "install", "--python", str(python)]
        if offline:
            argv.append("--offline")  # cache-only mode; never retry online
        argv.append(target)
    else:
        argv = [str(python), "-m", "pip", "install", target]
    _run(argv, cwd, env)


def _source_tests(sdist: Path, python: Path, work: Path, env: dict[str, str]) -> str:
    unpack = work / "sdist-src"
    unpack.mkdir()
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            archive.extractall(unpack, filter="data")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("sdist extraction failed") from exc
    roots = list(unpack.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError("sdist did not extract a single source root")
    done = _run([str(python), "-I", "-m", "pytest", "-q"], roots[0], env)
    summary = _last_line(done.stdout)
    if not _SUMMARY.fullmatch(summary) or not _PASSED.search(summary):
        raise ValueError("sdist source tests did not pass")
    return summary


def verify_installations(
    dist: Path,
    pyproject: Path,
    *,
    installer: str = "pip",
    offline: bool = False,
    source_tests: bool = True,
) -> dict[str, object]:
    if installer not in ("pip", "uv"):
        raise ValueError("unsupported installer")
    if offline and installer != "uv":
        raise ValueError("offline installs are only supported with uv")
    checked = check_artifacts.check_artifacts(Path(dist), Path(pyproject))
    smoke = Path(__file__).resolve().parent / "smoke_installed.py"
    if not smoke.is_file():
        raise ValueError("smoke_installed.py not found")
    env = _child_env()
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="verify-install-") as tmp:
        work = Path(tmp)
        frozen = work / "artifacts"
        frozen.mkdir()
        project_copy = work / "pyproject.toml"
        shutil.copyfile(pyproject, project_copy)
        for meta in checked["artifacts"]:
            original = (Path(dist) / str(meta["filename"])).resolve()
            if not original.is_relative_to(Path(dist).resolve()):
                raise ValueError("artifact location changed")
            shutil.copyfile(original, frozen / str(meta["filename"]))
        snapshot = check_artifacts.check_artifacts(frozen, project_copy)
        if {a["filename"]: a["sha256"] for a in snapshot["artifacts"]} != {
            a["filename"]: a["sha256"] for a in checked["artifacts"]
        }:
            raise ValueError("artifacts changed during verification")
        for kind in ("wheel", "sdist"):
            meta = next(a for a in checked["artifacts"] if a["kind"] == kind)
            artifact = frozen / str(meta["filename"])
            venv_dir = work / f"venv-{kind}"
            _run([sys.executable, "-m", "venv", str(venv_dir)], work, env)
            python = _venv_python(venv_dir)
            if not python.is_file():
                raise ValueError("virtual environment python missing")
            run_dir = work / f"run-{kind}"
            run_dir.mkdir()
            _install(python, artifact, kind, source_tests, installer, offline, run_dir, env)
            done = _run([str(python), "-I", str(smoke)], run_dir, env)
            if _SMOKE_SUCCESS not in done.stdout.splitlines():
                raise ValueError("smoke completion marker missing")
            entry: dict[str, object] = {
                "kind": kind,
                "filename": meta["filename"],
                "artifact_sha256": meta["sha256"],
                "clean_install": True,
                "install_offline": bool(offline),
                "smoke": _SMOKE_SUCCESS,
            }
            if kind == "sdist" and source_tests:
                entry["source_archive_tests"] = _source_tests(artifact, python, run_dir, env)
            results.append(entry)
    return {
        "python": platform.python_version(),
        "name": checked["name"],
        "version": checked["version"],
        "installer": installer,
        "offline": bool(offline),
        "source_tests": bool(source_tests),
        "results": results,
        "validation": "clean_install_and_offline_smoke",
        "real_api_used": False,
    }


def _is_protected(output: Path, protected: set[Path]) -> bool:
    if output.resolve() in protected:
        return True
    return output.exists() and any(
        os.path.samefile(output, path) for path in protected if path.exists()
    )


def _write_report(payload: str, output: Path, protected: set[Path]) -> None:
    if _is_protected(output, protected):
        raise ValueError("refusing to overwrite a protected file")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=output.parent, prefix=".verify-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, output)  # atomic publish
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify release artifacts via clean installs and mock smoke runs."
    )
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--installer", choices=("pip", "uv"), default="pip")
    parser.add_argument("--offline", action="store_true", help="uv cache-only installs")
    parser.add_argument("--skip-source-tests", action="store_true")
    parser.add_argument("--output", type=Path, default=None, help="JSON report path")
    args = parser.parse_args(argv)
    try:  # KeyboardInterrupt is a BaseException and propagates unchanged.
        protected = {
            args.pyproject.resolve(),
            (Path(__file__).resolve().parent / "smoke_installed.py").resolve(),
        }
        protected.update(
            path.resolve() for pattern in ("*.whl", "*.tar.gz") for path in args.dist.glob(pattern)
        )
        if args.output is not None and _is_protected(args.output, protected):
            raise ValueError("refusing to overwrite a protected file")
        report = verify_installations(
            args.dist,
            args.pyproject,
            installer=args.installer,
            offline=args.offline,
            source_tests=not args.skip_source_tests,
        )
        if args.output is None:
            json.dump(report, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            _write_report(
                json.dumps(report, indent=2, sort_keys=True) + "\n", args.output, protected
            )
    except Exception:
        print("installation verification failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
