"""数値の表から、定義1つのページを作るツール（tools/build_suji.py）：列の分け方、並べ方、止まる条件、docs/design.md 3節との対応。"""
import datetime
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import inputs  # noqa: E402
import suji  # noqa: E402
from test_suji import FakeGaibu, tsv  # noqa: E402

TODAY = datetime.date(2026, 11, 21)
SID = "0000008211_20241213_0156"
NAMAE = "日野町幼児教育保育施設再編整備計画"
DOC_NAMAE = "子育ての資料"
PAGE2 = "令和7年4月 2 2 11 15 3\n令和6年4月 3 15 16 34 8\n令和6年4月 目標 5\n令和6年度 40 41 42"


def fake():
    return FakeGaibu(
        statements={SID: ("森弘一郎", "前置きです。\n令和6年4月の待機児童は7名でした。")},
        docs={"jigyo-1": {"id": "jigyo-1", "title": DOC_NAMAE, "url": "https://example.jp/j.pdf", "archive_url": "",
                          "category": "jigyo"}},
        doc_texts={("jigyo-1", "text"): f"{DOC_NAMAE}\f令和7年度 9 人"},
        plans={"youho": {"meta": {"name": NAMAE}}},
        sources_index=[{"id": "youho", "file": "honpen.pdf", "url": "https://example.jp/p.pdf"}],
        pt_texts={("youho", "honpen", "text"): f"{NAMAE}\f{PAGE2}"})


def teigi_row(**kw):
    r = dict(id="taiki", name="待機児童数", nani="各年4月の待機児童の数", tani="人", iikata="", toki="各年4月1日現在",
             nendo_tsuki="4", sei="", chui="", kettei="案")
    r.update(kw)
    return r


def atai_row(**kw):
    r = dict(suji="taiki", kubun="", jiten="令和6年4月", nendo="2024", atai="8", shurui="", jotai=suji.ARU,
             shiryo="pt:youho/honpen/2", inyo="令和6年4月 3 15 16 34 8", hani="", kakunin="2026-11-19", chu="",
             bubun="", retsu="")
    r.update(kw)
    return r


def bunsho_rows():
    return [dict(bunsho="pt:youho/honpen", namae=NAMAE, shurui="keikaku", konkyo="", konkyo_tokoro="",
                 hiduke="2025-03", hiduke_moto="pt:youho/honpen/1", chu="根拠：全ページを探した"),
            dict(bunsho="doc:jigyo-1", namae=DOC_NAMAE, shurui="jigyo", konkyo="", konkyo_tokoro="",
                 hiduke="", hiduke_moto="", chu="日付：全ページを探した")]


def taiki_rows():
    return [atai_row(),                                                                 # 前か同じ時点（2024年4月）
            atai_row(jiten="令和7年4月", nendo="2025", atai="3", inyo="令和7年4月 2 2 11 15 3"),   # 後の時点
            atai_row(atai="7", shiryo=f"sp:{SID}", inyo="令和6年4月の待機児童は7名でした。"),    # 発言（2024年12月）
            atai_row(atai="5", shurui="目標", inyo="令和6年4月 目標 5"),                     # 資料の字が「目標」
            atai_row(jiten="令和7年度中", nendo="", atai="9", shiryo="doc:jigyo-1/2", inyo="令和7年度 9 人"),
            atai_row(jiten="令和8年4月", nendo="2026", atai="", jotai=suji.NAI, shiryo="", inyo="",
                     hani="会議録と計画を「待機」で探した"),
            atai_row(jiten="令和6年4月", nendo="2024", atai="9", shiryo="doc:jigyo-1/2", inyo="令和7年度 9 人")]


def tables(suji_rows=None, atai_rows=None, bunsho=None):
    s, _ = suji.read_suji(tsv(suji.SUJI_COLUMNS, suji_rows or [teigi_row()]))
    a, _ = suji.read_atai(tsv(suji.ATAI_COLUMNS, atai_rows if atai_rows is not None else taiki_rows()))
    b, _ = suji.read_bunsho(tsv(suji.BUNSHO_COLUMNS, bunsho if bunsho is not None else bunsho_rows()))
    return dict(suji=s, atai=a, bunsho=b, bubun=[])


def cells(page, label, after=""):
    """表の行（時点の字が label）の、列ごとの中身。after があれば、その字のあとの最初の行。"""
    start = page.index(after) if after else 0
    m = re.compile(r"<tr><th>" + re.escape(label) + r"</th>(.*?)</tr>", re.S).search(page, start)
    return re.findall(r"<td>(.*?)</td>", m.group(1), re.S)


