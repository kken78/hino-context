"""tools/konkyo.py のテスト（SCHEMA.md 7.10）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import konkyo  # noqa: E402


class Inp:
    """入力の確定済みの記録だけを返す、小さい入力。"""

    def __init__(self, taio, tsunagari, themes=()):
        self.t = {"records/taio.tsv": taio, "records/tsunagari.tsv": tsunagari, "ref/themes.tsv": list(themes)}

    def ronten_tsv(self, path):
        return self.t[path]


def taio(point, q="iq:0000000001_20250310_0001", hani="sp:0000000001_20250310_0002/3", status="confirmed"):
    return dict(question=q, point=point, hani=hani, bills="", bq="", status=status, reviewer="", date="", note="")


def tsunagari(upper, upper_ref, lower="下", lower_ref="", status="confirmed"):
    return dict(link="もとにした", upper=upper, upper_ref=upper_ref, lower=lower, lower_ref=lower_ref, source="",
                source_date="", quote="", status=status, reviewer="", date="", note="")


def toi(theme, q="iq:0000000001_20250310_0001"):
    return dict(theme=theme, kind="問い", value=q, source="", views="", reviewer="", date="", note="")


def nm(namae, shu, id_, betsumei="", theme="h"):
    return dict(theme=theme, namae=namae, shu=shu, id=id_, setsumei="", kohyo="", betsumei=betsumei, chu="")


BUNSHO = {"doc:teigen", "pt:youho/honpen", "plan:youho"}


class TestTsukuru(unittest.TestCase):
    def test_rows(self):
        inp = Inp([taio("提言"), taio("計画"), taio("論点A"), taio("案"), taio("頁"), taio("未", status="candidate")],
                  [tsunagari("提言", "doc:teigen/1"), tsunagari("計画", "plan:youho"), tsunagari("論点A", "doc:teigen/1"),
                   tsunagari("頁", "pt:youho/honpen/25"), tsunagari("未", "doc:teigen/1")])
        inp.t["ref/themes.tsv"] = [toi("h")]
        rows, dekinai = konkyo.tsukuru(inp, BUNSHO, {"論点A"})
        self.assertEqual([(r["aite"], r["yomi"], r["theme"]) for r in rows],
                         [("doc:teigen", "入力の確定済み", "h"), ("plan:youho", "入力の確定済み", "h")])
        self.assertEqual(rows[0]["hani"], "sp:0000000001_20250310_0002/3")
        self.assertIn("upper_ref「doc:teigen/1」", rows[0]["chu"])
        # 論点の名前（論点A）は作らない。ID が無い（案）、資料の1ページめでない（頁）は、理由とともに返す。案の記録は読まない
        self.assertEqual([p for p, _ in dekinai], ["案", "頁"])

    def test_namae(self):
        # 名前の表の名前（namae か betsumei）の point は、質問があるテーマの名前の表から作る。資料は質問の日で版を選び、
        # 出来事は namae のまま。質問がそのテーマに無い名前の表の行は使わない（2026-11-28）
        q2 = "iq:0000000001_20240310_0001"
        inp = Inp([taio("章"), taio("策定"), taio("章", q=q2), taio("会")],
                  [], [toi("x"), toi("k"), toi("k", q2)])
        namae = [nm("計画", "資料", "pt:youho/honpen", betsumei="章", theme="k"), nm("策定", "出来事", "k-sakutei", theme="k"),
                 nm("会", "出来事", "kai", theme="y")]
        rows, dekinai = konkyo.tsukuru(inp, BUNSHO, set(), namae, {"pt:youho/honpen": "2025-03"})
        self.assertEqual([(r["question"][14:22], r["theme"], r["aite"]) for r in rows],
                         [("20250310", "k", "pt:youho/honpen"), ("20250310", "k", "策定"),
                          ("20240310", "k", "計画")])
        self.assertIn("「計画」の行から", rows[0]["chu"])
        self.assertEqual([p for p, _ in dekinai], ["会"])
        # 入力の確定済みの行の出来事の名前は、そのテーマの名前の表の出来事にあればよい
        self.assertEqual(konkyo.check(rows[1:2], BUNSHO, {}, namae), [])
        self.assertEqual(len(konkyo.check([dict(rows[1], theme="y")], BUNSHO, {}, namae)), 1)

    def test_two_documents(self):
        inp = Inp([taio("X")], [tsunagari("X", "doc:teigen/1"), tsunagari("X", "pt:youho/honpen/1")])
        rows, dekinai = konkyo.tsukuru(inp, BUNSHO, set())
        self.assertEqual((rows, [p for p, _ in dekinai]), ([], ["X"]))

    def test_check(self):
        rows = [dict(question="iq:1", theme="", aite="doc:nai", hani="", yomi="確定", chu="")]
        self.assertEqual(len(konkyo.check(rows, BUNSHO)), 4)

    def test_check_namae(self):
        # 読み取りの行は、資料の ID の形でない名前（懇話会など）を持てる。入力の確定済みの行と、ID の形の字は、資料の一覧の表に要る
        ok = [dict(question="iq:1", theme="h", aite="懇話会", hani="sp:1/1", yomi="一致", chu="")]
        self.assertEqual(konkyo.check(ok, BUNSHO), [])
        bad = [dict(question="iq:1", theme="h", aite="懇話会", hani="sp:1/1", yomi="入力の確定済み", chu=""),
               dict(question="iq:1", theme="h", aite="doc:nai", hani="sp:1/1", yomi="一致", chu="")]
        self.assertEqual(len(konkyo.check(bad, BUNSHO)), 2)


class TestHiduke(unittest.TestCase):
    NAMAE = [nm("計画", "資料", "pt:youho/honpen"), dict(nm("提言", "資料", "doc:teigen"), kohyo="2024-02-01"),
             nm("指針", "資料", "")]
    HIDUKE = {"pt:youho/honpen": "2026-06", "doc:teigen": "", "plan:youho": ""}

    def test_check_hiduke(self):
        # 読み取りの行で、資料の日付が質問の日より後なら止まる。入力の確定済みの行は確認しない（SCHEMA.md 7.10）
        rows = [dict(question="iq:0000000001_20250310_0001", theme="h", aite="pt:youho/honpen", hani="sp:1/1", yomi="一致",
                     chu=""),
                dict(question="iq:0000000001_20240201_0001", theme="h", aite="doc:teigen", hani="sp:1/1", yomi="1回だけ",
                     chu=""),
                dict(question="iq:0000000001_20240131_0001", theme="h", aite="doc:teigen", hani="sp:1/1",
                     yomi="入力の確定済み", chu="")]
        bad = konkyo.check(rows, BUNSHO, self.HIDUKE, self.NAMAE)
        self.assertEqual(len(bad), 1)
        self.assertIn("2026-06-01", bad[0])

    def test_uchiwake(self):
        g = lambda a, y: dict(question="q", theme="h", aite=a, yomi=y)     # noqa: E731
        rows = [g("pt:youho/honpen", "一致"), g("計画", "一致"), g("計画", "1回だけ"), g("doc:teigen", "入力の確定済み"),
                g("指針", "一致"), dict(g("計画", "一致"), theme="x")]
        # 資料の ID が無い名前（指針）は、全部の行が結び付かなかった行。ほかのテーマの行は数えない
        self.assertEqual(konkyo.uchiwake(rows, self.NAMAE),
                         [("h", "計画", {"pt:youho/honpen": 1}, 2), ("h", "提言", {"doc:teigen": 0}, 0), ("h", "指針", {}, 1)])


class TestRepo(unittest.TestCase):
    def test_repo(self):
        try:
            inputs.Inputs()
        except inputs.InputError:
            raise unittest.SkipTest("lock の版の入力が無い")
        self.assertEqual(konkyo.main(["--kensa"]), 0)
        rows = konkyo.read()
        # はじめの6行は、入力の確定済みの記録から作った行。そのあとは、生成AIの2回の読み取りの行（幼保、介護の順。2026-11-28）
        self.assertEqual([(r["question"], r["theme"], r["aite"]) for r in rows[:6]],
                         [("iq:0000008582_20250912_0350", "hoiku", "doc:jigyo-shinkodomoen-kousou"),
                          ("iq:0000008397_20250310_0285", "hoiku", "doc:shingi-youho-teigen"),
                          ("sq:0000007861_20240307_0038", "kaigo", "pt:kaigo9/honpen"),
                          ("iq:0000008691_20251212_0210", "kaigo", "第10期の計画の策定"),
                          ("sq:0000008582_20250911_0033", "kaigo", "第10期の計画の策定"),
                          ("sq:0000008942_20260305_0170", "kaigo", "第10期の計画の策定")])
        self.assertEqual([r["yomi"] for r in rows[:6]], ["入力の確定済み"] * 6)
        self.assertEqual({r["yomi"] for r in rows[6:]}, {"一致", "1回だけ"})
        # 2回めの読み取り（2026-11-28）のあと。前は、幼保171行、介護34行、公共施設104行、地域のあり方56行の371行
        self.assertEqual([r["theme"] for r in rows[6:]], ["hoiku"] * 207 + ["kaigo"] * 41 + ["kokyo"] * 116 + ["chiiki"] * 70)
        self.assertEqual(len(rows), 440)
        # 資料の日付が質問の日より後の行は、ID を付けない（2026-11-28）
        u = {(t, n): (ids, c) for t, n, ids, c in konkyo.uchiwake(rows, konkyo.ym.read_namae())}
        self.assertEqual(u[("hoiku", "計画")], ({"pt:youho/honpen-202503": 4, "pt:youho/honpen": 0}, 1))
        self.assertEqual(u[("hoiku", "計画（案）")], ({"doc:jigyo-youhosaihen-keikakuan-202411": 13}, 7))
        self.assertEqual(sum(c for (t, _), (_, c) in u.items() if t == "hoiku"), 36)
        self.assertEqual(u[("kaigo", "第9期の計画")], ({"pt:kaigo9/honpen": 6}, 0))
        self.assertEqual(u[("kaigo", "アンケート調査")], ({"doc:jigyo-kaigo-chosa-r7": 0}, 3))
        # 公共施設の再編と地域のあり方（2026-11-28）。公共施設等総合管理計画は改定のあとの版だけなので、前の質問には ID を付けない
        self.assertEqual(u[("kokyo", "公共施設等総合管理計画")], ({"pt:kokyo-kanri/honpen": 6}, 5))
        self.assertEqual(u[("kokyo", "総合計画")], ({"plan:sogo6": 1}, 4))
        self.assertEqual(u[("chiiki", "自治会活動に関するアンケート調査")], ({"doc:chiiki-jichikai-chosa": 3}, 0))
        self.assertEqual(u[("kokyo", "学校施設の長寿命化計画")], ({}, 7))
        # 資料の一覧の表に足した「いま、私たちができること 2025」（令和８年２月。2026-11-28）。前の読み取りの2026年3月10日の
        # 質問の行も、この資料に結び付く
        self.assertEqual(u[("chiiki", "いま、私たちができること2025")], ({"doc:chiiki-jichikai-forum-shiryo": 2}, 0))


if __name__ == "__main__":
    unittest.main()
