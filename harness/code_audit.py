"""Static AST audit of SDK sources against declared bindings (stdlib only).

Parses ``src/ezviz_unified`` modules without importing or executing them and
checks that every declared ``Class.method`` symbol resolves through the C3
method-resolution order, that every declared ``argument_constants`` key names
a real parameter on every declared symbol, that ``public_entry`` attribute
paths resolve from both ``Client`` and ``AsyncClient`` to one of the binding's
declared implementation nodes, and that each migrated legacy ``client.*``
target resolves on both client flavors to a declared implementation node.

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
MethodNode = ast.FunctionDef | ast.AsyncFunctionDef
_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_NESTED = (ast.stmt, ast.excepthandler, getattr(ast, "match_case", ast.stmt))


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


def _resolve_under(base: Path, rel: PurePosixPath, where: str, *, kind: str) -> Path:
    """Resolve ``rel`` under a resolved ``base``; kind is ``dir`` or ``file``.

    The failing filesystem exception is swallowed and a fixed error is raised
    after the ``except`` block so no source path or OS detail is chained.
    """
    try:
        resolved = base.joinpath(*rel.parts).resolve(strict=True)
    except (OSError, RuntimeError):
        resolved = None
    ok = resolved is not None and _is_within(base, resolved)
    if ok and kind == "dir" and not resolved.is_dir():
        ok = False
    if ok and kind == "file" and not resolved.is_file():
        ok = False
    if not ok:
        raise _err(where, "path escapes allowed root or is missing")
    return resolved


def _sdk_module_path(value: object, where: str) -> str:
    """Validate a binding module path stays under src/ezviz_unified/.

    ``PurePosixPath`` silently collapses ``//`` and ``./`` segments, so the
    original string must round-trip through ``as_posix`` unchanged.
    """
    if not isinstance(value, str) or not value.strip():
        raise _err(where, "module must be a non-empty string")
    rel = PurePosixPath(value)
    parts = rel.parts
    ok = (
        not rel.is_absolute()
        and value == rel.as_posix()
        and "\\" not in value
        and rel.is_relative_to(SDK_ROOT_REL)
        and len(parts) > len(SDK_ROOT_REL.parts)
        and all(part not in ("", ".", "..") for part in parts)
        and parts[-1].endswith(".py")
        and parts[-1][:-3].isidentifier()
        and all(part.isidentifier() for part in parts[:-1])
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
        or value != rel.as_posix()
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
    if len(parts) < 2 or not all(
        part.isidentifier() and not part.startswith("_") for part in parts
    ):
        raise _err(where, "attribute path must be public identifiers")
    return parts


def _method_params(node: MethodNode) -> set[str]:
    args = node.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    return {name for name in names if name not in ("self", "cls")}


def _c3_merge(seqs: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """C3 linearization merge; fails on an inconsistent base order."""
    result: list[tuple[str, str]] = []
    pending = [list(seq) for seq in seqs]
    while True:
        pending = [seq for seq in pending if seq]
        if not pending:
            return result
        head = None
        for seq in pending:
            candidate = seq[0]
            if not any(candidate in other[1:] for other in pending):
                head = candidate
                break
        if head is None:
            raise _err("symbol", "inconsistent base class order")
        result.append(head)
        for seq in pending:
            if seq and seq[0] == head:
                del seq[0]


def _init_statements(func: MethodNode) -> list[tuple[ast.AST, bool]]:
    """Mark control-flow-dependent statements; never enter nested scopes."""
    out: list[tuple[ast.AST, bool]] = []
    stack = [(stmt, False) for stmt in func.body]
    while stack:
        stmt, conditional = stack.pop()
        if isinstance(stmt, _SCOPE_NODES):
            continue  # nested def/class bodies never run during __init__
        out.append((stmt, conditional))
        for _field, value in ast.iter_fields(stmt):
            if isinstance(value, list):
                stack.extend((item, True) for item in value if isinstance(item, _NESTED))
    return out


def _attribute_targets(target: ast.expr) -> list[ast.Attribute]:
    if isinstance(target, ast.Attribute):
        return [target]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [item for element in target.elts for item in _attribute_targets(element)]
    return []


def _own_method(class_def: ast.ClassDef, method: str) -> MethodNode | None:
    """Respect later definitions and refuse explicit non-method replacements."""
    for node in reversed(class_def.body):
        if isinstance(node, _FUNC_NODES) and node.name == method:
            return node
        if isinstance(node, ast.ClassDef) and node.name == method:
            raise _err("symbol", "method is explicitly replaced by a non-method")
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        if any(isinstance(target, ast.Name) and target.id == method for target in targets):
            raise _err("symbol", "method is explicitly replaced by a non-method")
    return None


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
                module_parts = node.module.split(".")
                if not all(part.isidentifier() for part in module_parts):
                    continue
                for alias in node.names:
                    if alias.name == "*" or not alias.name.isidentifier():
                        continue
                    local = alias.asname if alias.asname is not None else alias.name
                    if not local.isidentifier():
                        continue
                    imported = PurePosixPath(rel).parent.joinpath(*module_parts).with_suffix(".py")
                    self.imports[local] = (imported.as_posix(), alias.name)

    def class_symbol(self, name: str) -> tuple[str, str] | None:
        if name in self.classes:
            return (self.rel, name)
        return self.imports.get(name)


class _Model:
    """Parsed SDK modules plus C3 MRO resolution with bounded failure."""

    def __init__(self, repo_root: Path) -> None:
        if not isinstance(repo_root, Path):
            raise CodeAuditError("repo_root: must be a Path")
        try:
            root = repo_root.resolve(strict=True)
        except (OSError, RuntimeError):
            root = None
        if root is None or not root.is_dir():
            raise CodeAuditError("repo_root: cannot be resolved to a directory")
        self.root = root
        self.sdk_root = _resolve_under(root, SDK_ROOT_REL, "sdk_root", kind="dir")
        self.modules: dict[str, _ModuleInfo] = {}
        self.hashes: dict[str, str] = {}
        self._method_cache: dict[tuple[str, str, str], MethodNode | None] = {}
        self._mro_cache: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
        self._mro_building: set[tuple[str, str]] = set()

    def module(self, rel: str) -> _ModuleInfo:
        rel = _sdk_module_path(rel, "module")
        info = self.modules.get(rel)
        if info is not None:
            return info
        resolved = _resolve_under(self.root, PurePosixPath(rel), "module", kind="file")
        if not _is_within(self.sdk_root, resolved):
            raise _err("module", "path escapes allowed root or is missing")
        try:
            raw = resolved.read_bytes()
        except (OSError, RuntimeError):
            raw = None
        if raw is None:
            raise _err("module", "cannot read source file")
        try:
            tree = ast.parse(raw.decode("utf-8"), filename="<module>")
        except (SyntaxError, UnicodeDecodeError, ValueError, RecursionError, MemoryError):
            tree = None
        if tree is None:
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

    def class_mro(self, rel: str, name: str) -> tuple[tuple[str, str], ...]:
        """C3 linearization over local classes; external bases are skipped."""
        key = (rel, name)
        cached = self._mro_cache.get(key)
        if cached is not None:
            return cached
        if key in self._mro_building:
            raise _err("symbol", "cyclic base class resolution")
        self._mro_building.add(key)
        try:
            module_rel, class_def = self.resolve_class(rel, name)
            ident = (module_rel, class_def.name)
            info = self.module(module_rel)  # aliases resolve in the defining module
            seqs: list[list[tuple[str, str]]] = []
            local: list[tuple[str, str]] = []
            for base in class_def.bases:
                if not isinstance(base, ast.Name):
                    continue  # non-trivial or external bases hold no local methods
                symbol = info.class_symbol(base.id)
                if symbol is None:
                    continue
                base_mro = self.class_mro(symbol[0], symbol[1])
                seqs.append(list(base_mro))
                local.append(base_mro[0])
            merged = _c3_merge([*seqs, local])
            mro = (ident, *merged)
        finally:
            self._mro_building.discard(key)
        self._mro_cache[key] = mro
        return mro

    def find_method(self, rel: str, class_name: str, method: str) -> MethodNode | None:
        mro = self.class_mro(rel, class_name)
        key = (mro[0][0], mro[0][1], method)
        if key in self._method_cache:
            return self._method_cache[key]
        result: MethodNode | None = None
        for module_rel, class_id in mro:
            class_def = self.module(module_rel).classes[class_id]
            result = _own_method(class_def, method)
            if result is not None:
                break
        self._method_cache[key] = result
        return result

    def init_attributes(self, rel: str, class_name: str) -> dict[str, tuple[str, str] | None]:
        """Map ``self.attr = LocalClass(...)`` in the effective ``__init__``.

        ``None`` marks an attribute that cannot be trusted statically: assigned
        more than once, assigned a non-constructor value, or built from an
        unresolvable call target.
        """
        attrs: dict[str, tuple[str, str] | None] = {}
        init_node: MethodNode | None = None
        init_module: str | None = None
        for module_rel, class_id in self.class_mro(rel, class_name):
            class_def = self.module(module_rel).classes[class_id]
            node = _own_method(class_def, "__init__")
            if node is not None:
                init_node, init_module = node, module_rel
            if init_node is not None:
                break
        if init_node is None or init_module is None:
            return attrs
        info = self.module(init_module)
        found: dict[str, list[tuple[str, str] | None]] = {}
        for stmt, conditional in _init_statements(init_node):
            targets: list[ast.expr] = []
            call: ast.expr | None = None
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
                if len(targets) == 1:
                    call = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets, call = [stmt.target], stmt.value
            elif isinstance(stmt, ast.AugAssign):
                targets = [stmt.target]
            elif isinstance(stmt, ast.Delete):
                targets = stmt.targets
            for raw_target in targets:
                for target in _attribute_targets(raw_target):
                    if not (
                        isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        and target.attr.isidentifier()
                    ):
                        continue
                    candidate = None
                    if (
                        not conditional
                        and isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                    ):
                        candidate = info.class_symbol(call.func.id)
                    found.setdefault(target.attr, []).append(candidate)
        for attr, candidates in found.items():
            attrs[attr] = candidates[0] if len(candidates) == 1 else None
        return attrs

    def resolve_path(self, path: list[str], client: str) -> MethodNode:
        """Resolve ``client.a.b.method`` via ``__init__`` attribute wiring only."""
        cursor = (CLIENT_MODULE, client)
        for segment in path[:-1]:
            target = self.init_attributes(*cursor).get(segment)
            if target is None:
                raise _err("public path", "attribute segment cannot be resolved statically")
            cursor = target
        method = self.find_method(cursor[0], cursor[1], path[-1])
        if method is None:
            raise _err("public path", "final method cannot be resolved")
        return method


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


def _check_binding(model: _Model, raw: object, index: int, declared: list[MethodNode]) -> int:
    where = f"bindings[{index}]"
    if not isinstance(raw, dict):
        raise _err(where, "expected an object")
    rel = _sdk_module_path(raw.get("module"), where)
    symbols = _symbols(raw.get("symbols"), where)
    nodes: list[MethodNode] = []
    for class_name, method_name in symbols:
        try:
            node = model.find_method(rel, class_name, method_name)
        except CodeAuditError:
            node = None
        if node is None:
            raise _err(where, "symbol cannot be resolved")
        nodes.append(node)
    for key in _constants(raw.get("argument_constants"), where):
        if not all(key in _method_params(node) for node in nodes):
            raise _err(where, "argument constant names no parameter on declared symbols")
    entry = raw.get("public_entry")
    if entry is not None:
        path = _public_path(entry, where)
        for client in CLIENT_CLASSES:
            try:
                node = model.resolve_path(path, client)
            except CodeAuditError:
                node = None
            if node is None or not any(node is impl for impl in nodes):
                raise _err(where, "public entry does not reach a declared symbol")
    evidence = raw.get("live_evidence")
    if evidence is not None:
        _resolve_under(model.root, _evidence_path(evidence, where), where, kind="file")
    declared.extend(nodes)
    return len(symbols)


def _check_migration(model: _Model, raw: object, index: int, declared: list[MethodNode]) -> int:
    where = f"migration.methods[{index}]"
    if not isinstance(raw, dict):
        raise _err(where, "expected an object")
    if raw.get("status") != MIGRATED_STATUS:
        return 0
    target = raw.get("target")
    if not isinstance(target, str) or not target.startswith("client."):
        raise _err(where, "migrated target must start with 'client.'")
    path = _public_path(target[len("client.") :], where)
    for client in CLIENT_CLASSES:
        try:
            node = model.resolve_path(path, client)
        except CodeAuditError:
            node = None
        if node is None or not any(node is impl for impl in declared):
            raise _err(where, "migrated target reaches no declared binding symbol")
    return 1


def audit_code(repo_root: Path, bindings: dict, migration: dict) -> dict:
    """Statically verify declared symbols and client paths against the SDK AST.

    Reads only ``.py`` files under ``repo_root/src/ezviz_unified`` plus any
    declared ``live_evidence`` paths (existence only). Never imports or
    executes SDK code. Raises :class:`CodeAuditError` on any failure.
    """
    model = _Model(repo_root)
    if not isinstance(bindings, dict) or not isinstance(bindings.get("bindings"), list):
        raise _err("bindings", "expected an object with a bindings list")
    if not isinstance(migration, dict) or not isinstance(migration.get("methods"), list):
        raise _err("migration", "expected an object with a methods list")
    rows = bindings["bindings"]
    declared: list[MethodNode] = []
    symbols_checked = 0
    for i, raw in enumerate(rows):
        symbols_checked += _check_binding(model, raw, i, declared)
    migration_checked = 0
    for i, raw in enumerate(migration["methods"]):
        migration_checked += _check_migration(model, raw, i, declared)
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
