"""数値の定義の表と数値の表、文書の表と文書の部分の表の検査（SCHEMA.md §6・§7）。"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import suji  # noqa: E402
from test_shogo import FakeInputs  # noqa: E402

SID = "0000008211_20241213_0156"


class FakeGaibu(FakeInputs):
    """FakeInputs に、外部の公的な資料の表（SCHEMA.md §5）と、施設の参照表・施設の記録（SCHEMA.md §1）の読み口を足したもの。"""

    def __init__(self, gaibu=None, shisetsu=None, shisetsu_kiroku=None, **kw):
        super().__init__(**kw)
        self._gaibu = gaibu or []
        self._shisetsu = shisetsu or []
        self._shisetsu_kiroku = shisetsu_kiroku or []

    def gaibu(self):
        return self._gaibu

    def shisetsu(self):
        return self._shisetsu

    def shisetsu_kiroku(self):
        return self._shisetsu_kiroku


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
             nendo_tsuki="4", sei="", chui="", kettei="案")
    r.update(kw)
    return r


def atai_row(**kw):
    r = dict(suji="taiki", kubun="", jiten="令和7年4月", nendo="2025", atai="3", shurui="", jotai=suji.ARU,
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
        self.assertEqual([(m.gyo, m.naiyo) for m in p], [(4, f"列の数が 2（{len(suji.SUJI_COLUMNS)} のはず）")])   # 空の行も数える


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
                atai_row(atai="90％", shiryo="ext:soumu-1/2", inyo="充当率90％")]
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

    def test_nisha(self):
        # inyo が空の行は、2者が画像で確認した記録でも通る（SCHEMA.md §6.3・§6.4）
        ng = ("「数値がある」の行で、inyo が空なのに、chu に「依頼者が PDF で確認（YYYY-MM-DD）」と"
              "「2者が画像で確認（YYYY-MM-DD）」のどちらも無い")
        row = dict(shiryo="plan:sougou", inyo="")
        self.assertEqual(run(atai=[atai_row(chu="図の中の数値。2者が画像で確認（2026-11-23）", **row)]), [])
        self.assertEqual(run(atai=[atai_row(chu="図の中の数値。PDF で未確認", **row)]), [ng])
        # 日付の形が違う記録は、無いものとする
        self.assertEqual(run(atai=[atai_row(chu="2者が画像で確認（2026-13-40）", **row)]), [ng])
        # 広報ひのは、依頼者の確認だけを認める（inyo がある行も、空の行も）
        inp = fake()
        inp._docs["koho-1"] = {"id": "koho-1", "category": "koho", "title": "広報", "url": "https://example.jp/k.pdf",
                               "archive_url": ""}
        inp._doc_texts[("koho-1", "text")] = "開園時期：令和11年４月（予定）"
        ng_koho = "広報ひのを出典にした「数値がある」の行で、chu に「依頼者が PDF で確認（YYYY-MM-DD）」が無い"
        koho = dict(atai="令和11年4月", shiryo="doc:koho-1/1", chu="2者が画像で確認（2026-11-23）")
        self.assertEqual(run(atai=[atai_row(inyo="開園時期：令和11年４月（予定）", **koho)], inp=inp), [ng_koho])
        self.assertEqual(run(atai=[atai_row(inyo="", **koho)], inp=inp), [ng_koho])

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
        ng = ("「数値がある」の行で、inyo が空なのに、chu に「依頼者が PDF で確認（YYYY-MM-DD）」と"
              "「2者が画像で確認（YYYY-MM-DD）」のどちらも無い")
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


# ---------------------------------------------------------------- 文書と、文書の部分（SCHEMA.md §7）

SID7 = "0000008489_20250613_0084"
KODOMO_RAW = ("第３期\n子ども計画\n令和７年３月\f"
              "第５章 量の見込み\n"
              "①１号認定〔教育〕\n2025 年\n（R7）\n2026 年\n（R8）\n不足分（②－①） 0 0\n"
              "②２号認定〔保育〕\n2025 年\n（R7）\n2026 年\n（R8）\n①量の見込み 271 270\n②確保方策 266 266\n"
              "不足分（②－①） ▲5 ▲4\n"
              "③３号認定〔０歳児〕\n2025 年\n（R7）\n2026 年\n（R8）\n不足分（②－①） ▲6 ▲5\f"
              "本計画は、子ども・子育て支援法第 61 条に基づく計画です。")


def fake7():
    inp = fake()
    inp._pt[("kodomo", "honpen", "text_raw")] = KODOMO_RAW
    inp._st[SID7] = ("森弘一郎", "はじめに。\n現在の待機児童数は3名です。\n終わり。")
    return inp


def bunsho_row(**kw):
    r = dict(bunsho="pt:kodomo/honpen", namae="第３期子ども計画", shurui="keikaku",
             konkyo="子ども・子育て支援法第 61 条に基づく", konkyo_tokoro="pt:kodomo/honpen/3", hiduke="2025-03",
             hiduke_moto="pt:kodomo/honpen/1", chu="")
    r.update(kw)
    return r


def bubun_rows():
    """2ページの表②と表③。表①は部分の表に入れない（表②の題より前にあるので、範囲に入らない）。"""
    k = "pt:kodomo/honpen"
    rows = [("1", "", "見出し", "第５章 量の見込み", "", "機械"),
            ("2", "1", "表", "②２号認定〔保育〕", "", "機械"),
            ("3", "2", "行", "不足分（②－①）", "", "機械"),
            ("4", "2", "列", "2025 年（R7）", "1", "機械"),
            ("5", "2", "列", "2026 年（R8）", "2", "機械"),
            ("6", "2", "行", "①量の見込み", "", "機械"),
            ("7", "1", "表", "③３号認定〔０歳児〕", "", "機械"),
            ("8", "7", "行", "不足分（②－①）", "", "機械"),
            ("9", "7", "列", "2025 年（R7）", "1", "機械")]
    return [dict(bunsho=k, n=n, oya=o, shu=shu, name=name, tokoro=f"{k}/2", jun=jun, torikata=tk, chu="")
            for n, o, shu, name, jun, tk in rows]


def atai7(**kw):
    r = atai_row(atai="▲5", shiryo="pt:kodomo/honpen/2", inyo="不足分（②－①） ▲5 ▲4", bubun="3", retsu="4")
    r.update(kw)
    return r


def run7(atai=None, bunsho=None, bubun=None, inp=None, kankei=None):
    """§7 の表を含めて検査する。→ (問題の内容の並び, 数えた結果)。"""
    s, _ = suji.read_suji(tsv(suji.SUJI_COLUMNS, [teigi_row()]))
    a, p1 = suji.read_atai(tsv(suji.ATAI_COLUMNS, atai if atai is not None else [atai7()]))
    b, p2 = suji.read_bunsho(tsv(suji.BUNSHO_COLUMNS, bunsho if bunsho is not None else [bunsho_row()]))
    c, p3 = suji.read_bubun(tsv(suji.BUBUN_COLUMNS, bubun if bubun is not None else bubun_rows()))
    k, p4 = (suji.read_bunsho_kankei(tsv(suji.BUNSHO_KANKEI_COLUMNS, kankei)) if kankei is not None else (None, []))
    problems, _, kazoe = suji.check_all(inp or fake7(), s, a, b, c, k)
    return [m.naiyo for m in p1 + p2 + p3 + p4 + problems], kazoe


def change(rows, bango, **kw):
    """文書の部分の行の並びの、番号が bango の行を書き換えた並び。"""
    return [dict(r, **kw) if r["n"] == bango else r for r in rows]


class TestBunsho(unittest.TestCase):
    def test_ok(self):
        p, kazoe = run7()
        self.assertEqual(p, [])
        self.assertEqual((kazoe["taisho"], kazoe["atta"], kazoe["yonda"]), (1, 1, 0))

    def test_shurui_wa_keikaku(self):
        """計画ライブラリの文書の shurui は keikaku。こちらで付けた名前は止まる（SCHEMA.md §7.1）。"""
        p, _ = run7(bunsho=[bunsho_row(shurui="法定の計画")])
        self.assertTrue(any("shurui が §7.1 と違う（keikaku のはず：法定の計画）" in x for x in p), p)

    def test_shurui_jitsubutsu(self):
        """実際の入力と表：町の資料の shurui は、入力の台帳の category と同じ。別の字に変えると止まる。"""
        inp = real_inputs()
        if inp is None:
            self.skipTest("入力が無い")
        rows, p0 = suji.read_bunsho(suji._read_file(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), suji.BUNSHO_NAME)))
        self.assertEqual(p0, [])
        out, _ = suji.check_bunsho(inp, rows)
        self.assertEqual([m.naiyo for m in out], [])
        koho = [dict(r, shurui="広報") if r["bunsho"] == "doc:koho-no792-04" else r for r in rows]
        out, _ = suji.check_bunsho(inp, koho)
        self.assertTrue(any("shurui が §7.1 と違う（koho のはず：広報）" in m.naiyo for m in out), [m.naiyo for m in out])

    def test_key(self):
        p, _ = run7(bunsho=[bunsho_row(bunsho="pt:kodomo")])
        self.assertIn("bunsho の形が §7.1 と違う（pt:<id>/<名前>、doc:<id>、plan:<id> のはず：pt:kodomo）", p)
        p, _ = run7(bunsho=[bunsho_row(bunsho="pt:nai/honpen", konkyo="", konkyo_tokoro="", hiduke="",
                                       hiduke_moto="", chu="無い")], atai=[], bubun=[])
        self.assertEqual(p, ["bunsho が lock の版の入力に無い（pt:nai/honpen）"])
        p, _ = run7(bunsho=[bunsho_row(), bunsho_row()])
        self.assertEqual(p, ["bunsho が重なっている（pt:kodomo/honpen）"] * 2)

    def test_namae(self):
        p, _ = run7(bunsho=[bunsho_row(namae="第３期子ども・子育て支援事業計画")])
        self.assertEqual(p, ["namae の字が、1ページの原典の文字に無い（第３期子ども・子育て支援事業計画）"])

    def test_konkyo(self):
        p, _ = run7(bunsho=[bunsho_row(konkyo_tokoro="pt:kodomo/honpen/2")])
        self.assertEqual(p, ["konkyo の字が、konkyo_tokoro のページの原典の文字に無い（pt:kodomo/honpen/2）"])
        p, _ = run7(bunsho=[bunsho_row(konkyo_tokoro="pt:youho/honpen/3")])
        self.assertEqual(p, ["konkyo_tokoro が、この文書のページの鍵でない（pt:youho/honpen/3）"])
        p, _ = run7(bunsho=[bunsho_row(konkyo="", konkyo_tokoro="")])
        self.assertEqual(p, ["konkyo が空なのに、chu に探したページが無い"])
        p, _ = run7(bunsho=[bunsho_row(konkyo="", konkyo_tokoro="", chu="3ページを見た")])
        self.assertEqual(p, [])

    def test_hiduke(self):
        for h in ("2025-3", "2025-13", "2025/03", "2025-02-30"):
            p, _ = run7(bunsho=[bunsho_row(hiduke=h)])
            self.assertEqual(p, [f"hiduke の形が違う（YYYY-MM か YYYY-MM-DD のはず：{h}）"], h)
        self.assertEqual(run7(bunsho=[bunsho_row(hiduke="2025-03-24")])[0], [])
        p, _ = run7(bunsho=[bunsho_row(hiduke_moto="")])
        self.assertEqual(p, ["hiduke があるのに、hiduke_moto が空"])
        p, _ = run7(bunsho=[bunsho_row(hiduke_moto="pt:youho/honpen/1")])
        self.assertEqual(p, ["hiduke_moto が、この文書のページの鍵でない（pt:youho/honpen/1）"])
        self.assertEqual(run7(bunsho=[bunsho_row(hiduke_moto="shiga-hino-plans data/plans/kodomo.json")])[0], [])
        p, _ = run7(bunsho=[bunsho_row(hiduke_moto="台帳")])
        self.assertEqual(p, ["hiduke_moto が、ページの鍵でも、入力の台帳の名前でもない（台帳）"])
        p, _ = run7(bunsho=[bunsho_row(hiduke="", hiduke_moto="")])
        self.assertEqual(p, ["hiduke が空なのに、chu に理由が無い"])

    def test_han(self):
        """版の表記（SCHEMA.md §7.1・§7.4）：han が han_tokoro のページの原典の文字にある。"""
        self.assertEqual(run7(bunsho=[bunsho_row(han="令和７年３月", han_tokoro="pt:kodomo/honpen/1")])[0], [])
        p, _ = run7(bunsho=[bunsho_row(han="令和８年６月一部改正", han_tokoro="pt:kodomo/honpen/1")])
        self.assertEqual(p, ["han が、han_tokoro のページの原典の文字に無い（令和８年６月一部改正）"])
        p, _ = run7(bunsho=[bunsho_row(han="令和７年３月", han_tokoro="pt:youho/honpen/1")])
        self.assertEqual(p, ["han_tokoro が、この文書のページの鍵でない（pt:youho/honpen/1）"])
        p, _ = run7(bunsho=[bunsho_row(han="令和７年３月", han_tokoro="")])
        self.assertEqual(p, ["han_tokoro が、この文書のページの鍵でない（）"])
        p, _ = run7(bunsho=[bunsho_row(han="", han_tokoro="pt:kodomo/honpen/1")])
        self.assertEqual(p, ["han が空なのに、han_tokoro がある"])


class TestBubun(unittest.TestCase):
    def test_key_and_parent(self):
        rows = bubun_rows()
        p, _ = run7(bubun=rows + [dict(rows[2])])
        self.assertEqual(p.count("bunsho と n の組が重なっている（pt:kodomo/honpen の 3）"), 2)
        p, _ = run7(bubun=change(rows, "6", n="x"))
        self.assertIn("n が1からの整数でない（x）", p)
        p, _ = run7(bubun=[dict(r, bunsho="pt:youho/honpen", tokoro="pt:youho/honpen/2") for r in rows], atai=[])
        self.assertIn("bunsho が文書の表に無い（pt:youho/honpen）", p)
        p, _ = run7(bubun=change(rows, "6", oya="20"))
        self.assertEqual(p, ["oya が、同じ文書の部分の表に無い（20）"])
        p, _ = run7(bubun=change(rows, "1", oya="2"))
        self.assertEqual(p, ["oya が、自分より小さい番号でない（2）"])

    def test_shu(self):
        rows = bubun_rows()
        p, _ = run7(bubun=change(rows, "6", shu="セル"))
        self.assertEqual(p, ["shu が 見出し・表・行・列 のどれでもない（セル）"])
        p, _ = run7(bubun=change(rows, "6", oya="1"))         # 行の親が見出し
        self.assertEqual(p, ["「行」の親の種類が違う（表 のはず：見出し）"])
        p, _ = run7(bubun=change(rows, "7", oya="2"))         # 表の親が表
        self.assertIn("「表」の親の種類が違う（無し・見出し のはず：表）", p)
        p, _ = run7(bubun=change(rows, "6", torikata="AI"))
        self.assertEqual(p, ["torikata が 機械・読んだ のどちらでもない（AI）"])

    def test_kikai_kakunin(self):
        """torikata が「機械」の行の chu に確認の記録があると止まる（SCHEMA.md §7.4）。日付の形が違う記録は、無いものとする。"""
        rows = bubun_rows()
        for chu in ("2者が画像で確認（2026-11-23）", "依頼者が PDF で確認（2026-11-23）", "注。2者が画像で確認（2026-11-23）"):
            with self.subTest(chu=chu):
                p, _ = run7(bubun=change(rows, "6", chu=chu))
                self.assertEqual(p, ["torikata が「機械」の行の chu に、確認の記録がある"])
        self.assertEqual(run7(bubun=change(rows, "6", chu="2者が画像で確認（2026-13-40）"))[0], [])
        # 「読んだ」の行には書ける
        self.assertEqual(run7(bubun=change(rows, "6", torikata="読んだ", chu="2者が画像で確認（2026-11-23）"))[0], [])

    def test_name_and_jun(self):
        rows = bubun_rows()
        p, _ = run7(bubun=change(rows, "1", name="第６章 量の見込み"))
        self.assertEqual(p, ["name の字が、tokoro のページの原典の文字に無い（第６章 量の見込み）"])
        p, _ = run7(bubun=change(rows, "1", tokoro="pt:kodomo/honpen/1"))
        self.assertEqual(p, ["name の字が、tokoro のページの原典の文字に無い（第５章 量の見込み）"])
        p, _ = run7(bubun=change(rows, "5", jun=""))
        self.assertEqual(p, ["列の行で、jun が1からの整数でない（）"])
        p, _ = run7(bubun=change(rows, "6", jun="1"))
        self.assertEqual(p, ["列でない行に jun がある（1）"])
        p, _ = run7(bubun=change(rows, "5", jun="1"))
        self.assertIn("同じ表に、jun が同じ列がある（1）", p)

    def test_matome(self):
        """列のまとまりの見出し（SCHEMA.md §7.2・§7.4）：列の行だけに書け、tokoro のページの原典の文字にある。"""
        rows = bubun_rows()
        self.assertEqual(run7(bubun=change(change(rows, "4", matome="（R7）"), "5", matome="（R7）"))[0], [])
        p, _ = run7(bubun=change(rows, "4", matome="待機児童数から除かれる者"))
        self.assertEqual(p, ["matome が、tokoro のページの原典の文字に無い（待機児童数から除かれる者）"])
        p, _ = run7(bubun=change(rows, "6", matome="第５章 量の見込み"))
        self.assertEqual(p, ["列でない行に matome がある（第５章 量の見込み）"])

    def test_table_range(self):
        rows = bubun_rows()
        # 表の題の行が、ページに無い
        p, _ = run7(bubun=change(rows, "2", name="②２号認定"))
        self.assertIn("表の題と同じ字の行が、tokoro のページに 0 行ある（1行のはず：②２号認定）", p)
        # 行の見出しが、親の表の範囲に無い（表③の範囲には「②確保方策」が無い）
        p, _ = run7(bubun=rows + [dict(rows[5], n="10", oya="7", name="②確保方策")])
        self.assertEqual(p, ["行の見出しと数値の行が、親の表の範囲に 0 行ある（1行のはず：②確保方策）"])
        # 列の見出しが、ページにはあるが、親の表の範囲に無い（「②確保方策」は表②の範囲にあり、表③の範囲に無い）
        p, _ = run7(bubun=change(rows, "9", name="②確保方策"))
        self.assertEqual(p, ["列の見出しの字が、親の表の範囲に無い（②確保方策）"])
        # 「機械」の列は、範囲の中で jun の順に並んでいる
        p, _ = run7(bubun=change(change(rows, "4", jun="2"), "5", jun="1"), atai=[])
        self.assertEqual(p, ["列の見出しが、親の表の範囲で jun の順に並んでいない（2025 年（R7））"])
        # 「読んだ」の列は、順を確認しない
        p, _ = run7(bubun=change(change(rows, "4", jun="2", torikata="読んだ"), "5", jun="1", torikata="読んだ"),
                    atai=[])
        self.assertEqual(p, [])


class TestAtaiBubun(unittest.TestCase):
    def test_other_row(self):
        # 別の行（①量の見込み）の数値を取ると止まる
        p, _ = run7(atai=[atai7(bubun="6")])
        self.assertEqual(p, ["行の数値の 1 つ目（271）が、atai（▲5）と違う"])

    def test_other_column(self):
        # 別の列の数値を取ると止まる
        p, _ = run7(atai=[atai7(retsu="5")])
        self.assertEqual(p, ["行の数値の 2 つ目（▲4）が、atai（▲5）と違う"])

    def test_same_row_name_in_other_table(self):
        # 同じページの表①・表③にも「不足分（②－①）」がある。親の表（表②）の範囲の行だけを見る
        self.assertEqual(run7()[0], [])
        self.assertEqual(run7(atai=[atai7(atai="▲6", inyo="不足分（②－①） ▲6 ▲5", bubun="8", retsu="9")])[0], [])
        # 表③を部分の表から除くと、表②の範囲がページの終わりまで延び、同じ見出しの行が2つになって止まる
        rows = [r for r in bubun_rows() if r["n"] not in ("7", "8", "9")]
        p, _ = run7(bubun=rows)
        self.assertIn("行の見出しと数値の行が、親の表の範囲に 2 行ある（1行のはず：不足分（②－①））", p)

    def test_form(self):
        p, _ = run7(atai=[atai7(bubun="")])
        self.assertEqual(p, ["retsu があるのに、bubun が空"])
        p, _ = run7(atai=[atai7(bubun="30")])
        self.assertEqual(p, ["bubun が、shiryo の文書の部分の表に無い（pt:kodomo/honpen の 30）"])
        p, _ = run7(atai=[atai7(retsu="")])
        self.assertEqual(p, ["bubun が行なのに、retsu が空"])
        p, _ = run7(atai=[atai7(retsu="6")])
        self.assertEqual(p, ["bubun が行、retsu が列でない（bubun：行、retsu：行）"])
        p, _ = run7(atai=[atai7(retsu="9")])
        self.assertEqual(p, ["bubun の行と retsu の列の親の表が違う（2 と 7）"])
        p, _ = run7(atai=[atai7(bubun="1", retsu="")])                  # 見出しを指す
        self.assertEqual(p, [])
        p, _ = run7(atai=[atai7(shiryo="doc:yosan-1/2", inyo="3,000,000", atai="3,000,000")])
        self.assertEqual(p, ["shiryo の文書が、文書の表に無い（doc:yosan-1）"])
        p, _ = run7(atai=[atai7(shiryo="ext:soumu-1/2", inyo="充当率90％", atai="90％")])
        self.assertEqual(p, ["bubun を書けない shiryo（ext:soumu-1/2）"])

    def test_page_and_count(self):
        p, _ = run7(atai=[atai7(shiryo="pt:kodomo/honpen/3", inyo="本計画は")], )
        self.assertIn("shiryo のページが、表の tokoro と違う（pt:kodomo/honpen/3 と pt:kodomo/honpen/2）", p)
        rows = bubun_rows() + [dict(bubun_rows()[3], n="10", name="2026 年（R8）", jun="3", torikata="読んだ")]
        p, _ = run7(atai=[atai7(retsu="10")], bubun=rows)
        self.assertEqual(p, ["行の数値は 2 個で、列の jun（3）の数値が無い"])

    def test_yonda(self):
        # 行か表の torikata が「読んだ」なら、数値の検査から外して数える
        p, kazoe = run7(atai=[atai7(atai="▲4", inyo="▲5 ▲4")], bubun=change(bubun_rows(), "3", torikata="読んだ"))
        self.assertEqual(p, [])
        self.assertEqual((kazoe["taisho"], kazoe["yonda"]), (0, 1))
        p, kazoe = run7(bubun=change(bubun_rows(), "2", torikata="読んだ"))
        self.assertEqual((p, kazoe["yonda"]), ([], 1))

    def test_hatsugen(self):
        row = dict(atai="3", shiryo=f"sp:{SID7}", inyo="現在の待機児童数は3名です。", retsu="")
        self.assertEqual(run7(atai=[atai7(bubun=f"sp:{SID7}/2", **row)])[0], [])
        self.assertEqual(run7(atai=[atai7(bubun=f"sp:{SID7}/1-2", **row)])[0], [])     # 続いた段落の形
        p, _ = run7(atai=[atai7(bubun=f"sp:{SID7}/1", **row)])
        self.assertEqual(p, [f"inyo の字が、bubun の段落に無い（sp:{SID7}/1）"])
        p, _ = run7(atai=[atai7(bubun=f"sp:{SID7}/4", **row)])
        self.assertEqual(p, [f"bubun の番号の段落が、発言に無い（sp:{SID7}/4）"])
        p, _ = run7(atai=[atai7(bubun=f"sp:{SID}/1", **row)])
        self.assertEqual(p, [f"bubun の発言が、shiryo の発言と違う（sp:{SID}/1）"])
        p, _ = run7(atai=[atai7(bubun="2", **row)])
        self.assertEqual(p, ["発言を shiryo にした行で、bubun が段落の鍵の形でない（2）"])
        p, _ = run7(atai=[atai7(bubun=f"sp:{SID7}/2", **dict(row, retsu="4"))])
        self.assertEqual(p, ["発言を shiryo にした行に、retsu がある"])

    def test_row_numbers(self):
        self.assertEqual(suji.row_numbers("不足分（②－①） ▲5 ▲4 ▲4 0 0", "不足分（②－①）"), ["▲5", "▲4", "▲4", "0", "0"])
        self.assertEqual(suji.row_numbers("平成 30 年４月 ０ ０ ４ ４ １", "平成30年4月"), ["0", "0", "4", "4", "1"])
        self.assertEqual(suji.row_numbers("一般会計 9,935,000 12.7 △1.6", "一般会計"), ["9,935,000", "12.7", "△1.6"])
        self.assertIsNone(suji.row_numbers("令和10年4月 0 1", "令和1"))             # 見出しの続きに字がある
        self.assertIsNone(suji.row_numbers("1 8 件 件", "1"))                        # 数値でない字がある
        self.assertIsNone(suji.row_numbers("不足分（②－①）", "不足分（②－①）"))    # 数値が無い


def real_inputs():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class TestJitenKankei(unittest.TestCase):
    """時点の関係（SCHEMA.md §7.3）。数値の時点と資料の日付の、年と月の比較で決める。"""

    BUNSHO = {"pt:youho/honpen": {"hiduke": "2026-06"}, "pt:kodomo/honpen": {"hiduke": "2025-03"},
              "doc:yosan-1": {"hiduke": "2025-12-23"}, "doc:fuhyo": {"hiduke": ""}}
    T4 = {"nendo_tsuki": "4"}
    T0 = {"nendo_tsuki": ""}

    def k(self, teigi=None, **kw):
        r = dict(jiten="令和7年4月", nendo="2025", shiryo="pt:youho/honpen/11")
        r.update(kw)
        return suji.jiten_kankei(r, self.T4 if teigi is None else teigi, self.BUNSHO)

    def test_nengetsu(self):
        self.assertEqual(self.k(), suji.KANKEI_MAE)                                              # 2025年4月 と 2026年6月
        self.assertEqual(self.k(shiryo="pt:kodomo/honpen/72"), suji.KANKEI_ATO)                  # 2025年4月 と 2025年3月
        self.assertEqual(self.k(jiten="令和7年3月", nendo="2024", shiryo="pt:kodomo/honpen/72"), suji.KANKEI_MAE)  # 同じ月
        # 1〜3月は、年度（2024）ではなく暦の年（2025）で比較する
        self.assertEqual(self.k(jiten="令和7年2月", nendo="2024", shiryo="pt:kodomo/honpen/72"), suji.KANKEI_MAE)
        self.assertEqual(self.k(jiten="平成31年4月", nendo="2019", shiryo="sp:0000004662_20190614_0094"), suji.KANKEI_MAE)
        self.assertEqual(self.k(jiten="令和元年5月", nendo="2019", shiryo="sp:0000004662_20190401_0001"), suji.KANKEI_ATO)

    def test_hatsugen_no_hi(self):
        # 発言の日は、sid の日付（YYYYMMDD）の年と月。2019年6月14日の答弁が述べる平成31年度の数値は、4月として比較して「前か同じ」
        self.assertEqual(suji.shiryo_nengetsu("sp:0000004662_20190614_0094", {}), (2019, 6))
        self.assertEqual(self.k(jiten="平成31年度", nendo="2019", shiryo="sp:0000004662_20190614_0094"), suji.KANKEI_MAE)
        self.assertEqual(self.k(jiten="令和7年4月", nendo="2025", shiryo="sp:0000008489_20250613_0084"), suji.KANKEI_MAE)

    def test_nendo_to_tsuki(self):
        self.assertEqual(self.k(jiten="令和7年度", shiryo="pt:kodomo/honpen/72"), suji.KANKEI_ATO)     # 2025年4月 と 2025年3月
        self.assertEqual(self.k(jiten="令和6年度", nendo="2024", shiryo="pt:kodomo/honpen/72"), suji.KANKEI_MAE)
        # 月が1〜3の定義は、年度の翌年の暦の年で比較する
        self.assertEqual(self.k(teigi={"nendo_tsuki": "3"}, jiten="令和6年度", nendo="2024", shiryo="pt:kodomo/honpen/72"),
                         suji.KANKEI_MAE)                                                       # 2025年3月 と 2025年3月
        self.assertEqual(self.k(teigi={"nendo_tsuki": "3"}, jiten="令和7年度", nendo="2025", shiryo="pt:kodomo/honpen/72"),
                         suji.KANKEI_ATO)

    def test_nendo_wa_kikan(self):
        k = lambda nendo, shiryo: self.k(teigi=self.T0, jiten="年度", nendo=nendo, shiryo=shiryo)  # noqa: E731
        self.assertEqual(k("2025", "pt:kodomo/honpen/72"), suji.KANKEI_ATO)      # 期間 2025年4月〜2026年3月。資料 2025年3月
        self.assertEqual(k("2024", "pt:kodomo/honpen/72"), suji.KANKEI_TOCHU)    # 期間 2024年4月〜2025年3月。資料 2025年3月
        self.assertEqual(k("2025", "doc:yosan-1/2"), suji.KANKEI_TOCHU)          # 資料 2025年12月
        self.assertEqual(k("2025", "pt:youho/honpen/11"), suji.KANKEI_MAE)       # 資料 2026年6月
        self.assertEqual(k("2026", "pt:youho/honpen/11"), suji.KANKEI_TOCHU)     # 期間 2026年4月〜。資料 2026年6月
        # 注の付いた年度の字（補正）も、年度として扱う
        self.assertEqual(self.k(teigi=self.T0, jiten="令和7年度（12月補正）", shiryo="doc:yosan-1/2"), suji.KANKEI_TOCHU)

    def test_dasanai(self):
        self.assertIsNone(self.k(nendo=""))
        self.assertIsNone(self.k(shiryo=""))
        self.assertIsNone(self.k(shiryo="doc:fuhyo/1"))       # 文書の表の hiduke が空
        self.assertIsNone(self.k(shiryo="doc:nai/1"))         # 文書の表に無い
        self.assertIsNone(self.k(shiryo="plan:nai"))

    def test_jitsubutsu(self):
        """実際の表：どの行にも、3つの関係のどれかか「出さない」が決まる。決定にかかわる行を、中身で選んで確認する。"""
        t = real_tables()
        kk = suji.count_kankei(t["suji"], t["atai"], t["bunsho"])
        self.assertEqual(sum(kk.values()), len(t["atai"]))
        teigi = {r["id"]: r for r in t["suji"]}
        by = {r["bunsho"]: r for r in t["bunsho"]}
        one = lambda **kw: [r for r in t["atai"] if all(r[k] == v for k, v in kw.items())]  # noqa: E731
        r = one(suji="taiki", jiten="平成31年度", shiryo="sp:0000004662_20190614_0094")
        self.assertEqual(len(r), 1)
        self.assertEqual(suji.jiten_kankei(r[0], teigi["taiki"], by), suji.KANKEI_MAE)
        r = one(suji="taiki", shiryo="pt:senryaku2/x1/16", nendo="2025")
        self.assertEqual(suji.jiten_kankei(r[0], teigi["taiki"], by), suji.KANKEI_ATO)
        r = one(suji="yosan-hosei", jiten="令和7年度（12月補正）")
        self.assertEqual(suji.jiten_kankei(r[0], teigi["yosan-hosei"], by), suji.KANKEI_TOCHU)
        self.assertTrue(all(suji.jiten_kankei(x, teigi["kaien"], by) is None for x in one(suji="kaien")))

    def test_schema_no_rei(self):
        """SCHEMA.md §7.3 の実物の例の8行。行を中身で選んで判定し、印が §7.3 の表と同じであること。"""
        t = real_tables()
        teigi = {r["id"]: r for r in t["suji"]}
        by = {r["bunsho"]: r for r in t["bunsho"]}
        rei = [(dict(suji="taiki", jiten="令和7年度", shiryo="pt:senryaku2/x1/16"), "ato"),
               (dict(suji="taiki", jiten="令和7年4月", shiryo="pt:youho/honpen/11"), "mae"),
               (dict(suji="taiki", jiten="平成31年度", shiryo="sp:0000004662_20190614_0094"), "mae"),
               (dict(suji="fusoku", jiten="令和7年度", shiryo="pt:kodomo/honpen/72", atai="▲5"), "ato"),
               (dict(suji="yosan-hosei", jiten="令和7年度（12月補正）", shiryo="doc:yosan-r7-hosei-12/2"), "tochu"),
               (dict(suji="kaien", jiten="2026年7月の広報ひの", atai="令和11年4月"), None),
               (dict(suji="yosan-tosho", jiten="令和8年度", shiryo="doc:yosan-r8-fuhyo/1"), None),
               (dict(suji="taiki", jiten="令和8年4月", shiryo=""), None)]
        for kw, want in rei:
            hit = [r for r in t["atai"] if all(r[k] == v for k, v in kw.items())]
            self.assertEqual(len(hit), 1, kw)
            self.assertEqual(suji.jiten_kankei(hit[0], teigi[kw["suji"]], by), want, kw)

    def test_shirushi_dake(self):
        """データの側が返すのは、3つの印か None だけ。画面の文を返さない（データの構造と画面を分ける）。"""
        self.assertEqual(set(suji.KANKEI), {"ato", "mae", "tochu"})
        t = real_tables()
        kk = suji.count_kankei(t["suji"], t["atai"], t["bunsho"])
        self.assertTrue(set(kk) <= {"ato", "mae", "tochu", None}, set(kk))

    def test_nendo_tsuki_no_katachi(self):
        self.assertEqual(run(teigi=[teigi_row(nendo_tsuki="13")]), ["nendo_tsuki の形が違う（空か、1〜12の数のはず：13）"])
        self.assertEqual(run(teigi=[teigi_row(nendo_tsuki="")]), [])


class TestShurui(unittest.TestCase):
    """shurui の字が、shiryo の原典の文字にあるか（SCHEMA.md §6.2・§6.4）。実際の入力と表で確認する。"""

    def setUp(self):
        self.inp = real_inputs()
        if self.inp is None:
            self.skipTest("入力が無い")
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), suji.ATAI_NAME)
        self.rows, p = suji.read_atai(suji._read_file(path))
        self.assertEqual(p, [])

    def test_ima_no_hyo(self):
        out, kazoe = suji.check_shurui(self.inp, self.rows)
        self.assertEqual([m.naiyo for m in out], [])
        self.assertGreater(kazoe["shurui_taisho"], 0)

    def test_shiryo_ni_nai_ji(self):
        """再編整備計画の待機児童数の表には「実績」の字が無い。書くと止まる。"""
        rows = [dict(r) for r in self.rows]
        r = next(x for x in rows if x["suji"] == "taiki" and x["shiryo"] == "pt:youho/honpen/11")
        self.assertEqual(r["shurui"], "")
        r["shurui"] = "実績"
        out, _ = suji.check_shurui(self.inp, rows)
        self.assertEqual([(m.gyo, m.naiyo) for m in out], [(r["_gyo"], "shurui の字が、shiryo の原典の文字に無い（実績）")])

    def test_genten_no_moji_ga_nai(self):
        """原典の文字が入力に無い資料（総合計画）の行は、検査から除いて数える。"""
        rows = [dict(r) for r in self.rows if r["shiryo"] == "plan:sogo6" and r["shurui"]]
        self.assertTrue(rows)
        out, kazoe = suji.check_shurui(self.inp, rows)
        self.assertEqual(out, [])
        self.assertEqual((kazoe["shurui_taisho"], kazoe["shurui_nozoita"]), (0, len(rows)))

    def test_inp_ga_nai(self):
        self.assertEqual(suji.check_shurui(None, self.rows), ([], suji.Counter()))



def real_tables():
    out = {}
    for name, reader in (("suji", suji.read_suji), ("atai", suji.read_atai), ("bunsho", suji.read_bunsho),
                         ("bubun", suji.read_bubun)):
        with open(os.path.join(suji.TEIGI_DIR, name + ".tsv"), encoding="utf-8") as f:
            rows, p = reader(f.read())
        assert not p, p
        out[name] = rows
    return out


class TestReal7(unittest.TestCase):
    """lock の版の入力と、このリポジトリの表で確認する。入力が lock と合わなければ飛ばす。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.t = real_tables()

    # 子ども・子育て支援事業計画の表②（2号認定）の不足分の行
    FUSOKU2 = dict(suji="fusoku", shiryo="pt:kodomo/honpen/72", kubun="2号認定（3〜5歳・保育）")

    def run_real(self, atai=None, bubun=None):
        t = self.t
        p, _, kazoe = suji.check_all(self.inp, t["suji"], atai or t["atai"], t["bunsho"], bubun or t["bubun"])
        return [(m.hyo, m.gyo, m.naiyo) for m in p], kazoe

    def atai_at(self, gyo):
        return next(r for r in self.t["atai"] if r["_gyo"] == gyo)

    def gyo_of(self, **kw):
        """中身で行を選ぶ（行を足しても変わらないように、行の番号では選ばない）。→ 行の番号。"""
        hit = [r["_gyo"] for r in self.t["atai"] if all(r[k] == v for k, v in kw.items())]
        self.assertEqual(len(hit), 1, kw)
        return hit[0]

    def with_row(self, gyo, **kw):
        return [dict(r, **kw) if r["_gyo"] == gyo else r for r in self.t["atai"]]

    def test_tables_ok(self):
        p, kazoe = self.run_real()
        self.assertEqual(p, [])
        self.assertEqual(kazoe["taisho"], kazoe["atta"])

    def test_other_row(self):
        # 表②の不足分、令和7年度、▲5 の行が、同じ表の「②確保方策」の行を指すと止まる
        g = self.gyo_of(**self.FUSOKU2, nendo="2025")
        r = self.atai_at(g)
        self.assertEqual((r["atai"], r["bubun"], r["retsu"]), ("▲5", "6", "7"))
        p, _ = self.run_real(atai=self.with_row(g, bubun="5"))
        self.assertEqual(p, [(suji.ATAI_NAME, g, "行の数値の 1 つ目（266）が、atai（▲5）と違う")])

    def test_other_column(self):
        # 表②の不足分、令和8年度、▲4 の行が、令和7年度の列を指すと止まる
        g = self.gyo_of(**self.FUSOKU2, nendo="2026")
        self.assertEqual(self.atai_at(g)["retsu"], "8")
        p, _ = self.run_real(atai=self.with_row(g, retsu="7"))
        self.assertEqual(p, [(suji.ATAI_NAME, g, "行の数値の 1 つ目（▲5）が、atai（▲4）と違う")])
        # 待機児童数（再編整備計画の表の5つ目の列）が、小計（4つ目の列）を指すと止まる
        t = self.gyo_of(suji="taiki", shiryo="pt:youho/honpen/11", nendo="2025")
        n = self.gyo_of(suji="nozoku", shiryo="pt:youho/honpen/11", nendo="2025")
        self.assertEqual(self.atai_at(t)["atai"], "3")
        p, _ = self.run_real(atai=self.with_row(t, retsu=self.atai_at(n)["retsu"]))
        self.assertEqual(p, [(suji.ATAI_NAME, t, "行の数値の 4 つ目（15）が、atai（3）と違う")])

    def test_same_row_name_in_other_table(self):
        # 子ども・子育て支援事業計画の72ページには「不足分（②－①）」の行が3つある（表①・②・③）
        raw = suji.page_raw(self.inp, "pt:kodomo/honpen/72")
        self.assertEqual(sum(1 for ln in raw.split("\n") if ln.startswith("不足分（②－①）")), 3)
        bubun = self.t["bubun"]
        hyo = {r["name"][:1]: r for r in bubun if r["bunsho"] == "pt:kodomo/honpen" and r["shu"] == "表"}
        for k, want in (("②", ["▲5", "▲4", "▲4", "0", "0"]), ("③", ["▲6", "▲5", "▲5", "0", "0"])):
            lines, why = suji.table_range(self.inp, bubun, hyo[k])
            self.assertEqual(why, "")
            self.assertEqual(suji.row_in_range(lines, "不足分（②－①）"), (want, ""), k)
        # 表③を部分の表から除くと、表②の範囲に「不足分（②－①）」が2行入り、止まる
        n3 = hyo["③"]["n"]
        rest = [r for r in bubun if not (r["bunsho"] == "pt:kodomo/honpen" and n3 in (r["n"], r["oya"]))]
        atai = [r for r in self.t["atai"] if not (r["shiryo"] == "pt:kodomo/honpen/72" and r["kubun"].startswith("3号"))]
        p, _ = self.run_real(atai=atai, bubun=rest)
        gyo = next(r["_gyo"] for r in bubun if r["bunsho"] == "pt:kodomo/honpen" and r["oya"] == hyo["②"]["n"]
                   and r["name"] == "不足分（②－①）")
        ng = "行の見出しと数値の行が、親の表の範囲に 2 行ある（1行のはず：不足分（②－①））"
        self.assertIn((suji.BUBUN_NAME, gyo, ng), p)
        self.assertIn((suji.ATAI_NAME, self.gyo_of(**self.FUSOKU2, nendo="2025"), ng), p)


