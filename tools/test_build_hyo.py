"""資料の表1つを1ページにするツール（tools/build_hyo.py）：行と列の順、欄の数値の取り方、列のまとまりの見出し、版の表記、止まる条件。"""
import copy
import datetime
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_hyo as bh  # noqa: E402
import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import inputs  # noqa: E402
import suji  # noqa: E402
from test_suji import FakeGaibu, tsv  # noqa: E402

TODAY = datetime.date(2026, 11, 23)
NAMAE = "子ども計画"
DOC_NAMAE = "子育ての資料"
K = "pt:x/honpen"
# 2ページ：表の題、列の見出し（3つは「除かれる者」の下）、行（原典の文字では 平成30年4月 が先）、次の表
RAW = (f"{NAMAE}\n令和７年３月\n令和８年６月一部改正\f"
       "第５章 量の見込み\n◆待機児童数の推移\n①求職\n②特定\n小計\n"
       "平成30年4月 0 4 4 1\n令和7年4月 2 11 13 3\n除かれる者\n待機児童数\n"
       "■別の表\n平成30年4月 9 9")


def fake():
    return FakeGaibu(
        docs={"jigyo-1": {"id": "jigyo-1", "title": DOC_NAMAE, "url": "https://example.jp/j.pdf", "archive_url": "",
                          "category": "jigyo"}},
        doc_texts={("jigyo-1", "text"): f"{DOC_NAMAE}\f令和7年4月 3 人"},
        plans={"x": {"meta": {"name": NAMAE}}},
        sources_index=[{"id": "x", "file": "honpen.pdf", "url": "https://example.jp/p.pdf"}],
        pt_texts={("x", "honpen", "text"): RAW, ("x", "honpen", "text_raw"): RAW})


def bunsho_rows(**kw):
    r = dict(bunsho=K, namae=NAMAE, shurui="keikaku", konkyo="", konkyo_tokoro="", hiduke="2026-06",
             hiduke_moto=f"{K}/1", han="令和８年６月一部改正", han_tokoro=f"{K}/1", chu="根拠：全ページを探した")
    r.update(kw)
    return [r, dict(bunsho="doc:jigyo-1", namae=DOC_NAMAE, shurui="jigyo", konkyo="", konkyo_tokoro="",
                    hiduke="2025-04", hiduke_moto="doc:jigyo-1/1", han="", han_tokoro="", chu="根拠：全ページを探した")]


def bubun_rows():
    """行は、番号の順（令和7年4月 が先）と、原典の文字の順（平成30年4月 が先）を変えてある。"""
    m = "除かれる者"
    rows = [("1", "", "見出し", "第５章 量の見込み", "", "", "機械"),
            ("2", "1", "表", "◆待機児童数の推移", "", "", "機械"),
            ("3", "2", "列", "待機児童数", "4", "", "機械"),
            ("4", "2", "行", "令和7年4月", "", "", "機械"),
            ("5", "2", "行", "平成30年4月", "", "", "機械"),
            ("6", "2", "列", "①求職", "1", m, "機械"),
            ("7", "2", "列", "②特定", "2", m, "機械"),
            ("8", "2", "列", "小計", "3", m, "機械"),
            ("9", "1", "表", "■別の表", "", "", "機械")]
    return [dict(bunsho=K, n=n, oya=o, shu=shu, name=name, tokoro=f"{K}/2", jun=jun, matome=mt, torikata=tk, chu="")
            for n, o, shu, name, jun, mt, tk in rows]


def teigi_row():
    return dict(id="taiki", name="待機児童数", nani="各年4月の待機児童の数", tani="人", iikata="",
                toki="各年4月1日現在", nendo_tsuki="4", sei="", chui="", kettei="案")


def atai_rows():
    a = dict(suji="taiki", kubun="", jiten="令和7年4月", nendo="2025", atai="3", shurui="", jotai=suji.ARU,
             shiryo=f"{K}/2", inyo="令和7年4月 2 11 13 3", hani="", kakunin="2026-11-23", chu="", bubun="4", retsu="3")
    b = dict(a, shiryo="doc:jigyo-1/2", inyo="令和7年4月 3 人", bubun="", retsu="")
    return [a, b]


def tables(bunsho=None, bubun=None, atai=None):
    s, _ = suji.read_suji(tsv(suji.SUJI_COLUMNS, [teigi_row()]))
    a, p1 = suji.read_atai(tsv(suji.ATAI_COLUMNS, atai if atai is not None else atai_rows()))
    b, p2 = suji.read_bunsho(tsv(suji.BUNSHO_COLUMNS, bunsho if bunsho is not None else bunsho_rows()))
    c, p3 = suji.read_bubun(tsv(suji.BUBUN_COLUMNS, bubun if bubun is not None else bubun_rows()))
    assert not (p1 + p2 + p3), p1 + p2 + p3
    return dict(suji=s, atai=a, bunsho=b, bubun=c)


def change(rows, bango, **kw):
    return [dict(r, **kw) if r["n"] == bango else r for r in rows]


