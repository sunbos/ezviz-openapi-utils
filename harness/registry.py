"""Structural audit of the reviewed registry files (stdlib only).

Pure data validation over the three registry documents (transport contracts,
SDK bindings, source issues). Inputs are already-parsed JSON objects and are
never modified.
No SDK module is imported, no code is executed, and ``source_url`` targets
are never fetched — they are only compared as opaque strings.

Every structural violation raises :class:`RegistryError`. Messages contain
only a fixed reason plus the index path of the offending entry; raw values
are never echoed and no exception chain is retained.
"""

from __future__ import annotations

SCHEMA_VERSION = 1
EVIDENCE = "registry_structure_only"

REGIONS = frozenset(("domestic", "overseas"))
HTTP_METHODS = frozenset(("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"))
BODY_ENCODINGS = frozenset(("form_urlencoded", "json", "unknown"))
TOKEN_LOCATIONS = frozenset(("none", "form", "json", "query", "header"))
PARAMETER_LOCATIONS = frozenset(("body", "query", "header"))
TOKEN_PARAMETER_LOCATIONS = {"form": "body", "json": "body", "query": "query", "header": "header"}
SUCCESS_PATH_FIELDS = ("message_path", "data_path", "device_code_path")
NOT_VERIFIED = "not_verified"
_HEX = frozenset("0123456789abcdef")


class RegistryError(ValueError):
    """A registry document failed structural validation."""


def _fail(where, reason):
    raise RegistryError(f"{where}: {reason}")


def _entry(value, where):
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    return value


def _text(value, field, where):
    if not isinstance(value, str) or not value.strip():
        _fail(where, f"{field} must be a non-empty string")
    return value


def _stripped_text(value, field, where):
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(where, f"{field} must be a non-empty string without surrounding whitespace")
    return value


def _region(value, where):
    if not isinstance(value, str) or value not in REGIONS:
        _fail(where, "region must be domestic or overseas")
    return value


def _doc_identity(entry, where):
    doc = _stripped_text(entry.get("source_doc_id"), "source_doc_id", where)
    url = _text(entry.get("source_url"), "source_url", where)
    sha = entry.get("source_content_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or not set(sha) <= _HEX:
        _fail(where, "source_content_sha256 must be 64 lowercase hex characters")
    return doc, url, sha


def _dotted(value, field, where):
    if not (
        isinstance(value, str)
        and value
        and not any(ch.isspace() for ch in value)
        and all(value.split("."))
    ):
        _fail(where, f"{field} must be a non-empty dotted path")


def _path(value, where):
    if not (
        isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and "?" not in value
        and "#" not in value
        and "\\" not in value
        and not any(ch.isspace() for ch in value)
    ):
        _fail(where, "path must start with / (not //) and contain no ?, #, \\ or whitespace")


def _document(value, name, list_key):
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != SCHEMA_VERSION
    ):
        _fail(name, "expected a schema_version 1 object")
    rows = value.get(list_key)
    if not isinstance(rows, list):
        _fail(name, f"{list_key} must be a list")
    return rows


def _parameters(contract, where):
    params = contract.get("parameters")
    if not isinstance(params, list):
        _fail(where, "parameters must be a list")
    seen = set()
    for i, raw in enumerate(params):
        pwhere = f"{where}.parameters[{i}]"
        param = _entry(raw, pwhere)
        name = _text(param.get("name"), "name", pwhere)
        _text(param.get("type"), "type", pwhere)
        location = param.get("location")
        if not isinstance(location, str) or location not in PARAMETER_LOCATIONS:
            _fail(pwhere, "location must be body, query or header")
        if type(param.get("required")) is not bool:
            _fail(pwhere, "required must be a boolean")
        key = (location, name)
        if key in seen:
            _fail(pwhere, "duplicate (location, name) parameter")
        seen.add(key)
    return params