# ---------------------------------------------------------------- 施設（SCHEMA.md §2・§7.2・§7.4）

SHISETSU_REF = [
    dict(key="fa:minamihizusa-yo", name="南比都佐幼稚園", aliases=""),
    dict(key="fa:kaneka", name="みらいしゃくなげ保育園",
         aliases="鎌掛幼稚園（開設から）;日野幼稚園鎌掛分園（平成１０年度から）;保育所あおぞら園鎌掛分園（平成２８年度から）"),
    dict(key="fa:sakuradani-1", name="桜谷こども園第１園舎", aliases=""),
    dict(key="fa:sakuradani-2", name="桜谷こども園第２園舎", aliases=""),
]


def fake_shisetsu():
    inp = fake7()
    inp._shisetsu = [dict(r) for r in SHISETSU_REF]
    return inp


class TestShisetsu(unittest.TestCase):
    """文書の部分の表の shisetsu（SCHEMA.md §7.2・§7.4）。"""

    REF = {r["key"]: r for r in SHISETSU_REF}

    def icchi(self, name, shisetsu):
        return suji.shisetsu_icchi(dict(name=name, shisetsu=shisetsu), self.REF)

    def test_icchi(self):
        """§7.2 の判定の条件：name が、施設の name か aliases（「（…から）」の注記を除く）と、§3 の正規化のあとで一致する。"""
        self.assertTrue(self.icchi("南比都佐幼稚園", "fa:minamihizusa-yo"))
        self.assertTrue(self.icchi("南比都佐 幼稚園", "fa:minamihizusa-yo"))          # 空白は §3 の正規化で除く
        self.assertTrue(self.icchi("保育所あおぞら園鎌掛分園", "fa:kaneka"))           # aliases の注記を除いて一致
        self.assertFalse(self.icchi("保育所あおぞら園鎌掛分園（平成２８年度から）", "fa:kaneka"))
        self.assertFalse(self.icchi("南比幼稚園 676㎡", "fa:minamihizusa-yo"))
        self.assertFalse(self.icchi("あおぞら園 鎌掛分園", "fa:kaneka"))
        # 鍵が複数ある行は、どの鍵の施設とも一致する場合だけ一致。単語の一致で決めない
        self.assertFalse(self.icchi("桜谷こども園", "fa:sakuradani-1;fa:sakuradani-2"))
        self.assertFalse(self.icchi("桜谷こども園第１園舎", "fa:sakuradani-1;fa:sakuradani-2"))
        self.assertIsNone(self.icchi("南比都佐幼稚園", ""))
        self.assertIsNone(self.icchi("南比都佐幼稚園", "fa:nai"))

    def test_kazoe(self):
        rows = change(change(bubun_rows(), "3", shisetsu="fa:minamihizusa-yo", name="不足分（②－①）"),
                      "6", shisetsu="fa:sakuradani-1;fa:sakuradani-2")
        p, kazoe = run7(bubun=rows, inp=fake_shisetsu())
        self.assertEqual(p, [])
        self.assertEqual((kazoe["shisetsu_icchi"], kazoe["shisetsu_fuicchi"]), (0, 2))
        rows = change(bubun_rows(), "2", shisetsu="fa:minamihizusa-yo", name="南比都佐幼稚園")
        out, kazoe = suji.check_shisetsu(fake_shisetsu(), [dict({"shisetsu": ""}, **r, _gyo=i) for i, r in enumerate(rows, 2)])
        self.assertEqual((out, kazoe["shisetsu_icchi"], kazoe["shisetsu_fuicchi"]), ([], 1, 0))

    def test_kagi(self):
        """shisetsu の鍵は、施設の参照表の key にある。「;」で区切った空の鍵も止まる。"""
        for v, want in (("fa:nai", "fa:nai"), ("fa:kaneka;fa:nai", "fa:nai"), ("fa:kaneka;", "空"),
                        ("fa:kaneka; fa:minamihizusa-yo", " fa:minamihizusa-yo"), ("kaneka", "kaneka")):
            with self.subTest(v=v):
                p, _ = run7(bubun=change(bubun_rows(), "6", shisetsu=v), inp=fake_shisetsu())
                self.assertEqual(p, [f"shisetsu の鍵が、施設の参照表に無い（{want}）"])

    def test_yomanai(self):
        """shisetsu がある行が無ければ、施設の参照表を読まない。"""
        inp = fake7()
        inp.shisetsu = None          # 呼べば止まる
        self.assertEqual(run7(inp=inp)[0], [])


