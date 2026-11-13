import importlib.util
from pathlib import Path
import unittest


class CurrentDocumentTests(unittest.TestCase):
    def module(self):
        path = Path(__file__).parents[1] / "tools/documents/collect_current.py"
        self.assertTrue(path.exists(), "Current-page collector not implemented")
        spec = importlib.util.spec_from_file_location("collect_current", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_missing_data_is_source_gap_not_archived(self):
        m = self.module()
        self.assertIsNone(m.current_doc({"meta": {"code": "200"}, "data": {"doc": None}}, "81"))

    def test_document_identity_mismatch_is_rejected(self):
        m = self.module()
        with self.assertRaises(ValueError):
            m.current_doc({"data": {"doc": {"documentId": "82", "content": "wrong"}}}, "81")

    def test_visible_dates_and_body_are_preserved(self):
        m = self.module()
        doc = {"documentId": "81", "title": "token", "content": "<pre> raw </pre>",
               "modifyTime": "2025.02.21", "updateTime": "2026-06-01", "plateform": "doc_open"}
        self.assertEqual(m.current_doc({"data": {"doc": doc}}, "81"), doc)


if __name__ == "__main__":
    unittest.main()
