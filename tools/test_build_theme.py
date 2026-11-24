"""テーマ1つを1ページにするツール（tools/build_theme.py）と、テーマの表の検査（tools/suji.py の check_theme）。

テーマの表の検査の当たり方、会議録の町の答弁と議員の発言の判定、施設の表の行が複数の施設を指す場合、施設の表に無い施設の
並べ方、使わない言葉で止まること。
"""
import copy
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import build_theme as bt  # noqa: E402
import inputs  # noqa: E402
import ronten  # noqa: E402
import suji  # noqa: E402
from test_suji import FakeGaibu, tsv  # noqa: E402

TODAY = datetime.date(2026, 11, 24)
SID_G = "0000000001_20250310_0001"     # 議員の発言（役職「3番」）
SID_T = "0000000001_20260309_0002"     # 町の答弁（役職「子ども支援課長」）
SID_C = "0000000001_20260309_0003"     # 議長の発言
KK = "doc:jigyo-k"
KOHO = "doc:koho-1"
KAKUNIN2 = "2者が画像で確認（2026-11-24）"
D = bs.read_design()


class Fake(FakeGaibu):
    """FakeGaibu に、発言者の役職の読み口を足したもの。"""

    def __init__(self, roles=None, **kw):
        super().__init__(**kw)
        self._roles = roles or {}

    def role(self, sid):
        return self._roles.get(sid) if sid in self._st else None


def theme_defs():
    rows = [("名前", "保育の再編"), ("施設", "fa:hino-yo"), ("施設", "fa:s1"), ("施設", "fa:s2"), ("施設", "fa:shin"),
            ("資料", KOHO), ("系列", "youho")]
    return [dict(theme="hoiku", kind=k, value=v, source="", views="", reviewer="x", date="2026-10-27", note="")
            for k, v in rows]


def katei(**kw):
    rows = [dict(step="1", name="懇話会", **{"from": "2022-07-12", "to": "2024-01-12"},
                 sources="doc:gijiroku-1/1", quote="令和4年7月12日"),
            dict(step="2", name="計画の策定", **{"from": "2022-07", "to": ""},
                 sources=f"sp:{SID_T},sp:{SID_G}", quote="計画を策定しました。"),
            dict(step="3", name="提言", **{"from": "2021-01", "to": "2021-01"}, sources=f"{KOHO}/1",
                 quote="町は幼保の再編を進めています。")]
    out = []
    for r in rows:
        x = dict(theme="hoiku", cycle="", status="confirmed", reviewer="x", date="2026-10-27", note="")
        x.update(r)
        x.update(kw.get(r["step"], {}))
        out.append(x)
    return out


def kiroku(**kw):
    def k(fa, aspect, value, source, date, quote, kind="いまのこと", target=""):
        return dict(facility=fa, aspect=aspect, value=value, source=source, source_date=date, quote=quote,
                    target=target, kind=kind, prev="", status="confirmed", reviewer="x", date="2026-11-05", note="")
    rows = [k("fa:hino-yo", "運営", "直営", f"{KK}/2", "2025-08", "日野幼稚園"),
            k("fa:s1", "運営", "直営", f"{KK}/2", "2025-08", "桜谷こども園"),
            k("fa:s2", "運営", "直営", f"{KK}/2", "2025-08", "桜谷こども園"),
            k("fa:hino-yo", "状態", "休園", f"sp:{SID_T}", "2026-03-09", "休園する予定です。", kind="予定",
              target="令和8年度"),
            k("fa:shin", "状態", "開設", f"sp:{SID_G}", "2025-03-10", "新こども園の開設を問います。", kind="予定")]
    rows += kw.get("more", [])
    return rows


