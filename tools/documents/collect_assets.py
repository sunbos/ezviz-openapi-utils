"""采集公开文档的图片与附件；只存储字节，不执行 HTML、SVG 或 JavaScript。

python3 tools/documents/collect_assets.py --root data/official-docs/2026-11-14
依赖 requests；默认六线程、每次连接 8 秒/读取 25 秒、最多三次请求。
已完成资源按 SHA256 验证后续用，失败项可用 --retry-failures 重试。
"""

import argparse
import base64
import binascii
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import re
import socket
import threading
from urllib.parse import parse_qsl, unquote, unquote_to_bytes, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zipfile
import zlib

import requests


DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".xls", ".xlsx"}
MEDIA_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m3u8", ".mp3", ".wav", ".aac", ".ogg", ".flv"}
BINARY_EXTENSIONS = {".zip", ".exe", ".dll", ".so", ".dmg", ".apk", ".aar", ".ipa", ".rar", ".7z", ".gz", ".tar", ".msi"}
ALLOWED_HOSTS = {
    "resource.eziot.com", "izhstatic.ys7.com", "open.ys7.com", "img.ys7.com",
    "appres.ys7.com", "es.ys7.com", "download2.ys7.com",
    "ezviz-fastdfs-gateway.oss-cn-hangzhou.aliyuncs.com", "img.shields.io",
    "wework.qpic.cn", "camo.githubusercontent.com", "github.com",
    "raw.githubusercontent.com",
}
SENSITIVE_QUERY = {"accesstoken", "access_token", "token", "appsecret", "appkey", "secret", "password", "authorization", "signature", "ossaccesskeyid"}
MAX_BYTES = 50 * 1024 * 1024
_LOCAL = threading.local()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def normalized_url(url):
    return url.split("#", 1)[0] if not url.startswith("data:") else url


def extension(url):
    return Path(unquote(urlsplit(url).path)).suffix.lower()


def initial_status(url):
    if url.lower().replace(" ", "").rstrip(";") in {"javascript:void(0)", "javascript:;", "about:blank"}:
        return "excluded_placeholder"
    suffix = extension(url)
    if suffix in MEDIA_EXTENSIONS:
        return "excluded_non_document_media"
    if suffix in BINARY_EXTENSIONS:
        return "excluded_sdk_binary"
    return None


def check_public_addresses(addresses):
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("non_public_address")


def fetch_url(url, redirect_from=None):
    """只接受已观测的主机或同族 CDN 重定向，并拒绝 URL 凭据和业务 API。"""
    url = normalized_url(url)
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported_scheme")
    if parsed.username or parsed.password:
        raise ValueError("url_credentials")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("nonstandard_port")
    decoded = unquote(parsed.path).lower()
    for _ in range(3):
        decoded = unquote(decoded)
    if "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/")):
        raise ValueError("ambiguous_dot_segment")
    if any(part in decoded.split("/") for part in ["api", "openwebapi", "console"]):
        raise ValueError("business_api_path")
    query_names = {key.lower() for key, _ in parse_qsl(parsed.query)}
    signed_static = (host == "ezviz-fastdfs-gateway.oss-cn-hangzhou.aliyuncs.com"
                     and Path(decoded).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}
                     and not (query_names & (SENSITIVE_QUERY - {"signature", "ossaccesskeyid"})))
    if query_names & SENSITIVE_QUERY and not signed_static:
        raise ValueError("sensitive_query")
    if host not in ALLOWED_HOSTS:
        previous = (urlsplit(redirect_from).hostname or "").lower() if redirect_from else ""
        same_family = any(previous.endswith("." + suffix) and host.endswith("." + suffix)
                          for suffix in ["ys7.com", "eziot.com", "qpic.cn", "githubusercontent.com"])
        if not same_family:
            raise ValueError("unapproved_host")
    if host == "github.com":
        match = re.fullmatch(r"/Ezviz-OpenBiz/([^/]+)/blob/([^/]+)/(.+)", parsed.path)
        if not match:
            if re.fullmatch(r"/Ezviz-OpenBiz/[^/]+/workflows/[^/]+/badge\.svg", parsed.path):
                return urlunsplit(("https", host, parsed.path, parsed.query, ""))
            raise ValueError("not_official_github_file")
        repository, ref, path = match.groups()
        return f"https://raw.githubusercontent.com/Ezviz-OpenBiz/{repository}/{ref}/{path}"
    if host == "raw.githubusercontent.com" and not parsed.path.startswith("/Ezviz-OpenBiz/"):
        raise ValueError("not_official_github_file")
    return urlunsplit(("https", host, parsed.path, parsed.query, ""))


