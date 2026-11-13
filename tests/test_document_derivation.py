"""离线派生的证据完整性、分类与缺项回归；不请求网络。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class DocumentDerivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def module(self):
        path = Path(__file__).resolve().parents[1] / "tools/documents/derive.py"
        self.assertTrue(path.is_file(), "尚未实现离线派生模块")
        spec = importlib.util.spec_from_file_location("tools.documents.derive", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def source(self, doc_id="81", memberships=None):
        html = (
            '<h2>请求</h2><table><tr><th>字段</th><td>token</td></tr></table>'
            '<pre><code>example\n</code></pre><a href="/help/82">下一页</a>'
            '<img src="/example.png"><iframe src="/manual.pdf"></iframe>'
        )
        relative = f"pages/domestic/{doc_id}.source.json"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps({"html_content": html}, ensure_ascii=False).encode()
        path.write_bytes(raw)
        return {
            "region": "domestic", "doc_id": doc_id, "title": "示例",
            "source_url": f"https://open.ys7.com/help/{doc_id}", "status": "archived",
            "raw_file": relative,
            "raw_file_sha256": hashlib.sha256(raw).hexdigest(),
            "content_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "memberships": memberships or [{"category_path": ["服务端 API", "认证"]}],
        }

    def catalog(self, entries):
        (self.root / "catalog.json").write_text(json.dumps(entries, ensure_ascii=False))

    def rows(self, name):
        return [json.loads(line) for line in (self.root / name).read_text().splitlines()]

    def test_tampered_raw_file_is_rejected_before_writing_any_derived_output(self):
        entry = self.source()
        self.catalog([entry])
        (self.root / entry["raw_file"]).write_text('{"html_content":"modified"}')
        with self.assertRaisesRegex(ValueError, "raw_file_sha256"):
            self.module().derive(self.root)
        self.assertFalse((self.root / "documents.jsonl").exists())
        self.assertFalse((self.root / "derived").exists())

    def test_content_hash_is_checked_independently_of_raw_file_hash(self):
        entry = self.source()
        entry["content_sha256"] = "0" * 64
        self.catalog([entry])
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            self.module().derive(self.root)
        self.assertFalse((self.root / "derivation-summary.json").exists())

    def test_missing_source_stays_in_index_with_unknown_counts(self):
        missing = {
            "region": "overseas", "doc_id": "404", "title": "上游缺项",
            "source_url": "https://open.ys7.com/help/en/404", "status": "source_missing",
            "memberships": [{"category_path": ["正文引用补充"]}],
        }
        self.catalog([self.source(), missing])
        summary = self.module().derive(self.root)
        indexed = self.rows("documents.jsonl")
        self.assertEqual(len(indexed), 2)
        self.assertEqual(indexed[1]["status"], "source_missing")
        self.assertEqual(indexed[1]["derivation_status"], "not_archived")
        self.assertIsNone(indexed[1]["counts"])
        self.assertEqual(summary["by_status"], {"archived": 1, "source_missing": 1})
        self.assertEqual(summary["derived_documents"], 1)
        self.assertEqual(summary["by_region"]["overseas"]["documents"], 1)

    def test_all_category_relations_remain_but_body_is_derived_once(self):
        memberships = [
            {"category_path": ["服务端 API", "认证"]},
            {"category_path": ["快速入门", "认证"]},
            {"category_path": ["服务端 API", "认证"]},
            {"category_path": ["正文引用补充"]},
        ]
        self.catalog([self.source(memberships=memberships)])
        module = self.module()
        with patch.object(module, "extract_document", wraps=module.extract_document) as extract:
            summary = module.derive(self.root)
        self.assertEqual(extract.call_count, 1)
        document = self.rows("documents.jsonl")[0]
        self.assertEqual(document["memberships"], memberships)
        self.assertEqual(summary["documents"], 1)
        self.assertEqual(summary["membership_relations"], 4)
        categories = {item["top_category"]: item for item in summary["by_top_category"]}
        self.assertEqual(categories["服务端 API"]["documents"], 1)
        self.assertEqual(categories["服务端 API"]["membership_relations"], 2)
        self.assertEqual(categories["正文引用补充"]["category_kind"], "body_reference_supplement")

    def test_indexes_preserve_source_locations_and_derived_hashes(self):
        entry = self.source()
        self.catalog([entry])
        self.module().derive(self.root)
        document = self.rows("documents.jsonl")[0]
        for path_field, hash_field in (
            ("structure_file", "structure_sha256"), ("plain_text_file", "plain_text_sha256")
        ):
            data = (self.root / document[path_field]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), document[hash_field])
        for name in ("tables.jsonl", "code-blocks.jsonl", "references.jsonl"):
            rows = self.rows(name)
            self.assertGreater(len(rows), 0)
            for row in rows:
                self.assertEqual(row["region"], "domestic")
                self.assertEqual(row["doc_id"], "81")
                self.assertEqual(row["source_url"], entry["source_url"])
                self.assertIsInstance(row["source_element_index"], int)
        self.assertEqual(
            {row["reference_type"] for row in self.rows("references.jsonl")},
            {"link", "image", "embedded_resource"},
        )


if __name__ == "__main__":
    unittest.main()