def fake(roles=None, ki=None, ka=None):
    return Fake(
        roles=roles or {SID_G: "3番", SID_T: "子ども支援課長", SID_C: "議長"},
        statements={SID_G: ("山田太郎", "新こども園の開設を問います。"),
                    SID_T: ("森次郎", "計画を策定しました。\n休園する予定です。"),
                    SID_C: ("川田三郎", "休憩します。")},
        docs={"jigyo-k": {"id": "jigyo-k", "title": "構想", "url": "https://example.jp/k.pdf", "archive_url": "",
                          "category": "jigyo", "date": ""},
              "koho-1": {"id": "koho-1", "title": "お知らせ", "url": "https://example.jp/h.pdf", "archive_url": "",
                         "category": "koho", "date": "2026-07"},
              "gijiroku-1": {"id": "gijiroku-1", "title": "第1回議事録", "url": "https://example.jp/g.pdf",
                             "archive_url": "", "category": "shingi", "date": "2022-07-12"}},
        doc_texts={("jigyo-k", "text"): "構想\f■施設の表■\n日野幼稚園\n桜谷こども園\n計\n定員",
                   ("koho-1", "text"): "お知らせ\n町は幼保の再編を進めています。構想を基に整備します。",
                   ("gijiroku-1", "text"): "第1回 令和4年7月12日"},
        ronten={ronten.THEMES: theme_defs(), ronten.LINEAGE: [dict(series="youho", edition="", plan="youho")],
                ronten.KATEI: ka if ka is not None else katei()},
        shisetsu=[dict(key="fa:hino-yo", name="日野幼稚園", aliases=""),
                  dict(key="fa:s1", name="桜谷こども園第１園舎", aliases=""),
                  dict(key="fa:s2", name="桜谷こども園第２園舎", aliases=""),
                  dict(key="fa:shin", name="新こども園", aliases="新施設（令和7年から）;仮の園")],
        shisetsu_kiroku=ki if ki is not None else kiroku())


def bunsho_rows():
    return [dict(bunsho=KK, namae="構想", shurui="jigyo", hiduke="2025-08", hiduke_moto=f"{KK}/1", chu="根拠：全ページを探した"),
            dict(bunsho=KOHO, namae="お知らせ", shurui="koho", hiduke="2026-07", hiduke_moto=f"{KOHO}/1",
                 chu="根拠：全ページを探した")]


def bubun_rows(**kw):
    def b(n, oya, shu, name, jun="", matome="", shisetsu="", shisetsu_kakunin=""):
        return dict(bunsho=KK, n=n, oya=oya, shu=shu, name=name, tokoro=f"{KK}/2", jun=jun, matome=matome,
                    shisetsu=shisetsu, shisetsu_kakunin=shisetsu_kakunin, torikata="読んだ", chu=KAKUNIN2)
    rows = [b("1", "", "表", "■施設の表■"),
            b("2", "1", "行", "定員"),
            b("3", "1", "列", "日野幼稚園", "1", "幼稚園", "fa:hino-yo"),
            b("4", "1", "列", "桜谷こども園", "2", "こども園", "fa:s1;fa:s2", "依頼者が確認（2026-11-24）"),
            b("5", "1", "列", "計", "3")]
    return [dict(r, **kw.get(r["n"], {})) for r in rows]


def atai_rows():
    a = dict(suji="teiin", kubun="", jiten="令和7年4月1日現在", nendo="2025", atai="180", shurui="", jotai=suji.ARU,
             shiryo=f"{KK}/2", inyo="", hani="", kakunin="2026-11-24", chu=KAKUNIN2, bubun="2", retsu="3")
    return [a, dict(a, atai="120", retsu="4")]


def kankei_rows():
    return [dict(kara=KOHO, e=KK, hyogen="を基に", inyo="構想を基に整備します。", tokoro=f"{KOHO}/1", chu="")]


def theme_rows(*extra):
    return [dict(theme="hoiku", shu="施設の表", jun="1", inyo="", tokoro=f"{KK}/2", hyo="1", chu="")] + list(extra)