def check_dns(url):
    host = urlsplit(url).hostname
    addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    check_public_addresses(addresses)
    return sorted(addresses)


def camo_original_url(url):
    parsed = urlsplit(url)
    if parsed.hostname != "camo.githubusercontent.com":
        return None
    encoded = parsed.path.rsplit("/", 1)[-1]
    try:
        if len(encoded) > 8192:
            return None
        original = bytes.fromhex(encoded).decode("utf-8")
        if extension(original) not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}:
            return None
        return fetch_url(original)
    except (ValueError, UnicodeDecodeError):
        return None


def decode_data_uri(uri):
    head, separator, payload = uri.partition(",")
    if not separator or not head.startswith("data:"):
        raise ValueError("invalid_data_uri")
    media = head[5:].split(";", 1)[0].lower()
    if not (media.startswith("image/") or media in {"application/pdf", "text/plain", "text/markdown"}):
        raise ValueError("unsupported_data_mime")
    if len(payload) > MAX_BYTES * 4 // 3 + 1024:
        raise ValueError("size_limit")
    try:
        data = base64.b64decode(payload, validate=True) if ";base64" in head.lower() else unquote_to_bytes(payload)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid_data_encoding") from exc
    if len(data) > MAX_BYTES:
        raise ValueError("size_limit")
    return media, data