class TestShisetsuReal(unittest.TestCase):
    """lock の版の hino-ronten の、施設の参照表と施設の記録（SCHEMA.md §1・§2）。"""

    YOHO = ("fa:aozora", "fa:hino-yo", "fa:hinona", "fa:hisa-yo", "fa:kaneka", "fa:kobato", "fa:minamihizusa-yo",
            "fa:nishioji-yo", "fa:sakuradani-1", "fa:sakuradani-2", "fa:shin-kodomoen", "fa:warabe", "fa:warabe2")

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")

    def test_sanshohyo(self):
        ref = {r["key"]: r for r in self.inp.shisetsu()}
        self.assertEqual(len(ref), len(self.inp.shisetsu()))
        for k in self.YOHO:
            self.assertIn(k, ref)
        self.assertTrue(all(suji.RE_SHISETSU.fullmatch(k) for k in ref), sorted(ref))

    def test_kiroku(self):
        rows = self.inp.shisetsu_kiroku()
        self.assertTrue(rows)
        self.assertTrue(all(r["status"] == inputs.CONFIRMED for r in rows))
        keys = {r["key"] for r in self.inp.shisetsu()}
        self.assertTrue({r["facility"] for r in rows} <= keys)

    def test_schema_no_rei(self):
        """SCHEMA.md §7.2 の実物の例。"""
        ref = {r["key"]: r for r in self.inp.shisetsu()}
        rei = [("南比都佐幼稚園", "fa:minamihizusa-yo", True), ("南比幼稚園 676㎡", "fa:minamihizusa-yo", False),
               ("こども園B（こばと園の増築）", "fa:kobato", False), ("あおぞら園 鎌掛分園", "fa:kaneka", False),
               ("公立 新施設（１園）R10.4〜", "fa:shin-kodomoen", False),
               ("私立 わらべ保育園（2園）", "fa:warabe;fa:warabe2", False),
               ("桜谷こども園", "fa:sakuradani-1;fa:sakuradani-2", False),
               ("保育所あおぞら園鎌掛分園", "fa:kaneka", True)]
        for name, k, want in rei:
            self.assertIs(suji.shisetsu_icchi(dict(name=name, shisetsu=k), ref), want, name)