def tables(theme=None, bubun=None):
    s, p1 = suji.read_suji(tsv(suji.SUJI_COLUMNS, [dict(id="teiin", name="定員", nani="施設の定員", tani="人",
                                                        kettei="案")]))
    a, p2 = suji.read_atai(tsv(suji.ATAI_COLUMNS, atai_rows()))
    b, p3 = suji.read_bunsho(tsv(suji.BUNSHO_COLUMNS, bunsho_rows()))
    c, p4 = suji.read_bubun(tsv(suji.BUBUN_COLUMNS, bubun if bubun is not None else bubun_rows()))
    k, p5 = suji.read_bunsho_kankei(tsv(suji.BUNSHO_KANKEI_COLUMNS, kankei_rows()))
    t, p6 = suji.read_theme(tsv(suji.THEME_COLUMNS, theme if theme is not None else theme_rows()))
    assert not (p1 + p2 + p3 + p4 + p5 + p6), p1 + p2 + p3 + p4 + p5 + p6
    return dict(suji=s, atai=a, bunsho=b, bubun=c, kankei=k, theme=t)


def theme_check(rows, inp=None, bubun=None):
    """テーマの表の行の並び → check_all のうち、テーマの表の問題の内容の並び。"""
    t = tables(theme=rows, bubun=bubun)
    out, _, _ = suji.check_all(inp or fake(), t["suji"], t["atai"], t["bunsho"], t["bubun"], t["kankei"], t["theme"])
    return [m.naiyo for m in out if m.hyo == suji.THEME_NAME]