def body_rows(page):
    """表の本体の行 → [(行の見出し, [欄の数値])]。"""
    tb = page[page.index("<tbody>"):page.index("</tbody>")]
    return [(m.group(1), re.findall(r"<td>(.*?)</td>", m.group(2)))
            for m in re.finditer(r"<tr><th class=g>(.*?)</th>(.*?)</tr>", tb)]


D = bs.read_design()


class TestFake(unittest.TestCase):
    def setUp(self):
        self.kotoba = bn.read_kotoba()

    def build(self, t=None, n="2", inp=None, design=D):
        return bh.build(inp or fake(), t or tables(), K, n, self.kotoba, TODAY, design=design)

    def stop_kinds(self, **kw):
        with self.assertRaises(bh.Stop) as c:
            self.build(**kw)
        return {k for k, _ in c.exception.problems}, c.exception.problems

    def test_page(self):
        page, info = self.build()
        # 行は原典の文字の順、列は jun の順。欄の数値は原典の文字の行から取る
        self.assertEqual(body_rows(page), [("平成30年4月", ["0", "4", "4", "1"]), ("令和7年4月", ["2", "11", "13", "3"])])
        self.assertEqual((info["gyo"], info["retsu"], info["ran"], info["moji"], info["atai"]), (2, 4, 8, 8, 1))
        # 列のまとまりの見出しは、列の見出しの上の行に、続く列をまとめて出す
        self.assertIn("<th class=m colspan=3>除かれる者</th><th rowspan=2>待機児童数</th>", page)
        self.assertIn("<tr><th>①求職</th><th>②特定</th><th>小計</th></tr>", page)
        # 版の表記と資料の日付は、資料の名前のあとの括弧に出す
        self.assertIn(f"<p>{NAMAE}（令和８年６月一部改正、2026年6月）　{D.bun('page', n=2)}</p>", page)
        self.assertIn(D.bun("atama-hyo"), page)
        self.assertIn(f"<h1>◆待機児童数の推移</h1>", page)
        self.assertIn("<p class=s>第５章 量の見込み</p>", page)
        self.assertIn("https://example.jp/p.pdf#page=2", page)
        # 同じ定義の数値がある、ほかの文書
        self.assertIn(f"<h2>{D.bun('midashi-onaji')}</h2>", page)
        self.assertIn(f"<li>{DOC_NAMAE}（2025年4月）　{D.bun('page', n=2)}</li>", page)
        # 出さないもの：数値の表の inyo、文書の表の chu、印
        self.assertNotIn("令和7年4月 2 11 13 3", page)
        self.assertNotIn("根拠：全ページを探した", page)
        self.assertNotIn(bn.A, page)
        self.assertNotIn(bn.B, page)
        self.assertEqual(bh.out_name(K, "2"), "pt_x_honpen_2.html")

    def test_no_matome_no_han(self):
        rows = [dict(r, matome="") for r in bubun_rows()]
        page, _ = self.build(tables(bunsho=bunsho_rows(han="", han_tokoro=""), bubun=rows))
        self.assertNotIn("colspan", page)
        self.assertIn("<thead><tr><th class=g></th><th>①求職</th><th>②特定</th><th>小計</th><th>待機児童数</th></tr></thead>",
                      page)
        self.assertIn(f"<p>{NAMAE}（2026年6月）　", page)

    def test_stop_table_check(self):
        # 数値の表の atai が、原典の文字の行の数値と違えば止まる（表の検査で止まる）
        rows = atai_rows()
        rows[0]["atai"] = "13"
        rows[0]["inyo"] = "令和7年4月 2 11 13 3"
        kinds, _ = self.stop_kinds(t=tables(atai=rows))
        self.assertEqual(kinds, {"(a) 表の検査"})
        # matome が原典の文字に無い
        kinds, p = self.stop_kinds(t=tables(bubun=change(bubun_rows(), "6", matome="含まれる者")))
        self.assertEqual(kinds, {"(a) 表の検査"})
        self.assertTrue(any("matome が" in m for _, m in p), p)

    def test_stop_atai_differs(self):
        # 表の検査を通った後で数値が違う場合も止まる（Hyo の確認）
        t = tables()
        t["atai"][0]["atai"] = "4"
        with mock.patch.object(bh.sj, "check_all", return_value=([], None, None)):
            kinds, p = self.stop_kinds(t=t)
        self.assertEqual(kinds, {"(g) 数値の一致"})
        self.assertIn("atai（4）が、原典の文字の行の 4 つ目（3）と違う", p[0][1])

    def test_stop_table_and_rows(self):
        kinds, _ = self.stop_kinds(n="1")                         # 見出しは表でない
        self.assertEqual(kinds, {"(c) 文書と表"})
        kinds, _ = self.stop_kinds(n="9")                         # 表に行も列も無い
        self.assertEqual(kinds, {"(c) 文書と表"})
        # 行の数値が、列の jun に足りない（jun 5 の列）
        rows = bubun_rows() + [dict(bubun_rows()[2], n="10", name="除かれる者", jun="5", torikata="読んだ")]
        kinds, p = self.stop_kinds(t=tables(bubun=rows))
        self.assertEqual(kinds, {"(f) 行"})
        self.assertTrue(all("列の jun（5）の数値が無い" in m for _, m in p), p)

    def test_stop_range(self):
        # 表の題の行が、ページに2行ある（表の範囲が決まらない）。表の検査と、範囲の両方で止まる
        inp = fake()
        raw = RAW.replace("■別の表", "◆待機児童数の推移")
        inp._pt[("x", "honpen", "text_raw")] = raw
        inp._pt[("x", "honpen", "text")] = raw
        rows = [r for r in bubun_rows() if r["n"] != "9"]
        kinds, _ = self.stop_kinds(t=tables(bubun=rows), inp=inp)
        self.assertEqual(kinds, {"(a) 表の検査"})
        with mock.patch.object(bh.sj, "check_all", return_value=([], None, None)):
            kinds, _ = self.stop_kinds(t=tables(bubun=rows), inp=inp)
        self.assertEqual(kinds, {"(f) 表の範囲"})

    def test_yonda(self):
        # torikata が「読んだ」の表は、数値の表に行がある欄だけを出せる。無い欄があれば止まる
        rows = change(bubun_rows(), "2", torikata="読んだ")
        kinds, p = self.stop_kinds(t=tables(bubun=rows))
        self.assertEqual(kinds, {"(h) 数値の表に行が無い欄"})
        self.assertEqual(len(p), 7)
        # 欄が全部、数値の表にあれば出せる（数値は atai のまま）
        rows = [r for r in change(bubun_rows(), "2", torikata="読んだ") if r["n"] not in ("5", "6", "7", "8")]
        page, info = self.build(tables(bubun=rows))
        self.assertEqual(body_rows(page), [("令和7年4月", ["3"])])
        self.assertEqual((info["moji"], info["atai"]), (0, 1))

    def test_stop_word(self):
        d = copy.deepcopy(D)
        d.h2["atama-hyo"] = "資料の表の記載です。"
        kinds, _ = self.stop_kinds(design=d)
        self.assertEqual(kinds, {"(b) 使わない言葉"})

    def test_stop_design(self):
        d = copy.deepcopy(D)
        d.h2["midashi-onaji"] = "ほかの資料"
        kinds, p = self.stop_kinds(design=d)
        self.assertEqual(kinds, {"(e) デザインシステムとの対応"})
        self.assertIn("midashi-onaji", p[0][1])
        self.assertEqual(bh.design_problems(D), [])

    def test_main(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(bh.main(["pt:x/honpen"]), 2)
        out = os.path.join(bh.OUT_DIR, bh.out_name("pt:nai/honpen", "1"))
        with mock.patch("sys.stderr"), mock.patch.object(bh.inputs, "Inputs", side_effect=inputs.InputError("x")):
            self.assertEqual(bh.main(["pt:nai/honpen", "1"]), 1)
        self.assertFalse(os.path.exists(out))


def real_inputs():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class TestReal(unittest.TestCase):
    """lock の版の入力と、実際の表で、2つの表のページを作る。入力が lock と合わなければ飛ばす。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.tables, cls.read_problems = bs.read_tables()
        cls.kotoba = bn.read_kotoba()

    def build(self, bkey, n):
        return bh.build(self.inp, self.tables, bkey, n, self.kotoba, TODAY, self.read_problems, D)

    def test_taiki(self):
        page, info = self.build("pt:youho/honpen", "4")
        self.assertEqual((info["gyo"], info["retsu"], info["ran"]), (8, 5, 40))
        self.assertEqual(info["ran"] - info["atai"], 24)              # 数値の表に行が無い欄
        rows = body_rows(page)
        self.assertEqual([g for g, _ in rows][0], "平成30年4月")
        self.assertEqual(rows[0][1], ["0", "0", "4", "4", "1"])
        self.assertEqual(rows[-1], ("令和7年4月", ["2", "2", "11", "15", "3"]))
        self.assertIn("<th class=m colspan=4>待機児童数から除かれる者</th><th rowspan=2>待機児童数</th>", page)
        self.assertIn("日野町幼児教育保育施設再編整備計画（令和８年６月一部改正、2026年6月）", page)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertNotIn("<script", page)

    def test_2go(self):
        page, info = self.build("pt:kodomo/honpen", "4")
        self.assertEqual((info["gyo"], info["retsu"], info["ran"]), (3, 5, 15))
        self.assertEqual(info["ran"] - info["atai"], 5)
        self.assertEqual(body_rows(page), [("①量の見込み", ["271", "270", "270", "337", "358"]),
                                           ("②確保方策（保育所、認定こども園）", ["266", "266", "266", "337", "358"]),
                                           ("不足分（②－①）", ["▲5", "▲4", "▲4", "0", "0"])])
        self.assertNotIn("colspan", page)
        self.assertIn(D.kotoba("文書の表 konkyo"), page)


if __name__ == "__main__":
    unittest.main()
