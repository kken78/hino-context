"""数値の定義の表と数値の表の検査（SCHEMA.md §6）。"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import suji  # noqa: E402
from test_shogo import FakeInputs  # noqa: E402

SID = "0000008211_20241213_0156"


class FakeGaibu(FakeInputs):
    """FakeInputs に、外部の公的な資料の表（SCHEMA.md §5）の読み口を足した物。"""

    def __init__(self, gaibu=None, **kw):
        super().__init__(**kw)
        self._gaibu = gaibu or []

    def gaibu(self):
        return self._gaibu


def fake():
    return FakeGaibu(
        statements={SID: ("森弘一郎", "定員は40名程度を考えております。")},
        docs={"yosan-1": {"id": "yosan-1", "title": "予算書", "url": "https://example.jp/y.pdf", "archive_url": ""}},
        doc_texts={("yosan-1", "text"): "1ページ目\f認定こども園整備事業　3,000,000"},
        pt_texts={("youho", "honpen", "text"): "a\f不足分 ▲5 ▲4 ▲4 0 0\n令和7年4月 2 2 11 15 3"},
        gaibu=[dict(id="soumu-1", name="資料", hakkou="総務省", hiduke="", url="https://example.jp/s.pdf",
                    kakunin="2026-11-18", page="2", ji="充当率90％、交付税措置率50％")])


def tsv(columns, rows):
    return "\t".join(columns) + "\n" + "".join("\t".join(r.get(c, "") for c in columns) + "\n" for r in rows)


def teigi_row(**kw):
    r = dict(id="taiki", name="待機児童数", nani="各年4月の待機児童の数", tani="人", iikata="", toki="各年4月1日現在",
             sei="", chui="", kettei="案")
    r.update(kw)
    return r


def atai_row(**kw):
    r = dict(suji="taiki", kubun="", jiten="令和7年4月", nendo="2025", atai="3", shurui="実績", jotai=suji.ARU,
             shiryo="pt:youho/honpen/2", inyo="令和7年4月 2 2 11 15 3", hani="", kakunin="2026-11-19", chu="")
    r.update(kw)
    return r


def run(teigi=None, atai=None, inp=None):
    """行の辞書の並びから表の字を作って読み、検査する。→ 問題の内容の並び。"""
    s, p1 = suji.read_suji(tsv(suji.SUJI_COLUMNS, teigi if teigi is not None else [teigi_row()]))
    a, p2 = suji.read_atai(tsv(suji.ATAI_COLUMNS, atai if atai is not None else [atai_row()]))
    problems, _ = suji.check(inp or fake(), s, a)
    return [m.naiyo for m in p1 + p2 + problems]


class TestRead(unittest.TestCase):
    def test_ok(self):
        rows, p = suji.read_suji(tsv(suji.SUJI_COLUMNS, [teigi_row()]))
        self.assertEqual(p, [])
        self.assertEqual((rows[0]["id"], rows[0]["_gyo"]), ("taiki", 2))

    def test_column_missing(self):
        cols = [c for c in suji.ATAI_COLUMNS if c != "hani"]
        rows, p = suji.read_atai(tsv(cols, [atai_row()]))
        self.assertEqual(rows, [])
        self.assertEqual([(m.hyo, m.gyo, m.naiyo) for m in p], [(suji.ATAI_NAME, 1, "列が足りない（hani）")])

    def test_column_extra(self):
        rows, p = suji.read_suji(tsv(suji.SUJI_COLUMNS + ["biko"], [teigi_row()]))
        self.assertEqual([m.naiyo for m in p], ["余分な列がある（biko）"])

    def test_cell_count_and_line_number(self):
        text = tsv(suji.SUJI_COLUMNS, [teigi_row()]) + "\n" + "a\tb\n"
        rows, p = suji.read_suji(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual([(m.gyo, m.naiyo) for m in p], [(4, "列の数が 2（9 のはず）")])   # 空の行も数える


class TestTeigi(unittest.TestCase):
    def test_id_duplicate(self):
        self.assertEqual(run(teigi=[teigi_row(), teigi_row(id="hoka")]), [])
        p = run(teigi=[teigi_row(), teigi_row()])
        self.assertEqual(p, ["定義の id が重なっている（taiki）"] * 2)

    def test_required_and_form(self):
        self.assertEqual(run(teigi=[teigi_row(kettei="2026-11-19", tani="", sei="")]), [])
        self.assertIn("必ず書く列が空（name・nani）", run(teigi=[teigi_row(name="", nani="")]))
        self.assertIn("kettei の形が違う（YYYY-MM-DD か「案」のはず：決定）", run(teigi=[teigi_row(kettei="決定")]))
        self.assertTrue(any("id の形" in m for m in run(teigi=[teigi_row(id="Taiki")], atai=[])))


class TestAtai(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(run(), [])

    def test_suji_not_defined(self):
        self.assertEqual(run(atai=[atai_row(suji="nai")]), ["suji が定義の表に無い（nai）"])

    def test_jotai(self):
        self.assertTrue(run(atai=[atai_row(jotai="不明")])[0].startswith("jotai が 数値がある・"))
        for j, kw in ((suji.KARA, dict(atai="", inyo="")),
                      (suji.SETSUMEI, dict(atai="", inyo="定員は40名程度を考えております。")),
                      (suji.NAI, dict(atai="", shiryo="", inyo="", hani="会議録 2020〜2025年。語「待機」"))):
            sh = dict(shiryo=f"sp:{SID}") if j == suji.SETSUMEI else {}
            self.assertEqual(run(atai=[atai_row(jotai=j, **dict(kw, **sh))]), [], j)

    def test_required_empty(self):
        self.assertEqual(run(atai=[atai_row(atai="")]), ["「数値がある」の行で、必ず書く列が空（atai）"])
        self.assertEqual(run(atai=[atai_row(jotai=suji.KARA, atai="", shiryo="", inyo="")]),
                         ["「欄が空」の行で、必ず書く列が空（shiryo）"])
        self.assertEqual(run(atai=[atai_row(jotai=suji.SETSUMEI, atai="", inyo="")]),
                         ["「数値を示さない説明がある」の行で、必ず書く列が空（inyo）"])
        self.assertEqual(run(atai=[atai_row(jotai=suji.NAI, atai="", shiryo="", inyo="", kakunin="")]),
                         ["「調べた範囲に見つからない」の行で、必ず書く列が空（hani・kakunin）"])
        self.assertEqual(run(atai=[atai_row(jiten="")]), ["jiten（いつの数値か）が空"])

    def test_atai_in_empty_state(self):
        p = run(atai=[atai_row(jotai=suji.KARA)])
        self.assertEqual(p, ["「欄が空」の行で、atai に字がある（3）"])

    def test_inyo_not_in_source(self):
        p = run(atai=[atai_row(inyo="令和7年4月 2 2 11 15 4", atai="4")])
        self.assertEqual(p, ["inyo が shiryo の資料の本文に無い（引用が資料の本文に無い：pt:youho/honpen/2）"])
        p = run(atai=[atai_row(shiryo="doc:nai/2")])
        self.assertEqual(p, ["inyo が shiryo の資料の本文に無い（資料が入力に無いか、照合できない資料の鍵：doc:nai/2）"])

    def test_inyo_sources(self):
        rows = [atai_row(atai="40程度", shiryo=f"sp:{SID}", inyo="定員は40名程度を考えております。"),
                atai_row(atai="3,000,000", shiryo="doc:yosan-1/2", inyo="3,000,000"),
                atai_row(atai="90％", shurui="制度の率", shiryo="ext:soumu-1/2", inyo="充当率90％")]
        self.assertEqual(run(atai=rows), [])

    def test_koho(self):
        # 広報ひのを出典にした「数値がある」の行は、inyo が合っていても、確認の記録が要る
        inp = fake()
        inp._docs["koho-1"] = {"id": "koho-1", "category": "koho", "title": "広報", "url": "https://example.jp/k.pdf",
                               "archive_url": ""}
        inp._doc_texts[("koho-1", "text")] = "開園時期：令和11年４月（予定）"
        row = dict(atai="令和11年4月", shiryo="doc:koho-1/1", inyo="開園時期：令和11年４月（予定）")
        ng = "広報ひのを出典にした「数値がある」の行で、chu に「依頼者が PDF で確認（YYYY-MM-DD）」が無い"
        self.assertEqual(run(atai=[atai_row(**row)], inp=inp), [ng])
        self.assertEqual(run(atai=[atai_row(chu="依頼者が PDF で確認（2026-11-20）", **row)], inp=inp), [])
        # 広報ひのでない町の資料は、確認の記録が無くてもよい
        self.assertEqual(run(atai=[atai_row(atai="3,000,000", shiryo="doc:yosan-1/2", inyo="3,000,000")]), [])
        # 「数値がある」でない行には、求めない
        self.assertEqual(run(atai=[atai_row(jotai=suji.SETSUMEI, atai="", shiryo="doc:koho-1/1",
                                            inyo="開園時期")], inp=inp), [])

    def test_hatsugen_bun(self):
        # 発言を出典にした行の inyo は、文の頭から「。」まで（SCHEMA.md §6.2・§6.4）
        ng = "発言を出典にした行で、inyo が、文の頭から「。」までになっていない"
        row = dict(atai="40程度", shiryo=f"sp:{SID}")
        self.assertEqual(run(atai=[atai_row(inyo="定員は40名程度を考えております。", **row)]), [])
        self.assertEqual(run(atai=[atai_row(inyo="40名程度", **row)]), [ng])                    # 文の途中で切っている
        self.assertEqual(run(atai=[atai_row(inyo="定員は40名程度を考えております", **row)]), [ng])    # 「。」が無い
        # 続いた2つの文は、つないで引いてよい。改行も文の区切り
        inp = fake()
        inp._st[SID] = ("森弘一郎", "はじめに申し上げます。\n定員は40名程度です。今後、精査します。")
        self.assertEqual(run(atai=[atai_row(inyo="定員は40名程度です。今後、精査します。", **row)], inp=inp), [])
        self.assertEqual(run(atai=[atai_row(inyo="定員は40名程度です。", **row)], inp=inp), [])
        self.assertEqual(run(atai=[atai_row(inyo="申し上げます。定員は40名程度です。", **row)], inp=inp), [ng])
        # 町の資料の行には、求めない
        self.assertEqual(run(atai=[atai_row(atai="3,000,000", shiryo="doc:yosan-1/2", inyo="3,000,000")]), [])
        self.assertEqual(suji.bun_no_narabi("あ。い\nう。"), ["あ。", "い", "う。"])

    def test_shiryo_form(self):
        p = run(atai=[atai_row(shiryo="pt:youho")])
        self.assertEqual(len(p), 1)
        self.assertTrue(p[0].startswith("shiryo の鍵の形が SCHEMA.md §2 に合わない"))

    def test_inyo_without_shiryo(self):
        p = run(atai=[atai_row(jotai=suji.NAI, atai="", shiryo="", inyo="何か", hani="計画")])
        self.assertEqual(p, ["inyo があるが、shiryo が空"])

    def test_no_text_in_inputs(self):
        # 資料の本文が入力に無い行（plan:）は、inyo を空にでき、その場合は chu が必須
        ok = "総合計画の原文の文字が入力に無い。依頼者が PDF で確認（2026-11-20）"
        self.assertEqual(run(atai=[atai_row(shiryo="plan:sougou", inyo="", chu=ok)]), [])
        ng = "「数値がある」の行で、inyo が空なのに、chu に「依頼者が PDF で確認（YYYY-MM-DD）」が無い"
        self.assertEqual(run(atai=[atai_row(shiryo="plan:sougou", inyo="", chu="総合計画の原文の文字が入力に無い")]), [ng])
        # 日付の形が違う記録は、無いものとする
        self.assertEqual(run(atai=[atai_row(shiryo="plan:sougou", inyo="", chu="依頼者が PDF で確認（2026-13-40）")]), [ng])
        self.assertEqual(run(atai=[atai_row(shiryo="plan:sougou", inyo="")]),
                         ["「数値がある」の行で、inyo が空で、chu に理由が無い"])
        p = run(atai=[atai_row(shiryo="plan:sougou", chu="入力に無い")])     # inyo を書くと照合できずに止まる
        self.assertEqual(len(p), 1)
        self.assertIn("inyo が shiryo の資料の本文に無い", p[0])


class TestAtaiInInyo(unittest.TestCase):
    def test_examples(self):
        self.assertTrue(suji.atai_in_inyo("40程度", "40名程度"))
        self.assertTrue(suji.atai_in_inyo("3,000,000", "3,000,000"))
        self.assertTrue(suji.atai_in_inyo("▲5", "▲5 ▲4 ▲4 0 0"))
        self.assertTrue(suji.atai_in_inyo("約３,０００", "約3,000千円"))       # 全角は §3 の正規化でそろう

    def test_not_in(self):
        self.assertFalse(suji.atai_in_inyo("▲3", "▲5 ▲4 ▲4 0 0"))
        self.assertFalse(suji.atai_in_inyo("▲0", "▲5 ▲4 ▲4 0 0"))          # 符号も数字の部分に含める
        self.assertFalse(suji.atai_in_inyo("3,000,000", "3000000"))         # 桁区切りの「,」も字のまま

    def test_boundary(self):
        # 別の数の一部とは合わない
        self.assertFalse(suji.atai_in_inyo("40", "140名程度"))
        self.assertFalse(suji.atai_in_inyo("234", "1,234千円"))
        self.assertFalse(suji.atai_in_inyo("0", "達成率 100.0%"))
        self.assertTrue(suji.atai_in_inyo("3", "令和7年4月 2 2 11 15 3"))
        self.assertTrue(suji.atai_in_inyo("3", "５ ３ 100.0%"))
        self.assertTrue(suji.atai_in_inyo("1", "平成31年度は１名の待機児童が出た"))

    def test_no_digit(self):
        self.assertIsNone(suji.atai_in_inyo("なし", "該当なし"))
        self.assertEqual(suji.suji_parts("なし"), [])
        self.assertEqual(suji.suji_parts("1.5〜2"), ["1.5", "2"])

    def test_in_check(self):
        self.assertEqual(run(atai=[atai_row(atai="▲5", inyo="不足分 ▲5 ▲4 ▲4 0 0")]), [])
        self.assertEqual(run(atai=[atai_row(atai="なし", inyo="不足分 ▲5 ▲4 ▲4 0 0")]), [])
        self.assertEqual(run(atai=[atai_row(atai="16")]), ["atai の数字が inyo の中に無い（atai：16）"])


class TestForm(unittest.TestCase):
    def test_kakunin(self):
        self.assertEqual(run(atai=[atai_row(kakunin="")]), [])
        self.assertEqual(run(atai=[atai_row(kakunin="2026/11/19")]),
                         ["kakunin の形が違う（YYYY-MM-DD のはず：2026/11/19）"])
        self.assertEqual(run(atai=[atai_row(kakunin="2026-02-30")]),
                         ["kakunin の形が違う（YYYY-MM-DD のはず：2026-02-30）"])

    def test_nendo(self):
        self.assertEqual(run(atai=[atai_row(nendo="")]), [])
        self.assertEqual(run(atai=[atai_row(nendo="R7")]), ["nendo が西暦4桁でない（R7）"])
        self.assertEqual(run(atai=[atai_row(nendo="令和7")]), ["nendo が西暦4桁でない（令和7）"])


class TestMain(unittest.TestCase):
    def main(self, files, inp=None):
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(text)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err), \
                    mock.patch.object(suji.inputs, "Inputs", return_value=inp or fake()):
                code = suji.main([], teigi_dir=d)
        return code, out.getvalue(), err.getvalue()

    def test_no_tables(self):
        code, out, _ = self.main({})
        self.assertEqual(code, 0)
        self.assertIn("表がまだ無い", out)

    def test_one_table(self):
        code, _, err = self.main({"suji.tsv": tsv(suji.SUJI_COLUMNS, [teigi_row()])})
        self.assertEqual(code, 1)
        self.assertIn("表が片方しか無い（無い表：teigi/atai.tsv）", err)

    def test_ok(self):
        code, out, _ = self.main({"suji.tsv": tsv(suji.SUJI_COLUMNS, [teigi_row()]),
                                  "atai.tsv": tsv(suji.ATAI_COLUMNS, [atai_row(), atai_row(jotai=suji.KARA, atai="",
                                                                                           inyo="")])})
        self.assertEqual(code, 0)
        self.assertIn("定義：1 行", out)
        self.assertIn("数値：2 行", out)
        self.assertIn("数値がある：1 行", out)
        self.assertIn("欄が空：1 行", out)
        self.assertIn("inyo の照合：対象 1、合った 1、合わなかった 0", out)

    def test_problems(self):
        code, _, err = self.main({"suji.tsv": tsv(suji.SUJI_COLUMNS, [teigi_row(), teigi_row()]),
                                  "atai.tsv": tsv(suji.ATAI_COLUMNS, [atai_row(nendo="R7")])})
        self.assertEqual(code, 1)
        self.assertIn("問題が 3 件", err)
        self.assertIn("teigi/suji.tsv の 3 行目：定義の id が重なっている（taiki）", err)
        self.assertIn("teigi/atai.tsv の 2 行目：nendo が西暦4桁でない（R7）", err)


if __name__ == "__main__":
    unittest.main()
