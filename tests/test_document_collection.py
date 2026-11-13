import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / "tools/documents/collect.py"


class CollectionIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MODULE.exists():
            spec = importlib.util.spec_from_file_location("doc_collect", MODULE)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        else:
            cls.module = None

    def require_module(self):
        self.assertIsNotNone(self.module, "Document collector is not implemented")
        return self.module

    def test_parent_documents_and_duplicate_memberships_are_preserved(self):
        m = self.require_module()
        tree = [{"title": "API", "id": "10", "children": [
            {"title": "Token", "id": "1000007"}]},
            {"title": "Guide", "id": "group-uuid", "children": [
                {"title": "Same token", "id": "1000007"}]}]
        rows = m.menu_memberships(tree, "overseas")
        self.assertEqual([r["doc_id"] for r in rows], ["10", "1000007", "1000007"])
        self.assertEqual(rows[2]["category_path"], ["Guide", "Same token"])

    def test_language_is_checked_locally_not_assumed_from_query(self):
        m = self.require_module()
        records = [{"docId": "81", "platformType": "doc_open", "htmlContent": "CN"},
                   {"docId": "81", "platformType": "doc_open_en", "htmlContent": "EN"}]
        self.assertEqual(m.select_record(records, "overseas", "81")["htmlContent"], "EN")

    def test_ambiguous_record_identity_is_rejected(self):
        m = self.require_module()
        records = [{"docId": "81", "platformType": "doc_open", "htmlContent": "old"},
                   {"docId": "81", "platformType": "doc_open", "htmlContent": "new"}]
        with self.assertRaises(ValueError):
            m.select_record(records, "domestic", "81")

    def test_success_without_document_data_is_not_a_listing(self):
        m = self.require_module()
        with self.assertRaises(ValueError):
            m.listing_data({"meta": {"code": 200}})

    def test_listing_declared_total_is_kept_separate_from_page_length(self):
        m = self.require_module()
        total, rows = m.listing_data({"meta": {"code": "200"}, "data": {
            "total": 2, "list": [{"docId": "81", "htmlContent": "one"}]}})
        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 1)

    def test_cached_response_is_rejected_after_tampering(self):
        m = self.require_module()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "response.json"
            body = json.dumps({"meta": {"code": 200}}).encode()
            m.atomic_write(p, body)
            digest = m.sha256(body)
            self.assertEqual(m.verified_bytes(p, digest), body)
            p.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                m.verified_bytes(p, digest)

    def test_help_references_exclude_other_platforms_and_keep_explicit_regions(self):
        m = self.require_module()
        html = '''<a href="https://help.eziot.com/help/628">other platform</a>
        <a href="/help/81">local</a><p>open.ys7.com/help/en/476</p>
        <a href="https://wafopen.ys7.com/help/5432">official mirror</a>'''
        self.assertEqual(m.help_references(html), {(False, "81"), (True, "476"), (False, "5432")})

    def test_help_references_validate_whole_url_and_whole_document_id(self):
        m = self.require_module()
        html = '''<a href="https://evil.example/open.ys7.com/help/123">external</a>
        <a href="https://evil.example/?next=/help/123">external</a>
        <a href="https://open.ys7.com/help/123suffix">not an id</a>
        <a href="https://open.ys7.com:443/help/81">real</a>'''
        self.assertEqual(m.help_references(html), {(False, "81")})

    def test_pagination_uses_one_based_row_starts(self):
        m = self.require_module()
        self.assertEqual(m.page_offsets(268, 100), [1, 101, 201])

    def test_overlapping_bulk_pages_cannot_count_as_complete(self):
        m = self.require_module()
        with self.assertRaises(ValueError):
            m.validate_bulk_records([{"id": 1}, {"id": 1}], 2)

    def test_relative_document_links_resolve_from_the_actual_page(self):
        m = self.require_module()
        self.assertEqual(m.help_references('<a href="69">older page</a>',
            'https://open.ys7.com/help/777'), {(False, '69')})
        self.assertEqual(m.help_references('<a href="./69">other</a><a href="../81">CN</a>',
            'https://open.ys7.com/help/en/477'), {(True, '69'), (False, '81')})


if __name__ == "__main__":
    unittest.main()
