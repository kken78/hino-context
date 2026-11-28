"""tools/yomi.py のテスト（SCHEMA.md 7.10）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import yomi as ym  # noqa: E402

Q = "iq:0000000001_20250310_0001"
S = "0000000001_20250310_0002"


def nm(namae, shu, id_, setsumei="", kohyo="", betsumei="", theme="h"):
    """資料と出来事の名前の表の行。"""
    return dict(theme=theme, namae=namae, shu=shu, id=id_, setsumei=setsumei, kohyo=kohyo, betsumei=betsumei, chu="")


def gyo(yomite, point, hani, mayoi=""):
    return dict(question=Q, point=point, hani=hani, mayoi=mayoi, riyu="", yomite=yomite, taba=0)


class TestParts(unittest.TestCase):
    def test_matomeru(self):
        self.assertEqual(ym.matomeru({(S, 3), (S, 1), (S, 2), (S, 5), ("0000000001_20250310_0004", 1)}),
                         f"sp:{S}/1-3,sp:{S}/5,sp:0000000001_20250310_0004/1")

    def test_kumi_gyo(self):
        # 2回とも付けた段落は一致の行、片方だけの段落は、読み手ごとの1回だけの行。片方だけが付けた組は1回だけの行だけ
        rows = [gyo("a", "P", f"sp:{S}/1-3", "1"), gyo("b", "P", f"sp:{S}/2-4"), gyo("b", "R", f"sp:{S}/7")]
        out = ym.kumi_gyo(rows, "point", lambda x, q: x)
        self.assertEqual(out, [(Q, "", "P", f"sp:{S}/2-3", "一致", "", "a", ""),
                               (Q, "", "P", f"sp:{S}/1", "1回だけ", "a", "a", ""),
                               (Q, "", "P", f"sp:{S}/4", "1回だけ", "b", "a", ""),
                               (Q, "", "R", f"sp:{S}/7", "1回だけ", "b", "", "")])
        # 分野の読み取りの行（題の番号 n がある。SCHEMA.md 7.10。2026-11-28）は、質問と題の番号と相手の組ごとに行を作る
        rows = [dict(gyo("a", "P", f"sp:{S}/1-2"), n="1"), dict(gyo("b", "P", f"sp:{S}/2"), n="1"),
                dict(gyo("b", "P", f"sp:{S}/5"), n="2")]
        self.assertEqual(ym.kumi_gyo(rows, "point", lambda x, q: x),
                         [(Q, "1", "P", f"sp:{S}/2", "一致", "", "", ""), (Q, "1", "P", f"sp:{S}/1", "1回だけ", "a", "", ""),
                          (Q, "2", "P", f"sp:{S}/5", "1回だけ", "b", "", "")])
        self.assertEqual(ym.chu_of("a", "a、b"), "読み手 a だけが付けた。迷いの印：読み手 a、b")
        self.assertEqual(ym.chu_of("", "", "b"), "候補の名前から入れた段落がある：読み手 b")
        # 質問の読み取りについての注（taio/yomi-<テーマ>/chu.tsv）は、最後に足す
        self.assertEqual(ym.chu_of("b", "", "", "注"), "読み手 b だけが付けた。注")

    def test_kouho_ni_ireru(self):
        # 事項に入れる候補の段落は、入れる先の事項に読み手が付けた段落と合わせる。もとから事項に付いていた段落とも合わせる。
        # 資料を取り上げた部分にする候補は konkyo に入れる。出さない扱いは無い（2026-11-28）
        kg = lambda y, n, h: dict(question=Q, hani=h, namae=n, yomite=y, taba=0)  # noqa: E731
        yomi = {"shudai": [gyo("a", "P", f"sp:{S}/1-2")], "konkyo": [],
                "kouho": [kg("b", "候補1", f"sp:{S}/2-3"), kg("a", "候補2", f"sp:{S}/5"), kg("b", "候補3", f"sp:{S}/6"),
                          kg("a", "候補4", f"sp:{S}/7")]}
        kr = [dict(namae="候補1", atsukai="事項に入れる", saki="x1", chu=""),
              dict(namae="候補2", atsukai="資料を取り上げた部分にする", saki="提言", chu=""),
              dict(namae="候補3", atsukai="ほかのテーマで扱う候補", saki="情報発信", chu=""),
              dict(namae="候補4", atsukai="決めていない", saki="", chu="")]
        # 「ほかのテーマで扱う候補」と「決めていない」は、扱いの種類に無いので止まる
        self.assertEqual(len(ym.check_kouho(kr, yomi, {"x1"}, [nm("提言", "資料", "")])), 2)
        kr = kr[:2] + [dict(namae="候補3", atsukai="事項に入れる", saki="x1", chu=""),
                       dict(namae="候補4", atsukai="事項に入れる", saki="x1", chu="")]
        jr = [dict(id="x1", name="P")]
        namae = [nm("提言", "資料", "")]
        self.assertEqual(ym.check_kouho(kr, yomi, {"x1"}, namae), [])
        y2 = ym.kouho_ni_ireru(yomi, kr, jr)
        self.assertEqual([r["aite"] for r in y2["konkyo"]], ["提言"])
        out = ym.kumi_gyo(y2["shudai"], "point", lambda x, q: x)
        self.assertEqual(out, [(Q, "", "P", f"sp:{S}/2", "一致", "", "", "b"),
                               (Q, "", "P", f"sp:{S}/1,sp:{S}/7", "1回だけ", "a", "", "a"),
                               (Q, "", "P", f"sp:{S}/3,sp:{S}/6", "1回だけ", "b", "", "b")])
        # 表に無い候補の名前、読み取りに無い名前の行、saki が合わない行、atsukai が違う行は止まる
        bad = ym.check_kouho(kr[1:] + [dict(namae="候補5", atsukai="事項に入れる", saki="x9", chu=""),
                                       dict(namae="候補6", atsukai="あとで", saki="", chu="")],
                             yomi, {"x1"}, namae)
        self.assertEqual(len(bad), 5)

    def test_yomi_awase(self):
        # 2つのテーマの読み取りの行がある段落は、どちらかが一致なら一致（SCHEMA.md 7.10。2026-11-28）
        self.assertEqual([ym.yomi_awase(a, b) for a, b in ((None, "1回だけ"), ("一致", "1回だけ"), ("1回だけ", "一致"),
                                                           ("1回だけ", "1回だけ"))],
                         ["1回だけ", "一致", "一致", "1回だけ"])
        rows = [dict(question=Q, theme="k", jiko="x1"), dict(question=Q, theme="c", jiko="x1"),
                dict(question=Q, theme="k", jiko="x2")]
        self.assertEqual(ym.futatsu(rows, "jiko"), [(Q, "x1")])

    def test_shudai_rows_namae(self):
        yomi = {"shudai": [gyo("a", "無い名前", f"sp:{S}/1")]}
        rows, bad = ym.shudai_rows(yomi, [dict(id="x1", name="P")])
        self.assertEqual(rows, [])
        self.assertEqual(len(bad), 1)

    def test_aite(self):
        namae = [nm("提言", "資料", "doc:t"), nm("計画（案）", "資料", ""), nm("懇話会", "出来事", "konwakai"),
                 nm("説明会", "出来事", "setsumeikai", betsumei="住民説明会;公民館での説明会")]
        f = ym.aite_of(namae, {"doc:t": "2024-02"})
        # betsumei の字は namae に直す
        self.assertEqual([f(x, Q) for x in ("提言", "計画（案）", "懇話会", "子ども・子育て会議", "公民館での説明会")],
                         ["doc:t", "計画（案）", "懇話会", "子ども・子育て会議", "説明会"])
        self.assertEqual(ym.check_namae(namae, {"doc:t"}), [])
        bad = namae + [nm("提言", "資料", "doc:nai"), nm("会", "出来事", ""), nm("X", "会議", "")]
        # 同じ名前の資料の行（版ごとの行）は持てる。資料の一覧の表に無い id、出来事の id が空、shu が違う、の3つ
        self.assertEqual(len(ym.check_namae(bad, {"doc:t"})), 3)
        # ほかのテーマには、同じ名前の行を持てる。出来事の id は、テーマをまたいで重ならない。betsumei の字は、同じテーマの
        # ほかの名前と重ならない
        self.assertEqual(ym.check_namae(namae + [nm("懇話会", "出来事", "k-konwakai", theme="k")], {"doc:t"}), [])
        self.assertEqual(len(ym.check_namae(namae + [nm("懇話会", "出来事", "konwakai", theme="k")], {"doc:t"})), 1)
        self.assertEqual(len(ym.check_namae(namae + [nm("会議", "出来事", "kaigi", betsumei="住民説明会")], {"doc:t"})), 1)

    def test_aite_hiduke(self):
        # 質問の日より前か同じ日付の資料のうち、いちばん新しいもの。月までの日付は、その月の1日。当たる資料が無ければ名前のまま
        namae = [nm("計画", "資料", "pt:k-202503", "k"), nm("計画", "資料", "pt:k", "k"),
                 nm("案", "資料", "doc:an", kohyo="2024-11-08")]
        hiduke = {"pt:k-202503": "2025-03", "pt:k": "2026-06", "doc:an": ""}
        f = ym.aite_of(namae, hiduke)
        q = lambda d: f"iq:0000000001_{d}_0001"     # noqa: E731
        self.assertEqual([f("計画", q(d)) for d in ("20211214", "20250301", "20250310", "20260309", "20260601")],
                         ["計画", "pt:k-202503", "pt:k-202503", "pt:k-202503", "pt:k"])
        self.assertEqual([f("案", q(d)) for d in ("20240913", "20241107", "20241108", "20241213")],
                         ["案", "案", "doc:an", "doc:an"])
        self.assertEqual(ym.check_namae(namae, set(hiduke), hiduke), [])
        # 同じ名前の行は、資料の id のある行で setsumei が同じ、資料の日付が違う。hiduke と kohyo は片方だけ
        bad = [dict(namae[0], setsumei="x"), namae[1], dict(namae[2], kohyo="")]
        self.assertEqual(len(ym.check_namae(bad, set(hiduke), hiduke)), 2)
        bad = [namae[0], dict(namae[1], id="pt:k2"), dict(namae[2], kohyo="2024-11")]
        self.assertEqual(len(ym.check_namae(bad, set(hiduke) | {"pt:k2"}, dict(hiduke, **{"pt:k2": "2025-03"}))), 2)


class TestRepo(unittest.TestCase):
    def test_repo(self):
        try:
            inputs.Inputs()
        except inputs.InputError:
            raise unittest.SkipTest("lock の版の入力が無い")
        self.assertEqual(ym.main(["--kensa"]), 0)
        rows = ym.read()
        # 総合計画の分野の読み取り（2026-11-28）の30の分野は、4つのテーマのあとに、分野の番号の順に並ぶ
        bunya = ["b02", "b03", "b04", "b05", "b06", "b07", "b08", "b09", "b10", "b11", "b12", "b13", "b14", "b15", "b16",
                 "b17", "b19", "b20", "b21", "b22", "b23", "b24", "b25", "b26", "b27", "b28", "b29", "b31", "b33", "b34"]
        self.assertEqual(ym.themes(), ["hoiku", "kaigo", "kokyo", "chiiki"] + bunya)
        self.assertEqual(len(rows), 7143)
        bu_rows = [r for r in rows if ym.jiko.is_bunya(r["theme"])]
        self.assertEqual((len(bu_rows), sum(r["yomi"] == "一致" for r in bu_rows)), (5730, 2953))
        self.assertTrue(all(r["n"] for r in bu_rows))
        # 4つのテーマの行は、分野の読み取りを入れる前と同じ（題の番号の列 n は空）
        rows = [r for r in rows if not ym.jiko.is_bunya(r["theme"])]
        self.assertTrue(all(r["n"] == "" for r in rows))
        self.assertEqual(len(rows), 1413)
        self.assertEqual(sum(r["yomi"] == "一致" for r in rows), 727)
        # 行はテーマの順に並ぶ（2回めの読み取り（2026-11-28）のあと。前は、幼保484行、介護144行、公共施設232行、
        # 地域のあり方209行の1069行で、前からの質問の行は変わっていない）
        self.assertEqual([r["theme"] for r in rows], ["hoiku"] * 609 + ["kaigo"] * 221 + ["kokyo"] * 269 + ["chiiki"] * 314)
        self.assertEqual([sum(r["yomi"] == "一致" for r in rows if r["theme"] == t) for t in ("hoiku", "kaigo", "kokyo", "chiiki")],
                         [308, 137, 138, 144])
        self.assertEqual([len({r["question"] for r in rows if r["theme"] == t}) for t in ("hoiku", "kaigo", "kokyo", "chiiki")],
                         [63, 32, 49, 42])
        # 2回めの読み取りは、束の番号を続けて置いた（幼保35問、介護11問、公共施設10問、地域のあり方13問。SCHEMA.md 7.10）
        self.assertEqual([len(ym.shitsumon(t)) for t in ("hoiku", "kaigo", "kokyo", "chiiki")], [76, 33, 49, 42])
        # 事項の theme の列に、行の theme がある（2つのテーマと共通の事項を含む）
        th = {r["id"]: ym.jiko.themes_of(r) for r in ym.jiko.read()}
        self.assertTrue(all(r["theme"] in th[r["jiko"]] for r in rows))
        # 1つの質問を2つのテーマで読んだもの（28問。2回めの読み取りの前は12問）。同じ質問と事項の組に、2つのテーマの
        # 読み取りの行があるのは12組（前は6組）で、どれも公共施設の再編と地域のあり方に共通の事項
        self.assertEqual(sum(len([t for t in x if not ym.jiko.is_bunya(t)]) > 1 for x in ym.shitsumon_theme().values()), 28)
        f2 = ym.futatsu(rows, "jiko")
        self.assertEqual(len(f2), 12)
        self.assertTrue(all([t for t in th[j] if not ym.jiko.is_bunya(t)] == ["kokyo", "chiiki"] for _, j in f2))
        # 介護の2026年3月10日の質問（除雪・除草）は、読んだが、当たる論点が無かった（SKILL.md 4.4 の G5）。
        # 同じ質問を地域のあり方でも読み、地域のあり方の論点に付いた
        self.assertEqual(ym.nashi_shitsumon("kaigo", rows), ["iq:0000008942_20260310_0029"])
        # 幼保の2回めの読み取りの35問のうち13問は、2人の読み手とも、どの論点にも付けなかった（2026-11-28）
        self.assertEqual(len(ym.nashi_shitsumon("hoiku", rows)), 13)
        self.assertEqual([ym.nashi_shitsumon(t, rows) for t in ("kokyo", "chiiki")], [[], []])
        # 束7の注は、その質問の行の全部に付く
        q7 = "iq:0000008691_20251212_0378"
        self.assertTrue(all("読み手 a の結果のファイルを画面に出した" in r["chu"] for r in rows if r["question"] == q7))
        self.assertTrue(any(r["question"] == q7 for r in rows))
        # 分野の読み取りの束は、質問と題の番号の並び。題は、どれかの論点に関する部分がある
        self.assertEqual(len(ym.dai("b25")), 46)
        self.assertEqual(ym.nashi_dai("b25"), [])
        self.assertEqual(ym.dai("hoiku")[0][1], "")


if __name__ == "__main__":
    unittest.main()