def validate_content(data, content_type, suffix, category):
    """返回 (是否为预期文档, 检出的格式/失败原因)，不运行或渲染内容。"""
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    probe = data[:4096].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if not data:
        return False, "empty_body"
    if mime in {"text/html", "application/xhtml+xml", "application/javascript", "text/javascript"} or re.match(br"(?:<!doctype\s+html|<html\b|<head\b|<script\b)", probe):
        return False, "html_or_javascript_instead_of_document"
    if category == "image":
        detected = None
        for signature, kind in [(b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"),
                                (b"GIF87a", "gif"), (b"GIF89a", "gif"), (b"BM", "bmp"),
                                (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"), (b"\x00\x00\x01\x00", "ico")]:
            if data.startswith(signature):
                detected = kind
                break
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            detected = "webp"
        if b"<!entity" not in probe and b"<!doctype" not in probe and (b"<svg" in probe):
            try:
                if ET.fromstring(data).tag.rsplit("}", 1)[-1] == "svg":
                    detected = "svg"
            except ET.ParseError:
                pass
        aliases = {"png": {"image/png", "image/x-png"}, "jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
                   "gif": {"image/gif"}, "webp": {"image/webp"}, "bmp": {"image/bmp", "image/x-ms-bmp"},
                   "tiff": {"image/tiff"}, "ico": {"image/x-icon", "image/vnd.microsoft.icon"}, "svg": {"image/svg+xml"}}
        generic = {"", "application/octet-stream", "binary/octet-stream", "text/plain", "application/xml", "text/xml"}
        if detected and (mime in generic or mime in aliases[detected]) and complete_image(data, detected):
            return True, detected
        return False, "invalid_image_magic_or_mime"
    if suffix == ".pdf":
        marker = re.search(br"startxref\s+(\d+)\s+%%EOF\s*$", data[-4096:])
        offset = int(marker[1]) if marker else -1
        structure_ok = 0 < offset < len(data) and (data[offset:offset + 4] == b"xref" or re.match(br"\d+\s+\d+\s+obj\b", data[offset:offset + 100]))
        return (True, "pdf") if data.startswith(b"%PDF-") and structure_ok and mime in {"", "application/pdf", "application/octet-stream", "binary/octet-stream"} else (False, "invalid_pdf_structure_or_mime")
    if suffix in {".docx", ".xlsx"}:
        expected_mime = "application/vnd.openxmlformats-officedocument." + ("wordprocessingml.document" if suffix == ".docx" else "spreadsheetml.sheet")
        if mime not in {"", expected_mime, "application/zip", "application/octet-stream", "binary/octet-stream"}:
            return False, "unexpected_office_mime"
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
            expected = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
            return (True, suffix[1:]) if {expected, "[Content_Types].xml"} <= names else (False, "wrong_office_container")
        except zipfile.BadZipFile:
            return False, "invalid_office_container"
    if suffix in {".doc", ".xls"}:
        expected_mime = "application/msword" if suffix == ".doc" else "application/vnd.ms-excel"
        shift = int.from_bytes(data[30:32], "little") if len(data) >= 32 else 0
        structure_ok = data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") and data[28:30] == b"\xfe\xff" and shift in {9, 12} and len(data) >= 2 * (1 << shift) and len(data) % (1 << shift) == 0
        return (True, "ole_office") if structure_ok and mime in {"", expected_mime, "application/octet-stream", "binary/octet-stream", "application/x-ole-storage"} else (False, "invalid_ole_structure_or_mime")
    if suffix in {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}:
        if b"\x00" in data:
            return False, "binary_instead_of_text"
        try:
            text = data.decode("utf-8-sig")
            if suffix == ".json":
                json.loads(text)
        except (UnicodeDecodeError, ValueError):
            return False, "invalid_text_encoding_or_json"
        if mime and not (mime.startswith("text/") or mime in {"application/json", "application/yaml", "application/x-yaml", "application/octet-stream", "binary/octet-stream"}):
            return False, "unexpected_document_mime"
        return True, suffix[1:]
    return False, "unsupported_document_format"


def complete_image(data, kind):
    """校验容器边界，PNG同时校验每个chunk的CRC；不解压像素或执行SVG。"""
    if kind == "png":
        position, have_header, have_data = 8, False, False
        while position + 12 <= len(data):
            length = int.from_bytes(data[position:position + 4], "big")
            tag = data[position + 4:position + 8]
            end = position + 12 + length
            if end > len(data):
                return False
            chunk = data[position + 8:position + 8 + length]
            if int.from_bytes(data[end - 4:end], "big") != zlib.crc32(tag + chunk) & 0xFFFFFFFF:
                return False
            if not have_header:
                if tag != b"IHDR" or length != 13 or not int.from_bytes(chunk[:4], "big") or not int.from_bytes(chunk[4:8], "big"):
                    return False
                have_header = True
            have_data = have_data or tag == b"IDAT" and length > 0
            if tag == b"IEND":
                return length == 0 and have_data and end == len(data)
            position = end
        return False
    if kind == "jpeg":
        position, have_frame = 2, False
        while position + 4 <= len(data):
            if data[position] != 0xFF:
                return False
            while position + 1 < len(data) and data[position + 1] == 0xFF:
                position += 1
            marker = data[position + 1]
            if marker in {0x01, *range(0xD0, 0xD8)}:
                position += 2
                continue
            length = int.from_bytes(data[position + 2:position + 4], "big")
            end = position + 2 + length
            if length < 2 or end > len(data):
                return False
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                have_frame = length >= 8 and int.from_bytes(data[position + 5:position + 7], "big") > 0 and int.from_bytes(data[position + 7:position + 9], "big") > 0
            if marker == 0xDA:
                return have_frame and data.rfind(b"\xff\xd9") >= end
            position = end
        return False
    if kind == "gif":
        return len(data) >= 14 and data.endswith(b";") and b"\x2c" in data[13:]
    if kind == "webp":
        return len(data) >= 20 and int.from_bytes(data[4:8], "little") + 8 == len(data)
    if kind == "bmp":
        return len(data) >= 26 and int.from_bytes(data[2:6], "little") == len(data)
    if kind == "tiff":
        order = "little" if data[:2] == b"II" else "big"
        offset = int.from_bytes(data[4:8], order)
        return 8 <= offset < len(data) - 2
    if kind == "ico":
        count = int.from_bytes(data[4:6], "little")
        return count > 0 and 6 + count * 16 <= len(data) and all(int.from_bytes(data[6 + i * 16 + 8:6 + i * 16 + 12], "little") + int.from_bytes(data[6 + i * 16 + 12:6 + i * 16 + 16], "little") <= len(data) for i in range(count))
    return kind == "svg"


def group_references(references):
    grouped = {}
    for reference in references:
        url = reference["url"]
        if reference["reference_type"] not in {"image", "embedded_resource"} and not (reference["reference_type"] == "link" and extension(url) in DOCUMENT_EXTENSIONS):
            continue
        key = normalized_url(url)
        if key not in grouped:
            grouped[key] = {"asset_id": sha256(key.encode()), "url": key, "original_urls": [], "references": []}
        asset = grouped[key]
        if url not in asset["original_urls"]:
            asset["original_urls"].append(url)
        asset["references"].append(reference)
    return list(grouped.values())


def archived_asset(asset, archived_documents):
    existing = archived_documents.get(asset["url"])
    if existing is None:
        return None
    result = dict(asset)
    result.update(existing)
    result.update(status="already_archived_document", metadata_source="sdk_archive_manifest",
                  registered_at_utc=utc_now(), fetched_at_utc=None, content_type="text/html",
                  content_type_origin="archived_html_document", fetch_url=None, file=None, sha256=None)
    return result


def checkpoint_valid(record, root, output):
    if record.get("status") == "already_archived_document":
        path = root / record.get("archive_file", "")
        return path.is_file() and sha256(path.read_bytes()) == record.get("archive_sha256")
    if record.get("file"):
        path = output / record["file"]
        return path.is_file() and sha256(path.read_bytes()) == record.get("sha256")
    return True


def session():
    if not hasattr(_LOCAL, "session"):
        _LOCAL.session = requests.Session()
        # Avoid requests' implicit ~/.netrc lookup; proxy routing is supplied explicitly.
        _LOCAL.session.trust_env = False
        _LOCAL.session.headers.update({"User-Agent": "EZVIZ-public-document-archive/1.0", "Accept-Encoding": "identity"})
    return _LOCAL.session


def content_assessment(data, mime, suffix, category):
    good, detected = validate_content(data, mime, suffix, category)
    status = "ok" if good else "source_invalid_document"
    warnings = []
    if not good and category == "image" and (mime or "").lower().startswith("image/"):
        valid_container, actual_format = validate_content(data, "", suffix, category)
        if valid_container:
            status, detected = "source_mime_mismatch", actual_format
            warnings.append("HTTP image MIME differs from the validated image container")
    if detected == "jpeg" and data.rfind(b"\xff\xd9") + 2 < len(data):
        warnings.append(f"JPEG contains {len(data) - data.rfind(b'\xff\xd9') - 2} trailing metadata bytes after EOI")
    return {"status": status, "detected_format": detected, "validation_warnings": warnings}


def save_payload(output, asset, data, mime, category):
    assessment = content_assessment(data, mime, extension(asset["url"]), category)
    digest = sha256(data)
    relative = f"blobs/{digest[:2]}/{digest}.bin"
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    asset.update({"bytes": len(data), "sha256": digest, "file": relative, **assessment})
    return asset


def collect_one(asset, output, connector_cache, max_bytes=MAX_BYTES):
    asset = dict(asset)
    asset.update({"started_at_utc": utc_now(), "attempts": [], "http_status": None,
                  "content_type": None, "etag": None, "last_modified": None,
                  "file": None, "sha256": None, "fetch_url": None, "final_url": None,
                  "fetched_at_utc": None})
    category = "image" if any(r["reference_type"] == "image" for r in asset["references"]) else "document"
    asset["category"] = category
    excluded = initial_status(asset["url"])
    if excluded:
        asset["status"] = excluded
        return asset
    if asset["url"].startswith("data:"):
        try:
            mime, payload = decode_data_uri(asset["url"])
        except ValueError as exc:
            asset.update({"status": "size_limit" if str(exc) == "size_limit" else "source_invalid_document", "reason": str(exc)})
            return asset
        asset.update({"metadata_source": "inline_data_uri", "content_type": mime, "fetched_at_utc": utc_now()})
        return save_payload(output, asset, payload, mime, category)
    try:
        target = fetch_url(asset["url"])
    except ValueError as exc:
        asset.update({"status": "excluded_sensitive_query" if str(exc) in {"sensitive_query", "url_credentials"} else "excluded_url_policy", "reason": str(exc)})
        return asset
    asset["fetch_url"] = target
    asset["url_mapping"] = "github_blob_to_official_file" if urlsplit(asset["url"]).hostname == "github.com" else "https_upgrade" if asset["url"].startswith("http:") else "none"
    cached = connector_cache.get(asset["url"])
    if cached:
        payload = (output / cached["file"]).read_bytes()
        if sha256(payload) == cached["sha256"]:
            asset.update(cached)
            asset["metadata_source"] = "github_connector_file"
            return save_payload(output, asset, payload, "text/markdown", category)
    asset["metadata_source"] = "public_http_response"
    partial = output / "partial" / (asset["asset_id"] + ".part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial_meta = partial.with_suffix(".json")
    for attempt in range(1, 4):
        current = target
        request_meta = {"attempt": attempt, "started_at_utc": utc_now(), "redirects": []}
        try:
            for redirect_number in range(6):
                # Repeat safety checks before every redirect destination, without cookies or authorization.
                dns = check_dns(current)
                # A new empty cookie jar prevents remote cookies leaking between documentation hosts.
                client = session()
                client.cookies.clear()
                with client.get(current, proxies=requests.utils.get_environ_proxies(current), stream=True, allow_redirects=False, timeout=(8, 25)) as response:
                    asset.update({"final_url": current, "http_status": response.status_code,
                                  "fetched_at_utc": utc_now(), "content_type": response.headers.get("Content-Type"),
                                  "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified"),
                                  "content_length_header": response.headers.get("Content-Length"), "resolved_public_addresses": dns})
                    if response.status_code in {301, 302, 303, 307, 308}:
                        destination = urljoin(current, response.headers.get("Location", ""))
                        next_url = fetch_url(destination, redirect_from=current)
                        request_meta["redirects"].append({"from": current, "to": next_url, "http_status": response.status_code})
                        current = next_url
                        continue
                    request_meta["http_status"] = response.status_code
                    mime = (response.headers.get("Content-Type") or "").lower()
                    if response.status_code == 403 and urlsplit(current).hostname == "camo.githubusercontent.com":
                        original = camo_original_url(current)
                        if original:
                            asset["original_proxy_response"] = {"url": current, "http_status": 403, "fetched_at_utc": asset["fetched_at_utc"], "content_type": asset["content_type"]}
                            asset.update({"fallback_fetch_url": original, "fallback_source": "public_original_image_url_hex_encoded_in_camo_path", "url_mapping": "github_camo_original_after_proxy_403"})
                            request_meta["fallback"] = {"proxy_http_status": 403, "fetch_url": original}
                            current = original
                            continue
                    if mime.startswith(("video/", "audio/")):
                        asset["status"] = "excluded_non_document_media"
                        break
                    if mime.split(";", 1)[0] in {"application/zip", "application/x-zip-compressed", "application/x-msdownload", "application/x-executable", "application/x-rar-compressed"} and extension(asset["url"]) not in {".docx", ".xlsx"}:
                        asset["status"] = "excluded_sdk_binary"
                        break
                    if response.status_code != 200:
                        asset["status"] = "source_http_error"
                        break
                    total_expected = int(response.headers["Content-Length"]) if response.headers.get("Content-Length", "").isdigit() else None
                    if total_expected is not None and total_expected > max_bytes:
                        asset.update({"status": "size_limit", "reported_bytes": total_expected, "limit_bytes": max_bytes})
                        break
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        # requests streams decoded entity bytes; wire Content-Length is not comparable.
                        total_expected = None
                    partial_meta.write_text(json.dumps({"final_url": current, "etag": asset["etag"], "last_modified": asset["last_modified"]}))
                    downloaded = 0
                    with partial.open("wb") as stream:
                        for chunk in response.iter_content(64 * 1024):
                            if chunk:
                                downloaded += len(chunk)
                                if downloaded > max_bytes:
                                    asset.update({"status": "size_limit", "observed_bytes_at_least": downloaded, "limit_bytes": max_bytes})
                                    break
                                stream.write(chunk)
                    if asset.get("status") == "size_limit":
                        partial.unlink(missing_ok=True)
                        partial_meta.unlink(missing_ok=True)
                        break
                    if total_expected is not None and downloaded != total_expected:
                        raise requests.exceptions.ChunkedEncodingError("incomplete_response")
                    save_payload(output, asset, partial.read_bytes(), asset["content_type"], category)
                    partial.unlink(missing_ok=True)
                    partial_meta.unlink(missing_ok=True)
                    break
            else:
                asset.update({"status": "source_redirect_limit", "reason": "more_than_5_redirects"})
            request_meta["finished_at_utc"] = utc_now()
            asset["attempts"].append(request_meta)
            return asset
        except ValueError as exc:
            request_meta.update({"finished_at_utc": utc_now(), "error_type": "policy_or_format_error", "reason": str(exc)})
            asset["attempts"].append(request_meta)
            asset.update({"status": "excluded_url_policy", "reason": str(exc)})
            return asset
        except (requests.RequestException, socket.gaierror, OSError) as exc:
            partial.unlink(missing_ok=True)
            partial_meta.unlink(missing_ok=True)
            request_meta.update({"finished_at_utc": utc_now(), "error_type": type(exc).__name__})
            asset["attempts"].append(request_meta)
    asset["status"] = "network_error"
    return asset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/official-docs/2026-11-14"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / "assets"
    output.mkdir(parents=True, exist_ok=True)
    reference_paths = [root / "references.jsonl", root / "sdk-reference/domestic/references.jsonl", root / "sdk-reference/overseas/references.jsonl"]
    references = []
    sources = []
    for source in reference_paths:
        raw = source.read_bytes()
        sources.append({"path": str(source.relative_to(root)), "sha256": sha256(raw)})
        for line_number, line in enumerate(raw.decode().splitlines(), 1):
            reference = json.loads(line)
            reference.update({"reference_file": str(source.relative_to(root)), "reference_line": line_number})
            references.append(reference)
    assets = group_references(references)
    state = output / "state"
    state.mkdir(exist_ok=True)
    cache_file = output / "github-connector/index.json"
    connector_cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    archived_documents = {}
    for region in ["domestic", "overseas"]:
        sdk_root = root / "sdk-reference" / region
        for record in json.loads((sdk_root / "manifest.json").read_text())["entries"]:
            if record.get("status") == "ok" and record.get("local_path"):
                path = sdk_root / record["local_path"]
                if path.exists() and sha256(path.read_bytes()) == record.get("sha256"):
                    archived_documents[normalized_url(record["url"])] = {
                        "archive_file": str(path.relative_to(root)), "archive_sha256": record["sha256"],
                        "http_status": record.get("http_status"), "final_url": record.get("final_url", record["url"]),
                        "archive_manifest": str((sdk_root / "manifest.json").relative_to(root))}
    finished = []
    pending = []
    for asset in assets:
        checkpoint = state / (asset["asset_id"] + ".json")
        archived = archived_asset(asset, archived_documents)
        if archived is not None:
            checkpoint.write_text(json.dumps(archived, ensure_ascii=False, indent=2) + "\n")
            finished.append(archived)
            continue
        if checkpoint.exists():
            cached = json.loads(checkpoint.read_text())
            valid = checkpoint_valid(cached, root, output)
            retryable = cached.get("status") in {"network_error", "source_http_error", "source_redirect_limit"}
            if cached.get("status") == "excluded_url_policy":
                try:
                    fetch_url(asset["url"])
                    retryable = True
                except ValueError:
                    pass
            if valid and not (args.retry_failures and retryable):
                cached.update({"references": asset["references"], "original_urls": asset["original_urls"]})
                if cached.get("file") and cached.get("status") in {"ok", "source_invalid_document", "source_mime_mismatch"}:
                    cached.update(content_assessment((output / cached["file"]).read_bytes(), cached.get("content_type"), extension(asset["url"]), cached.get("category", "document")))
                checkpoint.write_text(json.dumps(cached, ensure_ascii=False, indent=2) + "\n")
                finished.append(cached)
                continue
            if args.retry_failures and retryable:
                asset["previous_attempts"] = cached.get("previous_attempts", []) + cached.get("attempts", [])
                asset["previous_status"] = cached.get("status")
        pending.append(asset)
    print(f"selected references={sum(len(a['references']) for a in assets)} unique assets={len(assets)} resumed={len(finished)} pending={len(pending)}", flush=True)
    with ThreadPoolExecutor(max_workers=min(6, max(1, args.workers))) as pool:
        futures = {pool.submit(collect_one, asset, output, connector_cache): asset for asset in pending}
        for future in as_completed(futures):
            result = future.result()
            checkpoint = state / (result["asset_id"] + ".json")
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(checkpoint)
            finished.append(result)
            if len(finished) % 50 == 0:
                print(f"progress {len(finished)}/{len(assets)} {dict(Counter(r['status'] for r in finished))}", flush=True)
    finished.sort(key=lambda r: r["asset_id"])
    with (output / "manifest.jsonl").open("w") as stream:
        for result in finished:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    summary = {"collected_at_utc": utc_now(), "source_indexes": sources,
               "reference_count": sum(len(a["references"]) for a in assets), "unique_asset_count": len(assets),
               "status_counts": dict(Counter(r["status"] for r in finished)),
               "saved_bytes": sum(r.get("bytes", 0) for r in finished),
               "unique_saved_blobs": len({r["sha256"] for r in finished if r.get("sha256")}),
               "unique_saved_blob_bytes": sum((output / file).stat().st_size for file in {r["file"] for r in finished if r.get("file")}),
               "readable_asset_count": sum(r["status"] in {"ok", "source_mime_mismatch"} for r in finished),
               "archived_response_count": sum(bool(r.get("file")) for r in finished),
               "size_limit_bytes": MAX_BYTES,
               "safety": "No HTML/JS/SVG is executed. Blobs use .bin suffix. Only observed hosts and validated same-family redirects are fetched; credentials/business APIs/private IPs are rejected. SDK binaries and non-document media are excluded."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