def _token_consistency(contract, params, where):
    token_location = contract.get("token_location")
    body_encoding = contract.get("body_encoding")
    if token_location == "form" and body_encoding != "form_urlencoded":
        _fail(where, "form token_location requires form_urlencoded body_encoding")
    if token_location == "json" and body_encoding != "json":
        _fail(where, "json token_location requires json body_encoding")
    expected = TOKEN_PARAMETER_LOCATIONS.get(token_location)
    tokens = [p for p in params if p.get("name") == "accessToken"]
    if expected is None:
        if tokens:
            _fail(where, "token_location none must not declare an accessToken parameter")
        return
    if not tokens:
        _fail(where, "a required accessToken parameter is missing")
    for param in tokens:
        if param.get("location") != expected:
            _fail(where, "accessToken parameter location does not match token_location")
    if not any(param.get("required") is True for param in tokens):
        _fail(where, "the accessToken parameter must be required")


def _success(value, where):
    success = _entry(value, where)
    if "envelope_paths" in success:
        paths = success["envelope_paths"]
        if not isinstance(paths, list) or not paths:
            _fail(where, "envelope_paths must be a non-empty list")
        seen = set()
        for path in paths:
            if not isinstance(path, str):
                _fail(where, "envelope_paths entries must be strings")
            if path:
                _dotted(path, "envelope_paths", where)
            if path in seen:
                _fail(where, "envelope_paths must not contain duplicates")
            seen.add(path)
    _dotted(success.get("code_path"), "code_path", where)
    values = success.get("values")
    if not isinstance(values, list) or not values:
        _fail(where, "values must be a non-empty list")
    for item in values:
        if type(item) not in (int, str):
            _fail(where, "values items must be int or str, never bool")
    for field in SUCCESS_PATH_FIELDS:
        if field in success:
            _dotted(success.get(field), field, where)
    if "device_success_values" in success:
        device_values = success.get("device_success_values")
        if not isinstance(device_values, list) or not device_values:
            _fail(where, "device_success_values must be a non-empty list")
        for item in device_values:
            if type(item) not in (int, str):
                _fail(where, "device_success_values items must be int or str, never bool")
    if "require_device_code" in success:
        if type(success.get("require_device_code")) is not bool:
            _fail(where, "require_device_code must be a boolean")
        if success.get("require_device_code") is True and "device_code_path" not in success:
            _fail(where, "require_device_code requires device_code_path")


def _contract(raw, where, operation_ids, doc_identities):
    contract = _entry(raw, where)
    operation_id = _stripped_text(contract.get("operation_id"), "operation_id", where)
    if operation_id in operation_ids:
        _fail(where, "duplicate operation_id")
    operation_ids.add(operation_id)
    region = _region(contract.get("region"), where)
    doc, url, sha = _doc_identity(contract, where)
    method = contract.get("method")
    if not isinstance(method, str) or method not in HTTP_METHODS:
        _fail(where, "method must be a known HTTP method")
    _path(contract.get("path"), where)
    if type(contract.get("read_only")) is not bool:
        _fail(where, "read_only must be a boolean")
    body_encoding = contract.get("body_encoding")
    if not isinstance(body_encoding, str) or body_encoding not in BODY_ENCODINGS:
        _fail(where, "body_encoding must be form_urlencoded, json or unknown")
    token_location = contract.get("token_location")
    if not isinstance(token_location, str) or token_location not in TOKEN_LOCATIONS:
        _fail(where, "token_location must be none, form, json, query or header")
    params = _parameters(contract, where)
    _token_consistency(contract, params, where)
    _success(contract.get("success"), f"{where}.success")
    identity = doc_identities.setdefault((region, doc), (url, sha))
    if identity != (url, sha):
        _fail(where, "source_url/source_content_sha256 differ for the same source document")
    return {"operation_id": operation_id, "region": region, "source_doc_id": doc}


