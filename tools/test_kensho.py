"""tools/kensho.py のテスト（SCHEMA.md 7.12）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import kensho as ks  # noqa: E402


def inp_or_none():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class TestParts(unittest.TestCase):
    def test_midashi(self):
        ran = ks.read_ran()
        # 入力の note の「欄の見出しが決まりと違う」の字が、欄の表の候補にあれば、その字
        m, bad = ks.midashi(dict(note="欄の見出しが決まりと違う：「●実施できていないこと・困難なこと」。決まりの見出しが無い："
                                      "「●実施できていないこと」・「●実施が困難なこと」"), ran)
        self.assertEqual((m["dekiteinai"], m["seika"], m["konnan"], bad),
                         ("実施できていないこと・困難なこと", "実施したことの成果や効果", "実施が困難なこと", []))
        m, _ = ks.midashi(dict(note="欄の見出しが決まりと違う：「●実施していること」。決まりの見出しが無い：「●実施したことの成果や効果」"),
                          ran)
        self.assertEqual(m["seika"], "実施していること")
        self.assertEqual(ks.midashi(dict(note=""), ran)[0]["seika"], "実施したことの成果や効果")
        # note に無い欄は、候補のうちシートのページの文字にある最初のもの（令和3・4年度の報告書は「実施していること」）
        self.assertEqual(ks.midashi(dict(note=""), ran, ks.norm("●実施していること ・…"))[0]["seika"], "実施していること")
        # 令和3年度の《》≪≫ の見出しも、字を除いて候補と照合する
        m, bad = ks.midashi(dict(note="欄の見出しが決まりと違う：「《実施していること》」・「≪実施できていないこと≫」"), ran)
        self.assertEqual((m["seika"], m["dekiteinai"], bad), ("実施していること", "実施できていないこと", []))
        # 候補に無い見出しは問題
        self.assertEqual(len(ks.midashi(dict(doc="d", page="1", note="欄の見出しが決まりと違う：「●無い見出し」"), ran)[1]), 1)

    def test_tani_tsuki(self):
        self.assertEqual(ks.tani_tsuki("52", "回"), "52回")
        self.assertEqual(ks.tani_tsuki("88,000", "人"), "88,000人")
        self.assertEqual(ks.tani_tsuki("(測定しない)", "集落"), "(測定しない)")
        self.assertEqual(ks.tani_tsuki("", "回"), "")
        self.assertEqual(ks.tani_tsuki("52", ""), "52")

    def test_kenshu(self):
        sh = dict(doc=ks.DOC, page="46", tasseido="41.3%", note="")
        kp = dict(doc=ks.DOC, page="46", shihyo_n="1", shu="nendo", nendo="令和３年度", note="")
        bn = dict(doc=ks.DOC, page="46", ran="jokyo", n="1", note="")

        def au(table, row, checked="✓", reviewer="auto:pdftext", note=""):
            return dict(table=table, row=row, checked=checked, reviewer=reviewer, note=note)
        st = dict(sheet=[sh], kpi=[kp], bun=[bn],
                  audit=[au("senryaku-sheet", f"{ks.DOC}/46"),
                         au("senryaku-kpi", f"{ks.DOC}/46/1/nendo/令和３年度", "", note="要人確認:段1 nendo：合わない"),
                         au("senryaku-bun", f"{ks.DOC}/46/jokyo/1")])
        out, nashi, bad, hito = ks.kenshu(st)
        self.assertEqual((len(out["sheet"]), len(out["kpi"]), len(out["bun"]), nashi, bad, hito),
                         (1, 0, 1, {(ks.DOC, "46"): {"kpi": 1}}, [], {(ks.DOC, "46"): False}))
        # 全部の行に人の印があれば、人の確認が済んだシート
        st2 = dict(st, audit=[dict(a, reviewer="依頼者") for a in st["audit"]])
        self.assertEqual(ks.kenshu(st2)[3], {(ks.DOC, "46"): True})
        # 台帳に行が無ければ問題
        self.assertEqual(len(ks.kenshu(dict(st, audit=st["audit"][:1]))[2]), 2)
        # checked が空のシートの行は、段1 で合わない列だけを空にして出す
        st3 = dict(st, audit=[au("senryaku-sheet", f"{ks.DOC}/46", "", note="要人確認:段1 tasseido：読み直せない。要人確認:H4 3点")]
                   + st["audit"][1:])
        out, _, bad, _ = ks.kenshu(st3)
        self.assertEqual((out["sheet"][0]["tasseido"], out["sheet"][0]["_mada"], bad), ("", ["tasseido"], []))
        # シートを決める列が合わないなら問題
        st3["audit"][0]["note"] = "要人確認:段1 name：違う"
        self.assertEqual(len(ks.kenshu(st3)[2]), 1)
        # 起票の2人の読みが違って空の列があるだけの行は、空のまま出す
        kp2 = dict(kp, mokuhyo="", note="mokuhyo は2人の読みが違う（a「100%」、b「100」）。書いていない")
        st4 = dict(st, kpi=[kp2], audit=[st["audit"][0], au("senryaku-kpi", f"{ks.DOC}/46/1/nendo/令和３年度", "",
                                                             note="要人確認:段1 note：2人の読みが違う"), st["audit"][2]])
        out, nashi, bad, _ = ks.kenshu(st4)
        self.assertEqual((len(out["kpi"]), out["kpi"][0]["_chigau"], nashi, bad), (1, ["mokuhyo"], {}, []))

    def test_nikai_dan1(self):
        self.assertEqual(ks.nikai_cols("項目 は2人の読みが違う（a「x」、b「y」）"), ["line"])
        self.assertEqual(ks.nikai_cols("mokuhyo は2人の読みが違う（…）。書いていない。jisseki は2人の読みが違う（…）"),
                         ["mokuhyo", "jisseki"])
        self.assertEqual(ks.dan1_cols("要人確認:段1 note：2人の読みが違う・line：空。要人確認:H4 8点 指標"), ["note", "line"])
        self.assertEqual(ks.dan1_cols("要人確認:段1 tantou：担当部署の字が合わない（data/text に無い字：R3：住民課、R4：…）"),
                         ["tantou"])
        self.assertEqual(ks.dan1_cols(""), [])

    def test_hikaku(self):
        def r(doc, n, nendo, mo, ji, ta, chigau=()):
            return dict(doc=doc, shihyo="指標Ａ" if doc == ks.DOCS[0] else "指標A", shu="nendo", nendo=nendo, mokuhyo=mo,
                        jisseki=ji, tasseiritsu=ta, _chigau=list(chigau))
        kpi = {ks.DOCS[0]: [("1", [dict(r(ks.DOCS[0], 1, "令和３年度", "1", "1", "100.0%"), shu="kijun"),
                                   r(ks.DOCS[0], 1, "令和３年度", "1", "1", "100.0%"),
                                   r(ks.DOCS[0], 1, "令和4年度", "2", "1", "50.0%")])],
               ks.DOCS[1]: [("1", [r(ks.DOCS[1], 1, "令和 3年度", "1", "1", "100.0%"),
                                   r(ks.DOCS[1], 1, "令和４年度", "2", "2", "100.0%")])],
               ks.DOCS[2]: [("1", [r(ks.DOCS[2], 1, "令和４年度", "", "", "100%", ("mokuhyo", "jisseki"))])]}
        hk = ks.hikaku(kpi)
        self.assertEqual(len(hk), 1)                     # 指標名は §3 の正規化で同じ
        self.assertEqual(hk[0]["shihyo"], "指標Ａ")      # いちばん新しい報告書の字
        n3, n4 = hk[0]["nendo"]
        self.assertEqual((n3[0], [ds for _, ds in n3[1]]), (3, [[ks.DOCS[0], ks.DOCS[1]]]))
        self.assertEqual((n4[0], [ds for _, ds in n4[1]]), (4, [[ks.DOCS[0]], [ks.DOCS[1]], [ks.DOCS[2]]]))
        self.assertEqual(ks.chigai(hk), (1, 1))          # 2人の読みが違って空の行は数えない

    def test_hokoku_nendo(self):
        self.assertEqual(ks.hokoku_nendo("日野町くらし安心ひとづくり総合戦略（第２期）施策検証結果報告書（令和３年度）"), "令和３年度")
        self.assertIsNone(ks.hokoku_nendo("施策検証結果報告書"))

    def test_check_ran(self):
        rows = ks.read_ran()
        self.assertEqual(ks.check_ran(rows), [])
        self.assertEqual(len(ks.check_ran(rows + [dict(rows[0])])), 1)
        self.assertEqual(len(ks.check_ran([r for r in rows if r["ran"] != "kadai"])), 1)

    def test_dumps(self):
        with self.assertRaises(ks.KenshoError):
            ks.dumps([dict(torikumi="k", bunya="a\tb", shisaku="", saisho="", yomi="", chu="")])


class TestReal(unittest.TestCase):
    """lock の版の入力と、読み取りの結果から作る。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = inp_or_none()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.m, cls.bad = ks.matome(cls.inp)

    def test_matome(self):
        self.assertEqual(self.bad, [])
        m = self.m
        self.assertEqual(len(m["tori"]), 40)
        # 5冊とも、40の取り組みのシートが結び付く
        self.assertTrue(all(sorted(v) == sorted(ks.DOCS) for v in m["sheet"].values()))
        self.assertEqual(m["maisu"], {ks.DOCS[0]: 2, ks.DOCS[1]: 2, ks.DOCS[2]: 1, ks.DOCS[3]: 1, ks.DOCS[4]: 1})
        r7 = {k: v[ks.DOC] for k, v in m["kpi"].items()}
        self.assertEqual(sum(len(rows) for v in r7.values() for _, rows in v), 390)
        self.assertEqual(sum(len(v) for v in r7.values()), 65)
        self.assertEqual(sum(len(rows) for v in m["kpi"].values() for x in v.values() for _, rows in x), 1829)
        self.assertEqual(sum(len(rows) for v in m["bun"].values() for _, _, rows, _ in v[ks.DOC]), 1018)
        self.assertEqual(sum(len(rows) for v in m["bun"].values() for x in v.values() for _, _, rows, _ in x), 4761)
        self.assertEqual(m["nashi_kei"], 33)
        self.assertEqual(sum(bool(t["_mada"]) for v in m["sheet"].values() for t in v.values()), 18)
        self.assertFalse(any(x for v in m["hito"].values() for x in v.values()))
        self.assertEqual(sum(ks.chigai(v)[0] for v in m["hikaku"].values()), 41)
        self.assertEqual(sum(ks.chigai(v)[1] for v in m["hikaku"].values()), 16)
        self.assertEqual(sorted(m["naka"]), sorted(m["tori"]))
        t = m["tori"]["node:senryaku2/e008"]
        self.assertEqual((t["kihon_no"], t["no"], t["name"], t["tasseido"], t["kekka"], t["page"]),
                         ("1", "8", "子どもの読書活動と学習活動の支援", "41.3%", "B", "46"))
        self.assertEqual(m["sr"]["node:senryaku2/e008"]["honpen"], "pt:senryaku2/honpen/18")
        _, rows = m["kpi"]["node:senryaku2/e008"][ks.DOC][0]
        self.assertEqual((rows[0]["shu"], rows[0]["nendo"], rows[0]["jisseki"], rows[-1]["tani"]),
                         ("kijun", "基準値【R2】", "27 回", "回"))
        # 1ページの報告書のシート
        t = m["sheet"]["node:senryaku2/e008"]["hyoka-r3-senryaku-kensho"]
        self.assertEqual((t["page"], t["tasseido"], t["kekka"]), ("39", "", "B"))
        # 欄の見出しが決まりと違うシート
        bun = dict((r, mi) for r, mi, _, _ in m["bun"]["node:senryaku2/e017"][ks.DOC])
        self.assertEqual(bun["seika"], "実施していること")
        bun = dict((r, mi) for r, mi, _, _ in m["bun"]["node:senryaku2/e017"]["hyoka-r3-senryaku-kensho"])
        self.assertEqual(bun["seika"], "実施していること")
        # 報告書の字は直さない
        self.assertIn("空用地不足しのため", "".join(r["line"] for v in m["bun"].values() for x in v.values()
                                                   for _, _, rs, _ in x for r in rs))

    def test_repo(self):
        # リポジトリの表は、いまの読み取りの結果から作ったものと同じ
        rows, bad, _ = ks.tsukuru(self.inp)
        self.assertEqual(bad, [])
        self.assertEqual(ks.dumps(rows), ks.dumps(ks.read()))


if __name__ == "__main__":
    unittest.main()
