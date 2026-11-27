"""docs/design.md 3節の表と、ページを作るツール（tools/build_suji.py）の対応の検査。"""
import copy
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_suji as bs  # noqa: E402
import inputs  # noqa: E402
import suji  # noqa: E402

with open(bs.SRC_PATH, encoding="utf-8") as _f:
    SRC = _f.read()


def design():
    return copy.deepcopy(bs.read_design())


def problems(d=None, src=SRC):
    return bs.design_problems(d or design(), src)


class TestDesign(unittest.TestCase):
    def test_real(self):
        # いまの docs/design.md と tools/build_suji.py は合っている
        self.assertEqual(problems(), [])

    def test_kankei_rows(self):
        # データの側が返す印のすべてに、1つ目の表の行がある
        d = design()
        for k in suji.KANKEI:
            self.assertIn(f"時点の関係 {k}", d.h1)
        del d.h1["時点の関係 tochu"]
        p = problems(d)
        self.assertIn("データの側が返す印 tochu に、1つ目の表の行が無い", p)
        self.assertIn("このツールが引く ID「時点の関係 tochu」が、1つ目の表に無い", p)

    def test_hidari(self):
        # 1つ目の表の左の列は、SCHEMA.md にある列か印か、決めた形の一覧にある字
        self.assertEqual(bs.hidari_problems("定義の表 nani"), [])
        self.assertEqual(bs.hidari_problems("文書の表 chu、文書の部分の表 chu"), [])
        self.assertEqual(bs.hidari_problems("時点の関係 無し"), [])
        self.assertEqual(bs.hidari_problems("bubun が空"), [])
        self.assertEqual(len(bs.hidari_problems("定義の表 namae")), 1)            # 定義の表の列ではない
        self.assertEqual(len(bs.hidari_problems("文書の表 chu、文書の部分の表 iro")), 1)
        self.assertEqual(len(bs.hidari_problems("時点の関係 kako")), 1)            # suji.KANKEI に無い印
        self.assertEqual(len(bs.hidari_problems("資料の名前")), 1)                 # 決めた形のどれでもない

    def test_extra_row(self):
        # 表にあって、ツールが引かない行があれば止まる
        d = design()
        d.h1["数値の表 nendo"] = ("対象の年度", "数値ごとの欄")
        d.h2["midashi-yobi"] = "予備の見出し"
        p = problems(d)
        self.assertIn("1つ目の表の行「数値の表 nendo」を、ページを作るツールのどれも引いていない", p)
        self.assertIn("2つ目の表の行「midashi-yobi」を、ページを作るツールのどれも引いていない", p)

    def test_missing_row(self):
        d = design()
        del d.h2["erabu"]
        self.assertIn("このツールが引く ID「erabu」が、2つ目の表に無い", problems(d))

    def test_names(self):
        # D.bun に渡す名前と、文の中の {名前} が合わない
        d = design()
        d.h2["kensu"] = "{riyu}（{kazu}件）"
        self.assertTrue(any("2つ目の表の行「kensu」" in m for m in problems(d)))

    def test_word_in_tool(self):
        # ツールの中に、表の画面の言葉や文（4字以上）を書けば止まる。1つ目の表の左の列の字は ID なので除く
        d = design()
        w = d.kotoba("文書の表 konkyo")
        self.assertIn(f"このツールの中に、表の字「{w}」が書かれている", problems(d, SRC + f'\nX = "{w}"\n'))
        t = d.retsu_setsumei("時点の関係 ato")
        self.assertIn(f"このツールの中に、表の字「{t}」が書かれている", problems(d, SRC + f'\nX = "{t}"\n'))
        self.assertEqual(problems(d, SRC + '\nX = "shiryo が計画・町の資料"\n'), [])

    def test_key_not_literal(self):
        p = problems(None, SRC + "\nk = 'dai'\nD.bun(k, name='x')\n")
        self.assertTrue(any("ID が字のままでない" in m for m in p))

    def test_read_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "design.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("## 3. 対応\n\n| データの側 | 画面の言葉 | 出し方 |\n| --- | --- | --- |\n| 定義の表 nani | 説明 | 欄 |\n")
            with self.assertRaises(inputs.InputError):                             # 2つ目の表が無い
                bs.read_design(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n| ID | 文 |\n| --- | --- |\n| dai | {name} |\n| dai | {name} |\n")
            with self.assertRaises(inputs.InputError):                             # 左の列が重なっている
                bs.read_design(path)

    def test_build_stops(self):
        d = design()
        del d.h1["定義の表 chui"]
        with self.assertRaises(bs.Stop) as c:
            bs.build(None, None, "taiki", None, None, design=d)
        self.assertEqual({k for k, _ in c.exception.problems}, {"(e) デザインシステムとの対応"})


if __name__ == "__main__":
    unittest.main()
