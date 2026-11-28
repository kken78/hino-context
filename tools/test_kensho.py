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


RAN = dict(ran="seika", kubun="naibu", midashi="実施したことの成果や効果;実施していること", chu="")
RAN2 = dict(ran="dekiteinai", kubun="naibu", midashi="実施できていないこと;実施できていないこと・困難なこと", chu="")


class TestParts(unittest.TestCase):
    def test_midashi_of(self):
        # 「●」を前に付けた字がある候補だけにする。項目の文の中の同じ字は、見出しとしない
        t = ks.nw("●実施したことの成果や効果\n・町が実施していることを広めました。")
        self.assertEqual(ks.midashi_of(RAN, t), ["実施したことの成果や効果"])
        self.assertEqual(ks.midashi_of(RAN, ks.nw("●実施していること\n・…")), ["実施していること"])
        # ほかの候補の一部である候補は除く
        self.assertEqual(ks.midashi_of(RAN2, ks.nw("●実施できていないこと・困難なこと\n・…")),
                         ["実施できていないこと・困難なこと"])
        self.assertEqual(ks.midashi_of(RAN2, ks.nw("●実施できていないこと\n・…")), ["実施できていないこと"])
        self.assertEqual(ks.midashi_of(RAN2, ks.nw("●基本目標")), [])

    def test_nw(self):
        # 空白と改行だけを除く。§3 の正規化と違い、行の頭の「3-2」を除かない
        self.assertEqual(ks.nw("・都市農村交流\n3-2の受入体制 と"), "・都市農村交流3-2の受入体制と")
        self.assertNotEqual(ks.norm("あ\n3-2の"), ks.nw("あ\n3-2の"))

    def test_nendo_of(self):
        self.assertEqual(ks.nendo_of("令和３年度"), "2021")
        self.assertEqual(ks.nendo_of("令和7年度"), "2025")
        self.assertEqual(ks.nendo_of("R7"), "")

    def test_ran_rows(self):
        src = "あいうえお。かきくけこ。さしすせそ。"
        n = ks.nw(src)
        # 2人が同じ：どれも一致
        rows, bad = ks.ran_rows(46, "node:senryaku2/e008", "jokyo", ["あいうえお。", "かきくけこ。"],
                                ["あいうえお。", "かきくけこ。"], "取り組み状況", (n, [n, ""]))
        self.assertEqual(bad, [])
        self.assertEqual([(r["n"], r["yomi"], r["shiryo"]) for r in rows],
                         [("1", "一致", "doc:hyoka-r7-senryaku-kensho/46"), ("2", "一致", "doc:hyoka-r7-senryaku-kensho/46")])
        # 区切りだけが違う：項目の数が多いほうの区切り。もう1人にもある項目は一致、ほかは1回だけ
        rows, bad = ks.ran_rows(46, "k", "comment", ["あいうえお。", "かきくけこ。", "さしすせそ。"],
                                ["あいうえお。", "かきくけこ。さしすせそ。"], "コメント", (n, ["", n]))
        self.assertEqual(bad, [])
        self.assertEqual([r["yomi"] for r in rows], ["一致", "1回だけ", "1回だけ"])
        self.assertTrue(all("区切り" in r["chu"] for r in rows))
        self.assertEqual(rows[0]["shiryo"], "doc:hyoka-r7-senryaku-kensho/47")
        # 字が違えば止まる。本文に無い項目も止まる
        _, bad = ks.ran_rows(46, "k", "comment", ["あいうえお。"], ["あいうえを。"], "コメント", (n, [n, ""]))
        self.assertEqual(len(bad), 1)
        _, bad = ks.ran_rows(46, "k", "comment", ["たちつてと。"], ["たちつてと。"], "コメント", (n, [n, ""]))
        self.assertEqual(len(bad), 1)

    def test_check_ran(self):
        rows = ks.read_ran()
        self.assertEqual(ks.check_ran(rows), [])
        self.assertEqual(len(ks.check_ran(rows + [dict(rows[0])])), 1)
        self.assertEqual(len(ks.check_ran([r for r in rows if r["ran"] != "kadai"])), 1)

    def test_dumps(self):
        with self.assertRaises(ks.KenshoError):
            ks.dumps([dict(torikumi="k", ran="a\tb")], ["torikumi", "ran"])


class TestReal(unittest.TestCase):
    """lock の版の入力と、読み取りの結果から作る。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = inp_or_none()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.out, cls.bad = ks.tsukuru(cls.inp)

    def test_rows(self):
        self.assertEqual(self.bad, [])
        o = self.out
        self.assertEqual(len(o["torikumi"]), 40)
        self.assertEqual(len({(r["torikumi"], r["shihyo_n"]) for r in o["kpi"]}), 65)
        self.assertEqual(len(o["kpi"]), 325)
        self.assertEqual(len(o["bun"]), 1018)
        self.assertEqual(sum(r["yomi"] == "1回だけ" for r in o["bun"]), 2)
        self.assertEqual((len(o["bunya"]), sum(r["yomi"] == "一致" for r in o["bunya"])), (61, 53))
        # 中身を出す分野は、40の取り組みのどれにも1つ
        self.assertEqual(sorted(r["torikumi"] for r in o["bunya"] if r["saisho"] == "一致"),
                         sorted(r["torikumi"] for r in o["torikumi"]))
        t = {r["torikumi"]: r for r in o["torikumi"]}
        x = t["node:senryaku2/e008"]
        self.assertEqual((x["kihon_no"], x["no"], x["name"], x["tasseido"], x["kekka"], x["shiryo"], x["honpen"]),
                         ("1", "8", "子どもの読書活動と学習活動の支援", "41.3%", "B", "doc:hyoka-r7-senryaku-kensho/46",
                          "pt:senryaku2/honpen/18"))
        # シートの担当部署の字が、総合戦略の担当課の字に無い2つと、取り組みの方向の字が違う6つは、注に書く（止めない）
        self.assertEqual(sum("担当部署" in r["chu"] for r in o["torikumi"]), 2)
        self.assertEqual(sum("取り組みの方向" in r["chu"] for r in o["torikumi"]), 6)
        # 報告書の字は直さない
        self.assertIn("空用地不足しのため", "".join(r["bun"] for r in o["bun"]))

    def test_repo(self):
        # リポジトリの表は、いまの読み取りの結果から作ったものと同じ
        self.assertEqual(ks.check(self.inp, ks.read_all()), [])


if __name__ == "__main__":
    unittest.main()
