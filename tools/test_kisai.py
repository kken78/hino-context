"""tools/kisai.py のテスト（SCHEMA.md 7.13）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import jiko  # noqa: E402
import kisai as ks  # noqa: E402

P = "doc:jinji-ikusei-hoshin/3"


def gyo(yomite, point, hani, mayoi="", kouho="", shiryo=P):
    return dict(shiryo=shiryo, hani=hani, point=point, kouho=kouho, mayoi=mayoi, riyu="", yomite=yomite, gyo=2)


class TestDanraku(unittest.TestCase):
    def test_kugiri(self):
        # 印刷のページ番号を除く。見出しの行は1つの段落。括弧の中の「。」では区切らない。行は空白を入れずにつなぐ
        page = ("1\nⅠ．人材育成基本方針について\n１．背景\n本町では、\n平成１１年に方針（以\n下、\n「基本方針」という。\n"
                "）を策定し、取り組んできました。\nしかし、環境は大きく変化して\nいます。\n")
        self.assertEqual(ks.danraku(page), [
            "Ⅰ．人材育成基本方針について", "１．背景",
            "本町では、平成１１年に方針（以下、「基本方針」という。）を策定し、取り組んできました。",
            "しかし、環境は大きく変化しています。"])

    def test_midashi_kakko(self):
        # 始まりの印で始まり、括弧が2行にまたがる見出しは、括弧が閉じるまで1つの段落
        page = "○プロ意識を持った職員\n《町民に信頼される実務\n能力を持った職員》\n高度化する課題に対応します。\n"
        self.assertEqual(ks.danraku(page), ["○プロ意識を持った職員", "《町民に信頼される実務能力を持った職員》",
                                            "高度化する課題に対応します。"])

    def test_sogo6(self):
        plan = dict(tabs=[dict(blocks=[
            dict(type="programs", source="honpen-05 p.24", groups=[dict(subgroups=[dict(
                items=[dict(no="(1)", name="適切な行政運営", desc="文1。\n主な取組:a／b")],
                intro=[dict(h="関連する個別計画", b="日野町人材育成基本方針")])])]),
            dict(type="table", source="honpen-05 p.24"),
            dict(type="narrative", source="honpen-05 p.2-3", text="使わない")])])
        self.assertEqual(ks.sogo6_danraku(plan, "honpen-05", 24),
                         ["(1) 適切な行政運営", "文1。", "主な取組:a／b", "関連する個別計画", "日野町人材育成基本方針"])


class TestParts(unittest.TestCase):
    def test_hani(self):
        self.assertEqual(ks.bangou("3-5,8"), [3, 4, 5, 8])
        self.assertEqual(ks.matomeru({8, 3, 4, 5}), "3-5,8")
        self.assertEqual(ks.hanchi("3-5,8"), [(3, 5), (8, 8)])
        with self.assertRaises(ks.KisaiError):
            ks.bangou("5-3")
        with self.assertRaises(ks.KisaiError):
            ks.bangou("3 - 5")

    def test_bunsho_of(self):
        self.assertEqual(ks.bunsho_of("doc:jinji-ikusei-hoshin/14"), "doc:jinji-ikusei-hoshin")
        self.assertEqual(ks.bunsho_of("pt:sogo6/honpen-05/24"), "plan:sogo6")
        self.assertEqual(ks.bunsho_of("pt:kaigo9/honpen/40"), "pt:kaigo9/honpen")
        self.assertIsNone(ks.bunsho_of("doc:x"))

    def test_kakunin(self):
        # 総合計画の段落は、字を確認した記録が無い間は出さない
        self.assertTrue(ks.kakunin_ari("doc:jinji-ikusei-hoshin/14"))
        self.assertFalse(ks.kakunin_ari("pt:sogo6/honpen-05/24"))

    def test_make_rows(self):
        jiko_rows = [dict(id="b33-07", theme="b33", name="職員研修とOJT"), dict(id="b33-09", theme="b33", name="人事評価")]
        taba = [dict(shiryo=P, danraku=8, sha256="")]
        yomi = [gyo("a", "職員研修とOJT", "3-5"), gyo("b", "職員研修とOJT", "4-6", mayoi="1"),
                gyo("a", "人事評価", "2"), gyo("b", "", "1", kouho="候補")]
        rows = ks.make_rows(yomi, taba, jiko_rows, ["doc:jinji-ikusei-hoshin"])
        self.assertEqual([(r["jiko"], r["hani"], r["yomi"], r["chu"]) for r in rows], [
            ("b33-07", "4-5", "一致", "迷いの印：読み手 b"),
            ("b33-07", "3", "1回だけ", "読み手 a だけが付けた。迷いの印：読み手 b"),
            ("b33-07", "6", "1回だけ", "読み手 b だけが付けた。迷いの印：読み手 b"),
            ("b33-09", "2", "1回だけ", "読み手 a だけが付けた")])
        self.assertEqual(ks.kouho(yomi), {"候補": [("b", P, "1", "", "")]})

    def test_check_yomi(self):
        taba = [dict(shiryo=P, danraku=8, sha256="")]
        bad = ks.check_yomi([gyo("a", "職員研修とOJT", "3-9"), gyo("a", "無い論点", "1"),
                             gyo("a", "職員研修とOJT", "1", kouho="候補"), gyo("b", "x", "1", shiryo="doc:y/1")],
                            taba, {"職員研修とOJT"})
        self.assertEqual(len(bad), 4)


class TestReal(unittest.TestCase):
    """リポジトリの表と、lock の版の入力で確認する。"""

    def test_taba_to_hyo(self):
        inp = inputs.Inputs()
        taba = ks.read_taba()
        self.assertEqual(ks.check_taba(inp, taba), [])
        jiko_rows = jiko.read()
        names = {r["name"] for r in jiko.of_theme(jiko_rows, ks.THEME)}
        yomi = ks.read_yomi()
        self.assertEqual(ks.check_yomi(yomi, taba, names), [])
        with open(os.path.join(inputs.ROOT, "teigi", "bunsho.tsv"), encoding="utf-8") as f:
            import suji as sj
            bunsho = [r["bunsho"] for r in sj.read_bunsho(f.read())[0]]
        rows = ks.make_rows(yomi, taba, jiko_rows, bunsho)
        with open(ks.PATH, encoding="utf-8") as f:
            self.assertEqual(ks.dumps(rows), f.read())
        # 出す記述の字は、もとの資料の文字と照合して合う（§3）。総合計画の行は出さない
        out, dasanai = ks.kijutsu(inp, rows, ks.bunsho_hiduke())
        self.assertEqual(dasanai, sum(r["shiryo"].startswith("pt:sogo6/") for r in rows))
        import shogo
        res = shogo.check_quotes(inp, [dict(where="", source=x["source"], quote=x["quote"]) for x in out])
        self.assertEqual(res.mismatched, [])


if __name__ == "__main__":
    unittest.main()