def _binding(raw, where, operation_ids):
    binding = _entry(raw, where)
    operation_id = _text(binding.get("operation_id"), "operation_id", where)
    if operation_id in operation_ids:
        _fail(where, "duplicate operation_id")
    operation_ids.add(operation_id)
    region = _region(binding.get("region"), where)
    doc = _stripped_text(binding.get("source_doc_id"), "source_doc_id", where)
    _text(binding.get("module"), "module", where)
    symbols = binding.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        _fail(where, "symbols must be a non-empty list")
    if any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols):
        _fail(where, "symbols items must be non-empty strings")
    if len(set(symbols)) != len(symbols):
        _fail(where, "symbols must not contain duplicates")
    _text(binding.get("offline_status"), "offline_status", where)
    live_status = _text(binding.get("live_status"), "live_status", where)
    if live_status != NOT_VERIFIED:
        _text(binding.get("live_evidence"), "live_evidence", where)
    if "public_entry" in binding:
        _text(binding.get("public_entry"), "public_entry", where)
    if "argument_constants" in binding:
        constants = binding.get("argument_constants")
        if not isinstance(constants, dict):
            _fail(where, "argument_constants must be an object")
        for key, val in constants.items():
            if not isinstance(key, str) or not key.isidentifier():
                _fail(where, "argument_constants keys must be identifiers")
            if val is not None and type(val) not in (bool, int, str):
                _fail(where, "argument_constants values must be None, bool, int or str")
    return {
        "operation_id": operation_id,
        "region": region,
        "source_doc_id": doc,
        "live_status": live_status,
    }


def _issue(raw, where, issue_ids, doc_identities):
    issue = _entry(raw, where)
    issue_id = _text(issue.get("id"), "id", where)
    if issue_id in issue_ids:
        _fail(where, "duplicate id")
    issue_ids.add(issue_id)
    region = _region(issue.get("region"), where)
    doc, url, sha = _doc_identity(issue, where)
    _text(issue.get("description"), "description", where)
    _text(issue.get("status"), "status", where)
    _text(issue.get("sdk_handling"), "sdk_handling", where)
    identity = doc_identities.setdefault((region, doc), (url, sha))
    if identity != (url, sha):
        _fail(where, "source_url/source_content_sha256 differ for the same source document")


def audit_registry(contracts, bindings, issues) -> dict:
    """Validate the three registry payloads and return a structural summary.

    Raises :class:`RegistryError` on the first structural violation. The
    returned report deliberately contains only registry structure counts —
    no safe_to_publish/approved verdict and no live-verification claims.
    """
    contract_rows = _document(contracts, "contracts", "contracts")
    binding_rows = _document(bindings, "bindings", "bindings")
    issue_rows = _document(issues, "issues", "issues")

    doc_identities = {}
    contract_ids = set()
    contract_index = {}
    region_counts = {}
    for i, raw in enumerate(contract_rows):
        info = _contract(raw, f"contracts[{i}]", contract_ids, doc_identities)
        contract_index[info["operation_id"]] = info
        region_counts[info["region"]] = region_counts.get(info["region"], 0) + 1

    binding_ids = set()
    binding_infos = []
    live_status_counts = {}
    for i, raw in enumerate(binding_rows):
        info = _binding(raw, f"bindings[{i}]", binding_ids)
        binding_infos.append((i, info))
        live_status_counts[info["live_status"]] = live_status_counts.get(info["live_status"], 0) + 1
    if binding_ids != contract_ids:
        _fail("bindings", "operation_id set does not match contracts")
    for i, info in binding_infos:
        contract = contract_index[info["operation_id"]]
        if (info["region"], info["source_doc_id"]) != (
            contract["region"],
            contract["source_doc_id"],
        ):
            _fail(f"bindings[{i}]", "region/source_doc_id do not match the contract")

    issue_ids = set()
    for i, raw in enumerate(issue_rows):
        _issue(raw, f"issues[{i}]", issue_ids, doc_identities)

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": EVIDENCE,
        "summary": {
            "contracts": len(contract_rows),
            "bindings": len(binding_rows),
            "source_documents": len(
                {(c["region"], c["source_doc_id"]) for c in contract_index.values()}
            ),
            "source_issues": len(issue_rows),
        },
        "regions": dict(sorted(region_counts.items())),
        "live_status_counts": dict(sorted(live_status_counts.items())),
    }
