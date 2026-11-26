"""MCP の応答を作るツール（tools/build_mcp.py）。

JSON の形（ツール4つ、引数の説明）、応答に資料の名前と URL が付くこと、定義が案であることの表示、上限と続き、
該当する組が無いときの文、使わない言葉で止まること、議員の名前が出ないこと。
"""
import copy
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_mcp as bm  # noqa: E402
import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import build_theme as bt  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import ronten  # noqa: E402

D = bs.read_design()


def inp_or_none():
    try:
        return inputs.Inputs()
    except (inputs.InputError, OSError):
        return None


class TestParts(unittest.TestCase):
    def test_kagi(self):
        self.assertEqual(bm.kagi([]), "")
        self.assertEqual(bm.kagi([("id", "taiki"), ("shiryo", ""), ("tsuzuki", None)]), "id=taiki")
        self.assertEqual(bm.kagi([("id", "taiki"), ("shiryo", "pt:youho/honpen"), ("tsuzuki", "2")]),
                         "id=taiki&shiryo=pt:youho/honpen&tsuzuki=2")

    def test_kakunin_kiroku(self):
        chu = "抽出した文字の並びが崩れている。2者が画像で確認（2026-11-23）。依頼者が PDF で確認（2026-13-01）"
        self.assertEqual(bm.kakunin_kiroku(chu), ["2者が画像で確認（2026-11-23）"])      # 日付の形が違う記録は出さない
        self.assertEqual(bm.kakunin_kiroku("対応づけの根拠：…"), [])

    def test_owari(self):
        self.assertEqual(bm.owari(bn.S("a&b") + "<b>c</b>&amp;"), "a&bc&")

    def test_pages(self):
        # 上限を超える組は、項目の途中で分けず、続きの文を付けて分ける
        items = [f"- 項目{i}：" + "あ" * 900 for i in range(20)]
        o = bm.Outou("題", ["- 定義の欄"], [(["## 見出し"], items)])
        pages = o.pages(D)
        self.assertGreater(len(pages), 2)
        for i, p in enumerate(pages, 1):
            t = bm.owari(p)
            self.assertLessEqual(len(t), bm.JOGEN)
            self.assertTrue(t.startswith(D.bun("mcp-atama") + "\n# 題\n" + D.bun("mcp-tsuzuki-dai", n=i, m=len(pages))))
            self.assertIn("## 見出し", t)                                         # ブロックの頭は、分けた先にも出す
            if i < len(pages):
                self.assertTrue(t.endswith(D.bun("mcp-tsuzuki", n=i + 1)))
            else:
                self.assertNotIn("tsuzuki=", t)
        alltext = "".join(bm.owari(p) for p in pages)
        self.assertEqual([alltext.count(f"- 項目{i}：") for i in range(20)], [1] * 20)
        self.assertIn("- 定義の欄", bm.owari(pages[0]))
        self.assertNotIn("- 定義の欄", bm.owari(pages[1]))
        # 上限に収まる組は1つで、続きの文を付けない
        one = bm.Outou("題", [], [(["## 見出し"], ["- 1"])]).pages(D)
        self.assertEqual(len(one), 1)
        self.assertNotIn(D.bun("mcp-tsuzuki-dai", n=1, m=1), bm.owari(one[0]))

    def test_read_skill(self):
        s = bm.read_skill()
        self.assertTrue(all(x.startswith("- ") for x in s.split("\n")))
        self.assertIn("theme", s)


