"""tools/bunya.py と tools/build_bunya.py のテスト（SCHEMA.md 7.11）。"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_bunya as bb  # noqa: E402
import build_mcp as bm  # noqa: E402
import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import bunya as bu  # noqa: E402
import inputs  # noqa: E402

D = bs.read_design()


def inp_or_none():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


def yg(bunya, wadai="", mayoi=""):
    return dict(bunya=bunya, wadai=wadai, mayoi=mayoi)


W = [dict(namae="国保", matome="国民健康保険", id="wadai-kokuho", chu=""),
     dict(namae="国民健康保険", matome="国民健康保険", id="wadai-kokuho", chu=""),
     dict(namae="選挙", matome="選挙", id="wadai-senkyo", chu="")]
JUN = {"①": 0, "②": 1, "③": 2}


class TestRows(unittest.TestCase):
    def test_make_rows(self):
        yomi = {("F", "1"): {"a": yg("①,②", mayoi="1"), "b": yg("②,①,③")},
                ("F", "2"): {"a": yg("", "国保"), "b": yg("", "国民健康保険")},
                ("F", "3"): {"a": yg("③"), "b": yg("", "選挙")},
                ("F", "4"): {"a": yg("", "国保"), "b": yg("", "選挙")}}
        rows = bu.make_rows(yomi, [("F", "1"), ("F", "2"), ("F", "3"), ("F", "4")], W, JUN)
        got = [(r["n"], r["bunya"], r["wadai"], r["chushin"], r["yomi"], r["chu"]) for r in rows]
        self.assertEqual(got, [
            # 中心の分野が分かれたときは、両方を「1回だけ」の中心にする。並びは、中心（一致、1回だけ）、ほか、分野の順
            ("1", "①", "", "1回だけ", "一致", "中心の分野にしたのは読み手 a だけ。迷いの印：読み手 a"),
            ("1", "②", "", "1回だけ", "一致", "中心の分野にしたのは読み手 b だけ。迷いの印：読み手 a"),
            ("1", "③", "", "", "1回だけ", "読み手 b だけが付けた。迷いの印：読み手 a"),
            # 2人とも空で、まとめた名前が同じなら一致
            ("2", "", "国民健康保険", "", "一致", ""),
            # 1人だけが空にした題は、分野の行（1回だけ）と話題の行（1回だけ）の両方を持つ
            ("3", "③", "", "1回だけ", "1回だけ", "読み手 a だけが付けた。中心の分野にしたのは読み手 a だけ"),
            ("3", "", "選挙", "", "1回だけ", "読み手 b だけが付けた"),
            # 2人とも空で、まとめた名前が違えば、読み手ごとに1回だけ
            ("4", "", "国民健康保険", "", "1回だけ", "読み手 a だけが付けた"),
            ("4", "", "選挙", "", "1回だけ", "読み手 b だけが付けた")])
        self.assertEqual(bu.check(rows, [("F", "1"), ("F", "2"), ("F", "3"), ("F", "4")], set(JUN), W), [])
        # 行が無い題は止まる
        self.assertEqual(len(bu.check(rows, [("F", "5")], set(JUN), W)), 1)

    def test_check_yomi(self):
        dai = [("F", "1"), ("F", "2")]
        yomi = {("F", "1"): {"a": yg("①,①"), "b": yg("④")}, ("F", "2"): {"a": yg("", "知らない話題")},
                ("G", "1"): {"a": yg("①"), "b": yg("①")}}
        bad = bu.check_yomi(yomi, dai, set(JUN), W)
        self.assertEqual(len(bad), 8)
        self.assertTrue(any("読み手 b の行が無い" in b for b in bad))
        self.assertTrue(any("台帳に無い" in b for b in bad))
        self.assertTrue(any("知らない話題" in b for b in bad))
        # 表の名前で、読み取りの結果に無いもの（出さない名前を作らない）
        self.assertTrue(any("「選挙」が、読み取りの結果に無い" in b for b in bad))

    def test_check_wadai(self):
        self.assertEqual(bu.check_wadai(W), [])
        bad = bu.check_wadai(W + [dict(namae="国保", matome="選挙", id="wadai-kokuho", chu=""),
                                  dict(namae="x", matome="y", id="kokuho", chu="")])
        self.assertEqual(len(bad), 3)

    def test_yomi_go(self):
        self.assertEqual(bb.yomi_go(D, dict(bunya="①", yomi="一致", chushin="")),
                         D.kotoba("質問の題と分野の対応の表 yomi が「一致」") + "　"
                         + D.kotoba("質問の題と分野の対応の表 chushin が空"))
        self.assertEqual(bb.yomi_go(D, dict(bunya="", yomi="1回だけ", chushin="")),
                         D.kotoba("質問の題と分野の対応の表 yomi が「1回だけ」"))


class FakeInp(inputs.Inputs):
    """dai_of_question のための、台帳だけの入力。"""

    def __init__(self, rows):
        self.rows = rows
        self._cache = {}

    def ippan(self):
        out = {}
        for r in self.rows:
            out.setdefault(r["from"], []).append(r)
        return out


class TestDai(unittest.TestCase):
    def test_dai_of_question(self):
        f = "0000000001_20250310_0001"
        s2, s3, s9 = "0000000001_20250310_0005", "0000000001_20250310_0009", "0000000001_20250310_0020"
        inp = FakeInp([dict(**{"from": f}, n="1", turns=f"{f}:q;{s2}:rq"), dict(**{"from": f}, n="2", turns=f"{s3}:q")])
        self.assertEqual(bu.dai_of_question(inp, "iq:" + f, {s3}), [(f, "2")])
        # 段落の発言がどの題の turns にも無い（答弁だけなど）ときは、区切りの最初の発言の質問なら、題の全部
        self.assertEqual(bu.dai_of_question(inp, "iq:" + f, {s9}), [(f, "1"), (f, "2")])
        # 区切りの2つめの問いの質問なら、その質問の発言を turns に含む題
        self.assertEqual(bu.dai_of_question(inp, "iq:" + s3, {s9}), [(f, "2")])
        self.assertEqual(bu.dai_of_question(inp, "iq:0000000002_20250310_0001", {s9}), [])
        # 議案への質疑は台帳に無い
        self.assertEqual(bu.dai_of_question(inp, "sq:" + f, {s3}), [])

    def test_ippan_ate_danraku(self):
        """題の範囲は段落の単位（SCHEMA.md 7.10。2026-11-28）。1つの発言の途中（段落5）から次の題が始まる。"""
        f = "0000000001_20250310_0001"
        s5, s7, s9 = "0000000001_20250310_0005", "0000000001_20250310_0007", "0000000001_20250310_0009"
        rs = [dict(**{"from": f}, n="1", start=f + ":2", turns=f"{f}:q;{s5}:req"),
              dict(**{"from": f}, n="2", start=s5 + ":5", turns=f"{s5}:q;{s9}:rq")]
        ate = inputs.Inputs.ippan_ate

        def n(paras):
            return [r["n"] for r in ate(rs, paras)]
        self.assertEqual(n({(s5, 4)}), ["1"])           # 次の題の start の発言の、start より前の段落は前の題
        self.assertEqual(n({(s5, 5)}), ["2"])
        self.assertEqual(n({(s5, 9)}), ["2"])
        self.assertEqual(n({(f, 1)}), ["1"])            # 最初の題は、start の発言の最初の段落から
        self.assertEqual(n({(s7, 1)}), ["2"])           # 答弁の発言は範囲で
        self.assertEqual(n({"0000000001_20250310_0003"}), ["1"])
        # 段落の番号が分からない発言は、全部の段落として扱う
        self.assertEqual(n({s5}), ["1", "2"])
        self.assertEqual(n({(s5, None)}), ["1", "2"])
        # start が空の題は、turns の発言で見る
        rs2 = [dict(**{"from": f}, n="1", start="", turns=f"{f}:q;{s5}:req")]
        self.assertEqual([r["n"] for r in ate(rs2, {(s5, 9)})], ["1"])
        self.assertEqual(ate(rs2, {(s9, 1)}), [])


class TestReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inp = inp_or_none()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")

    def test_keikaku(self):
        kk = bu.keikaku(self.inp)
        self.assertEqual(kk["name"], "第6次日野町総合計画")
        self.assertEqual([h["no"] for h in kk["hashira"]], ["柱1", "柱2", "柱3", "柱4", "柱5"])
        b = [x for h in kk["hashira"] for x in h["bunya"]]
        self.assertEqual(len(b), 34)
        self.assertEqual((b[0]["no"], b[0]["name"], b[0]["midashi"], b[0]["tokoro"]),
                         ("①", "子ども・子育て", "基本施策", ["pt:sogo6/honpen-03/5", "pt:sogo6/honpen-03/6"]))
        self.assertEqual(b[-1]["seisaku"], ("政策10", "時代の変化に柔軟に対応できる行財政運営"))

    def test_table(self):
        rows, bad, _ = bu.tsukuru(self.inp)
        self.assertEqual(bad, [])
        self.assertEqual(len({(r["from"], r["n"]) for r in rows}), 964)
        if os.path.exists(bu.PATH):
            self.assertEqual(bu.read(), rows)

    def pages(self):
        if not hasattr(self.__class__, "_pages"):
            out = {}
            for theme, T in bm.read_notes(self.inp).items():
                model, _, _ = bn.collect(self.inp, T, theme)
                out[theme] = (T, bn.Page(self.inp, T, model))
            self.__class__._pages = out
        return self.__class__._pages

    def test_dai_danraku(self):
        """発言の途中から次の題が始まる例（台帳の 0000008116_20240913_0104。2つめの題の start は 0108 の段落5）。"""
        rs = self.inp.ippan()["0000008116_20240913_0104"]
        ate = inputs.Inputs.ippan_ate
        self.assertEqual([r["title"] for r in ate(rs, {("0000008116_20240913_0108", 3)})], ["区長の仕事をもっと簡素化できないか"])
        self.assertEqual([r["title"] for r in ate(rs, {("0000008116_20240913_0108", 12)})], ["少子化対策に有効な施策の模索を"])

    def test_issue_to_field(self):
        """issue の質問の題と、field で題に添える論点が食い違わない（同じ関数 build_note.dai_gyo で決める。2026-11-28）。"""
        pages = self.pages()
        br = bu.ronten_of_dai(self.inp, pages)
        nashi = D.bun("bunya-dai-nashi")
        ip = {(r["from"], r["n"]): r for rs in self.inp.ippan().values() for r in rs}
        kara = {}
        for theme, (T, pg) in pages.items():
            for P, slug, _, _ in T["topics"]:
                for q in pg.ronten(P)["qs"]:
                    if q["sitsugi"]:
                        continue
                    ks = bu.dai_of_question(self.inp, q["question"], {(sid, i) for sid, i, _ in q["paras"]})
                    self.assertTrue(ks, q["question"])
                    # issue の題は、field で論点を添える題の題名を並べたもの
                    self.assertEqual(q["dai"], "".join(f"「{ip[k]['title']}」" if ip[k]["title"].strip() else nashi
                                                       for k in ks), (slug, q["question"]))
                    for k in ks:
                        self.assertIn(slug, [s for _, s, _ in br.get(k, [])], (slug, q["question"], k))
                        kara.setdefault(k, set()).add(slug)
        # field で論点を添えた題は、どれも issue の質問の題から来ている
        self.assertEqual({k: {s for _, s, _ in v} for k, v in br.items()}, kara)
        # 2026-11-28 の依頼者の指摘：分野⑤の題「図書館サービス」に、論点「入所の調整」が付かない
        k = ("0000005483_20200914_0202", "3")
        self.assertEqual(ip[k]["title"], "図書館サービス")
        self.assertNotIn("入所の調整", [p for p, _, _ in br.get(k, [])])
        self.assertEqual(len(br), 178)

    def test_page(self):
        page, info = bb.build(self.inp, D, bn.read_kotoba(), datetime.date(2026, 11, 28))
        self.assertEqual(info["dai"], 964)
        self.assertIn("<section id='b1' class='page'>", page)
        self.assertIn("<section id='wadai-kokuho' class='page'>", page)
        self.assertIn(D.bun("bunya-link"), page)


if __name__ == "__main__":
    unittest.main()
