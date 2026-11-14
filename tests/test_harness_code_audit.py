import copy
import hashlib
import importlib
from pathlib import Path

import pytest


def module():
    assert Path("harness/code_audit.py").exists(), "Static code auditor missing"
    return importlib.import_module("harness.code_audit")


def fixture_tree(root):
    sdk = root / "src/ezviz_unified"
    sdk.mkdir(parents=True)
    marker = root / "CODE_MUST_NOT_EXECUTE"
    files = {
        "__init__.py": "raise RuntimeError('must not import package')\n",
        "base.py": f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nclass Base:\n    def get(self, *, setting=None): pass\nclass AsyncBase:\n    async def get(self, *, setting=None): pass\n",
        "feature.py": "from .base import Base as Parent, AsyncBase\nclass Feature(Parent): pass\nclass AsyncFeature(AsyncBase): pass\n",
        "nested.py": "from .feature import Feature, AsyncFeature\nclass Nested:\n    def __init__(self):\n        self.feature = Feature()\nclass AsyncNested:\n    def __init__(self):\n        self.feature: AsyncFeature = AsyncFeature()\n",
        "client.py": "from .feature import Feature, AsyncFeature\nfrom .nested import Nested, AsyncNested\nclass Client:\n    def __init__(self):\n        self.feature = Feature()\n        self.nested = Nested()\nclass AsyncClient:\n    def __init__(self):\n        self.feature = AsyncFeature()\n        self.nested = AsyncNested()\n",
    }
    for name, content in files.items():
        (sdk / name).write_text(content)
    bindings = {
        "bindings": [
            {
                "module": "src/ezviz_unified/feature.py",
                "symbols": ["Feature.get", "AsyncFeature.get"],
                "public_entry": "feature.get",
                "argument_constants": {"setting": "first"},
            }
        ]
    }
    migration = {
        "methods": [
            {"status": "mapped_with_breaking_changes", "target": "client.nested.feature.get"}
        ]
    }
    return sdk, bindings, migration, marker


def test_static_alias_inheritance_and_nested_target_without_execution(tmp_path):
    sdk, bindings, migration, marker = fixture_tree(tmp_path)
    original = copy.deepcopy((bindings, migration))
    report = module().audit_code(tmp_path, bindings, migration)
    assert not marker.exists()
    assert (bindings, migration) == original
    assert report["evidence"] == "static_ast_symbols_only"
    assert report["summary"] == {
        "bindings_checked": 1,
        "symbols_checked": 2,
        "migration_targets_checked": 1,
    }
    key = "src/ezviz_unified/base.py"
    assert (
        report["source_files_sha256"][key]
        == hashlib.sha256((sdk / "base.py").read_bytes()).hexdigest()
    )
    assert not ({"safe_to_publish", "approved"} & report.keys())


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/secret.py",
        "src/ezviz_unified/../secret.py",
        "src/ezviz_unified//feature.py",
        "src\\ezviz_unified\\feature.py",
        "src/ezviz_unified/feature.txt",
        "src/elsewhere/feature.py",
    ],
)
def test_binding_module_must_be_canonical_and_inside_sdk(tmp_path, path):
    _, bindings, migration, _ = fixture_tree(tmp_path)
    bindings["bindings"][0]["module"] = path
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


@pytest.mark.parametrize("kind", ["module", "sdk_root", "evidence"])
def test_symlink_escape_is_rejected(tmp_path, kind):
    repo = tmp_path / "repo"
    sdk, bindings, migration, _ = fixture_tree(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    if kind == "module":
        (sdk / "feature.py").rename(outside / "feature.py")
        (sdk / "feature.py").symlink_to(outside / "feature.py")
    elif kind == "sdk_root":
        sdk.rename(outside / "sdk")
        sdk.symlink_to(outside / "sdk", target_is_directory=True)
    else:
        (outside / "evidence.json").write_text("{}")
        (repo / "evidence.json").symlink_to(outside / "evidence.json")
        bindings["bindings"][0]["live_evidence"] = "evidence.json"
    with pytest.raises(module().CodeAuditError):
        module().audit_code(repo, bindings, migration)


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbols", ["Feature.missing", "AsyncFeature.get"]),
        ("symbols", ["Feature.get.extra"]),
        ("public_entry", "feature.missing"),
        ("public_entry", "feature._hidden"),
        ("argument_constants", {"missing_keyword": True}),
        ("live_evidence", "missing.json"),
        ("live_evidence", "../outside.json"),
    ],
)
def test_missing_or_inconsistent_static_bindings_fail(tmp_path, field, value):
    _, bindings, migration, _ = fixture_tree(tmp_path)
    bindings["bindings"][0][field] = value
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


