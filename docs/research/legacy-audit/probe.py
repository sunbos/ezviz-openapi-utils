"""Offline diagnostic probes for legacy commit 25cd413; no device traffic."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

if len(sys.argv) != 2:
    raise SystemExit("Usage: python probe.py /path/to/legacy-source")
ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "src"))
os.environ["EZVIZ_APP_KEY"] = ""
os.environ["EZVIZ_APP_SECRET"] = ""

def blocked(*args, **kwargs):
    raise AssertionError("Unexpected network access blocked by audit")

socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked

import dotenv
import pytest
import requests
from ezviz_openapi_utils.client import Client
from ezviz_openapi_utils.api import EZVIZOpenAPI
from ezviz_openapi_utils.oauth import AccessTokenData
from ezviz_openapi_utils.exceptions import EZVIZAPIError

dotenv.load_dotenv = lambda *args, **kwargs: False

def response(payload, status=200, url="https://example.invalid/api"):
    r = requests.Response()
    r.status_code = status
    r.url = url
    r._content = json.dumps(payload).encode()
    return r

def fake_token():
    return SimpleNamespace(code="200", msg="success", data=SimpleNamespace(
        access_token="at.SYNTHETIC_AUDIT_MARKER", expire_time=1, area_domain=None
    ))

observations = {}
with patch("requests.sessions.Session.request", side_effect=blocked), patch(
    "ezviz_openapi_utils.client.AccessToken", side_effect=lambda *a, **kw: fake_token()
) as token_factory:
    client = Client("synthetic-key", "synthetic-secret")
    api = EZVIZOpenAPI(client)
    request = Mock(return_value=response({"code": "10002", "msg": "expired"}))
    client._session.request = request
    for _ in range(2):
        try:
            api.list_devices_by_page()
        except EZVIZAPIError as exc:
            assert exc.code == "10002"
    observations["token_not_refreshed"] = {
        "reproduced": token_factory.call_count == 1,
        "token_acquisitions": token_factory.call_count,
        "expired_business_requests": request.call_count,
        "token_expire_time": client.expire_time,
    }
    observations["missing_request_timeout"] = {
        "reproduced": "timeout" not in request.call_args.kwargs,
    }
    device_failure = {"meta": {"code": 200, "message": "success", "moreInfo": {
        "deviceMeta": {"code": "2003", "errorMsg": "device offline"}
    }}, "data": None}
    client._session.request = Mock(return_value=response(device_failure))
    accepted = api.execute_device_otap_action("AUDIT_DEVICE", "0", "global", "HDD", "GetHDDQuota", {})
    observations["device_failure_accepted"] = {"reproduced": accepted == device_failure}
    foreign = EZVIZOpenAPI(Client("synthetic-key", "synthetic-secret", region="eu"))
    observations["missing_foreign_domain_routes_to_china"] = {
        "reproduced": foreign._base_url == "https://open.ys7.com",
    }
    token = AccessTokenData({"accessToken": "at.SYNTHETIC_AUDIT_MARKER", "expireTime": 1})
    observations["repr_contains_token"] = {"reproduced": "SYNTHETIC_AUDIT_MARKER" in repr(token)}
    try:
        api._handle_api_response(response({"code": "500", "msg": "failure"}, 500,
            "https://example.invalid/api?accessToken=at.SYNTHETIC_AUDIT_MARKER"))
    except EZVIZAPIError as exc:
        observations["http_error_contains_query_token"] = {
            "reproduced": "SYNTHETIC_AUDIT_MARKER" in str(exc),
        }
    client._session.request = Mock(return_value=response({"code": "200", "data": {}}))
    api.get_device_status("AUDIT_DEVICE", channel_no=2)
    data = client._session.request.call_args.kwargs["data"]
    observations["status_channel_parameter"] = {
        "reproduced": "channelNo" in data and "channel" not in data,
        "sent_field": "channelNo" if "channelNo" in data else "channel",
    }

# Invoke one old test with a mock API; never create its real_client fixture.
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("legacy_test_api", ROOT / "tests/test_api.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
owner = next(c for c in vars(module).values() if isinstance(c, type) and
             "test_format_device_disk" in vars(c))
mock_api = Mock()
mock_api.format_device_disk.return_value = {"meta": {"code": 200, "message": "success"}}
skipped = False
try:
    with contextlib.redirect_stdout(io.StringIO()):
        owner().test_format_device_disk(mock_api, "AUDIT_DEVICE", "0")
except pytest.skip.Exception:
    skipped = True
observations["format_call_before_skip"] = {
    "reproduced": skipped and mock_api.format_device_disk.call_count == 1,
    "api_calls_before_skip": mock_api.format_device_disk.call_count,
}
assert all(item["reproduced"] for item in observations.values()), observations
print(json.dumps({"source_commit": "25cd41321d244592b4f5c9250b13443e5502129d",
                  "mode": "offline mocks, real network blocked",
                  "observations": observations}, ensure_ascii=False, indent=2))
