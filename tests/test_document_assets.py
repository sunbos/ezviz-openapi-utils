import base64
import importlib.util
import io
import unittest
from unittest.mock import patch
import tempfile
import hashlib
import zipfile
from pathlib import Path


class DocumentAssetTests(unittest.TestCase):
    def module(self):
        path = Path(__file__).parents[1] / "tools/documents/collect_assets.py"
        self.assertTrue(path.exists(), "Asset collector is not implemented")
        spec = importlib.util.spec_from_file_location("collect_assets", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_url_boundary_and_https_upgrade(self):
        m = self.module()
        self.assertEqual(m.fetch_url("http://resource.eziot.com/a.png#x"),
                         "https://resource.eziot.com/a.png")
        for url in ["https://127.0.0.1/a.png", "https://192.168.1.1/a.png",
                    "https://resource.eziot.com.evil.test/a.png",
                    "https://user:password@resource.eziot.com/a.png",
                    "https://open.ys7.com/api/lapp/token/get",
                    "https://resource.eziot.com/a.png?accessToken=placeholder"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.fetch_url(url)

    def test_dot_segments_cannot_escape_official_github_namespace(self):
        m = self.module()
        for url in ["https://raw.githubusercontent.com/Ezviz-OpenBiz/../unrelated/repo/main/API.md",
                    "https://github.com/Ezviz-OpenBiz/repo/blob/main/%2e%2e/API.md"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.fetch_url(url)

    def test_github_blob_maps_only_to_official_raw_file(self):
        m = self.module()
        url = "https://github.com/Ezviz-OpenBiz/EZUIKit-MultiScreen/blob/main/API.md#section"
        self.assertEqual(m.fetch_url(url),
                         "https://raw.githubusercontent.com/Ezviz-OpenBiz/EZUIKit-MultiScreen/main/API.md")
        with self.assertRaises(ValueError):
            m.fetch_url("https://github.com/other/repo/blob/main/API.md")

    def test_official_workflow_badge_is_a_public_image(self):
        m = self.module()
        url = "https://github.com/Ezviz-OpenBiz/EZUIKit-JavaScript-npm/workflows/build-demos/badge.svg"
        self.assertEqual(m.fetch_url(url), url)

    def test_camo_original_requires_public_approved_image(self):
        m = self.module()
        original = "https://img.shields.io/npm/v/ezuikit-js.svg"
        proxy = "https://camo.githubusercontent.com/public-hash/" + original.encode().hex()
        self.assertEqual(m.camo_original_url(proxy), original)
        for target in ["http://127.0.0.1/private.png", "https://open.ys7.com/api/device"]:
            self.assertIsNone(m.camo_original_url("https://camo.githubusercontent.com/public-hash/" + target.encode().hex()))

    def test_public_signed_static_file_is_allowed_without_business_api(self):
        m = self.module()
        url = "https://ezviz-fastdfs-gateway.oss-cn-hangzhou.aliyuncs.com/files/example.png?OSSAccessKeyId=public-id&Signature=public-signature&Expires=123"
        self.assertEqual(m.fetch_url(url), url)
        with self.assertRaises(ValueError):
            m.fetch_url("https://open.ys7.com/api/device?Signature=public-signature")

    def test_private_dns_result_is_rejected(self):
        m = self.module()
        with self.assertRaises(ValueError):
            m.check_public_addresses(["127.0.0.1", "1.1.1.1"])
        m.check_public_addresses(["1.1.1.1", "2606:4700:4700::1111"])

    def test_html_shell_is_not_markdown(self):
        m = self.module()
        body = b'<!doctype html><html><div id="root"></div><script src="main.js"></script></html>'
        self.assertFalse(m.validate_content(body, "text/html", ".md", "document")[0])
        self.assertTrue(m.validate_content(b"# API\n\nDescription\n", "text/plain", ".md", "document")[0])

    def test_magic_and_mime_must_agree(self):
        m = self.module()
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        self.assertTrue(m.validate_content(png, "image/png", ".png", "image")[0])
        self.assertFalse(m.validate_content(png, "text/html", ".png", "image")[0])
        self.assertFalse(m.validate_content(png, "image/jpeg", ".png", "image")[0])
        self.assertFalse(m.validate_content(b"not a PDF", "application/pdf", ".pdf", "document")[0])
        pdf = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        pdf += b"xref\n0 2\n0000000000 65535 f \n0000000009 00000 n \ntrailer\n<< /Size 2 /Root 1 0 R >>\nstartxref\n" + str(len(pdf)).encode() + b"\n%%EOF\n"
        self.assertTrue(m.validate_content(pdf, "application/pdf", ".pdf", "document")[0])

    def test_truncated_magic_is_not_a_complete_file(self):
        m = self.module()
        for body, mime, suffix, category in [(b"\x89PNG\r\n\x1a\n", "image/png", ".png", "image"),
                                            (b"%PDF-1.7", "application/pdf", ".pdf", "document"),
                                            (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "image/png", ".doc", "document")]:
            with self.subTest(suffix=suffix):
                self.assertFalse(m.validate_content(body, mime, suffix, category)[0])

    def test_valid_image_with_wrong_mime_is_recorded_as_source_metadata_mismatch(self):
        m = self.module()
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        assessment = m.content_assessment(png, "image/jpeg", ".jpg", "image")
        self.assertEqual(assessment["status"], "source_mime_mismatch")
        self.assertEqual(assessment["detected_format"], "png")

    def test_jpeg_container_allows_trailing_metadata_after_eoi(self):
        m = self.module()
        stream = (b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
                  b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x00\xff\xd9")
        self.assertTrue(m.complete_image(stream + b"source trailing metadata", "jpeg"))
        self.assertFalse(m.complete_image(stream[:-2], "jpeg"))

    def test_docx_requires_word_container(self):
        m = self.module()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml", "<document/>")
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.assertTrue(m.validate_content(out.getvalue(), mime, ".docx", "document")[0])
        self.assertFalse(m.validate_content(out.getvalue(), mime, ".xlsx", "document")[0])
        self.assertFalse(m.validate_content(out.getvalue(), "image/png", ".docx", "document")[0])

    def test_data_uri_decodes_bytes_and_rejects_active_html(self):
        m = self.module()
        payload = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
        uri = "data:image/png;base64," + base64.b64encode(payload).decode()
        self.assertEqual(m.decode_data_uri(uri), ("image/png", payload))
        for uri in ["data:text/html,<script>alert(1)</script>", "data:image/png;base64,***"]:
            with self.assertRaises(ValueError):
                m.decode_data_uri(uri)

    def test_dedup_preserves_all_reference_relationships(self):
        m = self.module()
        refs = [{"url": "https://open.ys7.com/help/a.md#one", "reference_type": "link", "doc_id": "1"},
                {"url": "https://open.ys7.com/help/a.md#two", "reference_type": "link", "doc_id": "2"}]
        assets = m.group_references(refs)
        self.assertEqual(len(assets), 1)
        self.assertEqual(len(assets[0]["references"]), 2)
        self.assertEqual(assets[0]["references"][0]["url"], refs[0]["url"])

    def test_media_and_placeholders_are_registered_without_fetch(self):
        m = self.module()
        self.assertEqual(m.initial_status("https://resource.eziot.com/a.mp4"), "excluded_non_document_media")
        self.assertEqual(m.initial_status("javascript:void(0)"), "excluded_placeholder")
        self.assertEqual(m.initial_status("https://download2.ys7.com/sdk.zip"), "excluded_sdk_binary")

    def test_existing_sdk_frame_is_linked_to_archive(self):
        m = self.module()
        url = "https://open.ys7.com/doc/en/android/overview-summary.html"
        asset = {"url": url, "asset_id": "test", "references": []}
        archived = {url: {"archive_file": "sdk-reference/overseas/android/overview-summary.html", "sha256": "abc"}}
        result = m.archived_asset(asset, archived)
        self.assertEqual(result["status"], "already_archived_document")
        self.assertEqual(result["archive_file"], archived[url]["archive_file"])

    def test_large_declared_document_is_not_downloaded(self):
        m = self.module()

        class Response:
            status_code = 200
            headers = {"Content-Type": "application/pdf", "Content-Length": "999999999"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_content(self, *_):
                raise AssertionError("oversized response body must not be read")

        class Client:
            cookies = {}

            def get(self, *_args, **_kwargs):
                return Response()

        asset = {"url": "https://resource.eziot.com/manual.pdf", "asset_id": "sample", "references": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(m, "session", return_value=Client()), patch.object(m, "check_dns", return_value=["1.1.1.1"]):
            result = m.collect_one(asset, Path(directory), {})
        self.assertEqual(result["status"], "size_limit")
        self.assertIsNone(result["file"])

    def test_archived_checkpoint_requires_existing_matching_file(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = {"status": "already_archived_document", "archive_file": "sdk.html", "archive_sha256": hashlib.sha256(b"original").hexdigest()}
            self.assertFalse(m.checkpoint_valid(checkpoint, root, root / "assets"))
            (root / "sdk.html").write_bytes(b"changed")
            self.assertFalse(m.checkpoint_valid(checkpoint, root, root / "assets"))
            (root / "sdk.html").write_bytes(b"original")
            self.assertTrue(m.checkpoint_valid(checkpoint, root, root / "assets"))

    def test_retry_discards_partial_representation(self):
        m = self.module()
        payload = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")

        class Response:
            status_code = 200
            headers = {"Content-Type": "image/png", "ETag": '"same"', "Content-Encoding": "gzip"}

            def __init__(self, fail):
                self.fail = fail

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_content(self, *_):
                if self.fail:
                    yield payload[:12]
                    raise m.requests.exceptions.ChunkedEncodingError("interrupted")
                yield payload

        class Client:
            cookies = {}
            calls = 0

            def get(inner, *_args, **kwargs):
                self.assertNotIn("Range", kwargs.get("headers", {}))
                inner.calls += 1
                return Response(inner.calls == 1)

        asset = {"url": "https://resource.eziot.com/image.png", "asset_id": "sample", "references": [{"reference_type": "image"}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(m, "session", return_value=Client()), patch.object(m, "check_dns", return_value=["1.1.1.1"]):
            result = m.collect_one(asset, Path(directory), {})
            self.assertEqual(result["status"], "ok")
            self.assertEqual((Path(directory) / result["file"]).read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