@pytest.mark.parametrize(
    "target",
    [
        "client.feature.missing",
        "client.unknown.get",
        "client.nested.get",
        "other.feature.get",
        "client..feature.get",
        "client._feature.get",
    ],
)
def test_migration_checks_whole_path_not_just_last_method(tmp_path, target):
    _, bindings, migration, _ = fixture_tree(tmp_path)
    migration["methods"][0]["target"] = target
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_same_method_name_in_unregistered_class_does_not_count(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    with (sdk / "client.py").open("a") as handle:
        handle.write(
            "\nclass Other:\n    def get(self, *, setting=None): pass\nclass Client:\n    def __init__(self): self.feature = Other()\n"
        )
    migration["methods"][0]["target"] = "client.feature.get"
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_base_cycle_is_reported_instead_of_recursing_forever(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "feature.py").write_text(
        "class A(B): pass\nclass B(A): pass\nclass Feature(A): pass\nclass AsyncFeature(A): pass\n"
    )
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_syntax_error_and_kwargs_do_not_silently_pass(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "base.py").write_text("PRIVATE_BROKEN = (\n")
    with pytest.raises(module().CodeAuditError) as caught:
        module().audit_code(tmp_path, bindings, migration)
    assert "PRIVATE_BROKEN" not in str(caught.value) and caught.value.__context__ is None
    (sdk / "base.py").write_text(
        "class Base:\n    def get(self, **kwargs): pass\nclass AsyncBase:\n    async def get(self, **kwargs): pass\n"
    )
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_missing_async_path_and_valid_evidence_reference(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    evidence = tmp_path / "docs/evidence.json"
    evidence.parent.mkdir()
    evidence.write_text("this evidence content is not audited here")
    bindings["bindings"][0]["live_evidence"] = "docs/evidence.json"
    module().audit_code(tmp_path, bindings, migration)
    (sdk / "client.py").write_text(
        "from .feature import Feature\nclass Client:\n    def __init__(self): self.feature = Feature()\nclass AsyncClient: pass\n"
    )
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_constant_must_exist_on_both_sync_and_async_methods(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "base.py").write_text(
        "class Base:\n    def get(self, *, setting=None): pass\nclass AsyncBase:\n    async def get(self): pass\n"
    )
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_explicit_non_method_override_must_not_fall_back_to_base(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "feature.py").write_text(
        "from .base import Base, AsyncBase\nclass Feature(Base):\n    get = 123\nclass AsyncFeature(AsyncBase): pass\n"
    )
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)


def test_c3_diamond_resolution_selects_override_before_shared_ancestor(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "feature.py").write_text(
        "class Root:\n    def get(self, *, setting=None): pass\n"
        "class Left(Root): pass\nclass Right(Root):\n    def get(self, *, setting=None): pass\n"
        "class Feature(Left, Right): pass\n"
        "class AsyncRoot:\n    async def get(self, *, setting=None): pass\n"
        "class AsyncLeft(AsyncRoot): pass\nclass AsyncRight(AsyncRoot):\n    async def get(self, *, setting=None): pass\n"
        "class AsyncFeature(AsyncLeft, AsyncRight): pass\n"
    )
    bindings["bindings"][0]["symbols"] = ["Right.get", "AsyncRight.get"]
    module().audit_code(tmp_path, bindings, migration)


def test_inherited_initializer_uses_definition_module_imports(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "parents.py").write_text(
        "from .feature import Feature as Target, AsyncFeature as AsyncTarget\n"
        "class Parent:\n    def __init__(self): self.feature = Target()\n"
        "class AsyncParent:\n    def __init__(self): self.feature = AsyncTarget()\n"
    )
    (sdk / "nested.py").write_text(
        "from .parents import Parent, AsyncParent\nclass Nested(Parent): pass\nclass AsyncNested(AsyncParent): pass\n"
    )
    module().audit_code(tmp_path, bindings, migration)


def test_relative_imports_resolve_from_nested_module_directory(tmp_path):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    (sdk / "pkg").mkdir()
    (sdk / "pkg/base.py").write_bytes((sdk / "base.py").read_bytes())
    (sdk / "pkg/feature.py").write_bytes((sdk / "feature.py").read_bytes())
    (sdk / "client.py").write_text(
        "from .pkg.feature import Feature, AsyncFeature\nclass Client:\n    def __init__(self): self.feature = Feature()\nclass AsyncClient:\n    def __init__(self): self.feature = AsyncFeature()\n"
    )
    bindings["bindings"][0]["module"] = "src/ezviz_unified/pkg/feature.py"
    migration["methods"][0]["target"] = "client.feature.get"
    report = module().audit_code(tmp_path, bindings, migration)
    assert "src/ezviz_unified/pkg/base.py" in report["source_files_sha256"]
    assert "src/ezviz_unified/base.py" not in report["source_files_sha256"]


@pytest.mark.parametrize(
    "body",
    [
        "def never_called():\n            self.feature = Feature()",
        "self.feature = Feature()\n        self.feature = factory()",
        "self.feature = Feature()\n        self.feature = object()",
        "if False:\n            self.feature = Feature()",
        "self.feature = Feature()\n        del self.feature",
    ],
)
def test_nonexecuted_or_dynamic_attribute_wiring_is_not_proof(tmp_path, body):
    sdk, bindings, migration, _ = fixture_tree(tmp_path)
    migration["methods"][0]["target"] = "client.feature.get"
    with (sdk / "client.py").open("a") as handle:
        handle.write("\nclass Client:\n    def __init__(self):\n        " + body + "\n")
    with pytest.raises(module().CodeAuditError):
        module().audit_code(tmp_path, bindings, migration)