class TestThemeCheck(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(theme_check(theme_rows()), [])

    def test_setsumei(self):
        ok = dict(theme="hoiku", shu="説明の文", jun="1", inyo="町は幼保の再編を進めています。", tokoro=f"{KOHO}/1",
                  hyo="", chu="依頼者が PDF で確認（2026-11-24）")
        self.assertEqual(theme_check(theme_rows(ok)), [])
        # 広報ひのの行に、依頼者の確認の記録が無い（日付の形が違う場合も無いものとする）
        for chu in ("", "依頼者が PDF で確認（2026-13-01）", KAKUNIN2):
            with self.subTest(chu=chu):
                p = theme_check(theme_rows(dict(ok, chu=chu)))
                self.assertEqual(len(p), 1)
                self.assertIn("依頼者が PDF で確認", p[0])
        # inyo がページの原典の文字に無い。こちらで書いた文は入らない
        p = theme_check(theme_rows(dict(ok, inyo="町は保育を充実させます。")))
        self.assertEqual(p, [f"inyo が、tokoro のページの原典の文字に無い（{KOHO}/1）"])
        self.assertEqual(theme_check(theme_rows(dict(ok, inyo=""))), ["「説明の文」の行で、inyo が空"])
        self.assertEqual(len(theme_check(theme_rows(dict(ok, hyo="1")))), 1)          # 説明の文に hyo がある
        # tokoro の文書が文書の表に無い。ページの鍵でない
        self.assertEqual(theme_check(theme_rows(dict(ok, tokoro="doc:gijiroku-1/1"))),
                         ["tokoro の文書が、文書の表に無い（doc:gijiroku-1）"])
        self.assertEqual(len(theme_check(theme_rows(dict(ok, tokoro=KOHO)))), 1)

    def test_shu_jun_theme(self):
        r = theme_rows()[0]
        self.assertEqual(len(theme_check([dict(r, shu="施設の一覧")])), 1)
        self.assertEqual(theme_check([dict(r, jun="0")]), ["jun が1からの整数でない（0）"])
        p = theme_check([dict(r, theme="kaigo")])
        self.assertEqual(p, ["テーマの定義に、theme（kaigo）の kind「名前」の行が無い"])
        s = dict(theme="hoiku", shu="説明の文", jun="1", inyo="構想を基に整備します。", tokoro=f"{KOHO}/1", hyo="",
                 chu="依頼者が PDF で確認（2026-11-24）")
        p = theme_check(theme_rows(s, dict(s, inyo="町は幼保の再編を進めています。")))
        self.assertEqual(p, ["同じ theme と shu の中で、jun が重なっている（1）"] * 2)

    def test_shisetsu_hyo(self):
        r = theme_rows()[0]
        # テーマごとに1行まで
        p = theme_check([r, dict(r, jun="2")])
        self.assertEqual(len(p), 2)
        self.assertTrue(all("1行まで" in m for m in p))
        # hyo が表でない（行を指している）、無い番号
        self.assertEqual(len(theme_check([dict(r, hyo="2")])), 1)
        self.assertEqual(len(theme_check([dict(r, hyo="9")])), 1)
        # tokoro が表の tokoro と違う
        self.assertEqual(theme_check([dict(r, tokoro=f"{KK}/1")]), [f"tokoro が、表の tokoro（{KK}/2）と違う（{KK}/1）"])
        # 表の行と列に、shisetsu がある部分が無い
        bub = bubun_rows(**{"3": dict(shisetsu=""), "4": dict(shisetsu="", shisetsu_kakunin="")})
        self.assertEqual(theme_check([r], bubun=bub), ["表（1）の行と列に、shisetsu がある部分が無い"])
        # inyo がある
        self.assertEqual(theme_check([dict(r, inyo="構想")]), ["「施設の表」の行に inyo がある"])


class TestPage(unittest.TestCase):
    def setUp(self):
        self.kotoba = bn.read_kotoba()

    def build(self, t=None, inp=None, design=D):
        return bt.build(inp or fake(), t or tables(), "hoiku", self.kotoba, TODAY, design=design)

    def stop(self, **kw):
        with self.assertRaises(bt.Stop) as c:
            self.build(**kw)
        return {k for k, _ in c.exception.problems}, c.exception.problems

    def test_page(self):
        page, info = self.build()
        self.assertEqual((info["katei"], info["kiroku"], info["shisetsu"], info["hyo"], info["setsumei"]),
                         (3, 5, 4, 2, 0))
        self.assertEqual(info["inyo"], 8)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))
        self.assertNotIn("<script", page)
        self.assertNotIn("<link", page)
        self.assertNotIn(bn.A, page)
        self.assertIn("<h1>保育の再編</h1>", page)
        self.assertIn(D.bun("atama-theme"), page)
        # 説明の文の行が無いテーマは、見出しも出さない
        self.assertNotIn(D.kotoba("テーマの表 shu が「説明の文」"), page)
        # 経過は from の年月の順（同じなら step の順）。to が空なら「〜」だけ、from と同じなら from だけ
        i1, i2, i3 = page.index("<td>提言</td>"), page.index("<td>懇話会</td>"), page.index("<td>計画の策定</td>")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        self.assertIn("<td>2021年1月</td><td>提言</td>", page)
        self.assertIn("<td>2022年7月12日〜2024年1月12日</td>", page)
        self.assertIn("<td>2022年7月〜</td>", page)
        # 文書の表に無い資料は sources.tsv の title、広報ひのは号と題
        self.assertIn("第1回議事録　1ページ", page)
        self.assertIn("広報ひの 2026年7月号「お知らせ」　1ページ", page)
        # 施設ごとの記述：前の名前、資料の日付の順、target は括弧
        self.assertIn(f"{D.kotoba('施設の参照表 aliases')}：新施設（令和7年から）、仮の園", page)
        self.assertIn("<td>休園（令和8年度）</td>", page)
        self.assertIn(D.bun("kubun-setsumei"), page)
        # 資料：テーマの資料（kind「資料」）の関係の行。相手の名前と表現
        self.assertIn(D.bun("aite", hyogen="を基に", aite="構想（2025年8月）"), page)
        self.assertIn(D.bun("owari-theme"), page)

    def test_kaigiroku_kubun(self):
        # 会議録は、発言者の役職から、町の答弁か議員の発言かを決める。発言者の名前は出さない
        page, _ = self.build()
        giin = bs.RE_KAGIKAKKO.search(D.kotoba("会議録の発言者の役職が「数字＋番」")).group(1)
        toben = bs.RE_KAGIKAKKO.search(D.kotoba("会議録の発言者の役職が、議長でも「数字＋番」でもない")).group(1)
        self.assertIn(D.bun("kaigiroku-kubun", hi="2025年3月10日", kubun=giin), page)
        self.assertIn(D.bun("kaigiroku-kubun", hi="2026年3月9日", kubun=toben), page)
        for name in ("山田太郎", "森次郎"):
            self.assertNotIn(name, page)
        # 全角の番号も議員とする
        page, _ = self.build(inp=fake(roles={SID_G: "１２番", SID_T: "町長"}))
        self.assertIn(D.bun("kaigiroku-kubun", hi="2025年3月10日", kubun=giin), page)
        # 役職が議長か空の発言は、区分を決められないので止まる
        for role in ("議長", "", "副議長"):
            with self.subTest(role=role):
                ki = kiroku(more=[dict(kiroku()[0], aspect="状態", value="x", source=f"sp:{SID_C}",
                                       source_date="2026-03-09", quote="休憩します。")])
                inp = fake(roles={SID_G: "3番", SID_T: "子ども支援課長", SID_C: role}, ki=ki)
                kinds, p = self.stop(inp=inp)
                self.assertEqual(kinds, {"(f) 資料の名前"})
                self.assertIn(f"sp:{SID_C}", p[0][1])

    def test_shisetsu_hyo(self):
        page, _ = self.build()
        # 行は shisetsu がある列だけ（「計」は出さない）。matome は字だけで、欄の見出しは空
        self.assertNotIn("<th>計", page)
        head = (f"<thead><tr><th></th><th></th><th>{D.kotoba('施設の記録 aspect が「運営」')}</th>"
                f"<th>{D.bun('retsu-tani', name='定員', tani='人')}</th></tr></thead>")
        self.assertIn(head, page)
        self.assertIn("<tr><th><a href='#fa-hino-yo'>日野幼稚園</a></th><td>幼稚園</td><td>直営</td>"
                      "<td class=r>180</td></tr>", page)
        # 行が複数の施設を指す：施設の参照表の name を添え、施設ごとの記述へのリンクにする。運営は重なりを除く
        self.assertIn("<tr><th>桜谷こども園<br><span class=s><a href='#fa-s1'>桜谷こども園第１園舎</a>、"
                      "<a href='#fa-s2'>桜谷こども園第２園舎</a></span></th><td>こども園</td><td>直営</td>"
                      "<td class=r>120</td></tr>", page)
        self.assertIn("<h3 id='fa-s1'>桜谷こども園第１園舎</h3>", page)
        # 数値の資料の名前と時期を、表の上の文で示す
        self.assertIn(D.bun("theme-suji", name="定員", shiryo="構想（2025年8月）　" + D.bun("page", n="2"),
                            jiten="令和7年4月1日現在"), page)
        # 施設の表に無い施設は、表の下に並べる
        self.assertIn(D.bun("hyo-ni-nai", shisetsu="<a href='#fa-shin'>新こども園</a>"), page)
        # 施設ごとの記述は、表の施設が先
        self.assertLess(page.index("id='fa-s2'"), page.index("id='fa-shin'"))

    def test_no_shisetsu_hyo(self):
        # 施設の表の行が無いテーマ：施設の表と、表に無い施設の文を出さない
        page, info = self.build(t=tables(theme=[]))
        self.assertEqual(info["hyo"], 0)
        self.assertNotIn(D.kotoba("テーマの表 shu が「施設の表」"), page)
        self.assertNotIn("<thead><tr><th></th>", page)
        self.assertIn("<h3 id='fa-shin'>新こども園</h3>", page)

    def test_setsumei_page(self):
        s = dict(theme="hoiku", shu="説明の文", jun="2", inyo="構想を基に整備します。", tokoro=f"{KOHO}/1", hyo="",
                 chu="依頼者が PDF で確認（2026-11-24）")
        page, info = self.build(t=tables(theme=theme_rows(s, dict(s, jun="1", inyo="町は幼保の再編を進めています。"))))
        self.assertEqual(info["setsumei"], 2)
        self.assertIn(f"<h2>{D.kotoba('テーマの表 shu が「説明の文」')}</h2>", page)
        self.assertLess(page.index("「町は幼保の再編を進めています。」"), page.index("「構想を基に整備します。」（"))

    def test_stop_table(self):
        s = dict(theme="hoiku", shu="説明の文", jun="1", inyo="町は幼保の再編を進めています。", tokoro=f"{KOHO}/1",
                 hyo="", chu="")
        kinds, _ = self.stop(t=tables(theme=theme_rows(s)))
        self.assertEqual(kinds, {"(a) 表の検査"})

    def test_stop_mikakunin(self):
        bub = bubun_rows(**{"4": dict(shisetsu_kakunin="")})
        kinds, p = self.stop(t=tables(bubun=bub))
        self.assertEqual(kinds, {"(g) 施設の表"})
        self.assertIn("施設の割り当てが未確認", p[0][1])

    def test_stop_quote(self):
        ki = kiroku()
        ki[0] = dict(ki[0], quote="書かれていない文")
        kinds, _ = self.stop(inp=fake(ki=ki))
        self.assertEqual(kinds, {"(f) 引用の照合"})
        kinds, _ = self.stop(inp=fake(ka=katei(**{"1": dict(quote="令和5年")})))
        self.assertEqual(kinds, {"(f) 引用の照合"})

    def test_stop_word(self):
        # 画面の文に、使わない言葉が残れば止まる
        d = copy.deepcopy(D)
        d.h2["keika-setsumei"] = "時期の古い順に記載しています。"
        kinds, _ = self.stop(design=d)
        self.assertEqual(kinds, {"(b) 使わない言葉"})
        # 施設の記録の項目（aspect）は検査の対象
        ki = kiroku(more=[dict(kiroku()[0], aspect="対応")])
        kinds, p = self.stop(inp=fake(ki=ki))
        self.assertEqual(kinds, {"(b) 使わない言葉"})
        # 施設の記録の value・quote、過程の記録の name は、検査の対象にしない
        page, _ = self.build(inp=fake(ka=katei(**{"2": dict(name="記載の対応")})))
        self.assertIn("<td>記載の対応</td>", page)

    def test_stop_design(self):
        d = copy.deepcopy(D)
        del d.h2["midashi-keika"]
        kinds, _ = self.stop(design=d)
        self.assertEqual(kinds, {"(e) デザインシステムとの対応"})
        self.assertEqual(bt.design_problems(D), [])

    def test_hidari(self):
        # テーマのページの左の列の形（表の名前と列。「、」で区切った列もそれぞれ確認する）
        for k in ("過程の記録 from、to", "施設の記録 value、target", "文書どうしの関係の表 kara、e",
                  "テーマの表 shu が「説明の文」", "会議録の発言者の役職が「数字＋番」"):
            self.assertEqual(bs.hidari_problems(k), [], k)
        self.assertEqual(len(bs.hidari_problems("過程の記録 from、tsugi")), 1)
        self.assertEqual(len(bs.hidari_problems("テーマの表 iro")), 1)


