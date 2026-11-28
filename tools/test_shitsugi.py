"""tools/shitsugi.py のテスト（議案への質疑の読み取りの行。SCHEMA.md 7.10。2026-11-28）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import shitsugi as st  # noqa: E402

KIHON = {"②(1)": "確かな学力の育成", "①(1)": "幼児教育・保育の充実", "㉚(1)": "協働のまちづくりの推進"}
JIKO = [dict(id="b02-k1", theme="b02", name="確かな学力の育成"),
        dict(id="chiiki01", theme="chiiki,b31", name="協働のまちづくりの推進"),
        dict(id="b02-05", theme="b02", name="学校の給食"),
        dict(id="hoiku73", theme="hoiku", name="地域子育て支援拠点事業")]
Q = "sq:0000003851_20170313_0043"


def sh(y, point, hani, riyu="", gian="議第18号"):
    return dict(question=Q, gian=gian, point=point, hani=hani, mayoi="1" if riyu else "", riyu=riyu, yomite=y, taba=0)


def ko(y, bunya, namae, hani, gian="議第18号"):
    return dict(question=Q, gian=gian, bunya=bunya, hani=hani, namae=namae, mayoi="", riyu="", yomite=y, taba=0)


class TestShitsugi(unittest.TestCase):
    def test_gian_jun(self):
        self.assertEqual(sorted(["不明", "報第2号", "議第10号", "議題外", "議第9号", "決議案第1号"], key=st.gian_jun),
                         ["議第9号", "議第10号", "報第2号", "決議案第1号", "不明", "議題外"])

    def test_tsukeru(self):
        yomi = dict(shudai=[sh("a", "確かな学力の育成", "sp:0000003851_20170313_0043/2"),
                            sh("b", "確かな学力の育成", "sp:0000003851_20170313_0043/2-3", riyu="字は議第19号の話"),
                            sh("a", "幼児教育・保育の充実", "sp:0000003851_20170313_0043/4"),     # 中心の分野で、同じ名前の事項が無い
                            sh("a", "協働のまちづくりの推進", "sp:0000003851_20170313_0043/5")],  # 中心の分野で、同じ名前の事項がある
                    kouho=[ko("a", "02", "給食の話", "sp:0000003851_20170313_0043/6"),
                           ko("b", "03", "子育て拠点", "sp:0000003851_20170313_0043/7"),
                           ko("a", "", "国保", "sp:0000003851_20170313_0043/8"),
                           ko("b", "09", "農業委員", "sp:0000003851_20170313_0043/9")])
        kr = [dict(bunya="02", namae="給食の話", saki="b02-05"), dict(bunya="03", namae="子育て拠点", saki="hoiku73"),
              dict(bunya="", namae="国保", saki="wadai-kokuho"), dict(bunya="09", namae="農業委員", saki="")]
        out, nai = st.tsukeru(yomi, kr, JIKO, KIHON)
        got = [(r["point"], r["theme"], r["ji"], r["kouho"]) for r in out]
        self.assertEqual(got, [("b02-k1", "b02", "", ""), ("b02-k1", "b02", "議第19号", ""), ("chiiki01", "chiiki", "", ""),
                               ("b02-05", "b02", "", "給食の話"), ("hoiku73", "hoiku", "", "子育て拠点")])
        self.assertEqual(nai["kihon_nashi"], {("01", "幼児教育・保育の充実"): 1})
        self.assertEqual(nai["wadai"], {("", "国保"): 1})
        self.assertEqual(nai["nashi"], {("09", "農業委員"): 1})
        # 一致と1回だけの行。字の議案は、重なる段落の読み手を chu に書く
        rows = st.shudai_rows(out, JIKO, ["hoiku", "kaigo", "kokyo", "chiiki", "b02", "b31"])
        b02 = [(r["jiko"], r["hani"], r["yomi"], r["chu"]) for r in rows if r["jiko"] == "b02-k1"]
        self.assertEqual(b02, [("b02-k1", "sp:0000003851_20170313_0043/2", "一致", "迷いの印：読み手 b。字は議第19号の話：読み手 b"),
                               ("b02-k1", "sp:0000003851_20170313_0043/3", "1回だけ",
                                "読み手 b だけが付けた。迷いの印：読み手 b。字は議第19号の話：読み手 b")])
        self.assertTrue(all(r["n"] == "議第18号" for r in rows))
        self.assertEqual([r["theme"] for r in rows], ["hoiku", "chiiki", "b02", "b02", "b02"])
        self.assertEqual(st.ji_of_chu(b02[0][3]), ["議第19号"])
        # 資料と出来事は、段落が重なる事項の行のテーマ。重ならなければ、もう1人の読み手の行。それも無ければ入れない
        kn = [dict(question=Q, gian="議第18号", aite="提言", hani="sp:0000003851_20170313_0043/7", yomite="b", taba=0),
              dict(question=Q, gian="議第18号", aite="計画", hani="sp:0000003851_20170313_0043/3", yomite="a", taba=0),
              dict(question=Q, gian="議第18号", aite="x", hani="sp:0000003851_20170313_0043/20", yomite="a", taba=0)]
        wari, nashi = st.konkyo_wariate(dict(konkyo=kn), out)
        self.assertEqual({k: [r["aite"] for r in v] for k, v in wari.items()}, {"hoiku": ["提言"], "b02": ["計画"]})
        self.assertEqual(nashi, 1)

    def test_check_kouho(self):
        yomi = dict(kouho=[ko("a", "02", "給食の話", "sp:x/1"), ko("a", "", "国保", "sp:x/1")])
        rows = [dict(bunya="02", namae="給食の話", saki="b02-05", chu=""), dict(bunya="", namae="国保", saki="wadai-kokuho", chu=""),
                dict(bunya="02", namae="無い名前", saki="", chu=""), dict(bunya="2", namae="給食", saki="zzz", chu="")]
        bad = st.check_kouho(rows, yomi, {"b02-05"}, {"wadai-kokuho"})
        self.assertEqual(len(bad), 4)
        self.assertTrue(any("bunya が 01〜34" in b for b in bad))
        self.assertTrue(any("saki が事項の表にも" in b for b in bad))
        self.assertTrue(any("「無い名前」" in b and "読み取りの結果に無い" in b for b in bad))
        self.assertTrue(any("「給食」" in b for b in bad))


class TestRepo(unittest.TestCase):
    def test_repo(self):
        try:
            inp = inputs.Inputs()
        except inputs.InputError:
            raise unittest.SkipTest("lock の版の入力が無い")
        x = st.tsukuru(inp)
        self.assertEqual(len(x["qs"]), 520)
        sh_, kn = x["shudai"], x["konkyo"]
        self.assertEqual((len(sh_), sum(r["yomi"] == "一致" for r in sh_)), (5209, 3256))
        self.assertEqual(len({(r["question"], r["n"]) for r in sh_}), 1027)
        self.assertEqual(len(kn), 798)
        self.assertEqual(sum(bool(st.ji_of_chu(r["chu"])) for r in sh_), 234)
        # 入れなかった読み手の行（2026-11-28）：中心の分野①⑱㉜の基本施策の行、分野に無い話題、入れ先なし
        self.assertEqual({k: sum(v.values()) for k, v in x["nai"].items()}, dict(kihon_nashi=493, wadai=200, nashi=141))
        self.assertEqual(len(x["nai"]["nashi"]), 14)
        # 題は、議案の番号と、議案の一覧の、その会議の題（12月の決算の議案は、番号ごとの題）
        self.assertEqual(st.dai(inp, "sq:0000003851_20170313_0043", "議第18号"), "議第18号 平成２９年度日野町一般会計予算")
        self.assertEqual(st.dai(inp, "sq:0000004466_20181213_0182", "議第91号"), "議第91号 平成３０年度日野町一般会計補正予算（第４号）")
        self.assertEqual(st.dai(inp, "sq:0000004268_8.22gijiroku_0013", "議題外"), "議題外")
        # sid が日付で始まらない区切り（71）は、会議録の索引の発言の日
        self.assertEqual(inputs.hatsugen_hi("0000005484_11gijiroku_0010"), "2020-11-27")


if __name__ == "__main__":
    unittest.main()
