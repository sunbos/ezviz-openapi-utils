"""Run with the clean installation's Python -I; uses only mock HTTP."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx

import ezviz_unified as sdk


def auth(request):
    assert request.method == "POST"
    return httpx.Response(
        200,
        json={
            "code": "200",
            "data": {
                "accessToken": "SMOKE_TOKEN",
                "expireTime": 2_000_000,
                "areaDomain": "https://isgpopen.ezviz.com",
            },
        },
    )


def business(request):
    assert request.url.host == "isgpopen.ezviz.com"
    if request.url.path == "/api/lapp/device/list":
        assert request.method == "POST"
        assert parse_qs(request.content.decode())["accessToken"] == ["SMOKE_TOKEN"]
        return httpx.Response(200, json={"code": "200", "data": []})
    assert request.url.path == "/api/v3/das/device/local/video/query"
    assert request.method == "GET" and request.content == b""
    assert request.headers["accessToken"] == "SMOKE_TOKEN"
    assert request.url.params["startTime"] == "2024-01-01 00:00:00"
    return httpx.Response(200, json={"meta": {"code": 200, "message": "ok"}, "data": []})


def options():
    return {
        "region": sdk.RegionConfig.overseas(),
        "clock": lambda: 1000,
        "auth_transport": httpx.MockTransport(auth),
        "transport_factory": lambda origin: httpx.MockTransport(business),
    }


async def asynchronous():
    async with sdk.AsyncClient("SMOKE_KEY", "SMOKE_SECRET", **options()) as client:
        assert (await client.devices.list()).data == []
        assert (await client.recordings.local("DEVICE", start_time=datetime(2024, 1, 1))).data == []
    assert client.is_closed


def main():
    assert Path(sdk.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (
        "SDK loaded outside installation"
    )
    with sdk.Client("SMOKE_KEY", "SMOKE_SECRET", **options()) as client:
        assert client.devices.list().data == []
        assert client.recordings.local("DEVICE", start_time=datetime(2024, 1, 1)).data == []
    assert client.is_closed
    asyncio.run(asynchronous())
    print("Installed SDK sync/async mock smoke passed")


if __name__ == "__main__":
    main()
