"""Release artifact consistency checker.

Performs metadata-and-contents validation of the built wheel and sdist
against pyproject.toml. This is not install verification and does not
prove the distributions pass any tests.
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import re
import stat
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

_TEST_FILE_RE = re.compile(r"(conftest\.py|test_offline_policy\.py|test_sdk[^/]*\.py)")
_ENV_RE = re.compile(r"\.env(\..*)?")
_WHEEL_FORBIDDEN_TOPS = {"tests", "data", "docs", "harness", "tools", ".claude"}
_SDIST_FORBIDDEN_TOPS = _WHEEL_FORBIDDEN_TOPS - {"tests"}


def _normalize_name(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _member_parts(name: str) -> tuple[str, ...]:
    """Validate an archive member path and return its components."""
    if name.startswith("/") or "\\" in name or re.match(r"[A-Za-z]:", name):
        raise ValueError("unsafe archive member path")
    raw_parts = name.rstrip("/").split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise ValueError("unsafe archive member path")
    parts = PurePosixPath(name).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("unsafe archive member path")
    return parts


def _load_expected(pyproject: Path) -> tuple[str, str, str, str]:
    if not pyproject.is_file() or pyproject.is_symlink():
        raise ValueError("invalid pyproject path")
    try:
        with pyproject.open("rb") as fh:
            project = tomllib.load(fh).get("project")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("unreadable pyproject") from exc
    if not isinstance(project, dict):
        raise ValueError("pyproject missing [project] table")
    license_field = project.get("license")
    if isinstance(license_field, dict):
        license_field = license_field.get("text")
    fields = (
        project.get("name"),
        project.get("version"),
        project.get("requires-python"),
        license_field,
    )
    if not all(isinstance(value, str) and value.strip() for value in fields):
        raise ValueError("pyproject missing required metadata fields")
    values = [str(value).strip() for value in fields]
    return values[0], values[1], values[2], values[3]


def _check_metadata(raw: bytes, expected: tuple[str, str, str, str]) -> None:
    name, version, requires_python, license_expr = expected
    message = email.parser.BytesParser().parsebytes(raw)
    for field in (
        "Name",
        "Version",
        "Requires-Python",
        "License-Expression",
        "Description-Content-Type",
    ):
        if len(message.get_all(field, [])) != 1:
            raise ValueError("missing or duplicate artifact metadata field")
    if _normalize_name(message.get("Name", "")) != _normalize_name(name):
        raise ValueError("artifact metadata Name mismatch")
    if (message.get("Version") or "").strip() != version:
        raise ValueError("artifact metadata Version mismatch")
    if (message.get("Requires-Python") or "").strip() != requires_python:
        raise ValueError("artifact metadata Requires-Python mismatch")
    if (message.get("License-Expression") or "").strip() != license_expr:
        raise ValueError("artifact metadata License-Expression mismatch")
    if (message.get("Description-Content-Type") or "").strip() != "text/markdown":
        raise ValueError("artifact metadata Description-Content-Type mismatch")
    payload = message.get_payload()
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("artifact description body is empty")


def _check_wheel(path: Path, expected: tuple[str, str, str, str], package: str) -> int:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("unreadable wheel") from exc
    with archive:
        infos = archive.infolist()
        names: set[str] = set()
        metadata = ""
        for info in infos:
            if info.filename in names:
                raise ValueError("duplicate archive member name")
            names.add(info.filename)
            parts = _member_parts(info.filename)
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("unsafe wheel member type")
            if parts[0] in _WHEEL_FORBIDDEN_TOPS:
                raise ValueError("forbidden top-level entry in wheel")
            if any(_ENV_RE.fullmatch(part) for part in parts):
                raise ValueError("forbidden env file in wheel")
            if len(parts) == 2 and parts[0].endswith(".dist-info") and parts[1] == "METADATA":
                if metadata:
                    raise ValueError("multiple dist-info METADATA entries")
                metadata = info.filename
        if not metadata:
            raise ValueError("wheel missing dist-info METADATA")
        dist_info = metadata.split("/", 1)[0]
        _check_distribution_stem(dist_info.removesuffix(".dist-info"), expected)
        if f"{package}/py.typed" not in names:
            raise ValueError("wheel missing py.typed marker")
        if f"{dist_info}/licenses/LICENSE" not in names:
            raise ValueError("wheel missing bundled license")
        _check_metadata(archive.read(metadata), expected)
        return len(infos)


def _check_sdist(path: Path, expected: tuple[str, str, str, str], package: str) -> int:
    try:
        archive = tarfile.open(path, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("unreadable sdist") from exc
    with archive:
        members = archive.getmembers()
        names: set[str] = set()
        roots: set[str] = set()
        pkg_info = None
        has_license = has_py_typed = False
        for member in members:
            if not (member.isfile() or member.isdir()):
                raise ValueError("unsafe sdist member type")
            if member.name in names:
                raise ValueError("duplicate archive member name")
            names.add(member.name)
            parts = _member_parts(member.name)
            roots.add(parts[0])
            rel = parts[1:]
            if not rel:
                continue
            if rel[0] in _SDIST_FORBIDDEN_TOPS:
                raise ValueError("forbidden top-level entry in sdist")
            if any(_ENV_RE.fullmatch(part) for part in rel):
                raise ValueError("forbidden env file in sdist")
            if rel[0] == "tests":
                ok = member.isdir() and rel == ("tests",)
                ok = ok or (
                    member.isfile() and len(rel) == 2 and bool(_TEST_FILE_RE.fullmatch(rel[1]))
                )
                if not ok:
                    raise ValueError("unexpected content under tests/")
            if member.isfile() and rel == ("PKG-INFO",):
                if pkg_info is not None:
                    raise ValueError("multiple root PKG-INFO entries")
                pkg_info = member
            has_license = has_license or (member.isfile() and rel == ("LICENSE",))
            has_py_typed = has_py_typed or (member.isfile() and rel == ("src", package, "py.typed"))
        if len(roots) != 1:
            raise ValueError("sdist must contain a single root directory")
        if next(iter(roots)) != path.name.removesuffix(".tar.gz"):
            raise ValueError("sdist root does not match its filename")
        if pkg_info is None:
            raise ValueError("sdist missing root PKG-INFO")
        if not has_license:
            raise ValueError("sdist missing LICENSE")
        if not has_py_typed:
            raise ValueError("sdist missing py.typed marker")
        source = archive.extractfile(pkg_info)
        if source is None:
            raise ValueError("sdist PKG-INFO unreadable")
        with source:
            _check_metadata(source.read(), expected)
        return len(members)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValueError("artifact unreadable") from exc
    return digest.hexdigest()


def _check_distribution_stem(stem: str, expected: tuple[str, str, str, str]) -> None:
    pieces = stem.rsplit("-", 1)
    if (
        len(pieces) != 2
        or _normalize_name(pieces[0]) != _normalize_name(expected[0])
        or pieces[1] != expected[1]
    ):
        raise ValueError("artifact filename or metadata directory does not match project")


def check_artifacts(dist: Path, pyproject: Path) -> dict[str, object]:
    """Validate dist artifacts against pyproject; return a JSON-ready report."""
    dist = Path(dist)
    pyproject = Path(pyproject)
    expected = _load_expected(pyproject)
    package = _normalize_name(expected[0]).replace("-", "_")
    if not dist.is_dir() or dist.is_symlink():
        raise ValueError("invalid dist directory")
    try:
        entries = sorted(dist.iterdir())
    except OSError as exc:
        raise ValueError("unreadable dist directory") from exc
    dist_root = dist.resolve()
    found: dict[str, list[Path]] = {"wheel": [], "sdist": []}
    for entry in entries:
        kind = ""
        if entry.suffix == ".whl":
            kind = "wheel"
        elif entry.name.endswith(".tar.gz"):
            kind = "sdist"
        if not kind:
            continue
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("artifact must be a regular file")
        if not entry.resolve().is_relative_to(dist_root):
            raise ValueError("artifact path escapes dist")
        found[kind].append(entry)
    if len(found["wheel"]) != 1 or len(found["sdist"]) != 1:
        raise ValueError("expected exactly one wheel and one sdist")
    wheel, sdist = found["wheel"][0], found["sdist"][0]
    wheel_parts = wheel.stem.split("-")
    if len(wheel_parts) not in (5, 6) or not all(wheel_parts):
        raise ValueError("invalid wheel filename")
    _check_distribution_stem("-".join(wheel_parts[:2]), expected)
    _check_distribution_stem(sdist.name.removesuffix(".tar.gz"), expected)
    return {
        "name": _normalize_name(expected[0]),
        "version": expected[1],
        "artifacts": [
            {
                "filename": wheel.name,
                "sha256": _sha256(wheel),
                "member_count": _check_wheel(wheel, expected, package),
                "kind": "wheel",
            },
            {
                "filename": sdist.name,
                "sha256": _sha256(sdist),
                "member_count": _check_sdist(sdist, expected, package),
                "kind": "sdist",
            },
        ],
        "validation": "metadata_and_contents_only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate built release artifacts against pyproject metadata."
    )
    parser.add_argument("--dist", type=Path, default=Path("dist"), help="artifact directory")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args(argv)
    try:
        report = check_artifacts(args.dist, args.pyproject)
    except Exception:
        print("artifact check failed", file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
