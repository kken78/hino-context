"""tools/yosan.py のテスト（SCHEMA.md 7.16）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import jiko  # noqa: E402
import yosan as ys  # noqa: E402


def gyo(yomite, jigyo, jiko_, name="", mayoi="", riyu="", taba=1):
    return dict(jigyo=jigyo, jiko=jiko_, name=name, mayoi=mayoi, riyu=riyu, yomite=yomite, gyo=2, taba=taba,
                file=f"{yomite}-{taba:02d}.tsv")


TABA = [dict(taba=1, kind="hosei", jigyo=["hj:r7-ippan-04/m003"]),
        dict(taba=2, kind="fuhyo", jigyo=["fu-0001"], members={"fu-0001": ["fh:fuhyo-r7/b001", "fh:fuhyo-r8/b002"]})]
JIKO = [dict(id="hiyo", name="新こども園の整備費用と財源"), dict(id="yochi", name="新こども園の用地")]
NAMES = {r["id"]: r["name"] for r in JIKO}


class TestMakeRows(unittest.TestCase):
    def test_icchi_ikkai_hiraku(self):
        # 2人とも付けた組は一致、1人だけは1回だけ。附表のまとまりは年度ごとの事業に開く。「無い」の行は持たない
        yomi = [gyo("a", "hj:r7-ippan-04/m003", "hiyo", mayoi="1", riyu="x"), gyo("b", "hj:r7-ippan-04/m003", "hiyo"),
                gyo("a", "fu-0001", "yochi", taba=2), gyo("b", "fu-0001", ys.NASHI, taba=2)]
        rows = ys.make_rows(yomi, TABA, JIKO)
        self.assertEqual(rows, [
            dict(jigyo="hj:r7-ippan-04/m003", jiko="hiyo", yomi=ys.ICCHI, chu="迷いの印：読み手 a"),
            dict(jigyo="fh:fuhyo-r7/b001", jiko="yochi", yomi=ys.IKKAI, chu="読み手 a だけが付けた"),
            dict(jigyo="fh:fuhyo-r8/b002", jiko="yochi", yomi=ys.IKKAI, chu="読み手 a だけが付けた")])


class TestCheckYomi(unittest.TestCase):
    def test_tomaru(self):
        taba = TABA[:1]
        j = "hj:r7-ippan-04/m003"
        self.assertEqual(ys.check_yomi([gyo("a", j, "hiyo", NAMES["hiyo"]), gyo("b", j, ys.NASHI)], taba, NAMES), [])
        # name が違う、選べない事項、「無い」と事項の両方、事業の行が無い
        bad = ys.check_yomi([gyo("a", j, "hiyo", "新こども園の費用"), gyo("a", j, ys.NASHI)], taba, NAMES)
        self.assertTrue(any("name が hiyo の名前と違う" in b for b in bad))
        self.assertTrue(any("両方ある" in b for b in bad))
        self.assertTrue(any("b-01.tsv：事業" in b for b in bad))
        bad = ys.check_yomi([gyo("a", j, "b25-k1", "x"), gyo("b", j, ys.NASHI)], taba, NAMES)
        self.assertTrue(any("選べる事項" in b for b in bad))


class TestDashikata(unittest.TestCase):
    def x(self, id_, shu, nendo, jun, name="認定こども園整備事業", setsumei=(), source="doc:yosan-r7-hosei-09/2"):
        return dict(id=id_, shu=shu, nendo=nendo, jun=jun, name=name, setsumei=list(setsumei), source=source)

    def test_narabe(self):
        # 種類ごとに分け（附表が先）、年度の新しい順、同じ年度の補正予算は新しい回から
        xs = [self.x("hj:r7-ippan-04/m003", "maru", 2025, 1), self.x("hj:r7-ippan-05/m008", "maru", 2025, 2),
              self.x("hj:r6-ippan-02/m001", "maru", 2024, 0), self.x("fh:fuhyo-r8/b010", "fuhyo", 2026, 9)]
        out = ys.narabe(xs)
        self.assertEqual([s for s, _ in out], ["fuhyo", "maru"])
        self.assertEqual([x["id"] for x in out[1][1]], ["hj:r7-ippan-05/m008", "hj:r7-ippan-04/m003", "hj:r6-ippan-02/m001"])

    def test_saisho(self):
        xs = [self.x(f"fh:a/{i}", "fuhyo", 2026 if i < 4 else 2025, i) for i in range(6)]
        mae, ato = ys.saisho(xs, 3)
        self.assertEqual([x["id"] for x in ato], ["fh:a/3"])
        self.assertEqual(len(mae), 5)

    def test_kakutei(self):
        # 同じページで、記録の引用に事業の名前か説明の字があれば、確定済みの記録にある事業
        x = self.x("fh:fuhyo-r8/b010", "fuhyo", 2026, 0, setsumei=[("details", "【新規】新こども園を整備する。")],
                   source="doc:yosan-r8-fuhyo/1")
        k = dict(source="doc:yosan-r8-fuhyo/1", quote="【新規】新こども園を 整備する。 228,421")
        self.assertTrue(ys.kakutei_ni_aru(x, [k]))
        self.assertFalse(ys.kakutei_ni_aru(x, [dict(k, source="doc:yosan-r8-fuhyo/2")]))
        self.assertFalse(ys.kakutei_ni_aru(x, [dict(k, yomi=ys.ICCHI)]))


class TestReal(unittest.TestCase):
    """lock の版の入力と、リポジトリの読み取りの結果で、表を作り直せること。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.inp = inputs.Inputs()
        except inputs.InputError as e:
            raise unittest.SkipTest(f"入力が無い（{e}）")

    def test_kensa(self):
        taba = ys.read_taba()
        self.assertEqual(ys.check_taba(self.inp, taba), [])
        rows = jiko.read()
        yomi = ys.read_yomi(taba)
        names = ys.erabu(self.inp, rows)
        self.assertEqual(ys.check_yomi(yomi, taba, names), [])
        out = ys.make_rows(yomi, taba, rows)
        self.assertEqual(ys.dumps(out), ys.dumps(ys.read()))
        naka, _ = ys.naka_of(self.inp)
        self.assertEqual(ys.check(out, naka, rows, names), [])
        # 附表の事業は hino-town-docs の資料のページで指す
        self.assertEqual(naka["fh:fuhyo-r8/b010"]["source"], "doc:yosan-r8-fuhyo/1")
        self.assertEqual(naka["node:jisshi/e008"]["source"], "pt:jisshi/honpen/2")


if __name__ == "__main__":
    unittest.main()
