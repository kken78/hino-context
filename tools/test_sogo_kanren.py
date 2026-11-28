"""第6次日野町総合計画の関連する個別計画と、指標の表（tools/sogo_kanren.py。SCHEMA.md 7.15）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import sogo_kanren as sk  # noqa: E402
import suji as sj  # noqa: E402

PLANS = {"kodomo": "第３期日野町子ども・子育て支援事業計画", "a3": "第3期A計画", "a4": "第4期A計画",
         "shinrin": "日野町森林整備計画"}
BETSUMEI = [dict(namae="B計画", plan="shinrin", riyu="依頼者の決定")]


class TestMusubu(unittest.TestCase):
    def test_musubu(self):
        self.assertEqual(sk.musubu("日野町森林整備計画", PLANS, []), (sk.ICCHI, ["shinrin"]))
        self.assertEqual(sk.musubu("日野町子ども・子育て支援事業計画", PLANS, []), (sk.HAN_ICCHI, ["kodomo"]))
        self.assertEqual(sk.musubu("A計画", PLANS, []), (sk.NASHI, []))          # 版の表記を除くと2つ：結ばない
        self.assertEqual(sk.musubu("B計画", PLANS, BETSUMEI), (sk.BETSUMEI, ["shinrin"]))
        self.assertEqual(sk.musubu("日野町森林整備計画案", PLANS, []), (sk.NASHI, []))

    def test_check_betsumei(self):
        self.assertEqual(sk.check_betsumei(BETSUMEI, PLANS), [])
        self.assertEqual(len(sk.check_betsumei([dict(namae="x", plan="nai", riyu="r")], PLANS)), 1)
        self.assertEqual(len(sk.check_betsumei(BETSUMEI + BETSUMEI, PLANS)), 1)


class TestReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.inp = inputs.Inputs()
            with open(os.path.join(inputs.ROOT, "teigi", "bunsho.tsv"), encoding="utf-8") as f:
                cls.m = sk.matome(cls.inp, sj.read_bunsho(f.read())[0])
        except inputs.InputError as e:
            raise unittest.SkipTest(str(e))

    def test_kazu(self):
        kei = [k for x in self.m.values() if x["kanren"] for k in x["kanren"]["keikaku"]]
        self.assertEqual(len(self.m), 34)
        self.assertEqual(len(kei), 96)
        self.assertEqual(sum(1 for k in kei if k["musubi"] == sk.NASHI), 53)
        self.assertEqual(sum(len(x["shihyo"]) for x in self.m.values()), 33)
        self.assertEqual([no for no, x in self.m.items() if not x["shihyo"]], ["㉜"])

    def test_jinzai(self):
        k = next(k for k in self.m["㉝"]["kanren"]["keikaku"] if k["namae"] == "日野町人材育成基本方針")
        self.assertEqual((k["musubi"], k["shiryo"]), (sk.NASHI, ["doc:jinji-ikusei-hoshin"]))
        self.assertEqual(self.m["㉝"]["kanren"]["tokoro"], ["pt:sogo6/honpen-05/24"])

    def test_suji_no_ji(self):
        # 数値は入力の字のまま（75.0 を 75 にしない）
        rows = self.m["②"]["shihyo"][0]["rows"]
        self.assertEqual(rows[0][1:], ["72.2", "75.0", "78.0"])


if __name__ == "__main__":
    unittest.main()
