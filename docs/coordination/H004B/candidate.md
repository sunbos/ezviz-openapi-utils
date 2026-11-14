```python
"""Static AST audit of SDK sources against declared bindings (stdlib only).

Parses ``src/ezviz_unified`` modules without importing or executing them and
checks that every declared ``Class.method`` symbol resolves, that declared
``argument_constants`` keys name real parameters, that ``public_entry``
attribute paths resolve from both ``Client`` and ``AsyncClient`` to one of
the binding's declared implementations, and that each migrated legacy
``client.*`` target resolves on both client flavors to a declared symbol.

The evidence is purely static: it proves names and paths exist in the AST,
not runtime behavior, argument values, or live API correctness.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
EVIDENCE = "static_ast_symbols_only"
SDK_ROOT_REL = PurePosixPath("src/ezviz_unified")
CLIENT_MODULE = "src/ezviz_unified/client.py"
CLIENT_CLASSES = ("Client", "AsyncClient")
MIGRATED_STATUS = "mapped_with_breaking_changes"
_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


class CodeAuditError(ValueError):
    """Raised for any audit input, path, or resolution failure."""


def _err(where: str, reason: str) -> CodeAuditError:
    return CodeAuditError(f"{where}: {reason}")


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _resolved_within(base: Path, rel: PurePosixPath, where: str) -> Path:
    candidate = base / Path(*rel.parts)
    try:
        resolved = candidate.resolve(strict=True)
        base_resolved = base.resolve()
    except OSError:
        raise _err(where, "path cannot be resolved")
    if not resolved.is_file() or not _is_within(base_resolved, resolved):
        raise _err(where, "path escapes allowed root or is missing")
    return resolved


def _sdk_module_path(value: object, where: str) -> str:
    """Validate a binding module path stays under src/ezviz_unified/."""
    if not isinstance(value, str) or not value.strip():
        raise _err(where, "module must be a non-empty string")
    rel = PurePosixPath(value)
    parts = rel.parts
    ok = (
        rel.is_relative_to(SDK_ROOT_REL)
        and not rel.is_absolute()
        and "\\" not in value
        and len(parts) > len(SDK_ROOT_REL.parts)
        and all(part not in ("", ".", "..") for part in parts)
        and parts[-1].endswith(".py")
    )
    if not ok:
        raise _err(where, "module must be a canonical .py path under src/ezviz_unified/")
    return value


def _evidence_path(value: object, where: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise _err(where, "live_evidence must be a non-empty string")
    rel = PurePosixPath(value)
    if (
        rel.is_absolute()
        or "\\" in value
        or not rel.parts
        or any(part in ("", ".", "..") for part in rel.parts)
    ):
        raise _err(where, "live_evidence must be a canonical relative POSIX path")
    return rel


def _public_path(value: object, where: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise _err(where, "attribute path must be a non-empty string")
    parts = value.split(".")
    if not all(part.isidentifier() and not part.startswith("_") for part in parts):
        raise _err(where, "attribute path must be public identifiers")
    return parts


class _ModuleInfo:
    """Static view of one parsed SDK module: top-level classes and local imports."""

    def __init__(self, rel: str, tree: ast.Module) -> None:
        self.rel = rel
        self.classes: dict[str, ast.ClassDef] = {}
        self.imports: dict[str, tuple[str, str]] = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
            elif isinstance(node, ast.ImportFrom):
                if node.level != 1 or not isinstance(node.module, str) or not node.module:
                    continue
                if not node.module.isidentifier():
                    continue
                for alias in node.names:
                    if alias.name == "*" or not alias.name.isidentifier():
                        continue
                    local = alias.asname if alias.asname is not None else alias.name
                    if not local.isidentifier():
                        continue
                    self.imports[local] = (f"{SDK_ROOT_REL}/{node.module}.py", alias.name)

    def class_symbol(self, name: str) -> tuple[str, str] | None:
        if name in self.classes:
            return (self.rel, name)
        return self.imports.get(name)


class _Model:
    """Parsed SDK modules plus method resolution with inheritance and cycle guards."""

    def __init__(self, repo_root: Path) -> None:
        if not isinstance(repo_root, Path):
            raise CodeAuditError("repo_root: must be a Path")
        try:
            root_resolved = repo_root.resolve(strict=True)
        except OSError:
            raise CodeAuditError("repo_root: cannot be resolved")
        if not root_resolved.is_dir():
            raise CodeAuditError("repo_root: not a directory")
        self._root = root_resolved
        self.sdk_root = _resolved_within(root_resolved, SDK_ROOT_REL, "sdk_root")
        self.modules: dict[str, _ModuleInfo] = {}
        self._method_cache: dict[tuple[str, str, str], _FUNC_NODES | None] = {}
        self.hashes: dict[str, str] = {}

    def module(self, rel: str) -> _ModuleInfo:
        info = self.modules.get(rel)
        if info is None:
            resolved = _resolved_within(self.sdk_root, PurePosixPath(rel), "module")
            try:
                raw = resolved.read_bytes()
            except OSError:
                raise _err("module", "cannot read source file")
            try:
                text = raw.decode("utf-8")
                tree = ast.parse(text, filename="<module>")
            except (UnicodeDecodeError, SyntaxError, ValueError):
                raise _err("module", "invalid encoding or syntax")
            info = _ModuleInfo(rel, tree)
            self.modules[rel] = info
            self.hashes[rel] = hashlib.sha256(raw).hexdigest()
        return info

    def resolve_class(self, rel: str, name: str) -> tuple[str, ast.ClassDef]:
        info = self.module(rel)
        target = info.class_symbol(name)
        if target is None:
            raise _err("symbol", "class cannot be resolved in module")
        module_rel, class_name = target
        class_def = self.module(module_rel).classes.get(class_name)
        if class_def is None:
            raise _err("symbol", "imported class cannot be resolved")
        return (module_rel, class_def)

    def find_method(self, rel: str, class_name: str, method: str) -> _FUNC_NODES | None:
        key = (rel, class_name, method)
        if key in self._method_cache:
            return self._method_cache[key]
        module_rel, class_def = self.resolve_class(rel, class_name)
        result: _FUNC_NODES | None = None
        for node in class_def.body:
            if isinstance(node, _FUNC_NODES) and node.name == method:
                result = node
                break
        if result is None:
            for base in class_def.bases:
                if not isinstance(base, ast.Name):
                    continue  # external or non-trivial bases are not resolved
                base_symbol = self.module(module_rel).class_symbol(base.id)
                if base_symbol is None:
                    continue
                found = self._find_in_class(base_symbol[0], base_symbol[1], method, frozenset(key))
                if found is not None:
                    result = found
                    break
        self._method_cache[key] = result
        return result

    def _find_in_class(
        self, rel: str, class_name: str, method: str, visiting: frozenset[tuple[str, str, str]]
    ) -> _FUNC_NODES | None:
        state = (rel, class_name, method)
        if state in visiting:
            raise _err("symbol", "cyclic base class resolution")
        module_rel, class_def = self.resolve_class(rel, class_name)
        for node in class_def.body:
            if isinstance(node, _FUNC_NODES) and node.name == method:
                return node
        for base in class_def.bases:
            if not isinstance(base, ast.Name):
                continue
            base_symbol = self.module(module_rel).class_symbol(base.id)
            if base_symbol is None:
                continue
            found = self._find_in_class(base_symbol[0], base_symbol[1], method, visiting | {state})
            if found is not None:
                return found
        return None

    def init_attributes(self, rel: str, class_name: str) -> dict[str, tuple[str, str]]:
        """Map ``self.attr = LocalClass(...)`` assignments made in ``__init__``."""
        _, class_def = self.resolve_class(rel, class_name)
        attrs: dict[str, tuple[str, str]] = {}
        for node in class_def.body:
            if not (isinstance(node, _FUNC_NODES) and node.name == "__init__"):
                continue
            for stmt in ast.walk(node):
                target = None
                call = None
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                    target, call = stmt.targets[0], stmt.value
                elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                    target, call = stmt.target, stmt.value
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr.isidentifier()
                    and isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                ):
                    continue
                symbol = self.module(rel).class_symbol(call.func.id)
                if symbol is not None:
                    attrs[target.attr] = symbol
        return attrs

    def resolve_path(self, path: list[str], client: str) -> _FUNC_NODES:
        """Resolve ``client.a.b.method`` via __init__ attribute wiring only."""
        cursor = (CLIENT_MODULE, client)
        for segment in path[:-1]:
            attrs = self.init_attributes(*cursor)
            target = attrs.get(segment)
            if target is None:
                raise _err("public path", "attribute segment cannot be resolved statically")
            cursor = target
        method = self.find_method(cursor[0], cursor[1], path[-1])
        if method is None:
            raise _err("public path", "final method cannot be resolved")
        return method


def _method_params(node: _FUNC_NODES) -> set[str]:
    args = node.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    return {name for name in names if name != "self"}


def _constants(value: object, where: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _err(where, "argument_constants must be an object")
    allowed = (str, bool, int)  # bool before int: bool is an int subclass
    for key, item in value.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise _err(where, "argument_constants keys must be identifiers")
        if item is not None and not isinstance(item, allowed):
            raise _err(where, "argument_constants values must be str, bool, int or null")
    return dict(value)


def _symbols(value: object, where: str) -> list[tuple[str, str]]:
    if not isinstance(value, list) or not value:
        raise _err(where, "symbols must be a non-empty list")
    parsed = []
    for item in value:
        parts = item.split(".") if isinstance(item, str) else ()
        if len(parts) != 2 or not all(part.isidentifier() for part in parts):
            raise _err(where, "symbols items must be 'Class.method'")
        parsed.append((parts[0], parts[1]))
    return parsed


def _check_binding(model: _Model, raw: object, index: int) -> int:
    where = f"bindings[{index}]"
    if not isinstance(raw, dict):
        raise _err(where, "expected an object")
    rel = _sdk_module_path(raw.get("module"), where)
    symbols = _symbols(raw.get("symbols"), where)
    resolved_methods: list[_FUNC_NODES] = []
    for class_name, method_name in symbols:
        try:
            node = model.find_method(rel, class_name, method_name)
        except CodeAuditError:
            raise _err(where, "symbol cannot be resolved")
        if node is None:
            raise _err(where, "symbol cannot be resolved")
        resolved_methods.append(node)
    for key in _constants(raw.get("argument_constants"), where):
        if not any(key in _method_params(node) for node in resolved_methods):
            raise _err(where, "argument constant names no parameter on declared symbols")
    entry = raw.get("public_entry")
    if entry is not None:
        path = _public_path(entry, where)
        declared = frozenset(id(node) for node in resolved_methods)
        for client in CLIENT_CLASSES:
            try:
                node = model.resolve_path(path, client)
            except CodeAuditError:
                raise _err(where, "public entry cannot be resolved")
            if id(node) not in declared:
                raise _err(where, "public entry does not reach a declared symbol")
    evidence = raw.get("live_evidence")
    if evidence is not None:
        _resolved_within(model._root, _evidence_path(evidence, where), where)
    return len(symbols)


def _check_migration(model: _Model, raw: object, index: int) -> int:
    where = f"migration.methods[{index}]"
    if not isinstance(raw, dict):
        raise _err(where, "expected an object")
    if raw.get("status") != MIGRATED_STATUS:
        return 0
    target = raw.get("target")
    if not isinstance(target, str) or not target.startswith("client."):
        raise _err(where, "migrated target must start with 'client.'")
    path = _public_path(target[len("client."):], where)
    if len(path) < 2:
        raise _err(where, "migrated target must name an attribute path and method")
    for client in CLIENT_CLASSES:
        try:
            model.resolve_path(path, client)
        except CodeAuditError:
            raise _err(where, "migrated target cannot be resolved")
    return 1


def _implementations(model: _Model, bindings: object) -> set[int]:
    ids: set[int] = set()
    rows = bindings.get("bindings") if isinstance(bindings, dict) else None
    if not isinstance(rows, list):
        raise _err("bindings", "bindings must be a list")
    for i, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise _err(f"bindings[{i}]", "expected an object")
        rel = _sdk_module_path(raw.get("module"), f"bindings[{i}]")
        for class_name, method_name in _symbols(raw.get("symbols"), f"bindings[{i}]"):
            node = model.find_method(rel, class_name, method_name)
            if node is not None:
                ids.add(id(node))
    return ids


def audit_code(repo_root: Path, bindings: dict, migration: dict) -> dict:
    """Statically verify declared symbols and client paths against the SDK AST.

    Reads only ``.py`` files under ``repo_root/src/ezviz_unified`` plus any
    declared ``live_evidence`` paths (existence only). Never imports or
    executes SDK code. Raises :class:`CodeAuditError` on any failure.
    """
    model = _Model(repo_root)
    bindings_obj = bindings if isinstance(bindings, dict) else None
    migration_obj = migration if isinstance(migration, dict) else None
    if bindings_obj is None or not isinstance(bindings_obj.get("bindings"), list):
        raise _err("bindings", "expected an object with a bindings list")
    if migration_obj is None or not isinstance(migration_obj.get("methods"), list):
        raise _err("migration", "expected an object with a methods list")
    rows = bindings_obj["bindings"]
    methods = migration_obj["methods"]
    symbols_checked = 0
    for i, raw in enumerate(rows):
        symbols_checked += _check_binding(model, raw, i)
    declared_impls = _implementations(model, bindings_obj)
    migration_checked = 0
    for i, raw in enumerate(methods):
        where = f"migration.methods[{i}]"
        if not isinstance(raw, dict):
            raise _err(where, "expected an object")
        if raw.get("status") != MIGRATED_STATUS:
            continue
        migration_checked += _check_migration(model, raw, i)
        target = raw.get("target")
        path = _public_path(target[len("client."):], where)  # type: ignore[union-attr]
        for client in CLIENT_CLASSES:
            node = model.resolve_path(path, client)
            if id(node) not in declared_impls:
                raise _err(where, "migrated target reaches no declared binding symbol")
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": EVIDENCE,
        "summary": {
            "bindings_checked": len(rows),
            "symbols_checked": symbols_checked,
            "migration_targets_checked": migration_checked,
        },
        "source_files_sha256": {rel: model.hashes[rel] for rel in sorted(model.hashes)},
    }
```
