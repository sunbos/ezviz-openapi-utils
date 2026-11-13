"""独立离线验收的篡改、范围遗漏与嵌套结构回归。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tools.documents.derive import derive


class DocumentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = []
        for doc_id in ("81", "452", "5287"):
            html = '<h2>说明</h2><table><tr><td>值</td></tr></table><pre>example</pre>'
            source_path = f"pages/domestic/{doc_id}.source.json"
            raw = self.write(source_path, {"html_content": html})
            api_path = f"sources/domestic-{doc_id}.json"
            api = self.write(api_path, {"meta": {"code": 200}, "data": {"doc": {
                "documentId": doc_id, "plateform": "doc_open", "content": html}}})
            self.catalog.append({
                "region": "domestic", "doc_id": doc_id, "title": "示例",
                "source_url": f"https://open.ys7.com/help/{doc_id}", "status": "archived",
                "raw_file": source_path, "raw_file_sha256": self.sha(raw),
                "content_sha256": self.sha(html.encode()),
                "memberships": [{"category_path": ["示例目录", doc_id]}],
                "source_receipt": {"raw_file": api_path, "sha256": self.sha(api),
                                   "bytes": len(api), "status_code": 200},
            })
        self.menus = {"domestic": [{"id": "81", "title": "示例"}], "overseas": []}
        self.finalize()

    @staticmethod
    def sha(value):
        return hashlib.sha256(value).hexdigest()

    def write(self, name, value):
        data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def finalize(self):
        self.write("catalog.json", self.catalog)
        self.write("menus.json", self.menus)
        self.write("menu-memberships.json", [{"region": "domestic", "doc_id": entry["doc_id"]}
                                            for entry in self.catalog])
        receipts = {}
        for region, tree in self.menus.items():
            payload = {"data": tree} if region == "domestic" else {
                "data": {"list": [{"content": json.dumps(tree)}]}}
            name = f"sources/menu-{region}.json"
            raw = self.write(name, payload)
            receipts[region] = {"raw_file": name, "sha256": self.sha(raw), "bytes": len(raw)}
        self.write("acquisition-summary.json", {
            "initial_receipts": receipts, "final_receipts": receipts, "menu_unchanged": True,
            "catalog_entries": len(self.catalog), "by_status": {"archived": len(self.catalog)},
        })
        derive(self.root)

    def module(self):
        path = Path(__file__).resolve().parents[1] / "tools/documents/verify.py"
        self.assertTrue(path.is_file(), "尚未实现独立离线验证器")
        spec = importlib.util.spec_from_file_location("document_verifier", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_valid_fixture_passes_all_offline_evidence_checks(self):
        report = self.module().verify(self.root)
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["documents"], 3)

    def test_api_response_hash_tampering_blocks_verification(self):
        path = self.root / self.catalog[0]["source_receipt"]["raw_file"]
        path.write_bytes(path.read_bytes() + b" ")
        report = self.module().verify(self.root)
        self.assertFalse(report["passed"])
        self.assertIn("receipt_sha256_mismatch", {error["code"] for error in report["errors"]})

    def test_missing_numeric_menu_entry_blocks_verification(self):
        self.menus["domestic"].append({"id": "999", "title": "遗漏的末级文档"})
        self.finalize()
        report = self.module().verify(self.root)
        self.assertFalse(report["passed"])
        self.assertIn("menu_catalog_missing", {error["code"] for error in report["errors"]})

    def test_parser_hash_in_derivation_receipt_is_verified(self):
        summary = json.loads((self.root / "derivation-summary.json").read_text())
        summary["parser"]["sha256"] = "0" * 64
        self.write("derivation-summary.json", summary)
        report = self.module().verify(self.root)
        self.assertFalse(report["passed"])
        self.assertIn("parser_source_sha256_mismatch", {error["code"] for error in report["errors"]})

    def test_nested_table_counts_each_row_and_cell_once(self):
        parser = self.module().IndependentHTMLInventory()
        parser.feed('<table><tr><td>A<table><tr><td>B</td></tr></table></td></tr></table>')
        self.assertEqual(parser.counts["tables"], 2)
        self.assertEqual(parser.counts["table_rows"], 2)
        self.assertEqual(parser.counts["table_cells"], 2)
        self.assertEqual(parser.nested_tables, 1)

    def test_help_reference_boundary_rejects_external_path_and_query(self):
        module = self.module()
        self.assertIsNone(module.help_identity("https://other.example/open.ys7.com/help/81"))
        self.assertIsNone(module.help_identity("https://other.example/?next=/help/81"))
        self.assertIsNone(module.help_identity("https://open.ys7.com/help/81suffix"))
        self.assertEqual(module.help_identity("https://open.ys7.com:443/help/en/81"), ("overseas", "81"))


if __name__ == "__main__":
    unittest.main()
