"""tools/konkyo.py のテスト（SCHEMA.md 7.10）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import konkyo  # noqa: E402


class Inp:
    """入力の確定済みの記録だけを返す、小さい入力。"""

    def __init__(self, taio, tsunagari):
        self.t = {"records/taio.tsv": taio, "records/tsunagari.tsv": tsunagari}

    def ronten_tsv(self, path):
        return self.t[path]


def taio(point, q="iq:0000000001_20250310_0001", hani="sp:0000000001_20250310_0002/3", status="confirmed"):
    return dict(question=q, point=point, hani=hani, bills="", bq="", status=status, reviewer="", date="", note="")


def tsunagari(upper, upper_ref, lower="下", lower_ref="", status="confirmed"):
    return dict(link="もとにした", upper=upper, upper_ref=upper_ref, lower=lower, lower_ref=lower_ref, source="",
                source_date="", quote="", status=status, reviewer="", date="", note="")


BUNSHO = {"doc:teigen", "pt:youho/honpen", "plan:youho"}


class TestTsukuru(unittest.TestCase):
    def test_rows(self):
        inp = Inp([taio("提言"), taio("計画"), taio("論点A"), taio("案"), taio("頁"), taio("未", status="candidate")],
                  [tsunagari("提言", "doc:teigen/1"), tsunagari("計画", "plan:youho"), tsunagari("論点A", "doc:teigen/1"),
                   tsunagari("頁", "pt:youho/honpen/25"), tsunagari("未", "doc:teigen/1")])
        rows, dekinai = konkyo.tsukuru(inp, BUNSHO, {"論点A"})
        self.assertEqual([(r["aite"], r["yomi"]) for r in rows],
                         [("doc:teigen", "入力の確定済み"), ("plan:youho", "入力の確定済み")])
        self.assertEqual(rows[0]["hani"], "sp:0000000001_20250310_0002/3")
        self.assertIn("upper_ref「doc:teigen/1」", rows[0]["chu"])
        # 論点の名前（論点A）は作らない。ID が無い（案）、資料の1ページめでない（頁）は、理由とともに返す。案の記録は読まない
        self.assertEqual([p for p, _ in dekinai], ["案", "頁"])

    def test_two_documents(self):
        inp = Inp([taio("X")], [tsunagari("X", "doc:teigen/1"), tsunagari("X", "pt:youho/honpen/1")])
        rows, dekinai = konkyo.tsukuru(inp, BUNSHO, set())
        self.assertEqual((rows, [p for p, _ in dekinai]), ([], ["X"]))

    def test_check(self):
        rows = [dict(question="iq:1", aite="doc:nai", hani="", yomi="確定", chu="")]
        self.assertEqual(len(konkyo.check(rows, BUNSHO)), 3)

    def test_check_namae(self):
        # 読み取りの行は、資料の ID の形でない名前（懇話会など）を持てる。入力の確定済みの行と、ID の形の字は、資料の一覧の表に要る
        ok = [dict(question="iq:1", aite="懇話会", hani="sp:1/1", yomi="一致", chu="")]
        self.assertEqual(konkyo.check(ok, BUNSHO), [])
        bad = [dict(question="iq:1", aite="懇話会", hani="sp:1/1", yomi="入力の確定済み", chu=""),
               dict(question="iq:1", aite="doc:nai", hani="sp:1/1", yomi="一致", chu="")]
        self.assertEqual(len(konkyo.check(bad, BUNSHO)), 2)


class TestHiduke(unittest.TestCase):
    NAMAE = [dict(namae="計画", shu="資料", id="pt:youho/honpen", setsumei="", kohyo="", chu=""),
             dict(namae="提言", shu="資料", id="doc:teigen", setsumei="", kohyo="2024-02-01", chu="")]
    HIDUKE = {"pt:youho/honpen": "2026-06", "doc:teigen": "", "plan:youho": ""}

    def test_check_hiduke(self):
        # 読み取りの行で、資料の日付が質問の日より後なら止まる。入力の確定済みの行は確認しない（SCHEMA.md 7.10）
        rows = [dict(question="iq:0000000001_20250310_0001", aite="pt:youho/honpen", hani="sp:1/1", yomi="一致", chu=""),
                dict(question="iq:0000000001_20240201_0001", aite="doc:teigen", hani="sp:1/1", yomi="1回だけ", chu=""),
                dict(question="iq:0000000001_20240131_0001", aite="doc:teigen", hani="sp:1/1", yomi="入力の確定済み", chu="")]
        bad = konkyo.check(rows, BUNSHO, self.HIDUKE, self.NAMAE)
        self.assertEqual(len(bad), 1)
        self.assertIn("2026-06-01", bad[0])

    def test_uchiwake(self):
        rows = [dict(question="q", aite="pt:youho/honpen", yomi="一致"), dict(question="q", aite="計画", yomi="一致"),
                dict(question="q", aite="計画", yomi="1回だけ"), dict(question="q", aite="doc:teigen", yomi="入力の確定済み")]
        self.assertEqual(konkyo.uchiwake(rows, self.NAMAE),
                         [("計画", {"pt:youho/honpen": 1}, 2), ("提言", {"doc:teigen": 0}, 0)])


class TestRepo(unittest.TestCase):
    def test_repo(self):
        try:
            inputs.Inputs()
        except inputs.InputError:
            raise unittest.SkipTest("lock の版の入力が無い")
        self.assertEqual(konkyo.main(["--kensa"]), 0)
        rows = konkyo.read()
        # はじめの2行は、入力の確定済みの記録から作った行。そのあとは、生成AIの2回の読み取りの行（2026-11-28）
        self.assertEqual([(r["question"], r["aite"]) for r in rows[:2]],
                         [("iq:0000008582_20250912_0350", "doc:jigyo-shinkodomoen-kousou"),
                          ("iq:0000008397_20250310_0285", "doc:shingi-youho-teigen")])
        self.assertEqual([r["yomi"] for r in rows[:2]], ["入力の確定済み"] * 2)
        self.assertEqual({r["yomi"] for r in rows[2:]}, {"一致", "1回だけ"})
        self.assertEqual(len(rows), 172)
        # 資料の日付が質問の日より後の行は、ID を付けない（2026-11-28）
        u = {n: (ids, c) for n, ids, c in konkyo.uchiwake(rows, konkyo.ym.read_namae())}
        self.assertEqual(u["計画"], ({"pt:youho/honpen-202503": 3, "pt:youho/honpen": 0}, 1))
        self.assertEqual(u["計画（案）"], ({"doc:jigyo-youhosaihen-keikakuan-202411": 8}, 7))
        self.assertEqual(sum(c for _, c in u.values()), 33)


if __name__ == "__main__":
    unittest.main()
