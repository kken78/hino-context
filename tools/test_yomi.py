"""tools/yomi.py のテスト（SCHEMA.md 7.10）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import yomi as ym  # noqa: E402

Q = "iq:0000000001_20250310_0001"
S = "0000000001_20250310_0002"


def gyo(yomite, point, hani, mayoi=""):
    return dict(question=Q, point=point, hani=hani, mayoi=mayoi, riyu="", yomite=yomite, taba=0)


class TestParts(unittest.TestCase):
    def test_matomeru(self):
        self.assertEqual(ym.matomeru({(S, 3), (S, 1), (S, 2), (S, 5), ("0000000001_20250310_0004", 1)}),
                         f"sp:{S}/1-3,sp:{S}/5,sp:0000000001_20250310_0004/1")

    def test_kumi_gyo(self):
        # 2回とも付けた段落は一致の行、片方だけの段落は、読み手ごとの1回だけの行。片方だけが付けた組は1回だけの行だけ
        rows = [gyo("a", "P", f"sp:{S}/1-3", "1"), gyo("b", "P", f"sp:{S}/2-4"), gyo("b", "R", f"sp:{S}/7")]
        out = ym.kumi_gyo(rows, "point", lambda x: x)
        self.assertEqual(out, [(Q, "P", f"sp:{S}/2-3", "一致", "", "a"),
                               (Q, "P", f"sp:{S}/1", "1回だけ", "a", "a"),
                               (Q, "P", f"sp:{S}/4", "1回だけ", "b", "a"),
                               (Q, "R", f"sp:{S}/7", "1回だけ", "b", "")])
        self.assertEqual(ym.chu_of("a", "a、b"), "読み手 a だけが付けた。迷いの印：読み手 a、b")

    def test_shudai_rows_namae(self):
        yomi = {"shudai": [gyo("a", "無い名前", f"sp:{S}/1")]}
        rows, bad = ym.shudai_rows(yomi, [dict(id="x1", name="P")])
        self.assertEqual(rows, [])
        self.assertEqual(len(bad), 1)

    def test_aite(self):
        namae = [dict(namae="提言", shu="資料", id="doc:t", setsumei="", chu=""),
                 dict(namae="計画（案）", shu="資料", id="", setsumei="", chu=""),
                 dict(namae="懇話会", shu="出来事", id="konwakai", setsumei="", chu="")]
        f = ym.aite_of(namae)
        self.assertEqual([f(x) for x in ("提言", "計画（案）", "懇話会", "子ども・子育て会議")],
                         ["doc:t", "計画（案）", "懇話会", "子ども・子育て会議"])
        self.assertEqual(ym.check_namae(namae, {"doc:t"}), [])
        bad = namae + [dict(namae="提言", shu="資料", id="doc:nai", setsumei="", chu=""),
                       dict(namae="説明会", shu="出来事", id="", setsumei="", chu=""),
                       dict(namae="X", shu="会議", id="", setsumei="", chu="")]
        self.assertEqual(len(ym.check_namae(bad, {"doc:t"})), 4)


class TestRepo(unittest.TestCase):
    def test_repo(self):
        try:
            inputs.Inputs()
        except inputs.InputError:
            raise unittest.SkipTest("lock の版の入力が無い")
        self.assertEqual(ym.main(["--kensa"]), 0)
        rows = ym.read()
        self.assertEqual(len(rows), 457)
        self.assertEqual(sum(r["yomi"] == "一致" for r in rows), 239)
        self.assertEqual(len({r["question"] for r in rows}), 41)
        self.assertEqual(len(ym.shitsumon()), 41)


if __name__ == "__main__":
    unittest.main()
