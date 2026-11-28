"""hino-ronten の構造にしていない記載を、事項、資料、出来事に対応づけるツール（tools/ronten_kisai.py。SCHEMA.md 7.14）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ronten  # noqa: E402
import ronten_kisai as rk  # noqa: E402
from test_shogo import FakeInputs  # noqa: E402


def gyo(about, source="doc:a/1", quote="文", status="confirmed", title="t"):
    return dict(title=title, about=about, source=source, source_date="2024-03", quote=quote, kind="", target="",
                suji="", status=status, reviewer="", date="", note="")


JIKO = [dict(id="j1", name="待機児童数", betsumei="待機児童")]
BUNSHO = [dict(bunsho="pt:keikaku/honpen", namae="計画"), dict(bunsho="pt:keikaku/honpen-old", namae="計画"),
          dict(bunsho="doc:kousou", namae="基本構想")]
NAMAE = [dict(theme="kaigo", namae="第9期の計画", shu="資料", id="pt:kaigo9/honpen", betsumei="第8期の評価"),
         dict(theme="kaigo", namae="第10期の計画の策定", shu="出来事", id="kaigo-x", betsumei=""),
         dict(theme="kaigo", namae="名前だけ", shu="資料", id="", betsumei="")]


class TestAteru(unittest.TestCase):
    def ate(self, rows):
        return rk.ateru(rows, JIKO, BUNSHO, NAMAE)

    def test_jiko(self):
        self.assertEqual(self.ate([gyo("待機児童数")]), [(rk.JIKO, "待機児童数")])

    def test_betsumei_tsukawanai(self):
        # 事項の表の betsumei は使わない（SCHEMA.md 7.9）
        self.assertEqual(self.ate([gyo("待機児童")]), [None])

    def test_shiryo_dekigoto(self):
        self.assertEqual(self.ate([gyo("基本構想"), gyo("第8期の評価"), gyo("第10期の計画の策定")]),
                         [(rk.SHIRYO, "doc:kousou"), (rk.SHIRYO, "pt:kaigo9/honpen"), (rk.DEKIGOTO, "kaigo-x")])

    def test_han(self):
        # 同じ名前の資料が2つ以上なら、行の資料が候補にあるときだけ
        self.assertEqual(self.ate([gyo("計画", source="pt:keikaku/honpen-old/3"), gyo("計画", source="doc:betsu/2")]),
                         [(rk.SHIRYO, "pt:keikaku/honpen-old"), None])

    def test_ataranai(self):
        # id の無い名前、空の about、近い字は対応づけない
        self.assertEqual(self.ate([gyo("名前だけ"), gyo(""), gyo("基本構想（案）")]), [None, None, None])

    def test_nokori(self):
        rows = [gyo("a"), gyo("a"), gyo(""), gyo("待機児童数")]
        md = rk.nokori_md(rows, self.ate(rows))
        self.assertIn("| a | 2 |", md)
        self.assertIn("| （空） | 1 |", md)
        self.assertIn("行の数：3。名前の数：2。", md)


class TestJikoKiroku(unittest.TestCase):
    def test_onaji_wa_hitotsu(self):
        inp = FakeInputs(ronten={ronten.KISAI: [gyo("P", quote="約 3,200㎡"), gyo("P", quote="別の文", title="u"),
                                                gyo("P", quote="未確認", status="candidate"), gyo("Q")]})
        ko = [dict(point="P", source="doc:a/1", quote="約3,200㎡")]
        rows, nozoku = rk.jiko_kiroku(inp, {"P"}, ko)
        self.assertEqual(nozoku, 1)
        self.assertEqual([(r["point"], r["quote"], r["value"], r["kind"]) for r in rows], [("P", "別の文", "", "")])


if __name__ == "__main__":
    unittest.main()