class TestReal(unittest.TestCase):
    """lock の版の入力と teigi/ の表から作る。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = inp_or_none()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.tables, cls.read_problems = bt.read_tables()
        cls.data, cls.info = bm.build(cls.inp, cls.tables, bn.read_kotoba(), cls.read_problems, D)

    def bun(self, tool, k):
        return self.data["bun"][self.data["outou"][tool][k]]

    def test_shape(self):
        d = self.data
        self.assertEqual((d["name"], d["version"]), ("hino-context", bm.VERSION))
        self.assertEqual([t["name"] for t in d["tools"]], ["theme", "suji", "shisetsu", "shiryo"])
        want = {"theme": ["theme", "tsuzuki"], "suji": ["id", "shiryo", "uchiwake", "tsuzuki"],
                "shisetsu": ["key", "tsuzuki"],
                "shiryo": ["bunsho", "hyo", "tsuzuki"]}
        for t in d["tools"]:
            self.assertTrue(t["description"])
            self.assertEqual([a["name"] for a in t["args"]], want[t["name"]])
            for a in t["args"]:
                self.assertTrue(a["description"], (t["name"], a["name"]))
                self.assertIn(a["type"], ("string", "integer"))
                self.assertIsInstance(a["required"], bool)
                self.assertIsInstance(a["erabu"], list)
        self.assertEqual({t["name"]: [a["name"] for a in t["args"] if a["required"]] for t in d["tools"]},
                         {"theme": [], "suji": ["id"], "shisetsu": ["key"], "shiryo": ["bunsho"]})
        self.assertIn("taiki（待機児童数）", d["tools"][1]["args"][0]["description"])
        self.assertNotIn("最初に", d["tools"][0]["description"])            # 2026-11-27 の修正
        self.assertIn("ツールの引数の説明か、theme の応答", d["tools"][0]["description"])
        self.assertEqual(d["tools"][1]["args"][2]["type"], "integer")
        self.assertEqual(set(d["nai"]), {"theme", "suji", "shisetsu", "shiryo"})
        self.assertEqual(d["instructions"], bm.read_skill() + "\n- " + D.bun("mcp-hani-nai"))
        n = len(d["bun"])
        self.assertTrue(all(0 <= i < n for v in d["outou"].values() for i in v.values()))
        self.assertEqual(set(range(n)), {i for v in d["outou"].values() for i in v.values()})
        # 組：テーマの一覧と幼保、定義26、施設13、文書22と表17
        o = d["outou"]
        self.assertIn("", o["theme"])
        self.assertIn("theme=hoiku", o["theme"])
        self.assertEqual(sum(1 for k in o["suji"] if re.fullmatch(r"id=[a-z0-9-]+", k)), 26)
        self.assertEqual(sum(1 for k in o["shisetsu"] if "tsuzuki" not in k), 13)
        self.assertEqual(sum(1 for k in o["shiryo"] if re.fullmatch(r"bunsho=[^&]+", k)), 22)
        self.assertEqual(sum(1 for k in o["shiryo"] if re.fullmatch(r"bunsho=[^&]+&hyo=[0-9]+", k)), 17)
        # 続きの1は、続きを付けない組と同じ
        for v in o.values():
            for k, i in v.items():
                if "tsuzuki" not in k:
                    self.assertEqual(v[bm.kagi([(x.split("=", 1)[0], x.split("=", 1)[1]) for x in k.split("&") if x]
                                               + [("tsuzuki", "1")])], i)

    def test_moto(self):
        # 数値と引用に、資料の名前、ページ、URL が付く
        t = self.bun("suji", "id=taiki&shiryo=pt:youho/honpen")
        self.assertIn("### 日野町幼児教育保育施設再編整備計画（令和８年６月一部改正、2026年6月）　11ページ", t)
        self.assertIn(D.kotoba("文書の表 namae と、shiryo のページ") + "：https://www.town.shiga-hino.lg.jp/cmsfiles/"
                      "contents/0000008/8225/syuusei.pdf#page=11", t)
        self.assertIn("- 令和7年4月：3（" + D.kotoba("時点の関係 mae") + "）", t)
        t = self.bun("suji", "id=taiki&shiryo=doc:jigyo-shinkodomoen-kousou")
        self.assertIn("2者が画像で確認（2026-11-23）", t)
        self.assertNotIn("対応づけ", self.bun("suji", "id=nozoku"))      # chu の作業の注は出さない
        t = self.bun("suji", "id=kaien")
        self.assertIn("会議録 2025年9月11日（議会での答弁）", t)
        self.assertIn("https://kken78.github.io/hino-council-search/#sid=", t)
        t = self.bun("suji", "id=juto")                                    # 外部の公的な資料
        self.assertIn("総務省自治財政局財務調査課「", t)

    def test_an(self):
        # 定義が案なら、案であることを示す
        for t in self.tables["suji"]:
            text = self.bun("suji", f"id={t['id']}")
            self.assertEqual(D.kotoba("定義の表 kettei が「案」") in text, t["kettei"] == "案", t["id"])

    def test_jogen(self):
        self.assertTrue(all(len(b) <= bm.JOGEN for b in self.data["bun"]))
        o = self.data["outou"]["suji"]
        n = max(int(k.rsplit("=", 1)[1]) for k in o if k.startswith("id=taiki&tsuzuki="))
        self.assertGreater(n, 1)
        for i in range(1, n):
            self.assertTrue(self.bun("suji", f"id=taiki&tsuzuki={i}").endswith(D.bun("mcp-tsuzuki", n=i + 1)))
        self.assertNotIn("tsuzuki=", self.bun("suji", f"id=taiki&tsuzuki={n}"))
        self.assertNotIn(f"id=taiki&tsuzuki={n + 1}", o)
        # 年齢別の内訳は、資料の中で内訳ごとにまとめる
        t = "".join(self.data["bun"][o[k]] for k in o if k.startswith("id=fusoku&uchiwake=1&tsuzuki="))
        midashi = f"- {D.kotoba('数値の表 kubun')}：2号認定（3〜5歳・保育）"
        self.assertEqual(t.count(midashi), 1)

    def test_nai(self):
        o = self.data["outou"]
        for k in ("id=taikii", "id=taiki&tsuzuki=99", "id=taiki&shiryo=doc:koho-no771-08"):
            self.assertNotIn(k, o["suji"])
        self.assertNotIn("key=nishioji", o["shisetsu"])
        self.assertEqual(self.data["nai"]["suji"], D.bun("mcp-nai", tool="suji") + D.bun("mcp-hani-nai"))
        # 表の形で出せない表は、決まった文
        self.assertIn(D.bun("mcp-hyo-dasenai"), self.bun("shiryo", "bunsho=doc:shingi-youho-teigen&hyo=16"))

    def test_giin(self):
        # 議会での議員の発言の、発言者の名前を出さない
        sids = set()
        for r in self.tables["atai"]:
            if r["shiryo"].startswith("sp:"):
                sids.add(keys.parse(r["shiryo"])[1][0])
        for r in ronten.katei(self.inp, "hoiku"):
            sids |= {keys.parse(s.strip())[1][0] for s in r["sources"].split(",") if s.strip().startswith("sp:")}
        for r in self.inp.shisetsu_kiroku():
            if r["source"].startswith("sp:"):
                sids.add(keys.parse(r["source"])[1][0])
        names = {self.inp.speaker(s) for s in sids if re.fullmatch(r"[0-9０-９]+番", (self.inp.role(s) or "").strip())}
        self.assertTrue(names)
        alltext = "\n".join(self.data["bun"])
        for n in names:
            self.assertNotIn(n, alltext)
        self.assertIn("（議会での議員の発言）", alltext)

    def test_shisetsu(self):
        t = self.bun("shisetsu", "key=fa:nishioji-yo")
        self.assertIn("# 西大路幼稚園（key：fa:nishioji-yo）", t)
        self.assertEqual(t.count("〇町立幼児教育保育施設の再編整備について"), 2)
        self.assertIn("定員（id：teiin）：90", t)
        self.assertNotIn("延床面積（id：", t)                               # 資料の表での記述に出した欄は除く

    def test_uchiwake(self):
        # uchiwake を付けない組は内訳の無い数値だけ、uchiwake=1 は内訳のある数値だけ
        o = self.data["outou"]["suji"]
        base = "".join(self.data["bun"][o[k]] for k in o if re.fullmatch(r"id=taiki&tsuzuki=[0-9]+", k))
        uchi = "".join(self.data["bun"][o[k]] for k in o if re.fullmatch(r"id=taiki&uchiwake=1&tsuzuki=[0-9]+", k))
        kubun = f"- {D.kotoba('数値の表 kubun')}："
        self.assertNotIn(kubun, base)
        self.assertIn(kubun + "うち0歳児", uchi)
        self.assertIn(D.bun("mcp-uchiwake"), base)
        self.assertNotIn(D.bun("mcp-uchiwake"), uchi)
        self.assertIn(D.bun("mcp-uchiwake-dake"), uchi)
        self.assertEqual(sum(1 for k in o if re.fullmatch(r"id=taiki&tsuzuki=[0-9]+", k)), 3)
        # 内訳のある数値が無い定義には、uchiwake の組を作らない。どれも内訳の定義は、内訳の無い数値が無いことを示す
        self.assertNotIn("id=kaien&uchiwake=1", o)
        self.assertNotIn(D.bun("mcp-uchiwake"), self.bun("suji", "id=kaien"))
        self.assertIn(D.bun("mcp-uchiwake-nomi"), self.bun("suji", "id=fusoku"))
        self.assertIn("id=taiki&shiryo=pt:kodomo/honpen&uchiwake=1", o)
        self.assertNotIn("id=taiki&shiryo=plan:sogo6&uchiwake=1", o)

    def test_chigau(self):
        # 資料の間で一致しない時期は、数値のページと同じ判定で出す（待機児童数の2018年4月）
        t = self.bun("suji", "id=taiki")
        midashi = f"## {D.bun('chigau')}"
        self.assertEqual(t.count(midashi), 1)
        part = t[t.index(midashi):t.index(f"## {D.bun('mcp-midashi-suji')}")]
        self.assertIn("- 2018年4月：1（", part)
        self.assertIn("なし（会議録 2019年6月14日（議会での答弁））", part)
        self.assertEqual(part.count("\n- "), 1)
        self.assertIn(D.bun("chigau-setsumei"), part)
        for k, i in self.data["outou"]["suji"].items():
            if not k.startswith("id=taiki"):
                self.assertNotIn(midashi, self.data["bun"][i], k)

    def test_hiduke(self):
        # 年度だけが分かる資料は年度を出し、資料に日付の記述が無い資料は最後に並べて、そのことを書く
        t = self.bun("shisetsu", "key=fa:nishioji-yo")
        self.assertIn("指定避難所・指定緊急避難場所一覧（2018年度）", t)
        self.assertIn(D.bun("hiduke-nendo-setsumei"), t)
        t = self.bun("suji", "id=kaien")
        self.assertIn(D.bun("hiduke-nashi-setsumei"), t)
        self.assertGreater(t.index("パブリックコメントの実施結果"), t.index("会議録 2025年9月26日"))
        self.assertNotIn(D.bun("hiduke-nashi-setsumei"), self.bun("suji", "id=juto"))   # 外部の資料には出さない

    def test_irete_inai(self):
        nai = D.bun("mcp-irete-inai")
        t = self.bun("shiryo", "bunsho=plan:sogo6")
        self.assertIn(f"- {D.kotoba('文書の表 konkyo')}：{nai}", t)
        self.assertIn(f"## {D.bun('mcp-midashi-hyo-ichiran')}\n{nai}", t)
        t = self.bun("shiryo", "bunsho=pt:youho/honpen-202503")
        self.assertIn(f"## {D.kotoba('文書どうしの関係の表 e')}\n", t)
        t = self.bun("shiryo", "bunsho=doc:yosan-r7-hosei-12")
        self.assertIn(D.bun("mcp-konkyo-nashi", hani=D.kotoba("文書の表 chu（「根拠：」の記述の「見つからない（…）」の括弧の中の字）")
                                                + "：全ページを「基づ」「法」の字で探し、1ページを読んだ"), t)
        self.assertEqual(bm.konkyo_hani("根拠：記載は見つからない（1ページ（表）を見た）。日付：…"), "1ページ（表）を見た")
        self.assertEqual(bm.konkyo_hani("根拠：原典の文字が入力に無いので探していない"), "")

    def test_hani(self):
        self.assertIn(D.bun("mcp-shisetsu-teigi", theme="hoiku"), self.bun("shisetsu", "key=fa:shin-kodomoen"))

    def test_shurui(self):
        # 資料の種類は、内部の値ではなく、docs/design.md の言葉で出す
        self.assertIn(f"- {D.kotoba('文書の表 shurui')}：{D.kotoba('文書の表 shurui が「keikaku」')}",
                      self.bun("shiryo", "bunsho=pt:youho/honpen"))
        self.assertIn(f"- {D.kotoba('文書の表 shurui')}：{D.kotoba('文書の表 shurui が「koho」')}",
                      self.bun("shiryo", "bunsho=doc:koho-no771-08"))
        for k, i in self.data["outou"]["shiryo"].items():
            self.assertIsNone(re.search(r"資料の種類：[a-z]", self.data["bun"][i]), k)
        tables = copy.deepcopy(self.tables)
        tables["bunsho"][0]["shurui"] = "bosai"
        with self.assertRaises(bm.Stop) as c:
            bm.build(self.inp, tables, bn.read_kotoba(), self.read_problems, D)
        self.assertTrue(any("bosai" in m for _, m in c.exception.problems))

    def test_kuzure(self):
        # 取り出した文字が崩れている数値は、資料の該当部分を出さず、決まった文と確認の記録を出す
        t = self.bun("suji", "id=taiki&shiryo=doc:hyoka-r4-senryaku-kensho")
        self.assertEqual(t.count(D.bun("inyo-kuzure")), 6)
        self.assertNotIn("「基準値【R1】", t)
        self.assertIn("2者が画像で確認（2026-11-23）", t)
        self.assertNotIn(D.bun("inyo-kuzure"), self.bun("suji", "id=taiki&shiryo=pt:youho/honpen"))

    def test_shiryo_hani(self):
        t = self.bun("shiryo", "bunsho=doc:koho-no771-08")
        lines = t.split("\n")
        self.assertEqual(lines[2], D.bun("mcp-shiryo-hani"))                # 名前のすぐあと
        self.assertEqual(lines[3], D.bun("mcp-shiryo-kazu", hyo=3, atai=10, teigi=1, kara=0, e=0))
        self.assertIn(D.bun("mcp-hani"), self.bun("theme", ""))
        self.assertNotIn(D.bun("mcp-hani-nai"), self.bun("theme", ""))

    def test_stop_word(self):
        # 応答の文に、使わない言葉が残っていれば止まる
        tables = copy.deepcopy(self.tables)
        next(t for t in tables["suji"] if t["id"] == "taiki")["chui"] = "この事項の注意"
        with self.assertRaises(bm.Stop) as c:
            bm.build(self.inp, tables, bn.read_kotoba(), self.read_problems, D)
        self.assertEqual({k for k, _ in c.exception.problems}, {"(b) 使わない言葉"})
        self.assertTrue(any("「事項」" in m for _, m in c.exception.problems))

    def test_stop_design(self):
        d = copy.deepcopy(D)
        del d.h2["mcp-atama"]
        with self.assertRaises(bm.Stop) as c:
            bm.build(self.inp, self.tables, bn.read_kotoba(), self.read_problems, d)
        self.assertEqual({k for k, _ in c.exception.problems}, {"(e) デザインシステムとの対応"})

    def test_repo_json(self):
        # リポジトリの JSON は、いまの表から作ったものと同じ（違えば、作り直していない）
        path = bm.OUT_PATH
        if not os.path.exists(path):
            self.skipTest("mcp/data/outou.json がまだ無い")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), bm.dumps(self.data))


if __name__ == "__main__":
    unittest.main()
