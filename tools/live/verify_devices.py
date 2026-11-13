"""Explicit read-only live verification; credentials stay in process memory."""

from __future__ import annotations

import argparse
import html
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from ezviz_unified import Client, EzvizError, RegionConfig


def verify(config: dict[str, str]) -> dict[str, object]:
    scope = config["region"]
    if scope not in {"domestic", "overseas"}:
        raise ValueError("invalid region")
    region = (
        RegionConfig.china()
        if scope == "domestic"
        else RegionConfig.overseas(
            auth_base_url=config.get("auth_base_url") or "https://open.ezvizlife.com"
        )
    )
    results: list[dict[str, object]] = []
    origins: list[str] = []
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "region": scope,
        "auth_origin": region.auth_base_url,
        "business_origins": origins,
        "read_only": True,
        "results": results,
    }

    def transport(origin: str) -> httpx.BaseTransport:
        origins.append(origin)
        return httpx.HTTPTransport(retries=0, trust_env=False)

    def record_error(operation: str, error: EzvizError) -> None:
        code = str(error.code) if error.code is not None else ""
        results.append(
            {
                "operation": operation,
                "status": "failed",
                "error_type": type(error).__name__,
                "code": code if re.fullmatch(r"\d{3,8}", code) else None,
                "http_status": error.http_status,
            }
        )

    with Client(
        config["app_key"],
        config["app_secret"],
        region=region,
        timeout=10,
        transport_factory=transport,
    ) as client:
        try:
            response = client.devices.list(page_size=1)
        except EzvizError as exc:
            record_error("devices.list", exc)
            return report
        rows = response.data
        if not isinstance(rows, list):
            results.append({"operation": "devices.list", "status": "unexpected_data_shape"})
            return report
        results.append(
            {"operation": "devices.list", "status": "passed", "returned_items": len(rows)}
        )
        serial = rows[0].get("deviceSerial") if rows and isinstance(rows[0], dict) else None
        if not isinstance(serial, str) or not serial.strip():
            reason = "no_device" if not rows else "missing_device_serial"
            results.append(
                {"operation": "device_details", "status": "not_verified", "reason": reason}
            )
            return report
        for name in ("get", "channels", "status"):
            try:
                response = getattr(client.devices, name)(serial)
                expected_type = list if name == "channels" else dict
                status = (
                    "passed"
                    if isinstance(response.data, expected_type)
                    else "unexpected_data_shape"
                )
                results.append({"operation": f"devices.{name}", "status": status})
            except EzvizError as exc:
                record_error(f"devices.{name}", exc)
    return report


def serve(output: Path) -> None:
    """Temporary loopback form lets authorized browser inputs reach the local SDK."""
    route = "/" + secrets.token_urlsafe(24)
    form = """<!doctype html><meta charset=utf-8><title>EZVIZ 只读验收</title>
    <h1>EZVIZ 只读验收</h1><p>仅认证、查询一页设备及第一台设备的资料、通道、状态。
    密钥仅用于本次进程；结果不包含设备标识、密钥或原始响应。</p>
    <form method=post autocomplete=off>
    <label>区域<select name=region><option value=domestic>国内</option>
    <option value=overseas>海外</option></select></label><br>
    <label>AppKey<input name=app_key type=password required autocomplete=off></label><br>
    <label>AppSecret<input name=app_secret type=password required autocomplete=off></label><br>
    <label>海外认证入口（留空使用官方文档默认值）<input name=auth_base_url></label><br>
    <button>运行只读验收</button></form>"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def reply(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; form-action 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self) -> None:
            self.reply(200, form) if self.path == route else self.reply(404, "Not found")

        def do_POST(self) -> None:
            if self.path != route or self.headers.get("Origin") != origin:
                self.reply(403, "Forbidden")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("invalid input size")
                values = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
                config = {k: v[0] for k, v in values.items()}
                result = verify(config)
                config.clear()
                values.clear()
            except Exception as exc:
                self.reply(400, f"Verification stopped: {html.escape(type(exc).__name__)}")
                return
            output.mkdir(parents=True, exist_ok=True)
            destination = output / f"{result['region']}.json"
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            self.reply(
                200,
                "<h1>只读验收结果</h1><pre>"
                + html.escape(json.dumps(result, ensure_ascii=False, indent=2))
                + "</pre>",
            )

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    origin = f"http://127.0.0.1:{server.server_port}"
    print(origin + route, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("docs/validation/live"))
    args = parser.parse_args()
    if args.serve:
        serve(args.output)
    else:
        try:
            print(json.dumps(verify(json.load(sys.stdin)), ensure_ascii=False, indent=2))
        except Exception as error:
            print(json.dumps({"status": "stopped", "error_type": type(error).__name__}))
            sys.exit(1)
