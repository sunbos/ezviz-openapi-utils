import pytest

from ezviz_unified import (
    ApiError,
    DeviceError,
    PermissionDeniedError,
    ProtocolError,
    ResponsePolicy,
    decode_response,
)


def policy(**kwargs):
    return ResponsePolicy(
        code_path="meta.code",
        message_path="meta.message",
        success_values=(200,),
        envelope_paths=("", "body"),
        **kwargs,
    )


@pytest.mark.parametrize("wrapped", [False, True])
def test_explicit_envelopes_preserve_raw_and_select_matching_data(wrapped):
    inner = {"meta": {"code": 200, "message": "ok"}, "data": {"status": 3}}
    raw = {"status": 200, "body": inner} if wrapped else inner
    result = decode_response(raw, policy=policy())
    assert result.raw is raw and result.data is inner["data"]


def test_observed_unauthenticated_root_meta_is_business_error():
    with pytest.raises(ApiError) as caught:
        decode_response(
            {"meta": {"code": "10001", "message": "AccessToken is null."}}, policy=policy()
        )
    assert type(caught.value) is ApiError and caught.value.code == "10001"


@pytest.mark.parametrize("second", [200, 10002, None, True])
def test_multiple_matching_envelopes_are_rejected_instead_of_chosen(second):
    raw = {"meta": {"code": 200}, "body": {"meta": {"code": second}}}
    with pytest.raises(ProtocolError):
        decode_response(raw, policy=policy())


def test_default_policy_does_not_search_wrapped_objects():
    with pytest.raises(ProtocolError):
        decode_response({"body": {"code": "200", "data": []}})


def test_single_layout_http_error_keeps_existing_message_without_code():
    with pytest.raises(ApiError) as caught:
        decode_response({"msg": "useful error"}, http_status=500)
    assert caught.value.message == "useful error" and caught.value.code is None


def test_nonmatching_nested_code_does_not_override_explicit_scope():
    raw = {"meta": {"code": 200}, "body": {"code": "10002"}, "data": 0}
    assert decode_response(raw, policy=policy()).data == 0


def test_device_status_paths_are_relative_to_selected_envelope():
    with pytest.raises(DeviceError):
        decode_response(
            {"body": {"meta": {"code": 200}, "data": {"ret": 400}}},
            policy=policy(device_code_path="data.ret", device_success_values=(200,)),
        )


def test_http_failure_wins_even_when_envelope_selection_is_ambiguous():
    raw = {"meta": {"code": 200}, "body": {"meta": {"code": 200}}}
    with pytest.raises(PermissionDeniedError):
        decode_response(raw, policy=policy(), http_status=403)


@pytest.mark.parametrize(
    "paths", [(), "body", ("", ""), (None,), ("body..value",), (1,), {"body": 1}]
)
def test_invalid_envelope_paths_rejected(paths):
    with pytest.raises(ValueError):
        ResponsePolicy(envelope_paths=paths)


def test_envelope_paths_are_immutable_copies():
    paths = ["", "body"]
    configured = ResponsePolicy(envelope_paths=paths)
    paths.append("unreviewed")
    assert configured.envelope_paths == ("", "body")