def heads(page, after=""):
    """表の見出しの字（列の説明を除く）。"""
    start = page.index(after) if after else 0
    m = re.compile(r"<thead><tr>(.*?)</tr></thead>", re.S).search(page, start)
    return [re.sub(r"<span class=setsumei>.*?</span>", "", h) for h in re.findall(r"<th>(.*?)</th>", m.group(1))]


D = bs.read_design()
JIKI = D.bun("hyo-jiki")


def go(k):
    return D.kotoba(f"時点の関係 {k}")


def chips(cell):
    return re.findall(r"<b>(.*?)</b>", cell)


class TestFake(unittest.TestCase):
    def setUp(self):
        self.kotoba = bn.read_kotoba()

    def build(self, t=None, sid="taiki", inp=None):
        return bs.build(inp or fake(), t or tables(), sid, self.kotoba, TODAY, design=D)

    def test_columns(self):
        page, info = self.build()
        self.assertEqual(heads(page), [JIKI, go("ato"), go("mae")])      # 1行も無い印の列は出さない
        self.assertEqual([chips(c) for c in cells(page, "2025年4月")], [["3"], []])
        self.assertEqual([chips(c) for c in cells(page, "2024年4月")], [[], ["8", "7", "5"]])
        self.assertNotIn("2026年4月", re.findall(r"<tr><th>(.*?)</th>", page))         # 印が無い行は表に入れない
        self.assertEqual(info["gyo"], 7)
        self.assertNotIn(bn.A, page)
        self.assertNotIn(bn.B, page)
        self.assertIn(D.kotoba("定義の表 kettei が「案」"), page)
        # 列の説明は ato と mae にだけ付ける（docs/design.md 3節の出し方）
        self.assertIn(f"<span class=setsumei>{D.retsu_setsumei('時点の関係 ato')}</span>", page)
        self.assertIn(f"<span class=setsumei>{D.retsu_setsumei('時点の関係 mae')}</span>", page)

    def test_tochu_and_kubun(self):
        t = teigi_row(id="fusoku", name="保育の不足分", nendo_tsuki="", toki="年度")
        rows = [atai_row(suji="fusoku", kubun=k, jiten=j, nendo=n, atai=v, inyo="令和6年度 40 41 42")
                for k, j, n, v in (("2号", "令和5年度", "2023", "40"), ("2号", "令和6年度", "2024", "41"),
                                   ("2号", "令和7年度", "2025", "42"), ("3号", "令和6年度", "2024", "40"))]
        page, _ = self.build(tables([t], rows), "fusoku")
        self.assertEqual(heads(page, "：2号</h3>"), [JIKI, go("ato"), go("tochu"), go("mae")])
        self.assertEqual([chips(c) for c in cells(page, "2023年度", "：2号</h3>")], [[], [], ["40"]])
        self.assertEqual([chips(c) for c in cells(page, "2024年度", "：2号</h3>")], [[], ["41"], []])
        self.assertEqual([chips(c) for c in cells(page, "2025年度", "：2号</h3>")], [["42"], [], []])
        # kubun ごとに表を分ける。列は、定義の中に1行でもある印の列（kubun ごとには減らさない）
        self.assertIn(f"<h3>{D.kotoba('数値の表 kubun')}：2号</h3>", page)
        self.assertEqual(heads(page, "：3号</h3>"), [JIKI, go("ato"), go("tochu"), go("mae")])
        self.assertEqual([chips(c) for c in cells(page, "2024年度", "：3号</h3>")], [[], ["40"], []])
        self.assertIn(D.bun("nendo-kikan"), page)

    def test_not_shown_rows(self):
        page, info = self.build()
        self.assertEqual(info["kankei"][None], 3)
        i = page.index(f"<h3>{D.bun('midashi-nai')}</h3>")
        riyu = [D.kotoba("数値の表 nendo が空"), D.kotoba("文書の表 hiduke が空"), D.kotoba("数値の表 shiryo が空")]
        kensu = [D.bun("kensu", riyu=r, n=1) for r in riyu]
        order = [page.index(k, i) for k in kensu]
        self.assertEqual(order, sorted(order))                         # 理由ごとに、決めた順に並べる
        self.assertIn("会議録と計画を「待機」で探した", page)

    def test_chigau(self):
        page, info = self.build()
        self.assertIn(D.bun("chigau"), cells(page, "2024年4月")[1])
        self.assertEqual(info["chigau"], 1)
        rows = taiki_rows()
        rows[2] = atai_row(atai="8", shiryo=f"sp:{SID}", inyo="令和6年4月の待機児童は8名でした。")
        inp = fake()
        inp._st[SID] = ("森弘一郎", "令和6年4月の待機児童は8名でした。")
        page, info = self.build(tables(atai_rows=rows), inp=inp)
        self.assertNotIn(D.bun("chigau"), page)     # shurui が「目標」の 5 は比較しない
        self.assertEqual(info["chigau"], 0)

    def test_hiduke_order_when_no_kankei(self):
        t = teigi_row(id="kaien", name="開園の時期", nendo_tsuki="", tani="")
        rows = [atai_row(suji="kaien", jiten="資料A", nendo="", atai="9", shiryo="doc:jigyo-1/2", inyo="令和7年度 9 人"),
                atai_row(suji="kaien", jiten="資料B", nendo="", atai="7", shiryo=f"sp:{SID}",
                         inyo="令和6年4月の待機児童は7名でした。"),
                atai_row(suji="kaien", jiten="資料C", nendo="", atai="3", inyo="令和7年4月 2 2 11 15 3",
                         shiryo="pt:youho/honpen/2")]
        page, _ = self.build(tables([t], rows), "kaien")
        self.assertNotIn(f"<h2>{D.bun('midashi-hyo')}</h2>", page)
        self.assertNotIn("並べ方は、まだ決まっていません", page)        # docs/design.md 4節（2026-11-21 の依頼者の決定）
        body = page[page.index(f"<h2>{D.bun('midashi-hiduke')}</h2>"):page.index(f"<h2>{D.bun('midashi-shosai')}</h2>")]
        self.assertEqual(re.findall(r"<tr><td>(.*?)</td>", body),
                         ["2024年12月13日", "2025年3月", D.kotoba("文書の表 hiduke が空")])
        # shurui がどの行にも無ければ、その列を出さない
        self.assertNotIn(D.kotoba("数値の表 shurui"), heads(page, f"<h2>{D.bun('midashi-hiduke')}</h2>"))

    def test_detail(self):
        page, _ = self.build()
        self.assertIn("<dt>区分</dt><dd>議会での答弁</dd>", page)
        self.assertIn("<dt>区分</dt><dd>町の資料</dd>", page)
        tokoro = D.kotoba("文書の部分（bubun・retsu から親をたどった並び）")
        self.assertIn(f"<dt>{tokoro}</dt><dd>{D.kotoba('bubun が空')}</dd>", page)
        self.assertIn("https://example.jp/p.pdf#page=2", page)
        self.assertIn(f"#sid={SID}", page)
        self.assertIn(f"<dt>{D.kotoba('数値の表 jotai が「数値がある」でない')}</dt><dd>調べた範囲に見つからない</dd>", page)
        self.assertIn(f"<dt>{D.kotoba('数値の表 kakunin')}</dt><dd>2026年11月19日</dd>", page)
        self.assertNotIn("根拠：全ページを探した", page)            # 文書の表の chu は出さない
        self.assertNotIn("日付：全ページを探した", page)
        # 出さない欄：時点の関係の欄。shurui が空の行の、shurui の欄
        self.assertNotIn("時点の関係", page)
        sec = page[page.index("<section id='g2'>"):page.index("</section>", page.index("<section id='g2'>"))]
        self.assertNotIn(D.kotoba("数値の表 shurui"), sec)

    def test_stop_word(self):
        with self.assertRaises(bs.Stop) as c:
            self.build(tables([teigi_row(nani="各年4月の待機児童の記載")]))
        self.assertEqual({k for k, _ in c.exception.problems}, {"(b) 使わない言葉"})

    def test_word_in_quote_is_allowed(self):
        inp = fake()
        inp._pt[("youho", "honpen", "text")] += "\n記載 令和6年4月 8"
        rows = taiki_rows()
        rows[0] = atai_row(inyo="記載 令和6年4月 8")
        page, _ = self.build(tables(atai_rows=rows), inp=inp)
        self.assertIn("記載 令和6年4月 8", page)

    def test_stop_table_check(self):
        rows = taiki_rows()
        rows[0] = atai_row(inyo="令和6年4月 3 15 16 34 9")                  # 資料の本文に無い
        with self.assertRaises(bs.Stop) as c:
            self.build(tables(atai_rows=rows))
        self.assertEqual({k for k, _ in c.exception.problems}, {"(a) 表の検査"})
        self.assertTrue(any("teigi/atai.tsv の 2 行目" in m for _, m in c.exception.problems))

    def test_stop_id_not_defined(self):
        with self.assertRaises(bs.Stop) as c:
            self.build(sid="nai")
        self.assertEqual([k for k, _ in c.exception.problems], ["(c) 定義の id"])

    def test_main_stops_without_writing(self):
        out = os.path.join(bs.OUT_DIR, "nai-teigi.html")
        with mock.patch("sys.stderr"), mock.patch.object(bs.inputs, "Inputs", side_effect=inputs.InputError("x")):
            self.assertEqual(bs.main(["nai-teigi"]), 1)                      # (d) lock と入力が合わない
        self.assertFalse(os.path.exists(out))


