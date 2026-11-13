"""文档派生结构的离线回归；不证明官方业务协议或真实 API 正确。"""

from pathlib import Path
import importlib.util
import unittest


class DocumentParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module_path = (
            Path(__file__).resolve().parents[1]
            / "tools"
            / "documents"
            / "parse_html.py"
        )

    def extract(self, html, base_url="https://open.ys7.com/help/en/476"):
        self.assertTrue(self.module_path.is_file(), "尚未实现文档结构提取模块")
        spec = importlib.util.spec_from_file_location("document_parser", self.module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.extract_document(html, base_url)

    def test_empty_document_has_explicit_empty_collections_and_counts(self):
        result = self.extract("")
        self.assertEqual(result.get("text"), "")
        for field in (
            "headings", "tables", "code_blocks", "links", "images", "embedded_resources"
        ):
            self.assertEqual(result.get(field), [])
            self.assertEqual(result.get("counts", {}).get(field), 0)
        self.assertEqual(result.get("counts", {}).get("table_rows"), 0)
        self.assertEqual(result.get("counts", {}).get("table_cells"), 0)

    def test_heading_levels_entities_and_executable_content(self):
        result = self.extract(
            '<h1>接口 &amp; 约束</h1><h3>字段 <em>说明</em></h3>'
            '<p>必须 &lt; 10，保留 &#20013; 文。</p>'
            '<script>throw new Error("SCRIPT_SENTINEL")</script>'
            '<style>.STYLE_SENTINEL { color: red; }</style><!-- COMMENT_SENTINEL -->'
        )
        self.assertEqual(
            [(h["level"], h["text"]) for h in result.get("headings", [])],
            [(1, "接口 & 约束"), (3, "字段 说明")],
        )
        self.assertIn("必须 < 10，保留 中 文。", result.get("text", ""))
        for excluded in ("SCRIPT_SENTINEL", "STYLE_SENTINEL", "COMMENT_SENTINEL"):
            self.assertNotIn(excluded, result.get("text", ""))

    def test_table_sections_cell_kinds_and_spans_are_preserved(self):
        result = self.extract(
            '<h2>请求参数</h2><table><thead><tr><th rowspan="2">名称</th>'
            '<th colspan="2">约束 &amp; 类型</th></tr></thead><tbody>'
            '<tr><td>accessToken</td><td><strong>必填</strong></td><td>string</td></tr>'
            '</tbody><tfoot><tr><td colspan="3">不得为空</td></tr></tfoot></table>'
        )
        self.assertEqual(len(result.get("tables", [])), 1)
        table = result["tables"][0]
        self.assertEqual(table["heading"], "请求参数")
        self.assertEqual(table["rows"], [
            [
                {"kind": "th", "text": "名称", "rowspan": 2, "colspan": 1},
                {"kind": "th", "text": "约束 & 类型", "rowspan": 1, "colspan": 2},
            ],
            [
                {"kind": "td", "text": "accessToken", "rowspan": 1, "colspan": 1},
                {"kind": "td", "text": "必填", "rowspan": 1, "colspan": 1},
                {"kind": "td", "text": "string", "rowspan": 1, "colspan": 1},
            ],
            [{"kind": "td", "text": "不得为空", "rowspan": 1, "colspan": 3}],
        ])
        self.assertEqual(result["counts"]["table_rows"], 3)
        self.assertEqual(result["counts"]["table_cells"], 6)

    def test_nested_table_rows_do_not_leak_into_parent_table(self):
        result = self.extract(
            '<table><tr><td>外层<table><tbody><tr><td>内层</td></tr></tbody>'
            '</table></td></tr></table>'
        )
        self.assertEqual(len(result.get("tables", [])), 2)
        self.assertEqual([len(t["rows"]) for t in result["tables"]], [1, 1])
        self.assertEqual([len(t["rows"][0]) for t in result["tables"]], [1, 1])
        self.assertEqual(result["counts"]["table_cells"], 2)

    def test_rowspan_zero_and_nonstandard_span_values_are_not_silently_rewritten(self):
        result = self.extract(
            '<table><tr><td rowspan="0">A</td><td colspan="invalid">B</td>'
            '</tr></table>'
        )
        self.assertEqual(len(result.get("tables", [])), 1)
        cells = result["tables"][0]["rows"][0]
        self.assertEqual(cells[0]["rowspan"], 0)
        self.assertEqual(cells[1]["colspan"], "invalid")

    def test_pre_code_is_counted_once_and_code_whitespace_is_preserved(self):
        result = self.extract(
            '<pre><code class="language-json">{\n  "code": "200",\n  "value": "&lt;x&gt;"\n}\n</code></pre>'
            '<pre class="lang-python">  value = 1\n</pre><p><code>accessToken</code></p>'
        )
        blocks = result.get("code_blocks", [])
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["language"], "json")
        self.assertEqual(blocks[0]["text"], '{\n  "code": "200",\n  "value": "<x>"\n}\n')
        self.assertEqual(blocks[1]["language"], "python")
        self.assertEqual(blocks[1]["text"], "  value = 1\n")
        self.assertEqual(blocks[2]["text"], "accessToken")
        self.assertEqual(result["counts"]["code_blocks"], 3)

    def test_relative_links_fragments_and_duplicate_references_are_retained(self):
        result = self.extract(
            '<a href="../81?a=1&amp;b=2">认证</a><a href="#response">响应</a>'
            '<a href="//static.example.org/manual.pdf">PDF</a>'
            '<a href="../81?a=1&amp;b=2">再次引用</a><a>无 href</a>'
        )
        self.assertEqual(
            [(a["url"], a["text"]) for a in result.get("links", [])],
            [
                ("https://open.ys7.com/help/81?a=1&b=2", "认证"),
                ("https://open.ys7.com/help/en/476#response", "响应"),
                ("https://static.example.org/manual.pdf", "PDF"),
                ("https://open.ys7.com/help/81?a=1&b=2", "再次引用"),
            ],
        )

    def test_images_keep_src_lazy_sources_and_alt(self):
        result = self.extract(
            '<img src="/assets/diagram.png" alt="A &amp; B">'
            '<img data-src="../media/flow.svg"><img src="//cdn.example.org/b.png">'
        )
        self.assertEqual(
            [(i["url"], i["alt"]) for i in result.get("images", [])],
            [
                ("https://open.ys7.com/assets/diagram.png", "A & B"),
                ("https://open.ys7.com/help/media/flow.svg", ""),
                ("https://cdn.example.org/b.png", ""),
            ],
        )

    def test_picture_srcset_and_svg_references_are_not_lost(self):
        result = self.extract(
            '<picture><source srcset="/small.png 1x, /large.png 2x">'
            '<img src="fallback.png" srcset="data:image/png;base64,AAAA 1x, /retina.png 2x">'
            '</picture><svg><image xlink:href="/drawing.svg" /></svg>'
        )
        self.assertEqual(
            [i["url"] for i in result.get("images", [])],
            [
                "https://open.ys7.com/small.png",
                "https://open.ys7.com/large.png",
                "https://open.ys7.com/help/en/fallback.png",
                "data:image/png;base64,AAAA",
                "https://open.ys7.com/retina.png",
                "https://open.ys7.com/drawing.svg",
            ],
        )

    def test_code_br_is_a_line_break_without_executing_markup(self):
        result = self.extract('<pre><code>first<br>  second&lt;br&gt;</code></pre>')
        self.assertEqual(len(result.get("code_blocks", [])), 1)
        self.assertEqual(result["code_blocks"][0]["text"], "first\n  second<br>")

    def test_mixed_br_markup_does_not_drop_recovered_child_elements(self):
        # 上游混用 br 与 br/，且 td 不在 tr 中；html.parser 可将后续内容恢复为 br 子树。
        result = self.extract(
            '<p>API<br>\n<td>area<br/>keep<a href="/help/81">link</a>'
            '<code>value</code><table><tr><td>nested value</td></tr></table></td>'
        )
        self.assertEqual(result["counts"]["tables"], 1)
        self.assertEqual(result["counts"]["code_blocks"], 1)
        self.assertEqual(result["counts"]["links"], 1)
        self.assertIn("nested value", result["text"])

    def test_source_element_indices_are_stable_across_extractions(self):
        html = '<h2>结果</h2><table><tr><td>200</td></tr></table><pre>ok</pre>'
        first = self.extract(html)
        second = self.extract(html)
        self.assertEqual(len(first.get("tables", [])), 1)
        self.assertEqual(first, second)
        self.assertEqual(first["tables"][0]["element_index"], 1)
        self.assertEqual(first["code_blocks"][0]["element_index"], 4)

    def test_embedded_pdf_and_document_resources_keep_tag_and_origin(self):
        result = self.extract(
            '<iframe src="../manual.pdf"></iframe><embed src="/files/spec.pdf">'
            '<object data="//cdn.example.org/protocol.pdf" src="ignored.pdf"></object>'
        )
        self.assertEqual(result.get("embedded_resources"), [
            {"kind": "iframe", "url": "https://open.ys7.com/help/manual.pdf", "element_index": 0},
            {"kind": "embed", "url": "https://open.ys7.com/files/spec.pdf", "element_index": 1},
            {"kind": "object", "url": "https://cdn.example.org/protocol.pdf", "element_index": 2},
        ])
        self.assertEqual(result["counts"]["embedded_resources"], 3)

    def test_legacy_frameset_references_are_retained(self):
        result = self.extract(
            '<frameset><frame src="overview-frame.html">'
            '<frame src="allclasses-frame.html"><frame src="overview-summary.html"></frameset>',
            "https://open.ys7.com/doc/en/android/index.html",
        )
        self.assertEqual(
            [(r["kind"], r["url"]) for r in result["embedded_resources"]],
            [("frame", "https://open.ys7.com/doc/en/android/" + name) for name in
             ("overview-frame.html", "allclasses-frame.html", "overview-summary.html")],
        )

    def test_audio_video_sources_and_captions_are_retained_in_document_order(self):
        result = self.extract(
            '<audio src="/clip.ogg"><source src="/clip.mp3"></audio>'
            '<video src="/demo.mp4"><source src="/demo.webm">'
            '<track src="captions.vtt"></video>'
            '<picture><source srcset="/diagram.png 1x"></picture>'
        )
        self.assertEqual(
            [(r["kind"], r["url"]) for r in result.get("embedded_resources", [])],
            [
                ("audio", "https://open.ys7.com/clip.ogg"),
                ("source", "https://open.ys7.com/clip.mp3"),
                ("video", "https://open.ys7.com/demo.mp4"),
                ("source", "https://open.ys7.com/demo.webm"),
                ("track", "https://open.ys7.com/help/en/captions.vtt"),
            ],
        )
        self.assertEqual(result["counts"]["embedded_resources"], 5)
        self.assertEqual(result["images"][0]["url"], "https://open.ys7.com/diagram.png")

    def test_embedded_non_http_urls_are_inert_data_and_duplicate_uses_remain(self):
        result = self.extract(
            '<iframe src="javascript:alert(1)"></iframe>'
            '<object data="data:application/pdf;base64,AAAA"></object>'
            '<video src="blob:https://example.org/video-id"></video>'
            '<embed src="ezopen://example/resource"><embed src="ezopen://example/resource">'
            '<iframe></iframe><script>"<embed src=hidden.pdf>"</script>'
        )
        self.assertEqual(
            [r["url"] for r in result.get("embedded_resources", [])],
            [
                "javascript:alert(1)",
                "data:application/pdf;base64,AAAA",
                "blob:https://example.org/video-id",
                "ezopen://example/resource",
                "ezopen://example/resource",
            ],
        )
        self.assertEqual(result["counts"]["embedded_resources"], 5)


if __name__ == "__main__":
    unittest.main()
