import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from ezviz_unified import ApiError, AsyncClient, Client, RegionConfig

START = datetime(2026, 1, 2, 3, 4, 5)
END = datetime(2026, 1, 2, 4, 5, 6)
TIMES = {"start_time": START, "end_time": END}
COMPACT = {"startTime": "20260102030405", "endTime": "20260102040506"}
SPACED = {"startTime": "2026-01-02 03:04:05", "endTime": "2026-01-02 04:05:06"}
DEVICE_HEADERS = {"deviceserial": "EVAL_DEVICE", "localindex": "2"}
CASES = [
    (
        "space",
        ("SPACE",),
        {},
        "GET",
        "/api/service/cloudrecord/video/space",
        {"spaceId": "SPACE"},
        {},
    ),
    (
        "one_off_plan",
        ("PLAN",),
        {},
        "GET",
        "/api/service/cloudrecord/video/plan/oneOff",
        {"oneOffPlanId": "PLAN"},
        {},
    ),
    (
        "plan_devices",
        (12,),
        {},
        "POST",
        "/api/service/cloudrecord/video/plan/oneOff/devInfos",
        {"oneOffPlanId": "12"},
        {},
    ),
    (
        "plans",
        (34,),
        TIMES,
        "GET",
        "/api/service/cloudrecord/video/plan/oneOff/listById",
        {"spaceId": "34", **COMPACT, "lastOneOffPlanId": "0", "pageSize": "10"},
        {},
    ),
    (
        "tasks",
        (12,),
        {},
        "GET",
        "/api/service/cloudrecord/video/plan/oneOff/task/list",
        {"planId": "12", "pageStart": "0", "pageSize": "10"},
        {},
    ),
    (
        "running_tasks",
        ("EVAL_DEVICE",),
        {**TIMES, "channel": 2},
        "GET",
        "/api/service/cloudrecord/video/plan/oneOff/task/listRunningByDevId",
        {"deviceSerial": "EVAL_DEVICE", "localIndex": "2", **COMPACT},
        {},
    ),
    (
        "calendar",
        ("EVAL_DEVICE",),
        {"channel": 2, "month": "202601"},
        "GET",
        "/api/service/cloudrecord/video/exist/month",
        {"month": "202601"},
        DEVICE_HEADERS,
    ),
    (
        "recordings",
        ("EVAL_DEVICE",),
        {"channel": 2, "space_id": 34, **TIMES},
        "GET",
        "/api/service/cloudrecord/video/info/list",
        {"spaceId": "34", **SPACED},
        DEVICE_HEADERS,
    ),
    (
        "hls_recordings",
        ("EVAL_DEVICE",),
        {"channel": 2, "format": "HLS", **TIMES},
        "POST",
        "/api/service/open/vod/hls/info/list",
        {"format": "HLS", "pageSize": "50", **SPACED},
        DEVICE_HEADERS,
    ),
    (
        "templates",
        (),
        {},
        "GET",
        "/api/service/cloud/video/template/list",
        {"pageStart": "0", "pageSize": "10"},
        {},
    ),
]


def payload(name, code=None):
    root = name in {"plans", "templates"}
    if code is None:
        code = "200" if root else 200
    status = {"code": code, "msg" if root else "message": "ok"}
    return {
        **(status if root else {"meta": status}),
        "data": {"extra": [True, 1, {"untouched": True}]},
    }


def execute(kind, case, *, region=None, responses=None):
    name, args, kwargs, *_ = case
    requests, auth_requests = [], []
    replies = iter(responses) if responses else None

    def auth(req):
        auth_requests.append(req)
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {"accessToken": f"at.EVAL_{len(auth_requests)}", "expireTime": 2000000},
            },
        )

    def business(req):
        requests.append(req)
        return httpx.Response(200, json=next(replies) if replies else payload(name))

    def factory(base_url):
        return httpx.MockTransport(business)

    options = dict(
        region=region or RegionConfig.china(),
        auth_transport=httpx.MockTransport(auth),
        transport_factory=factory,
        clock=lambda: 1000,
    )
    try:
        if kind == "sync":
            with Client("EVAL_KEY", "EVAL_SECRET", **options) as client:
                result = getattr(client.cloud_recording, name)(*args, **kwargs)
        else:

            async def run():
                async with AsyncClient("EVAL_KEY", "EVAL_SECRET", **options) as client:
                    return await getattr(client.cloud_recording, name)(*args, **kwargs)

            result = asyncio.run(run())
    except ValueError:
        assert not requests and not auth_requests
        raise
    return result, requests, auth_requests


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_exact_http_contracts_and_response_preservation(kind, case):
    result, requests, auth = execute(kind, case)
    name, _, _, method, path, fields, headers = case
    assert len(auth) == len(requests) == 1
    request = requests[0]
    assert request.method == method and request.url.path == path
    assert request.url.host == "open.ys7.com"
    assert request.headers["accessToken"] == "at.EVAL_1"
    assert {k: request.headers[k] for k in headers} == headers
    if method == "GET":
        actual = dict(request.url.params)
        assert not request.content
    else:
        actual = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        assert not request.url.query
        assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    assert actual == fields
    assert result.raw == payload(name) and result.data == payload(name)["data"]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_no_inferred_overseas_support_or_network(kind, case):
    with pytest.raises(ValueError):
        execute(kind, case, region=RegionConfig.overseas())


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", ["plans", "plan_devices", "hls_recordings", "templates"])
def test_readonly_post_and_get_refresh_exactly_once(kind, name):
    case = next(c for c in CASES if c[0] == name)
    root = name in {"plans", "templates"}
    result, requests, auth = execute(
        kind, case, responses=[payload(name, "10002" if root else 10002), payload(name)]
    )
    assert len(requests) == len(auth) == 2
    assert [r.headers["accessToken"] for r in requests] == ["at.EVAL_1", "at.EVAL_2"]
    assert result.raw == payload(name)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", ["space", "plans", "templates"])