def real_inputs():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class TestReal(unittest.TestCase):
    """lock の版の入力と、実際の表で作る。入力が lock と合わなければ飛ばす。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.tables, cls.read_problems = bs.read_tables()
        cls.kotoba = bn.read_kotoba()
        cls.pages = {}

    def page(self, sid):
        if sid not in self.pages:
            self.pages[sid] = bs.build(self.inp, self.tables, sid, self.kotoba, TODAY, self.read_problems, D)
        return self.pages[sid]

    def test_pages(self):
        for sid in ("taiki", "fusoku", "kakuho", "kaien"):
            with self.subTest(sid=sid):
                page, info = self.page(sid)
                self.assertEqual(info["gyo"], sum(1 for r in self.tables["atai"] if r["suji"] == sid))
                self.assertTrue(page.startswith("<!DOCTYPE html>"))
                self.assertNotIn("<link", page)
                self.assertNotIn("<script", page)

    def test_taiki_kuzure(self):
        """chu に「抽出した文字の並びが崩れている」がある数値は、資料の該当部分に決まった文を出す（2026-11-27）。"""
        page, _ = self.page("taiki")
        n = sum(1 for r in self.tables["atai"] if r["suji"] == "taiki" and suji.inyo_kuzure(r) and r["inyo"])
        self.assertEqual(n, 10)
        self.assertEqual(page.count(D.bun("inyo-kuzure")), n)
        self.assertNotIn("「基準値【R1】 82 % 1 件」", page)

    def test_taiki_2025(self):
        page, _ = self.page("taiki")
        self.assertEqual(heads(page), [JIKI, go("ato"), go("mae")])
        ato, mae = cells(page, "2025年4月")
        self.assertEqual(len(re.findall("class=chip", ato)), 3)
        self.assertEqual(len(re.findall("class=chip", mae)), 3)
        # 行は中身で選ぶ：後の時点の列に総合計画の目標、前か同じ時点の列に再編整備計画の表の行と基本構想の表の行
        self.assertIn("第6次日野町総合計画", ato)
        self.assertIn("日野町幼児教育保育施設再編整備計画", mae)
        self.assertIn("日野町認定こども園整備基本構想", mae)

    def test_taiki_kubun(self):
        # 年齢別の行（kubun が「うち0歳児」〜「うち5歳児」）は、内訳ごとに表を分ける。年齢別の数値は、資料の間で一致する
        page, info = self.page("taiki")
        for i in range(6):
            self.assertIn(f"<h3>{D.kotoba('数値の表 kubun')}：うち{i}歳児</h3>", page)
        self.assertEqual(info["chigau"], 1)

    def test_kaien(self):
        page, info = self.page("kaien")
        self.assertEqual(info["kankei"][None], info["gyo"])
        self.assertNotIn("並べ方は、まだ決まっていません", page)

    def test_no_chu_of_bunsho_and_bubun(self):
        # 文書の表と文書の部分の表の chu は、どのページにも出さない。数値の表の chu（確認の状態として出す）と
        # 同じ字の chu（「2者が画像で確認（2026-11-23）」だけの chu など）は除く
        chus = {r["chu"] for r in self.tables["bunsho"] + self.tables["bubun"] if len(r["chu"]) >= 6}
        chus -= {r["chu"] for r in self.tables["atai"]}
        for sid in ("taiki", "fusoku", "kakuho", "kaien"):
            page, _ = self.page(sid)
            with self.subTest(sid=sid):
                self.assertEqual([c for c in chus if c in page], [])

    def test_stop_table_changed(self):
        t = dict(self.tables)
        t["atai"] = [dict(r) for r in self.tables["atai"]]
        r = next(r for r in t["atai"] if r["suji"] == "taiki" and r["jiten"] == "令和7年4月" and r["bubun"] == "12")
        r["atai"] = "4"
        with self.assertRaises(bs.Stop) as c:
            bs.build(self.inp, t, "taiki", self.kotoba, TODAY, self.read_problems, D)
        self.assertEqual({k for k, _ in c.exception.problems}, {"(a) 表の検査"})


if __name__ == "__main__":
    unittest.main()