# ---------------------------------------------------------------- 文書どうしの関係（SCHEMA.md §7.6・§7.4）

def bunsho_youho():
    return bunsho_row(bunsho="pt:youho/honpen", namae="a", konkyo="", konkyo_tokoro="", hiduke="", hiduke_moto="",
                      chu="無い")


def kankei_row(**kw):
    r = dict(kara="pt:kodomo/honpen", e="pt:youho/honpen", hyogen="に基づく",
             inyo="子ども・子育て支援法第 61 条に基づく計画です。", tokoro="pt:kodomo/honpen/3", chu="")
    r.update(kw)
    return r


class TestBunshoKankei(unittest.TestCase):
    def run_k(self, *rows):
        return run7(bunsho=[bunsho_row(), bunsho_youho()], kankei=list(rows))[0]

    def test_ok(self):
        self.assertEqual(self.run_k(kankei_row()), [])
        self.assertEqual(self.run_k(), [])

    def test_bunsho(self):
        self.assertEqual(self.run_k(kankei_row(e="pt:nai/honpen")), ["e が文書の表に無い（pt:nai/honpen）"])
        p = self.run_k(kankei_row(kara="doc:nai", tokoro="doc:nai/1"))
        self.assertIn("kara が文書の表に無い（doc:nai）", p)

    def test_tokoro_inyo_hyogen(self):
        self.assertEqual(self.run_k(kankei_row(tokoro="pt:youho/honpen/2")),
                         ["tokoro が、kara の文書のページの鍵でない（pt:youho/honpen/2）"])
        self.assertEqual(self.run_k(kankei_row(tokoro="pt:kodomo/honpen/2")),
                         ["inyo が、tokoro のページの原典の文字に無い（pt:kodomo/honpen/2）"])
        self.assertEqual(self.run_k(kankei_row(hyogen="を上位計画とし")), ["hyogen が、inyo の中に無い（を上位計画とし）"])
        self.assertEqual(self.run_k(kankei_row(hyogen="")), ["必ず書く列が空（hyogen）"])
        self.assertEqual(self.run_k(kankei_row(inyo="", hyogen="")), ["必ず書く列が空（hyogen・inyo）"])

    def test_columns(self):
        rows, p = suji.read_bunsho_kankei("kara\te\thyogen\tinyo\ttokoro\n")
        self.assertEqual([m.naiyo for m in p], ["列が足りない（chu）"])

    def test_real(self):
        inp = real_inputs()
        if inp is None:
            self.skipTest("入力が無い")
        t = real_tables()
        with open(os.path.join(suji.TEIGI_DIR, "bunsho-kankei.tsv"), encoding="utf-8") as f:
            rows, p = suji.read_bunsho_kankei(f.read())
        self.assertEqual(p, [])
        names = {r["bunsho"] for r in t["bunsho"]}
        self.assertEqual([m.naiyo for m in suji.check_bunsho_kankei(inp, rows, names)], [])
        # 再編整備計画 令和7年3月の版の「基本とした」の行を、別の文書のページに置くと止まる
        r = next(x for x in rows if x["kara"] == "pt:youho/honpen-202503")
        bad = [dict(r, tokoro="pt:youho/honpen-202503/24")]
        self.assertEqual([m.naiyo for m in suji.check_bunsho_kankei(inp, bad, names)],
                         ["inyo が、tokoro のページの原典の文字に無い（pt:youho/honpen-202503/24）"])


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

    def test_kankei_dake(self):
        """文書どうしの関係の表があり、文書の表と文書の部分の表が無ければ止まる。"""
        code, _, err = self.main({"suji.tsv": tsv(suji.SUJI_COLUMNS, [teigi_row()]),
                                  "atai.tsv": tsv(suji.ATAI_COLUMNS, [atai_row()]),
                                  "bunsho-kankei.tsv": tsv(suji.BUNSHO_KANKEI_COLUMNS, [kankei_row()])})
        self.assertEqual(code, 1)
        self.assertIn("teigi/bunsho-kankei.tsv がある", err)

    def test_problems(self):
        code, _, err = self.main({"suji.tsv": tsv(suji.SUJI_COLUMNS, [teigi_row(), teigi_row()]),
                                  "atai.tsv": tsv(suji.ATAI_COLUMNS, [atai_row(nendo="R7")])})
        self.assertEqual(code, 1)
        self.assertIn("問題が 3 件", err)
        self.assertIn("teigi/suji.tsv の 3 行目：定義の id が重なっている（taiki）", err)
        self.assertIn("teigi/atai.tsv の 2 行目：nendo が西暦4桁でない（R7）", err)


if __name__ == "__main__":
    unittest.main()
