"""画面に出す言葉の検査（docs/design.md 2節）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_note as bn  # noqa: E402


def page(body):
    return f"<html><head><title>t</title><style>.点{{}}</style></head><body>{body}<script>var 値=1;</script></body></html>"


class TestTable(unittest.TestCase):
    def test_read_design(self):
        ng, ok = bn.read_kotoba()
        words = [w for w, _ in ng]
        for w in ("事項", "点", "題材", "当たる", "記載", "段落", "値", "性質", "対応", "原" "典", "出典", "開けます", "見本"):
            self.assertIn(w, words)
        self.assertEqual(dict(ng)["段落"], "リンクの名前")
        self.assertEqual(dict(ng)["点"], "文")
        self.assertTrue({"論点", "テーマ", "記述", "会議録", "金額", "数値", "もとの資料", "確認できます", "試作"} <= ok)
        self.assertNotIn("", ok)

    def test_read_from_design_only(self):
        # 言葉の表は docs/design.md の2節にだけある。SKILL.md には無い
        self.assertTrue(bn.DESIGN_PATH.endswith(os.path.join("docs", "design.md")))
        with self.assertRaises(bn.inputs.InputError):
            bn.read_kotoba(os.path.join(bn.inputs.ROOT, "SKILL.md"))


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.ng, self.ok = bn.read_kotoba()

    def found(self, body):
        return [m for _, m in bn.kotoba_problems(page(body), self.ng, self.ok)]

    def test_clean(self):
        self.assertEqual(self.found("<p>論点ごとのページ。数値：3,000。もとの資料で確認できます。試作。</p>"), [])

    def test_forbidden(self):
        self.assertEqual(len(self.found("<p>この事項の記載</p>")), 2)
        self.assertEqual(len(self.found("<p>大事な点</p>")), 1)
        self.assertEqual(len(self.found("<p>値は</p>")), 1)

    def test_jiten(self):
        # 「時点」は、残っていると見ない言葉（docs/design.md 2節の表の読み方の項目）。「点」だけなら止まる
        self.assertIn("時点", self.ok)
        self.assertEqual(self.found("<p>資料の日付より後の時点について書いた数値。時点の関係</p>"), [])
        self.assertEqual(len(self.found("<p>時点と、この点</p>")), 1)
        self.assertEqual(len(self.found("<p>出典：見本</p>")), 2)

    def test_quote_excluded(self):
        self.assertEqual(self.found(f"<p>「{bn.A}事項の記載と原典{bn.B}」</p>"), [])
        self.assertEqual(len(self.found(f"<p>「{bn.A}事項{bn.B}」の記載</p>")), 1)

    def test_link_name_only(self):
        self.assertEqual(self.found("<p>段落ごとに見る</p>"), [])            # 文の中の「段落」は対象外
        self.assertEqual(len(self.found("<a href='#'>段落</a>")), 1)
        self.assertEqual(self.found("<a href='#'>会議録</a>"), [])

    def test_style_and_script_ignored(self):
        self.assertEqual(self.found("<p>論点</p>"), [])


if __name__ == "__main__":
    unittest.main()
