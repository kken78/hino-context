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
        self.assertEqual(out, [(Q, "P", f"sp:{S}/2-3", "一致", "", "a", ""),
                               (Q, "P", f"sp:{S}/1", "1回だけ", "a", "a", ""),
                               (Q, "P", f"sp:{S}/4", "1回だけ", "b", "a", ""),
                               (Q, "R", f"sp:{S}/7", "1回だけ", "b", "", "")])
        self.assertEqual(ym.chu_of("a", "a、b"), "読み手 a だけが付けた。迷いの印：読み手 a、b")
        self.assertEqual(ym.chu_of("", "", "b"), "候補の名前から入れた段落がある：読み手 b")
        # 質問の読み取りについての注（taio/yomi-<テーマ>/chu.tsv）は、最後に足す
        self.assertEqual(ym.chu_of("b", "", "", "注"), "読み手 b だけが付けた。注")

    def test_kouho_ni_ireru(self):
        # 事項に入れる候補の段落は、入れる先の事項に読み手が付けた段落と合わせる。もとから事項に付いていた段落とも合わせる。
        # 資料を取り上げた部分にする候補は konkyo に、ほかのテーマで扱う候補と決めていない候補は、どちらにも入れない
        kg = lambda y, n, h: dict(question=Q, hani=h, namae=n, yomite=y, taba=0)  # noqa: E731
        yomi = {"shudai": [gyo("a", "P", f"sp:{S}/1-2")], "konkyo": [],
                "kouho": [kg("b", "候補1", f"sp:{S}/2-3"), kg("a", "候補2", f"sp:{S}/5"), kg("b", "候補3", f"sp:{S}/6"),
                          kg("a", "候補4", f"sp:{S}/7")]}
        kr = [dict(namae="候補1", atsukai="事項に入れる", saki="x1", chu=""),
              dict(namae="候補2", atsukai="資料を取り上げた部分にする", saki="提言", chu=""),
              dict(namae="候補3", atsukai="ほかのテーマで扱う候補", saki="情報発信", chu=""),
              dict(namae="候補4", atsukai="決めていない", saki="", chu="")]
        jr = [dict(id="x1", name="P")]
        namae = [nm("提言", "資料", "")]
        self.assertEqual(ym.check_kouho(kr, yomi, {"x1"}, namae), [])
        y2 = ym.kouho_ni_ireru(yomi, kr, jr)
        self.assertEqual([r["aite"] for r in y2["konkyo"]], ["提言"])
        out = ym.kumi_gyo(y2["shudai"], "point", lambda x, q: x)
        self.assertEqual(out, [(Q, "P", f"sp:{S}/2", "一致", "", "", "b"),
                               (Q, "P", f"sp:{S}/1", "1回だけ", "a", "", ""),
                               (Q, "P", f"sp:{S}/3", "1回だけ", "b", "", "b")])
        # 表に無い候補の名前、読み取りに無い名前の行、saki が合わない行、atsukai が違う行は止まる
        bad = ym.check_kouho(kr[1:] + [dict(namae="候補5", atsukai="事項に入れる", saki="x9", chu=""),
                                       dict(namae="候補6", atsukai="あとで", saki="", chu="")],
                             yomi, {"x1"}, namae)
        self.assertEqual(len(bad), 5)

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
        self.assertEqual(ym.themes(), ["hoiku", "kaigo"])
        self.assertEqual(len(rows), 624)
        self.assertEqual(sum(r["yomi"] == "一致" for r in rows), 339)
        # 幼保の行は、テーマごとに読むようにする前（2026-11-28）と同じ482行で、表の頭に並ぶ
        th = {r["id"]: r["theme"] for r in ym.jiko.read()}
        self.assertEqual([th[r["jiko"]] for r in rows], ["hoiku"] * 482 + ["kaigo"] * 142)
        self.assertEqual(sum(r["yomi"] == "一致" for r in rows[:482]), 247)
        self.assertEqual(len({r["question"] for r in rows[:482]}), 41)
        self.assertEqual(len({r["question"] for r in rows[482:]}), 21)
        self.assertEqual([len(ym.shitsumon(t)) for t in ("hoiku", "kaigo")], [41, 22])
        # 介護の2026年3月10日の質問（除雪・除草）は、読んだが、当たる論点が無かった（SKILL.md 4.4 の G5）
        self.assertEqual(ym.nashi_shitsumon("kaigo", rows), ["iq:0000008942_20260310_0029"])
        self.assertEqual(ym.nashi_shitsumon("hoiku", rows), [])
        # 束7の注は、その質問の行の全部に付く
        q7 = "iq:0000008691_20251212_0378"
        self.assertTrue(all("読み手 a の結果のファイルを画面に出した" in r["chu"] for r in rows if r["question"] == q7))
        self.assertTrue(any(r["question"] == q7 for r in rows))


if __name__ == "__main__":
    unittest.main()
