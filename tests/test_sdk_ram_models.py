import importlib
import importlib.util
import json
from dataclasses import FrozenInstanceError

import pytest


def module():
    assert importlib.util.find_spec("ezviz_unified.ram_models") is not None, "RAM models missing"
    return importlib.import_module("ezviz_unified.ram_models")


def test_password_encoding_is_explicit_and_input_not_trimmed():
    # Synthetic fixture digests independently checked with OpenSSL.
    digest = module().ram_password_digest("APP", " pass ", encoding="ascii")
    assert digest == "4166568c104542735245652d5722b904"
    assert (
        module().ram_password_digest("APP", "密码", encoding="utf-8")
        == "82b8b63929a7587bca61c377b55f74b4"
    )
    with pytest.raises(TypeError):
        module().ram_password_digest("APP", "pass")


@pytest.mark.parametrize(
    "key,password,encoding",
    [
        ("", "PASS", "utf-8"),
        ("APP", " ", "utf-8"),
        ("APP", "PRIVATE_PASSWORD", "missing-codec"),
        ("APP", "PRIVATE_密码", "ascii"),
        ("APP", "PRIVATE_\ud800", "utf-8"),
    ],
)
def test_password_errors_do_not_echo_or_chain(key, password, encoding):
    with pytest.raises(ValueError) as caught:
        module().ram_password_digest(key, password, encoding=encoding)
    assert "PRIVATE_" not in str(caught.value)
    assert caught.value.__context__ is None


def test_permission_models_preserve_exact_case_resources_and_order():
    mod = module()
    permissions = ["Get", "GET", "FuturePermission"]
    resources = ["dev:PRIVATE_DEVICE", "cam:OTHER_DEVICE:01"]
    statement = mod.RamStatement(permissions, resources)
    permissions.append("DevCtrl")
    resources.append("dev:WIDENED")
    assert statement.permissions == ("Get", "GET", "FuturePermission")
    assert statement.resources == ("dev:PRIVATE_DEVICE", "cam:OTHER_DEVICE:01")
    assert "PRIVATE_DEVICE" not in repr(statement)
    with pytest.raises(FrozenInstanceError):
        statement.permissions = ("DevCtrl",)
    expected = {
        "Permission": "Get,GET,FuturePermission",
        "Resource": ["dev:PRIVATE_DEVICE", "cam:OTHER_DEVICE:01"],
    }
    assert json.loads(mod.serialize_statement(statement)) == expected
    assert json.loads(mod.serialize_policy([statement])) == {"Statement": [expected]}
    assert mod.serialize_policy([]) == '{"Statement":[]}'


@pytest.mark.parametrize(
    "permissions,resources",
    [
        ("Get", ["dev:D"]),
        (["Get"], "dev:D"),
        ([], ["dev:D"]),
        (["Get"], []),
        ([None], ["dev:D"]),
        (["Get,Update"], ["dev:D"]),
        ([" Get"], ["dev:D"]),
        (["Get\n"], ["dev:D"]),
        (["PRIVATE_\x80"], ["dev:D"]),
        (["Get"], ["dev:"]),
        (["Get"], ["cam:D"]),
        (["Get"], ["cam:D:"]),
        (["Get"], ["other:D"]),
        (["Get"], ["dev:PRIVATE_\nDEVICE"]),
        (["Get"], ["dev:PRIVATE_\ud800"]),
        (["Get"], ["dev:D:extra"]),
    ],
)
def test_invalid_statement_structure_is_rejected_without_guessing(permissions, resources):
    with pytest.raises(ValueError) as caught:
        statement = module().RamStatement(permissions, resources)
        module().serialize_statement(statement)
    assert "PRIVATE_" not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("value", ["", {}, ["Get"], [None]])
def test_policy_requires_statement_objects(value):
    with pytest.raises(ValueError):
        module().serialize_policy(value)


def test_hash_backend_failure_does_not_preserve_original_exception(monkeypatch):
    mod = module()

    def fail(*args, **kwargs):
        raise ValueError("PRIVATE_PASSWORD")

    monkeypatch.setattr("hashlib.md5", fail)
    with pytest.raises(ValueError) as caught:
        mod.ram_password_digest("APP", "PRIVATE_PASSWORD", encoding="utf-8")
    assert "PRIVATE_PASSWORD" not in str(caught.value) and caught.value.__context__ is None
