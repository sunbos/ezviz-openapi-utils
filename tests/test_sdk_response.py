"""Independent acceptance tests; changes require coordinator review."""

import copy
import importlib
import importlib.util

import pytest


@pytest.fixture
def sdk():
    assert importlib.util.find_spec("ezviz_unified") is not None, "SDK is not implemented"
    return importlib.import_module("ezviz_unified")


def test_lapp_response_preserves_data_and_original_code(sdk):
    payload = {"code": "200", "msg": "ok", "data": [{"serial": "EXAMPLE"}]}
    result = sdk.decode_response(payload, operation="devices.list")
    assert result.code == "200"
    assert result.data == payload["data"]
    assert result.raw == payload
    assert result.http_status == 200
    assert result.operation == "devices.list"


def test_policy_selects_meta_instead_of_unrelated_top_level_code(sdk):
    payload = {"code": "999", "meta": {"code": 200, "message": "ok"}, "data": 0}
    policy = sdk.ResponsePolicy(code_path="meta.code", message_path="meta.message")
    result = sdk.decode_response(payload, policy=policy)
    assert result.code == 200 and result.data == 0


def test_result_envelope_supports_endpoint_specific_success(sdk):
    policy = sdk.ResponsePolicy(
        code_path="result.code",
        message_path="result.msg",
        data_path="result.data",
        success_values=("20020",),
    )
    result = sdk.decode_response(
        {"result": {"code": "20020", "msg": "present", "data": []}}, policy=policy
    )
    assert result.data == [] and result.code == "20020"


def test_device_failure_is_not_platform_success(sdk):
    policy = sdk.ResponsePolicy(
        code_path="meta.code",
        message_path="meta.message",
        device_code_path="meta.moreInfo.deviceMeta.code",
        device_message_path="meta.moreInfo.deviceMeta.errorMsg",
    )
    with pytest.raises(sdk.DeviceError) as caught:
        sdk.decode_response(
            {
                "meta": {
                    "code": 200,
                    "moreInfo": {"deviceMeta": {"code": "2003", "errorMsg": "offline"}},
                }
            },
            policy=policy,
            operation="otap.read",
        )
    assert caught.value.code == "2003"
    assert caught.value.operation == "otap.read"


def test_missing_optional_device_metadata_is_allowed(sdk):
    policy = sdk.ResponsePolicy(
        code_path="meta.code", device_code_path="meta.moreInfo.deviceMeta.code"
    )
    assert sdk.decode_response({"meta": {"code": 200, "moreInfo": None}}, policy=policy).code == 200


def test_required_device_metadata_cannot_be_missing(sdk):
    policy = sdk.ResponsePolicy(
        code_path="meta.code",
        require_device_code=True,
        device_code_path="meta.moreInfo.deviceMeta.code",
    )
    with pytest.raises(sdk.ProtocolError):
        sdk.decode_response({"meta": {"code": 200, "moreInfo": None}}, policy=policy)


def test_http_failure_wins_over_successful_business_code(sdk):
    with pytest.raises(sdk.ApiError) as caught:
        sdk.decode_response({"code": "200", "msg": "upstream error"}, http_status=503)
    assert caught.value.http_status == 503


@pytest.mark.parametrize(
    "code,error", [("10002", "AuthenticationError"), (10031, "PermissionDeniedError")]
)
def test_authentication_and_permission_failures_are_distinct(sdk, code, error):
    with pytest.raises(getattr(sdk, error)) as caught:
        sdk.decode_response({"code": code, "msg": "failed"})
    assert caught.value.code == code


def test_unknown_error_codes_do_not_cause_keyerror(sdk):
    with pytest.raises(sdk.ApiError) as caught:
        sdk.decode_response({"code": "VENDOR_NEW_CODE", "msg": "new error"})
    assert caught.value.code == "VENDOR_NEW_CODE"


@pytest.mark.parametrize(
    "payload", [[], None, {}, {"meta": None}, {"code": True}, {"code": {"value": 200}}]
)
def test_malformed_success_payload_is_a_protocol_error(sdk, payload):
    with pytest.raises(sdk.ProtocolError):
        sdk.decode_response(payload)


def test_non_json_http_failure_still_has_http_context(sdk):
    with pytest.raises(sdk.ApiError) as caught:
        sdk.decode_response("proxy unavailable", http_status=502, operation="devices.list")
    assert caught.value.http_status == 502 and caught.value.operation == "devices.list"


def test_exception_strings_redact_secrets_and_query_tokens(sdk):
    message = "secret=SENSITIVE_KEY; https://example.invalid/a?accessToken=TOKEN_VALUE&x=1"
    with pytest.raises(sdk.ApiError) as caught:
        sdk.decode_response({"code": "500", "msg": message}, secrets=("SENSITIVE_KEY",))
    for value in (str(caught.value), repr(caught.value), caught.value.message):
        assert "SENSITIVE_KEY" not in value
        assert "TOKEN_VALUE" not in value


def test_response_repr_does_not_expose_payload_or_message(sdk):
    result = sdk.decode_response(
        {"code": "200", "msg": "PRIVATE_MESSAGE", "data": {"accessToken": "PRIVATE_PAYLOAD"}}
    )
    assert "PRIVATE_MESSAGE" not in repr(result)
    assert "PRIVATE_PAYLOAD" not in repr(result)
    assert result.data["accessToken"] == "PRIVATE_PAYLOAD"


def test_decoder_does_not_mutate_input(sdk):
    payload = {"code": "10001", "msg": "SECRET", "data": {"x": [1, 2]}}
    before = copy.deepcopy(payload)
    with pytest.raises(sdk.ApiError):
        sdk.decode_response(payload, secrets=("SECRET",))
    assert payload == before


def test_exception_does_not_retain_redaction_secrets(sdk):
    with pytest.raises(sdk.ApiError) as caught:
        sdk.decode_response({"code": "500", "msg": "SENSITIVE_KEY"}, secrets=("SENSITIVE_KEY",))
    assert "SENSITIVE_KEY" not in repr(vars(caught.value))


def test_overlapping_secrets_are_redacted_longest_first(sdk):
    from ezviz_unified.errors import redact

    assert redact("TOKEN-EXTENDED", ("TOKEN", "TOKEN-EXTENDED")) == "***"


@pytest.mark.parametrize(
    "kwargs",
    [{"message_path": ""}, {"data_path": ""}, {"device_code_path": ""}, {"message_path": None}],
)
def test_invalid_policy_paths_fail_at_configuration_time(sdk, kwargs):
    with pytest.raises(ValueError):
        sdk.ResponsePolicy(**kwargs)


@pytest.mark.parametrize("device_code", [False, None])
def test_present_invalid_device_code_is_not_optional_success(sdk, device_code):
    policy = sdk.ResponsePolicy(code_path="meta.code", device_code_path="meta.device.code")
    with pytest.raises(sdk.ProtocolError):
        sdk.decode_response({"meta": {"code": 200, "device": {"code": device_code}}}, policy=policy)
