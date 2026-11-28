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
        m = ks.midashi(dict(note="欄の見出しが決まりと違う：「●実施できていないこと・困難なこと」。決まりの見出しが無い："
                                 "「●実施できていないこと」・「●実施が困難なこと」"), ran)
        self.assertEqual((m["dekiteinai"], m["seika"], m["konnan"]),
                         ("実施できていないこと・困難なこと", "実施したことの成果や効果", "実施が困難なこと"))
        m = ks.midashi(dict(note="欄の見出しが決まりと違う：「●実施していること」。決まりの見出しが無い：「●実施したことの成果や効果」"),
                       ran)
        self.assertEqual(m["seika"], "実施していること")
        self.assertEqual(ks.midashi(dict(note=""), ran)["seika"], "実施したことの成果や効果")

    def test_tani_tsuki(self):
        self.assertEqual(ks.tani_tsuki("52", "回"), "52回")
        self.assertEqual(ks.tani_tsuki("88,000", "人"), "88,000人")
        self.assertEqual(ks.tani_tsuki("(測定しない)", "集落"), "(測定しない)")
        self.assertEqual(ks.tani_tsuki("", "回"), "")
        self.assertEqual(ks.tani_tsuki("52", ""), "52")

    def test_kenshu(self):
        sh = dict(doc=ks.DOC, page="46")
        kp = dict(doc=ks.DOC, page="46", shihyo_n="1", nendo="令和３年度")
        bn = dict(doc=ks.DOC, page="46", ran="jokyo", n="1")

        def au(table, row, checked="✓", reviewer="auto:pdftext"):
            return dict(table=table, row=row, checked=checked, reviewer=reviewer)
        st = dict(sheet=[sh], kpi=[kp], bun=[bn],
                  audit=[au("senryaku-sheet", f"{ks.DOC}/46"), au("senryaku-kpi", f"{ks.DOC}/46/1/令和３年度", ""),
                         au("senryaku-bun", f"{ks.DOC}/46/jokyo/1")])
        out, nashi, bad, hito = ks.kenshu(st)
        self.assertEqual((len(out["sheet"]), len(out["kpi"]), len(out["bun"]), nashi, bad, hito),
                         (1, 0, 1, 1, [], {"46": False}))
        # 全部の行に人の印があれば、人の確認が済んだシート
        st["audit"] = [dict(a, reviewer="依頼者") for a in st["audit"]]
        self.assertEqual(ks.kenshu(st)[3], {"46": True})
        # 台帳に行が無ければ問題
        st["audit"] = st["audit"][:1]
        self.assertEqual(len(ks.kenshu(st)[2]), 2)

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
        self.assertEqual(sum(len(rows) + (k is not None) for v in m["kpi"].values() for k, rows in v), 390)
        self.assertEqual(sum(len(v) for v in m["kpi"].values()), 65)
        self.assertEqual(sum(len(rows) for v in m["bun"].values() for _, _, rows in v), 1018)
        self.assertEqual(m["nashi"], 0)
        self.assertFalse(any(m["hito"].values()))
        self.assertEqual(sorted(m["naka"]), sorted(m["tori"]))
        t = m["tori"]["node:senryaku2/e008"]
        self.assertEqual((t["kihon_no"], t["no"], t["name"], t["tasseido"], t["kekka"], t["page"]),
                         ("1", "8", "子どもの読書活動と学習活動の支援", "41.3%", "B", "46"))
        self.assertEqual(m["sr"]["node:senryaku2/e008"]["honpen"], "pt:senryaku2/honpen/18")
        kijun, rows = m["kpi"]["node:senryaku2/e008"][0]
        self.assertEqual((kijun["nendo"], kijun["jisseki"], rows[-1]["tani"]), ("基準値【R2】", "27 回", "回"))
        # 欄の見出しが決まりと違うシート
        bun = dict((r, mi) for r, mi, _ in m["bun"]["node:senryaku2/e017"])
        self.assertEqual(bun["seika"], "実施していること")
        # 報告書の字は直さない
        self.assertIn("空用地不足しのため", "".join(r["line"] for v in m["bun"].values() for _, _, rs in v for r in rs))

    def test_repo(self):
        # リポジトリの表は、いまの読み取りの結果から作ったものと同じ
        rows, bad, _ = ks.tsukuru(self.inp)
        self.assertEqual(bad, [])
        self.assertEqual(ks.dumps(rows), ks.dumps(ks.read()))


if __name__ == "__main__":
    unittest.main()
