import json

from ezviz_unified import ApiError, ApiResponse
from tools.live import verify_devices


def test_live_verifier_calls_only_bounded_read_operations_and_redacts_report(monkeypatch):
    calls = []

    class Devices:
        def list(self, *, page_size):
            calls.append(("list", page_size))
            return ApiResponse(200, "200", data=[{"deviceSerial": "PRIVATE_DEVICE"}])

        def get(self, serial):
            calls.append(("get", serial))
            return ApiResponse(200, "200", data={"deviceName": "PRIVATE_NAME"})

        def channels(self, serial):
            calls.append(("channels", serial))
            return ApiResponse(200, "200", data=[])

        def status(self, serial):
            calls.append(("status", serial))
            raise ApiError("PRIVATE_MESSAGE", code="PRIVATE_CODE", http_status=400)

    class Client:
        def __init__(self, *args, **kwargs):
            self.devices = Devices()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(verify_devices, "Client", Client)
    result = verify_devices.verify(
        {"region": "domestic", "app_key": "PRIVATE_KEY", "app_secret": "PRIVATE_SECRET"}
    )
    assert calls == [
        ("list", 1),
        ("get", "PRIVATE_DEVICE"),
        ("channels", "PRIVATE_DEVICE"),
        ("status", "PRIVATE_DEVICE"),
    ]
    assert "PRIVATE" not in json.dumps(result)
    assert result["results"][-1] == {
        "operation": "devices.status",
        "status": "failed",
        "error_type": "ApiError",
        "code": None,
        "http_status": 400,
    }


def test_empty_account_is_not_reported_as_device_validation(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            self.devices = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def list(self, *, page_size):
            return ApiResponse(200, "200", data=[])

    monkeypatch.setattr(verify_devices, "Client", Client)
    result = verify_devices.verify({"region": "overseas", "app_key": "K", "app_secret": "S"})
    assert result["results"][-1]["status"] == "not_verified"
    assert result["results"][-1]["reason"] == "no_device"


def test_managed_inventory_is_opt_in_and_does_not_trigger_detail_queries(monkeypatch):
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.devices = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def list(self, *, page_size):
            calls.append("ordinary")
            return ApiResponse(200, "200", data=[])

        def list_managed(self, *, page_size):
            assert page_size == 1
            calls.append("managed")
            return ApiResponse(200, "200", data=[{"deviceSerial": "PRIVATE_MANAGED_DEVICE"}])

    monkeypatch.setattr(verify_devices, "Client", Client)
    result = verify_devices.verify(
        {"region": "domestic", "app_key": "K", "app_secret": "S", "include_managed": "true"}
    )
    assert calls == ["ordinary", "managed"]
    assert {"operation": "devices.list_managed", "status": "passed", "returned_items": 1} in result[
        "results"
    ]
    assert "PRIVATE" not in json.dumps(result)


def test_protocol_probe_uses_public_sample_and_does_not_query_devices(monkeypatch):
    calls = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.diagnostics = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def protocol_support(self, model, version, *, app_key):
            calls.append((model, version, app_key))
            return ApiResponse(200, "200", data=[{"isSupport": 1}])

    monkeypatch.setattr(verify_devices, "Client", Client)
    result = verify_devices.verify(
        {
            "region": "domestic",
            "app_key": "PRIVATE_KEY",
            "app_secret": "PRIVATE_SECRET",
            "protocol_only": "true",
        }
    )
    assert calls == [("CS-C1-10F", "V4.1.0 build 130101", "PRIVATE_KEY")]
    assert result["results"][0]["operation"] == "diagnostics.protocol_support"
    assert result["results"][0]["reported_support"] == [1] and "PRIVATE" not in json.dumps(result)