def real_inputs():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class TestReal(unittest.TestCase):
    """lock の版の入力と実際の表で、幼保のテーマのページを作る。施設の表は、基本構想の14ページの表（文書の部分の表の18）。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.tables, cls.read_problems = bt.read_tables()
        t, p = suji.read_theme(tsv(suji.THEME_COLUMNS, [dict(theme="hoiku", shu="施設の表", jun="1",
                                                             tokoro="doc:jigyo-shinkodomoen-kousou/14", hyo="18")]))
        assert not p
        cls.tables["theme"] = t

    def test_hoiku(self):
        page, info = bt.build(self.inp, self.tables, "hoiku", bn.read_kotoba(), TODAY, self.read_problems, D)
        self.assertEqual((info["katei"], info["kiroku"], info["shisetsu"], info["hyo"]), (13, 69, 13, 10))
        self.assertEqual(info["inyo"], 82)
        self.assertIn("<h1>幼児教育・保育施設の再編</h1>", page)
        self.assertIn("<a href='#fa-sakuradani-1'>", page)
        self.assertIn(D.bun("hyo-ni-nai", shisetsu="<a href='#fa-hinona'>みらいひのな保育園</a>、"
                                                   "<a href='#fa-shin-kodomoen'>新こども園</a>"), page)
        self.assertIn("<td>幼稚園</td><td>直営</td><td class=r>180</td><td class=r>69</td><td class=r>大窪331番地</td>",
                      page)


if __name__ == "__main__":
    unittest.main()