def test_wrong_success_scalar_type_is_rejected(kind, name):
    case = next(c for c in CASES if c[0] == name)
    with pytest.raises(ApiError):
        execute(kind, case, responses=[payload(name, "200" if name == "space" else 200)])


INVALID = [
    ("space", "args", (" ",)),
    ("one_off_plan", "args", (None,)),
    ("plan_devices", "args", (True,)),
    ("tasks", "page_start", -1),
    ("tasks", "page_size", 51),
    ("templates", "page_size", 101),
    ("plans", "last_plan_id", -1),
    ("plans", "page_size", True),
    ("plans", "end_time", START + timedelta(days=1)),
    ("recordings", "end_time", START + timedelta(days=1)),
    ("running_tasks", "end_time", START + timedelta(days=30, seconds=1)),
    ("hls_recordings", "end_time", START + timedelta(hours=48, seconds=1)),
    ("hls_recordings", "format", "mp4"),
    ("hls_recordings", "page_size", 0),
    ("calendar", "month", "202613"),
    ("calendar", "month", "000001"),
    ("calendar", "month", "２０２６０１"),
    ("calendar", "channel", True),
    ("recordings", "space_id", True),
    ("templates", "template_id", False),
    ("templates", "template_name", " "),
]


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name,key,value", INVALID)
def test_invalid_inputs_fail_before_authentication(kind, name, key, value):
    base = next(c for c in CASES if c[0] == name)
    case = (
        name,
        value if key == "args" else base[1],
        {**base[2], **({key: value} if key != "args" else {})},
        *base[3:],
    )
    with pytest.raises(ValueError):
        execute(kind, case)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", ["plans", "running_tasks", "recordings", "hls_recordings"])
@pytest.mark.parametrize(
    "bad",
    [
        START.replace(tzinfo=timezone.utc),
        START.replace(microsecond=1),
        "20260102030405",
        END + timedelta(seconds=1),
    ],
)
def test_time_precision_timezone_and_order_are_explicit(kind, name, bad):
    base = next(c for c in CASES if c[0] == name)
    case = (name, base[1], {**base[2], "start_time": bad}, *base[3:])
    with pytest.raises(ValueError):
        execute(kind, case)


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize(
    "name,span",
    [
        ("running_tasks", timedelta(days=30)),
        ("hls_recordings", timedelta(hours=48)),
        ("plans", timedelta()),
    ],
)
def test_inclusive_time_bounds_and_four_digit_year(kind, name, span):
    base = next(c for c in CASES if c[0] == name)
    start = datetime(1, 1, 1)
    case = (name, base[1], {**base[2], "start_time": start, "end_time": start + span}, *base[3:])
    _, requests, _ = execute(kind, case)
    req = requests[0]
    fields = (
        dict(req.url.params)
        if req.method == "GET"
        else {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
    )
    assert fields["startTime"].startswith("0001")


@pytest.mark.parametrize("kind", ["sync", "async"])
@pytest.mark.parametrize("name", ["calendar", "hls_recordings", "templates"])
def test_optional_filters_are_sent_only_when_explicit(kind, name):
    base = next(c for c in CASES if c[0] == name)
    additions = {
        "calendar": {"space_id": "SPACE"},
        "hls_recordings": {"space_id": 34},
        "templates": {"template_id": 56, "template_name": "EVAL_TEMPLATE"},
    }[name]
    case = (name, base[1], {**base[2], **additions}, *base[3:])
    _, requests, _ = execute(kind, case)
    req = requests[0]
    fields = (
        dict(req.url.params)
        if req.method == "GET"
        else {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
    )
    expected = {
        "calendar": {"spaceId": "SPACE"},
        "hls_recordings": {"spaceId": "34"},
        "templates": {"templateId": "56", "templateName": "EVAL_TEMPLATE"},
    }[name]
    assert {k: fields[k] for k in expected} == expected


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_missing_optional_meta_message_is_not_an_invented_protocol_requirement(kind):
    case = CASES[0]
    body = {"meta": {"code": 200}, "data": {"spaceId": 34}}
    result, _, _ = execute(kind, case, responses=[body])
    assert result.raw == body and result.message == ""


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_template_identifiers_are_redacted_from_errors(kind):
    case = next(c for c in CASES if c[0] == "templates")
    case = (
        case[0],
        (),
        {"template_id": 987654321, "template_name": "EVAL_PRIVATE_NAME"},
        *case[3:],
    )
    with pytest.raises(ApiError) as captured:
        execute(
            kind, case, responses=[{"code": "60020", "msg": "missing 987654321 EVAL_PRIVATE_NAME"}]
        )
    assert "987654321" not in str(captured.value)
    assert "EVAL_PRIVATE_NAME" not in str(captured.value)


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_numeric_id_redaction_does_not_change_token_retry_decision(kind):
    base = next(c for c in CASES if c[0] == "templates")
    case = (base[0], (), {"template_id": 1000}, *base[3:])
    _, requests, auth = execute(
        kind, case, responses=[payload("templates", "10002"), payload("templates")]
    )
    assert len(requests) == len(auth) == 2
    assert requests[0].url.params["templateId"] == "1000"
