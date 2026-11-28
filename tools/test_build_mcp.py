"""MCP の応答を作るツール（tools/build_mcp.py）。

JSON の形（ツール6つ、引数の説明）、論点（issue）が試作のページと同じ集め方の結果から作られていること、応答に資料の名前と URL が付くこと、項目が案であることの表示、上限と続き、
該当する組が無いときの文、使わない言葉で止まること、議員の名前が出ないこと。
"""
import copy
import json
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
        self.assertEqual(bm.kagi([("item", "taiki"), ("document", ""), ("page", None)]), "item=taiki")
        self.assertEqual(bm.kagi([("item", "taiki"), ("document", "pt:youho/honpen"), ("page", "2")]),
                         "item=taiki&document=pt:youho/honpen&page=2")

    def test_kakunin_kiroku(self):
        chu = "抽出した文字の並びが崩れている。生成AIが画像を2回読んで一致（2026-11-23）。人が PDF で確認（2026-13-01）"
        self.assertEqual(bm.kakunin_kiroku(chu), ["生成AIが画像を2回読んで一致（2026-11-23）"])      # 日付の形が違う記録は出さない
        self.assertEqual(bm.kakunin_kiroku("対応づけの根拠：…"), [])

    def test_owari(self):
        self.assertEqual(bm.owari(bn.S("a&b") + "<b>c</b>&amp;"), "a&bc&")

    def test_pages(self):
        # 上限を超える組は、項目の途中で分けず、続きの文を付けて分ける
        items = [f"- 項目{i}：" + "あ" * 900 for i in range(20)]
        o = bm.Outou("題", ["- 項目の欄"], [(["## 見出し"], items)])
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
                self.assertNotIn(D.bun("mcp-tsuzuki", n=i + 1), t)
        alltext = "".join(bm.owari(p) for p in pages)
        self.assertEqual([alltext.count(f"- 項目{i}：") for i in range(20)], [1] * 20)
        self.assertIn("- 項目の欄", bm.owari(pages[0]))
        self.assertNotIn("- 項目の欄", bm.owari(pages[1]))
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
        self.assertEqual([t["name"] for t in d["tools"]],
                         ["theme", "issue", "item", "facility", "document", "event", "field", "review"])
        # field と review は 2026-11-28 に追加
        want = {"theme": ["theme", "page"], "issue": ["issue", "page"], "item": ["item", "document", "breakdown", "page"],
                "facility": ["facility", "page"],
                "document": ["document", "table", "page"], "event": ["event", "page"], "field": ["field", "page"],
                "review": ["review", "page"]}
        for t in d["tools"]:
            self.assertTrue(t["description"])
            self.assertEqual([a["name"] for a in t["args"]], want[t["name"]])
            for a in t["args"]:
                self.assertTrue(a["description"], (t["name"], a["name"]))
                self.assertIn(a["type"], ("string", "integer"))
                self.assertIsInstance(a["required"], bool)
                self.assertIsInstance(a["erabu"], list)
        self.assertEqual({t["name"]: [a["name"] for a in t["args"] if a["required"]] for t in d["tools"]},
                         {"theme": [], "issue": ["issue"], "item": ["item"], "facility": ["facility"],
                          "document": ["document"], "event": ["event"], "field": [], "review": ["review"]})
        self.assertIn("taiki（待機児童数）", d["tools"][2]["args"][0]["description"])
        self.assertIn("teiin（新こども園の定員）", d["tools"][1]["args"][0]["description"])
        self.assertNotIn("最初に", d["tools"][0]["description"])            # 2026-11-27 の修正
        self.assertIn("ツールの引数の説明か、theme の応答", d["tools"][0]["description"])
        self.assertEqual(d["tools"][2]["args"][2]["type"], "integer")
        self.assertEqual(set(d["nai"]), {"theme", "issue", "item", "facility", "document", "event", "field", "review"})
        self.assertEqual(d["instructions"], bm.read_skill() + "\n- " + D.bun("mcp-hani-nai") + "\n- "
                         + D.bun("mcp-hani-bunya", keikaku="第6次日野町総合計画"))
        n = len(d["bun"])
        self.assertTrue(all(0 <= i < n for v in d["outou"].values() for i in v.values()))
        self.assertEqual(set(range(n)), {i for v in d["outou"].values() for i in v.values()})
        # 組：テーマの一覧と4つのテーマ、論点85（幼保48、介護23、公共施設9、地域5）、項目27、施設13、資料22と表17、出来事3
        o = d["outou"]
        self.assertIn("", o["theme"])
        self.assertEqual(sorted(k for k in o["theme"] if re.fullmatch(r"theme=[a-z]+", k)),
                         ["theme=chiiki", "theme=hoiku", "theme=kaigo", "theme=kokyo"])
        issue = [k for k in o["issue"] if "page" not in k and ":" not in k and not re.fullmatch(r"issue=b[0-9]{2}-.+", k)]
        # 幼保57、介護45、公共施設56、地域のあり方41（共通の事項4は、公共施設で作る。2回めの読み取りのあと。2026-11-28）
        self.assertEqual(len(issue), 199)
        # まとまりの ID（見出しの ID とまとまりの名前を「:」でつないだ字。2026-11-28）も issue で引く
        self.assertEqual(sum(1 for k in o["issue"] if "page" not in k and ":" in k), 265)
        self.assertIn("b33-k1:職員の育成と人事評価", d["tools"][1]["args"][0]["erabu"])
        # 総合計画の分野の論点（2026-11-28）は 1176。ID は b と分野の番号で始まる
        self.assertEqual(sum(1 for k in o["issue"] if "page" not in k and ":" not in k and re.fullmatch(r"issue=b[0-9]{2}-.+", k)),
                         1176)
        ev = sorted(k for k in o["event"] if "page" not in k and not re.fullmatch(r"event=b[0-9]{2}-.+", k))
        self.assertEqual(len(ev), 33)
        self.assertEqual(sum(1 for k in o["event"] if "page" not in k and re.fullmatch(r"event=b[0-9]{2}-.+", k)), 295)
        # 引数の説明に並べるのは、テーマの論点と出来事だけ。選べる値（erabu）には、分野の論点と出来事も入る
        self.assertNotIn("b25-23", d["tools"][1]["args"][0]["description"])
        self.assertIn("b25-23", d["tools"][1]["args"][0]["erabu"])
        self.assertEqual([k for k in ev if not k.startswith(("event=kokyo-", "event=chiiki-"))],
                         ["event=hoiku-daredemo-tsuen-kaigi", "event=hoiku-genba-bukai", "event=hoiku-kousou-sakutei-iinkai",
                          "event=hoiku-sekkei-proposal", "event=kaigo-choisoko-wg",
                          "event=kaigo-dai10ki-sakutei", "event=kaigo-dai8ki-sakutei", "event=kaigo-pabukome",
                          "event=kaigo-setsumeikai", "event=kaigo-unei-kyogikai",
                          "event=konwakai", "event=pabukome", "event=setsumeikai"])
        for k in ("issue=hiyo", "issue=menseki", "issue=teiin", "issue=yochi", "issue=kaigo23", "issue=chiiki05"):
            self.assertIn(k, issue)
        self.assertEqual(sum(1 for k in o["item"] if re.fullmatch(r"item=[a-z0-9-]+", k)), 27)
        self.assertEqual(sum(1 for k in o["facility"] if "page" not in k), 13)
        # 2026-11-28 に2つと、施策検証結果報告書（令和7年度）と、「いま、私たちができること 2025」を足した
        self.assertEqual(sum(1 for k in o["document"] if re.fullmatch(r"document=[^&]+", k)), 30)
        self.assertEqual(sum(1 for k in o["document"] if re.fullmatch(r"document=[^&]+&table=[0-9]+", k)), 17)
        # 続きの1は、続きを付けない組と同じ
        for v in o.values():
            for k, i in v.items():
                if "page" not in k:
                    self.assertEqual(v[bm.kagi([(x.split("=", 1)[0], x.split("=", 1)[1]) for x in k.split("&") if x]
                                               + [("page", "1")])], i)

    def test_moto(self):
        # 数値と引用に、資料の名前、ページ、URL が付く
        t = self.bun("item", "item=taiki&document=pt:youho/honpen")
        self.assertIn("### 日野町幼児教育保育施設再編整備計画（令和８年６月一部改正、2026年6月）　11ページ", t)
        self.assertIn(D.kotoba("資料の一覧の表 namae と、shiryo のページ") + "：https://www.town.shiga-hino.lg.jp/cmsfiles/"
                      "contents/0000008/8225/syuusei.pdf#page=11", t)
        self.assertIn("- 令和7年4月：3（" + D.kotoba("時点の関係 mae") + "）", t)
        t = self.bun("item", "item=taiki&document=doc:jigyo-shinkodomoen-kousou")
        self.assertIn("生成AIが画像を2回読んで一致（2026-11-23）", t)
        self.assertNotIn("対応づけ", self.bun("item", "item=nozoku"))      # chu の作業の注は出さない
        t = self.bun("item", "item=kaien")
        self.assertIn("会議録 2025年9月11日（議会での答弁）", t)
        self.assertIn("https://kken78.github.io/hino-council-search/#sid=", t)
        t = self.bun("item", "item=juto")                                    # 外部の公的な資料
        self.assertIn("総務省自治財政局財務調査課「", t)

    def test_an(self):
        # 項目が案なら、案であることを示す
        for t in self.tables["suji"]:
            text = self.bun("item", f"item={t['id']}")
            self.assertEqual(D.kotoba("項目の表 kettei が「案」") in text, t["kettei"] == "案", t["id"])

    def test_keika_kaisei(self):
        """経過：資料の一覧の表にある資料には ID を付ける（13行のうち9行）。13行めの下に、改正前の資料と、違う数値を出す。"""
        o = self.data["outou"]["theme"]
        t = "\n".join(self.data["bun"][o[k]] for k in sorted(o) if k.startswith("theme=hoiku&page="))
        s = t.index(f"## {D.bun('midashi-keika')}")
        keika = t[s:t.index("\n## ", s + 1)]
        rows = re.split(r"\n(?=- )", keika)[1:]
        self.assertEqual(len(rows), 13)
        self.assertEqual(sum("（document：" in r for r in rows), 9)
        mae = D.kotoba("資料どうしの関係の表 hyogen が「一部改正」の行の e")
        self.assertEqual([i for i, r in enumerate(rows, 1) if f"  - {mae}：" in r], [13])
        want = "\n".join([
            "  - もとの資料：日野町幼児教育保育施設再編整備計画（令和８年６月一部改正、2026年6月）（document：pt:youho/honpen）"
            "　1ページ　https://www.town.shiga-hino.lg.jp/cmsfiles/contents/0000008/8225/syuusei.pdf#page=1",
            f"  - {mae}：日野町幼児教育保育施設再編整備計画（2025年3月）（document：pt:youho/honpen-202503）",
            "  - " + D.kotoba("資料どうしの関係の表 kara、e の資料の、同じ項目の、改正前と改正後の組み合わせで、atai が違うもの") + D.bun("mcp-kaisei-hani"),
            "    - 新こども園の開園の時期（item：kaien）　保育所あおぞら園・日野幼稚園・必佐幼稚園・桜谷こども園第１園舎："
            "改正前「令和10年度」（34ページ）、改正後「令和11年度」（34ページ）",
            "    - 再編整備スケジュール（item：seibi-sukejuru）　西大路幼稚園：改正前「令和６年度に地区説明会・保護者説明会を実施し、"
            "入園者数や地域事情等を考慮しながら令和９年度にかけて子育て支援施設・学童保育所の拠点としての整備を検討し、"
            "令和1０年度での開設を目指します。」（34ページ）、改正後「令和６年度に地区説明会・保護者説明会を実施し、"
            "入園者数や地域事情等を考慮しながら令和８年度に子育て支援施設・学童保育所の拠点として移行します。」（34ページ）"])
        self.assertIn(want + "\n", rows[12] + "\n")
        # 段落の文が違う5つ（34ページの段落の見出しを添える）。桜谷こども園第２園舎は同じなので出ない
        for n in ("保育所こばと園", "保育所あおぞら園鎌掛分園", "南比都佐幼稚園",
                  "保育所あおぞら園・日野幼稚園・必佐幼稚園・桜谷こども園第１園舎"):
            self.assertIn(f"    - 再編整備スケジュール（item：seibi-sukejuru）　{n}：改正前「", rows[12])
        self.assertEqual(rows[12].count("    - 再編整備スケジュール（item：seibi-sukejuru）"), 5)
        self.assertNotIn("　桜谷こども園第２園舎：", rows[12])
        want = "\n".join([
            "    - 待機児童数（item：taiki）：改正後に、令和7年4月の数値が加わっている（11ページ）",
            "    - 待機児童数から除かれる者の小計（item：nozoku）：改正後に、令和7年4月の数値が加わっている（11ページ）"])
        self.assertIn(want + "\n", rows[12] + "\n")
        # 会議録には ID を付けない
        self.assertNotIn("（document：sp:", keika)
        self.assertEqual((self.info["kaisei_shinai"], self.info["kaisei_hoka"]), (0, 1))

    def test_jogen(self):
        self.assertTrue(all(len(b) <= bm.JOGEN for b in self.data["bun"]))
        o = self.data["outou"]["item"]
        n = max(int(k.rsplit("=", 1)[1]) for k in o if k.startswith("item=taiki&page="))
        self.assertGreater(n, 1)
        for i in range(1, n):
            self.assertTrue(self.bun("item", f"item=taiki&page={i}").endswith(D.bun("mcp-tsuzuki", n=i + 1)))
        self.assertNotIn(D.bun("mcp-tsuzuki", n=n + 1), self.bun("item", f"item=taiki&page={n}"))
        self.assertNotIn(f"item=taiki&page={n + 1}", o)
        # 年齢別の内訳は、資料の中で内訳ごとにまとめる
        t = "".join(self.data["bun"][o[k]] for k in o if k.startswith("item=fusoku&breakdown=1&page="))
        midashi = f"- {D.kotoba('数値と内容の表 kubun')}：2号認定（3〜5歳・保育）"
        self.assertEqual(t.count(midashi), 1)

    def test_nai(self):
        o = self.data["outou"]
        for k in ("item=taikii", "item=taiki&page=99", "item=taiki&document=doc:koho-no771-08"):
            self.assertNotIn(k, o["item"])
        self.assertNotIn("facility=nishioji", o["facility"])
        self.assertEqual(self.data["nai"]["item"], D.bun("mcp-nai", tool="item") + D.bun("mcp-hani-nai"))
        # 表の形で出せない表は、定型文
        self.assertIn(D.bun("mcp-hyo-dasenai"), self.bun("document", "document=doc:shingi-youho-teigen&table=16"))

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
        # 会議録の段落の引用（「」の中）は、もとの資料の字のまま出すので、除いて見る（議員が自分の名前を挙げた段落がある。2026-11-28）
        alltext = re.sub(r"「[^\n]*」", "", "\n".join(self.data["bun"]))
        for n in names:
            self.assertNotIn(n, alltext)
        self.assertIn("（議会での議員の発言）", alltext)

    def test_shisetsu(self):
        t = self.bun("facility", "facility=fa:nishioji-yo")
        self.assertIn("# 西大路幼稚園（facility：fa:nishioji-yo）", t)
        self.assertEqual(t.count("〇町立幼児教育保育施設の再編整備について"), 2)
        self.assertIn("定員（item：teiin）：90", t)
        self.assertNotIn("延床面積（item：", t)                               # 資料の表での記述に出した欄は除く

    def test_shisetsu_danraku(self):
        """再編整備計画 34ページの段落（施設の名前を見出しにした段落。SCHEMA.md 7.2）の文は、施設の記録に同じページの同じ文が
        ある9つの園では、「この施設についての数値と内容」に重ねて出さない。施設の記録に無い新こども園には、2つの資料の2行ずつを出す。"""
        o = self.data["outou"]["facility"]
        suji_midashi = f"## {D.bun('mcp-midashi-shisetsu-suji')}"
        for k in ("fa:nishioji-yo", "fa:kobato", "fa:kaneka", "fa:minamihizusa-yo", "fa:aozora", "fa:hino-yo",
                  "fa:hisa-yo", "fa:sakuradani-1", "fa:sakuradani-2", "fa:shin-kodomoen"):
            with self.subTest(k=k):
                t = "\n".join(self.data["bun"][o[x]] for x in sorted(o)
                              if re.fullmatch(rf"facility={re.escape(k)}&page=[0-9]+", x))
                part = t[t.index(suji_midashi):]
                n = 2 if k == "fa:shin-kodomoen" else 0
                self.assertEqual(part.count("- 再編整備スケジュール（item：seibi-sukejuru）："), n)
                self.assertEqual(part.count("- 新こども園の開園の時期（item：kaien）："), n)
                if n == 0:                                                  # 同じ文は、施設の記録の所に出ている
                    self.assertIn("34ページ", t[:t.index(suji_midashi)])

    def test_kaien_danraku(self):
        # 開園の時期の、再編整備計画の2行は、34ページの段落の見出しを指す
        t = self.bun("item", "item=kaien")
        ichi = (f"  - {D.kotoba('資料の中の場所（bubun・retsu から親をたどった並び）')}：「第３章 日野町幼児教育保育施設の再編整備計画」"
                " ＞ 「４ 再編整備スケジュール」 ＞ 「保育所あおぞら園・日野幼稚園・必佐幼稚園・桜谷こども園第１園舎」")
        self.assertEqual(t.count(ichi + "\n"), 2)

    def test_uchiwake(self):
        # breakdown を付けない組は内訳の無い数値だけ、breakdown=1 は内訳のある数値だけ
        o = self.data["outou"]["item"]
        base = "".join(self.data["bun"][o[k]] for k in o if re.fullmatch(r"item=taiki&page=[0-9]+", k))
        uchi = "".join(self.data["bun"][o[k]] for k in o if re.fullmatch(r"item=taiki&breakdown=1&page=[0-9]+", k))
        kubun = f"- {D.kotoba('数値と内容の表 kubun')}："
        self.assertNotIn(kubun, base)
        self.assertIn(kubun + "うち0歳児", uchi)
        self.assertIn(D.bun("mcp-uchiwake"), base)
        self.assertNotIn(D.bun("mcp-uchiwake"), uchi)
        self.assertIn(D.bun("mcp-uchiwake-dake"), uchi)
        self.assertEqual(sum(1 for k in o if re.fullmatch(r"item=taiki&page=[0-9]+", k)), 3)
        # 内訳のある数値が無い項目には、uchiwake の組を作らない。どれも内訳の項目は、内訳の無い数値が無いことを示す
        self.assertNotIn("item=kaien&breakdown=1", o)
        self.assertNotIn(D.bun("mcp-uchiwake"), self.bun("item", "item=kaien"))
        self.assertIn(D.bun("mcp-uchiwake-nomi"), self.bun("item", "item=fusoku"))
        self.assertIn("item=taiki&document=pt:kodomo/honpen&breakdown=1", o)
        self.assertNotIn("item=taiki&document=plan:sogo6&breakdown=1", o)

    def test_naiyo(self):
        # 単位の無い項目（開園の時期）は「内容」、単位のある項目（待機児童数）は「数値」と出す（docs/design.md 3節）
        for k, atai, toki in (("item=kaien", "数値と内容の表 atai（項目の表 tani が空）", "項目の表 toki（項目の表 tani が空）"),
                              ("item=taiki", "数値と内容の表 atai", "項目の表 toki")):
            with self.subTest(k=k):
                t = self.bun("item", k)
                self.assertIn(f"## {D.bun('mcp-midashi-suji', nakami=D.kotoba(atai))}", t)
                self.assertIn(f"- {D.kotoba(toki)}：", t)

    def test_kakunin_ji(self):
        # 確認の記録は、読む人に通じる字で出す（SCHEMA.md §6.3・§7.2。2026-11-27）
        zenbu = json.dumps(self.data, ensure_ascii=False)
        for ji in ("人が PDF で確認（", "生成AIが画像を2回読んで一致（", "人が確認（", "生成AIが2回読んで一致（"):
            self.assertIn(ji, zenbu)

    def test_chigau(self):
        # 資料の間で一致しない時期は、数値のページと同じ判定で出す（待機児童数の2018年4月）
        t = self.bun("item", "item=taiki")
        midashi = f"## {D.bun('chigau')}"
        self.assertEqual(t.count(midashi), 1)
        part = t[t.index(midashi):t.index(f"## {D.bun('mcp-midashi-suji', nakami=D.kotoba('数値と内容の表 atai'))}")]
        self.assertIn("- 2018年4月：1（", part)
        self.assertIn("なし（会議録 2019年6月14日（議会での答弁））", part)
        self.assertEqual(part.count("\n- "), 1)
        self.assertIn(D.bun("chigau-setsumei"), part)
        for k, i in self.data["outou"]["item"].items():
            if not k.startswith("item=taiki"):
                self.assertNotIn(midashi, self.data["bun"][i], k)

    def test_hiduke(self):
        # 年度だけが分かる資料は年度を出し、資料に日付の記述が無い資料は最後に並べて、そのことを書く
        t = self.bun("facility", "facility=fa:nishioji-yo")
        self.assertIn("指定避難所・指定緊急避難場所一覧（2018年度）", t)
        self.assertIn(D.bun("hiduke-nendo-setsumei"), t)
        t = self.bun("item", "item=kaien")
        self.assertIn(D.bun("hiduke-nashi-setsumei"), t)
        self.assertGreater(t.index("パブリックコメントの実施結果"), t.index("会議録 2025年9月26日"))
        self.assertNotIn(D.bun("hiduke-nashi-setsumei"), self.bun("item", "item=juto"))   # 外部の資料には出さない

    def test_irete_inai(self):
        nai = D.bun("mcp-irete-inai")
        t = self.bun("document", "document=plan:sogo6")
        self.assertIn(f"- {D.kotoba('資料の一覧の表 konkyo')}：{nai}", t)
        self.assertIn(f"## {D.bun('mcp-midashi-hyo-ichiran')}\n{nai}", t)
        t = self.bun("document", "document=pt:youho/honpen-202503")
        self.assertIn(f"## {D.kotoba('資料どうしの関係の表 e')}\n", t)
        t = self.bun("document", "document=doc:yosan-r7-hosei-12")
        self.assertIn(D.bun("mcp-konkyo-nashi", hani=D.kotoba("資料の一覧の表 chu（「根拠：」の記述の「見つからない（…）」の括弧の中の字）")
                                                + "：全ページを「基づ」「法」の字で探し、1ページを読んだ"), t)
        self.assertEqual(bm.konkyo_hani("根拠：記載は見つからない（1ページ（表）を見た）。日付：…"), "1ページ（表）を見た")
        self.assertEqual(bm.konkyo_hani("根拠：もとの資料から取り出した文字が入力に無いので探していない"), "")

    def test_hani(self):
        self.assertIn(D.bun("mcp-shisetsu-teigi", theme="hoiku"), self.bun("facility", "facility=fa:shin-kodomoen"))

    def test_shurui(self):
        # 資料の種類は、内部の値ではなく、docs/design.md の言葉で出す
        self.assertIn(f"- {D.kotoba('資料の一覧の表 shurui')}：{D.kotoba('資料の一覧の表 shurui が「keikaku」')}",
                      self.bun("document", "document=pt:youho/honpen"))
        self.assertIn(f"- {D.kotoba('資料の一覧の表 shurui')}：{D.kotoba('資料の一覧の表 shurui が「koho」')}",
                      self.bun("document", "document=doc:koho-no771-08"))
        for k, i in self.data["outou"]["document"].items():
            self.assertIsNone(re.search(r"資料の種類：[a-z]", self.data["bun"][i]), k)
        tables = copy.deepcopy(self.tables)
        tables["bunsho"][0]["shurui"] = "bosai"
        with self.assertRaises(bm.Stop) as c:
            bm.build(self.inp, tables, bn.read_kotoba(), self.read_problems, D)
        self.assertTrue(any("bosai" in m for _, m in c.exception.problems))

    def test_kuzure(self):
        # 取り出した文字が崩れている数値は、資料の該当部分を出さず、定型文と確認の記録を出す
        t = self.bun("item", "item=taiki&document=doc:hyoka-r4-senryaku-kensho")
        self.assertEqual(t.count(D.bun("inyo-kuzure")), 6)
        self.assertNotIn("「基準値【R1】", t)
        self.assertIn("生成AIが画像を2回読んで一致（2026-11-23）", t)
        self.assertNotIn(D.bun("inyo-kuzure"), self.bun("item", "item=taiki&document=pt:youho/honpen"))

    def test_shiryo_hani(self):
        t = self.bun("document", "document=doc:koho-no771-08")
        lines = t.split("\n")
        self.assertEqual(lines[2], D.bun("mcp-shiryo-hani"))                # 名前のすぐあと
        self.assertEqual(lines[3], D.bun("mcp-shiryo-kazu", hyo=3, atai=10, teigi=1, kara=0, e=0, q=0))
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

    # ---- 論点（issue） ----

    def issue_pages(self, slug):
        o = self.data["outou"]["issue"]
        n = sum(1 for k in o if k.startswith(f"issue={slug}&page="))
        return [self.data["bun"][o[f"issue={slug}&page={i}"]] for i in range(1, n + 1)]

    def test_matome(self):
        """まとまり（SCHEMA.md 7.9、docs/design.md 4節。2026-11-28）：issue にまとまりの ID を付けると、まとまりの論点の全部と、
        取り上げた質問の一覧を返す。論点の issue には、質問の一覧のあとに、同じまとまりの論点と、同じ題で取り上げられた論点を出す。"""
        mid = "b33-k1:職員の育成と人事評価"
        t = "\n".join(self.issue_pages(mid))
        self.assertIn(f"# 職員の育成と人事評価（issue：{mid}）", t)
        self.assertIn(D.bun("ronten-matome-setsumei-an"), t)
        ronten = [x for x in t.split("\n") if x.startswith("## ")]
        self.assertEqual([re.sub("（issue：.*", "", x[3:]) for x in ronten],
                         ["職員研修とOJT", "メンター制度", "人事評価", "職員のメンタルヘルス", "職場の風土づくり", "職員のやりがい",
                          "職員の知識と経験の組織での共有", "職員の配置と異動"])
        self.assertIn("- 2017年12月13日　一般質問　「人材育成の方針」　" + D.bun("mcp-matome-bubun", n=13), t)
        # field ㉝ の論点の一覧に、まとまりの ID がある
        f = "\n".join(self.data["bun"][i] for k, i in sorted(self.data["outou"]["field"].items()) if k.startswith("field=㉝&page="))
        self.assertIn(f"#### 職員の育成と人事評価（issue：{mid}）", f)
        # 論点の issue：質問の一覧のあとに、同じまとまりの論点と、同じ題で取り上げられた論点（ほかのテーマの論点も含む）
        i = self.issue_pages("b33-07")[0]
        a, b, c = (i.index("## " + x) for x in (D.bun("mcp-midashi-issue-gikai", n=6), D.bun("mcp-midashi-issue-matome"),
                                                D.bun("mcp-midashi-issue-issho")))
        self.assertTrue(a < b < c, (a, b, c))
        self.assertIn("- メンター制度（issue：b33-08）\n", i)
        self.assertIn("- 適切な行政運営（issue：b33-k1）　" + D.bun("mcp-issue-issho-kazu", n=6), i)
        self.assertIn("（テーマ：公共施設の再編）", i)
        # 2つの分野の一覧で違うまとまりに入る論点は、両方のまとまりを出す
        i = self.issue_pages("b29-14")[0]
        self.assertIn("（issue：b29-k2:行政手続とキャッシュレス決済）", i)
        self.assertIn("（issue：b33-k1:窓口）", i)
        # 確定済みの記録だけの論点にも、同じまとまりの論点を出す
        self.assertIn("## " + D.bun("mcp-midashi-issue-matome"), self.issue_pages("hoiku33")[0])

    def test_issho_of(self):
        """同じ質問の同じ題で一緒に取り上げられた論点の数（題の数の多い順。同じ数は事項の表の順）。"""
        class Inp:
            def ippan_dai(self, sid, paras):
                return sid, [dict(n="1")] if ("0000000001_20250310_0002", 1) in paras else [dict(n="2")]
        Q = "iq:0000000001_20250310_0001"
        rows = [dict(question=Q, n="", jiko="a", hani="sp:0000000001_20250310_0002/1"),
                dict(question=Q, n="", jiko="b", hani="sp:0000000001_20250310_0002/1-2"),
                dict(question=Q, n="", jiko="c", hani="sp:0000000001_20250310_0002/3"),
                dict(question=Q, n="2", jiko="a", hani="sp:0000000001_20250310_0002/3"),
                dict(question="sq:0000000001_20250305_0001", n="", jiko="d", hani="sp:0000000001_20250305_0001/1")]
        j = [dict(id=x) for x in "abcd"]
        self.assertEqual(bm.issho_of(Inp(), rows, j), {"a": [("b", 1), ("c", 1)],
                                                       "b": [("a", 1)], "c": [("a", 1)]})

    @staticmethod
    def setsu(t, midashi):
        """応答の文の、見出しの行から次の見出しの前まで。"""
        s = t.index(midashi + "\n")
        e = t.find("\n## ", s + 1)
        return t[s:e if e >= 0 else len(t)]

    def test_ronten_ichiran(self):
        # テーマの応答の論点の一覧（事項の表があるテーマ）：計画の章立ての要素ごとに、章立ての順にまとめ、種類を出す。
        # 記録のある論点は名前と ID、記録の無い論点は、ID を付けずに、まだ入れていないことの文（2026-11-27）
        T = bm.read_notes(self.inp)["hoiku"]
        self.assertEqual((len(T["topics"]), len(T["junbi"]), len(T["jiko"])), (57, 0, 57))
        t = "\n".join(self.data["bun"][i] for k, i in sorted(self.data["outou"]["theme"].items())
                      if k.startswith("theme=hoiku&page="))
        s = t.index(f"## {D.bun('mcp-midashi-ronten')}\n")
        part = t[s:t.index("\n## ", s + 1)]
        keikaku = "日野町幼児教育保育施設再編整備計画"
        self.assertIn(D.bun("mcp-ronten-setsumei-jiko", keikaku=keikaku), part)
        mi = [x[4:] for x in part.split("\n") if x.startswith("### ")]
        self.assertEqual(mi[:2], ["３ 計画の期間", "７ 日野町の幼児教育・保育をめぐる課題"])
        self.assertEqual(mi[-1], D.bun("ronten-nashi", keikaku=keikaku))
        self.assertEqual(len(mi), 9)
        self.assertIn(D.bun("ronten-kazu-setsumei"), part)
        gyo = [x for x in part.split("\n") if x.startswith("- ")]
        self.assertEqual(len(gyo), 57)
        # 生成AIの2回の読み取りの行を入れたので、全部に ID がある（2026-11-28。候補から足した11と2と、2回めの読み取りの候補から
        # 足した7を含む）
        self.assertEqual(sum("（issue：" in x for x in gyo), 57)
        for i in range(37, 57):
            self.assertIn(f"issue=hoiku{i}", self.data["outou"]["issue"])
        # 章立てに入らない論点のうち、資料の外のまとまりがあるものは、まとまりの名前の見出しにまとめる（2026-11-28）
        nashi = part[part.index("### " + D.bun("ronten-nashi", keikaku=keikaku)):]
        # 依頼者が決めたまとまり（園の安全）と、生成AIの案のまとまり（地域と子育てなど）で、見出しの下の文が違う。まとまりの名前の
        # あとに、まとまりの ID を付ける（2026-11-28）
        self.assertIn("\n#### 園の安全（issue：hoiku:園の安全）\n" + D.bun("ronten-matome-setsumei") + "\n", nashi)
        self.assertIn("\n#### 地域と子育て（issue：hoiku:地域と子育て）\n" + D.bun("ronten-matome-setsumei-an") + "\n", nashi)
        anzen = nashi[nashi.index("#### 園の安全"):nashi.index("#### 保育士の勤務と配置")]
        self.assertEqual([re.sub("　質問 .*", "", x) for x in anzen.split("\n") if x.startswith("- ")],
                         ["- 園の施設の修繕と安全対策（issue：hoiku33）　種類：取り組み",
                          "- 園での感染症対策（issue：hoiku34）　種類：取り組み",
                          "- 園児の安全対策（issue：hoiku42）　種類：取り組み"])
        # 「ほかの分野にかかわる話題」のまとまりは、最後に置く（2026-11-28）
        hoka = nashi[nashi.index(f"#### {bn.jiko.HOKA}"):]
        self.assertNotIn("\n#### ", hoka)
        self.assertIn(f"#### {bn.jiko.HOKA}（issue：hoiku:{bn.jiko.HOKA}）\n" + D.bun("ronten-matome-setsumei")
                      + "\n- 子育て施策の情報発信（issue：hoiku48）　種類：取り組み　質問 ", hoka)
        self.assertTrue(any(x.startswith("- 給食のアレルギー対応（issue：hoiku40）　種類：取り組み　質問 ") for x in gyo))
        self.assertEqual(sum(x.endswith(f"（{D.bun('ronten-mada')}）") for x in gyo), 0)
        self.assertTrue(any(x.startswith("- 新こども園の定員（issue：teiin）　種類：数・時期・場所・費用") for x in gyo))
        # 論点ごとに、質問の数と、いちばん古い日といちばん新しい日を添える（2026-11-28）
        self.assertTrue(all(re.search("　質問 [0-9]+件（[0-9]+年[0-9]+月[0-9]+日(〜[0-9]+年[0-9]+月[0-9]+日)?）$", x)
                            or x.endswith("　" + D.bun("ronten-kazu-nashi")) for x in gyo), [x for x in gyo if "　質問 " not in x])
        # 議会での質問が無く、町の資料の記述だけがある論点は、質問の数を0と出す
        self.assertIn("- 認定こども園3園への再編整備の時期（issue：hoiku04）　種類：数・時期・場所・費用　" + D.bun("ronten-kazu-nashi"), gyo)
        for P in ("子育て環境の未来に向けての提言", "日野町幼児教育保育施設再編整備計画（案）", "日野町認定こども園整備基本構想",
                  "小規模保育施設の整備"):
            self.assertFalse(any(P in x for x in gyo), P)
        for slug in ("hoiku07", "hoiku09", "hoiku12"):
            self.assertNotIn(f"issue={slug}", self.data["outou"]["issue"])

    def test_mokuteki(self):
        # 論点の応答の「目的と手段」：両端が事項の表にある、入力の確定済みの組だけ。相手の名前と ID、資料の文、もとの資料
        t = "\n".join(self.issue_pages("hoiku10"))
        part = self.setsu(t, "## 目的と手段")
        self.assertIn(D.bun("mokuteki-setsumei"), part)
        self.assertEqual([x for x in part.split("\n") if x.startswith("- ")],
                         ["- 手段：幼保連携型認定こども園の新設（issue：hoiku08）",
                          "- 手段：幼児教育保育施設の再編整備（issue：hoiku11）"])
        self.assertEqual(part.count("  - 資料の文：「"), 4)
        self.assertIn("    - もとの資料：日野町認定こども園整備基本構想（2025年8月）　5ページ　https://", part)
        self.assertIn("- 目的：適正な集団規模の確保（issue：hoiku10）", "\n".join(self.issue_pages("hoiku08")))
        self.assertNotIn("## 目的と手段", "\n".join(self.issue_pages("hiyo")))
        # 両端の片方が事項の表に無い組（「より良い幼児教育保育環境を…」→ 再編整備）は出さない
        self.assertNotIn("より良い幼児教育保育環境", self.setsu("\n".join(self.issue_pages("hoiku11")), "## 目的と手段"))

    def test_konkyo(self):
        # 質問が取り上げた資料（taio/konkyo.tsv）：資料の応答に、issue と同じ形で質問の一覧と、続きで段落を出す
        o = self.data["outou"]["document"]
        t = self.bun("document", "document=doc:shingi-youho-teigen")
        # 提言（2024年2月）より前の質問は、提言に結び付けない（SCHEMA.md 7.10。2026-11-28）
        part = self.setsu(t, "## " + D.bun("mcp-midashi-konkyo", n=12))
        # 題は、テーマの定義にある質問も、一般質問の台帳の題（SCHEMA.md 7.10。2026-11-28）
        # 2025年3月10日の質問には、入力の確定済みの行と、2回めの読み取り（2026-11-28）の行がある。確定済みの行だけを出す
        self.assertIn("- 2025年3月10日　一般質問　「幼児教育保育施設再編整備計画（案）について」\n  - "
                      + D.bun("shitsumon-kakutei") + "\n  - この資料に関する部分（8か所）（page：4）", part)
        self.assertEqual(part.count("  - " + D.kotoba("質問と事項の対応の表 question") + "\n"), 11)   # 読み取りの質問
        self.assertNotIn("2023年", part)
        self.assertIn(D.bun("keisai-yomi", short="この資料"), part)
        rest = self.data["bun"][o["document=doc:shingi-youho-teigen&page=4"]]
        self.assertEqual(rest.count("\n- 「"), 8)
        self.assertIn("発言の段落7", rest)
        self.assertNotIn(D.kotoba("質問と事項の対応の表 yomi が「一致」"), rest)      # 確定済みの質問の段落には付けない
        self.assertNotIn(D.kotoba("質問と事項の対応の表 yomi が「1回だけ」"), rest)
        rest = self.data["bun"][o["document=doc:shingi-youho-teigen&page=2"]]
        self.assertEqual(rest.count("\n- 「"), rest.count(D.kotoba("質問と事項の対応の表 yomi が「一致」"))
                         + rest.count(D.kotoba("質問と事項の対応の表 yomi が「1回だけ」")))
        self.assertIn("この資料を取り上げている、議会での質問 12 件", t)
        # 計画は、質問の日より前か同じ日付の資料に結び付く。令和８年６月一部改正より前の質問しか無いので、改正後の資料には出ない
        self.assertIn("document=pt:youho/honpen-202503&page=2", o)
        self.assertNotIn("document=pt:youho/honpen&page=2", o)
        self.assertIn("document=doc:jigyo-shinkodomoen-kousou&page=2", o)
        self.assertNotIn("document=doc:koho-no771-08&page=2", o)
        self.assertNotIn(D.bun("mcp-midashi-konkyo", n=1), self.bun("document", "document=doc:koho-no771-08"))
        # テーマの資料の一覧で、取り上げた質問がある資料が分かる
        t = "\n".join(self.data["bun"][i] for k, i in self.data["outou"]["theme"].items() if k.startswith("theme=hoiku&page="))
        ari = [x for x in t.split("\n") if x.endswith(D.bun("mcp-shiryo-konkyo-ari"))]
        self.assertEqual(len(ari), 5)
        self.assertTrue(ari[0].startswith("- 子育て環境の未来に向けての提言（最終報告）"))

    def test_themes4(self):
        """4つのテーマとも、theme と issue で、確定済みの記録を返す（2026-11-27）。"""
        ichiran = self.bun("theme", "")
        for th, name in (("hoiku", "幼児教育・保育施設の再編"), ("chiiki", "地域のあり方・自治会活動"),
                         ("kaigo", "高齢者福祉・介護"), ("kokyo", "公共施設の再編")):
            self.assertIn("- " + D.bun("mcp-kagi", name=name, hikisu="theme", ji=th), ichiran)
        notes = bm.read_notes(self.inp)
        self.assertEqual(list(notes), ["chiiki", "hoiku", "kaigo", "kokyo"])          # テーマの定義の順
        self.assertEqual({th: len(T["topics"]) for th, T in notes.items()},
                         dict(hoiku=57, kaigo=45, kokyo=56, chiiki=45))          # 2回めの読み取りのあと（2026-11-28）
        self.assertEqual({th: len(T["junbi"]) for th, T in notes.items()}, dict(hoiku=0, kaigo=0, kokyo=0, chiiki=0))
        slugs = [slug for T in notes.values() for _, slug, _, _ in T["topics"]]
        # ID がテーマをまたいで重なるのは、公共施設の再編と地域のあり方に共通の事項の4つだけ（2026-11-28。kokyo38 は2回めの
        # 読み取りのあとに共通にした）
        self.assertEqual(sorted({x for x in slugs if slugs.count(x) > 1}), ["kokyo10", "kokyo11", "kokyo35", "kokyo38"])
        o = self.data["outou"]
        for th, T in notes.items():
            t = "\n".join(self.data["bun"][o["theme"][k]] for k in sorted(o["theme"]) if k.startswith(f"theme={th}&page="))
            part = self.setsu(t, f"## {D.bun('mcp-midashi-ronten')}")
            if not T["jiko"]:                                                           # 事項の表が無いテーマ
                self.assertEqual([x for x in part.split("\n") if x.startswith("- ")],
                                 ["- " + D.bun("mcp-kagi", name=P, hikisu="issue", ji=slug) for P, slug, _, _ in T["topics"]]
                                 + ["- " + D.bun("mcp-junbi", name=x) for x in T["junbi"]])
            for _, slug, _, _ in T["topics"]:
                self.assertIn(f"issue={slug}", o["issue"])
            if th != "hoiku":                                                           # テーマの表に行が無いテーマ
                self.assertNotIn(f"## {D.kotoba('テーマの表 shu が「説明の文」')}\n", t)
                self.assertNotIn(f"## {D.kotoba('テーマの表 shu が「施設の表」')}\n", t)
                self.assertNotIn("（準備中）", t)
        # 経過の行の数（出さない過程の記録を除く）
        for th, n in (("kaigo", 5), ("chiiki", 7), ("kokyo", 0), ("hoiku", 13)):
            t = "\n".join(self.data["bun"][o["theme"][k]] for k in sorted(o["theme"]) if k.startswith(f"theme={th}&page="))
            if n:
                self.assertEqual(self.setsu(t, f"## {D.bun('midashi-keika')}").count("\n- "), n)
            else:
                self.assertNotIn(f"## {D.bun('midashi-keika')}\n", t)
        # facility で返す内容が無い施設（kokyo と chiiki の公民館など）は、施設の一覧にも、facility の組にも入れない
        for th in ("kokyo", "chiiki"):
            self.assertNotIn(f"## {D.bun('mcp-midashi-shisetsu')}\n", self.bun("theme", f"theme={th}"))
        self.assertNotIn("facility=fa:hino-km", o["facility"])

    def test_katei_dasanai(self):
        # 検査で止まる過程の記録は、出さない。出さない行は、理由に当たることを確認している
        out = {th: ronten.katei_dasanai(self.inp, th) for th in ("hoiku", "kaigo", "kokyo", "chiiki")}
        self.assertEqual({th: [] for th in out}, {th: p for th, (_, p) in out.items()})
        self.assertEqual({th: len(x) for th, (x, _) in out.items()}, dict(hoiku=0, kaigo=7, kokyo=0, chiiki=3))
        for th in out:
            steps = {r["step"] for r, _ in out[th][0]}
            self.assertFalse(steps & {r["step"] for r in ronten.katei(self.inp, th)})

    def test_issue_teiin(self):
        """論点「新こども園の定員」：町の資料の記述1、説明と答弁6（うち1つに作成者の注）、今後検討・決定するとされていること1、
        質問8件（確定済み3件は20、7、5か所。読み取りの5件は3、3、10、7、2か所）。質問ごとの部分は、一覧に示した番号の続きから始まる。
        2025年9月12日の質問は、ほかの論点に確定済みの記録があり、この論点には読み取りの行だけがあるので、読み取りの質問として出る
        （2026-11-28）。確定済みの3件にも読み取りの行があるが、確定済みの記録だけを出す（SCHEMA.md 7.10）。"""
        pages = self.issue_pages("teiin")
        t = pages[0]
        n = {}
        for k in ("mcp-midashi-issue-shiryo", "mcp-midashi-issue-setsumei", "mcp-midashi-issue-kongo"):
            n[k] = self.setsu(t, f"## {D.bun(k)}").count("\n- 「")
        self.assertEqual(list(n.values()), [1, 6, 1])
        setsumei = self.setsu(t, f"## {D.bun('mcp-midashi-issue-setsumei')}")
        self.assertEqual(setsumei.count("  - " + D.bun("mcp-issue-chu", chu="")), 1)
        gikai = self.setsu(t, f"## {D.bun('mcp-midashi-issue-gikai', n=8)}")
        self.assertEqual(re.findall(r"に関する部分（(\d+)か所）", gikai), ["3", "20", "3", "7", "5", "10", "7", "2"])
        self.assertNotIn("\n- 「", gikai)                                   # 1回めには、段落の文を出さない
        heads = re.findall(r"\n- (.+)\n  - .+\n  - .+（page：(\d+)）", gikai)
        self.assertEqual(len(heads), 8)
        self.assertEqual([D.bun("shitsumon-kakutei") in x for x in re.findall(r"\n- .+\n  - (.+)\n", gikai)],
                         [False, True, False, True, True, False, False, False])
        hi = [tuple(int(x) for x in re.match(r"(\d+)年(\d+)月(\d+)日", h).groups()) for h, _ in heads]
        self.assertEqual(hi, sorted(hi, reverse=True))                          # 日付の新しい順
        for (h, p), k in zip(heads, (3, 20, 3, 7, 5, 10, 7, 2)):
            body = pages[int(p) - 1]
            self.assertIn(f"\n### {h}　", body)
            alltext = "\n".join(x for x in pages[int(p) - 1:] if f"\n### {h}　" in x)
            self.assertEqual(alltext.count("\n- 「"), k)
        self.assertTrue(all(len(x) <= bm.JOGEN for x in pages))
        self.assertTrue(t.endswith(D.bun("mcp-tsuzuki", n=2)))

    def test_issue_hani(self):
        """論点の応答に、扱っている質問の範囲を、数と時期で書く（データから数える）。"""
        for slug in ("hiyo", "menseki", "yochi", "teiin"):
            t = "\n".join(self.issue_pages(slug))
            self.assertIn(D.bun("mcp-issue-hani", toi=16, shitsugi=3, toi_zumi=4, kikan="2025年3月〜2025年12月",
                                shitsugi_zumi=3), t)
            # 残りの12問は生成AIが2回読んだので、「まだ読んでいません」は出ない（2026-11-28）
            self.assertNotIn("まだ読んでいません", t)
            # 2回めの読み取り（2026-11-28）の35問を含む。13問は、当たる論点が無かった
            self.assertIn(D.bun("mcp-issue-hani-yomi", n=76, kikan="2017年3月〜2026年6月", soto=60, toi=16), t)
            self.assertIn(D.bun("mcp-issue-hani-yomi-nashi", n=13), t)
            self.assertNotIn(D.bun("mcp-issue-hani-shitsugi", n=0), t)
        # ほかのテーマも、テーマごとの数で出す
        for slug, kazu, toi, shitsugi in (
                ("kaigo01", dict(toi=11, shitsugi=11, toi_zumi=6, kikan="2024年3月〜2025年12月", shitsugi_zumi=5),
                 None, dict(n=6)),
                ("kokyo01", dict(toi=22, shitsugi=18, toi_zumi=5, kikan="2021年6月〜2024年9月", shitsugi_zumi=2),
                 None, dict(n=16)),
                ("chiiki01", dict(toi=22, shitsugi=10, toi_zumi=1, kikan="2021年6月", shitsugi_zumi=1),
                 None, dict(n=9))):
            with self.subTest(slug=slug):
                t = "\n".join(self.issue_pages(slug))
                self.assertIn(D.bun("mcp-issue-hani", **kazu), t)
                self.assertIn(D.bun("mcp-issue-hani-shitsugi", **shitsugi), t)
                if toi:
                    self.assertIn(D.bun("mcp-issue-hani-toi", **toi), t)
                elif slug == "kaigo01":                 # 介護は、未読の一般質問を全部読んだ（2026-11-28）
                    self.assertNotIn("残りの一般質問", t)
        # 介護は、テーマの定義の未読の5問と、題名に語がある17問を読み、2回めの読み取りで11問を読んだ。2026年3月10日の質問は、
        # 当たる論点が無かった（2026-11-28）
        t = "\n".join(self.issue_pages("kaigo01"))
        self.assertIn(D.bun("mcp-issue-hani-yomi", n=33, kikan="2017年3月〜2026年3月", soto=23, toi=11), t)
        self.assertIn(D.bun("mcp-issue-hani-yomi-nashi", n=1), t)
        self.assertNotIn(D.bun("mcp-issue-hani-yomi-nashi", n=0), "\n".join(self.issue_pages("hiyo")))

    def test_kokyo_chiiki(self):
        """公共施設の再編と地域のあり方（2026-11-28）：論点の一覧は、作成者が決めたまとまりごと。共通の事項の issue は1つで、
        どちらのテーマで読んだ質問も並べる。範囲の文は、読んだ質問の数（定義の問いは、台帳の turns で照合する）。"""
        t = self.bun("theme", "theme=kokyo")
        part = self.setsu(t, f"## {D.bun('mcp-midashi-ronten')}")
        self.assertIn(D.bun("mcp-ronten-setsumei-matome"), part)
        # まとまりは、表で最初に出る順（2026-11-28 の案で、前のまとまりを分けた。まとまりに入れていない論点は無い）
        self.assertEqual([re.sub("（issue：.*", "", x[4:]) for x in part.split("\n") if x.startswith("### ")][:7],
                         ["総合管理計画と基本方針", "老朽化と更新費用", "公民館の施設と利用", "公民館の制度と運営", "学校の施設",
                          "跡地と使わなくなった施設", "公園の施設"])
        self.assertNotIn(D.bun("ronten-matome-nashi"), part)
        self.assertIn("### 学校の施設（issue：kokyo:学校の施設）\n" + D.bun("ronten-matome-setsumei") + "\n", part)
        self.assertEqual(part.count(f"（{D.bun('ronten-mada')}）"), 4)
        # 共通の事項は、テーマごとに違うまとまりに入る（事項の表の matome の「<テーマ>=<名前>」の形）
        c = self.setsu(self.bun("theme", "theme=chiiki"), f"## {D.bun('mcp-midashi-ronten')}")
        mi = [re.sub("（issue：.*", "", x[4:]) for x in c.split("\n") if x.startswith("### ")]
        self.assertEqual((mi[0], mi[-1]), ("公民館", bn.jiko.HOKA))
        self.assertIn("kokyo10", self.setsu(c, "### 公民館（issue：chiiki:公民館）"))
        self.assertIn("kokyo10", self.setsu(part, "### 公民館の制度と運営（issue：kokyo:公民館の制度と運営）"))
        for slug in ("kokyo10", "kokyo11", "kokyo35"):
            self.assertIn(f"（issue：{slug}）", part)
            self.assertIn(f"（issue：{slug}）", c)
        # 地域のあり方でだけ読んだ質問（2021年3月12日「地域コミュニティーの再編」）も、共通の事項の issue に出る
        i = "\n".join(self.issue_pages("kokyo10"))
        self.assertIn("2021年3月12日　一般質問　「地域福祉活動」「地域コミュニティーの再編」", i)
        self.assertIn("「公共施設の再編」のうち", i)
        for slug, n, kikan, soto, shitsugi in (("kokyo01", 49, "2017年3月〜2026年6月", 33, 16),
                                               ("chiiki01", 42, "2017年12月〜2026年6月", 21, 9)):
            t = "\n".join(self.issue_pages(slug))
            self.assertIn(D.bun("mcp-issue-hani-yomi", n=n, kikan=kikan, soto=soto, toi=22), t)
            self.assertNotIn("残りの一般質問", t)
            self.assertIn(D.bun("mcp-issue-hani-shitsugi", n=shitsugi), t)
        # 資料の一覧の表に足した2つの資料（2026-11-28）
        self.assertIn(D.kotoba("資料の一覧の表 shurui が「chiiki」"), self.bun("document", "document=doc:chiiki-jichikai-chosa"))
        self.assertIn("document=pt:kokyo-kanri/honpen&page=2", self.data["outou"]["document"])

    def test_issue_hani_dake(self):
        """記録がある問いか質疑が0のテーマでも、範囲の文が文として読める（docs/design.md 4節）。"""
        class Inp:
            def __init__(self, taio):
                self.t = {ronten.THEMES: [dict(theme="x", kind="問い", value="iq:0000000001_20250310_0001"),
                                          dict(theme="x", kind="問い", value="iq:0000000001_20240910_0001"),
                                          dict(theme="x", kind="質疑", value="sq:0000000001_20250305_0001")],
                          ronten.TAIO: [dict(question=q, point="P", status="confirmed") for q in taio]}

            def ronten_tsv(self, path):
                return self.t[path]

        class Tk:
            pass
        tk = Tk()
        tk.D = D
        tk.yomi_q = {}
        tk.inp = Inp(["sq:0000000001_20250305_0001"])
        self.assertEqual([bm.owari(x) for x in bm.Tsukuru.issue_hani(tk, "x")],
                         [D.bun("mcp-issue-hani-shitsugi-dake", toi=2, shitsugi=1, shitsugi_zumi=1),
                          D.bun("mcp-issue-hani-toi", n=2, kikan="2024年9月〜2025年3月")])
        tk.inp = Inp(["iq:0000000001_20250310_0001"])
        self.assertEqual([bm.owari(x) for x in bm.Tsukuru.issue_hani(tk, "x")],
                         [D.bun("mcp-issue-hani-toi-dake", toi=2, shitsugi=1, toi_zumi=1, kikan="2025年3月"),
                          D.bun("mcp-issue-hani-toi", n=1, kikan="2024年9月"),
                          D.bun("mcp-issue-hani-shitsugi", n=1)])
        tk.inp = Inp([])
        self.assertEqual(bm.Tsukuru.issue_hani(tk, "x"), [])

    def test_issue_onaji(self):
        """試作のページと同じ集め方（build_note の collect と Page.ronten）の結果から作られている：記述の数、質問の数、
        段落の数、引用の字。4つの論点の合計で、質問と答弁は16件、関する部分は96か所。"""
        import datetime
        T = bm.read_notes(self.inp)["hoiku"]
        model, problems, _ = bn.collect(self.inp, T, "hoiku")
        self.assertEqual(problems, [])
        pg = bn.Page(self.inp, T, model)
        page, counts, _ = pg.render(datetime.date(2026, 11, 27))
        nq = nb = 0
        for (P, slug, short, _), (P2, nk, nt) in zip(T["topics"][:4], counts[:4]):     # 前からある4つの論点
            with self.subTest(slug=slug):
                R = pg.ronten(P)
                pages = self.issue_pages(slug)
                k = next(i for i, x in enumerate(pages) if "\n### " in x)     # 質問ごとの部分は、新しい応答から始まる
                first, rest = "\n".join(pages[:k]), "\n".join(pages[k:])
                self.assertFalse(any("\n### " in x for x in pages[:k]))
                self.assertTrue(all("\n### " in x for x in pages[k:]))
                setsumei = self.setsu(first, f"## {D.bun('mcp-midashi-issue-setsumei')}")
                self.assertEqual(setsumei.count("\n- 「"), nk)
                for x in R["ko"]:
                    self.assertIn(f"\n- 「{x['quote']}」\n", setsumei)
                gikai = self.setsu(first, f"## {D.bun('mcp-midashi-issue-gikai', n=nt)}")
                self.assertEqual([int(x) for x in re.findall(r"に関する部分（(\d+)か所）", gikai)],
                                 [len(q["paras"]) for q in R["qs"]])
                for q in R["qs"]:
                    for sid, i, para in q["paras"]:
                        self.assertIn(f"- 「{para}」\n", rest)
                        self.assertIn(keys.search_url(sid, i), rest)
                self.assertEqual(rest.count("\n- 「"), sum(len(q["paras"]) for q in R["qs"]))
                nq += nt
                nb += sum(len(q["paras"]) for q in R["qs"])
        # 4つの論点の合計（確定済みの記録だけのときは、質問16件、関する部分96か所。2026-11-28 に読み取りの行を入れた。
        # 2回めの読み取りの前は、30件、188か所）
        # 総合計画の分野の読み取り（2026-11-28）で、新こども園の整備費用と財源（hiyo）に、分野の読み取りの質問が3件（14か所）加わった
        self.assertEqual((nq, nb), (35, 221))
        # 試作のページは、幼保の57の論点の全部（2026-11-28 に候補から11を足した。37の論点のときは 2052。さらに2を足す前の
        # 48の論点のときは 2189。2回めの読み取りの前の50の論点のときは 2196。総合計画の分野の読み取りの前は 2576。分野の読み取りの
        # 候補を入れた幼保の論点に、分野の読み取りの部分が加わった）（確定済みの記録だけのときは、13の論点で121か所）
        self.assertEqual(sum(int(x) for x in re.findall(r"に関する部分を表示（(\d+)か所）", page)), 2615)

    def test_issue_namae(self):
        # 発言者の名前（議員と、答弁した人）を出さない。区分は発言者の役職から決める（委員長の報告は議員の発言）
        sids = set()
        for th, T in bm.read_notes(self.inp).items():                                   # 4つのテーマの全部
            model, _, _ = bn.collect(self.inp, T, th)
            sids |= {keys.sid_of(x["source"]) for x in model["ko"] if x["source"].startswith("sp:")}
            sids |= {sid for r in model["ta"] + model["yomi"] for sid, _ in keys.paras_of(r["hani"])}
        names = {self.inp.speaker(s) for s in sids}
        self.assertGreaterEqual(len(names), 4)
        o = self.data["outou"]["issue"]
        alltext = "\n".join(self.data["bun"][i] for i in set(o.values()))
        # 引用（「- 「」で始まる行。会議録の段落と資料の文）の中に、発言者の名前が原文のまま出ることはある（2026-11-28。
        # 公共施設の答弁者の名前が、介護の質問の段落の原文にある）。引用の外に出ないことを確認する
        soto = "\n".join(x for x in alltext.split("\n") if not x.startswith("- 「"))
        for nm in names:
            self.assertNotIn(nm, soto)
        self.assertNotIn("議員）", alltext)
        t = self.bun("issue", "issue=yochi")
        i = t.index("「園舎、園庭、駐車場を含め、8,000平米から１万平米程度を想定しているとの答弁でした。」")
        self.assertIn("  - " + D.bun("mcp-issue-jiki-kubun", jiki="2025年3月24日", kubun="議会での議員の発言"), t[i:i + 200])
        self.assertIn("（議会での答弁）", alltext)

    def test_yomi(self):
        """生成AIの2回の読み取りの行（SCHEMA.md 7.10）：質問ごとに未確認の印、段落ごとに一致か1回だけか（2026-11-28）。"""
        pages = self.issue_pages("hoiku17")
        first = pages[0]
        mi = D.kotoba("質問と事項の対応の表 question")
        self.assertIn(D.bun("yomi-setsumei", short="保育士等の不足"), first)
        self.assertEqual(first.count(f"  - {mi}\n"), 26)                    # 2回めの読み取りの前は24
        # テーマの定義に無い質問の題は、論点に付いた段落の発言を含む問いの題名だけ（SCHEMA.md 7.10。2026-11-28）
        self.assertIn("- 2017年9月14日　一般質問　「待機児童問題」\n  - " + mi, first)
        self.assertNotIn("松尾公園テニスコート", first)
        rest = "\n".join(pages[1:])
        n = rest.count("\n- 「")
        ichi = rest.count("  - " + D.kotoba("質問と事項の対応の表 yomi が「一致」") + "\n")
        ikkai = rest.count("  - " + D.kotoba("質問と事項の対応の表 yomi が「1回だけ」") + "\n")
        self.assertEqual(ichi + ikkai, n)
        self.assertGreater(ichi, 0)
        self.assertGreater(ikkai, 0)

    def test_event(self):
        """出来事（懇話会、パブリックコメント、説明会）：theme に数と ID、event で質問と段落（2026-11-28）。"""
        t = "\n".join(self.data["bun"][i] for k, i in sorted(self.data["outou"]["theme"].items())
                      if k.startswith("theme=hoiku&page="))
        part = self.setsu(t, "## " + D.kotoba("資料と出来事の名前の表 shu が「出来事」"))
        self.assertEqual([x for x in part.split("\n") if x.startswith("- ")],
                         ["- 懇話会（日野町幼児教育保育の在り方検討懇話会）（event：konwakai）　" + D.bun("mcp-dekigoto-kazu", n=18),
                          "- パブリックコメント（event：pabukome）　" + D.bun("mcp-dekigoto-kazu", n=8),
                          "- 説明会（住民や保護者への説明会、行政懇談会）（event：setsumeikai）　" + D.bun("mcp-dekigoto-kazu", n=9),
                          # 2回めの読み取りで足した出来事（2026-11-28）。名前の表の順
                          "- こども誰でも通園制度に伴う会議（event：hoiku-daredemo-tsuen-kaigi）　" + D.bun("mcp-dekigoto-kazu", n=1),
                          "- 保育現場の部会（event：hoiku-genba-bukai）　" + D.bun("mcp-dekigoto-kazu", n=1),
                          "- 基本構想の策定委員会（event：hoiku-kousou-sakutei-iinkai）　" + D.bun("mcp-dekigoto-kazu", n=3),
                          "- 設計委託業務の公募型プロポーザル（event：hoiku-sekkei-proposal）　" + D.bun("mcp-dekigoto-kazu", n=1)])
        # 公共施設の再編と地域のあり方の出来事（2026-11-28）。行政懇談会と意見交換会は、テーマごとに ID が違う
        for th, n in (("kokyo", 12), ("chiiki", 8)):
            # 2回めの読み取りのあと、地域のあり方の出来事は、theme の続き（page=2）に入る（2026-11-28）
            t = "\n".join(self.data["bun"][i] for k, i in sorted(self.data["outou"]["theme"].items())
                          if k.startswith(f"theme={th}&page="))
            part = self.setsu(t, "## " + D.kotoba("資料と出来事の名前の表 shu が「出来事」"))
            gyo = [x for x in part.split("\n") if x.startswith("- ")]
            self.assertEqual(len(gyo), n)
            self.assertTrue(all(f"（event：{th}-" in x for x in gyo))
        self.assertIn("- 行政懇談会（event：chiiki-gyosei-kondankai）　" + D.bun("mcp-dekigoto-kazu", n=11),
                      self.bun("theme", "theme=chiiki&page=2"))
        # 介護の出来事（2026-11-28）。同じ名前の出来事（パブリックコメント）も、テーマごとに ID が違い、数はそのテーマの質問だけ
        t = "\n".join(self.data["bun"][i] for k, i in sorted(self.data["outou"]["theme"].items())
                      if k.startswith("theme=kaigo&page="))
        part = self.setsu(t, "## " + D.kotoba("資料と出来事の名前の表 shu が「出来事」"))
        self.assertEqual([x for x in part.split("\n") if x.startswith("- ")],
                         ["- 第10期の計画の策定（event：kaigo-dai10ki-sakutei）　" + D.bun("mcp-dekigoto-kazu", n=4),
                          "- 第8期の計画の策定（event：kaigo-dai8ki-sakutei）　" + D.bun("mcp-dekigoto-kazu", n=1),
                          "- 介護保険運営協議会（event：kaigo-unei-kyogikai）　" + D.bun("mcp-dekigoto-kazu", n=2),
                          "- 住民説明会（event：kaigo-setsumeikai）　" + D.bun("mcp-dekigoto-kazu", n=2),
                          "- パブリックコメント（event：kaigo-pabukome）　" + D.bun("mcp-dekigoto-kazu", n=1),
                          "- チョイソコのワーキンググループ（event：kaigo-choisoko-wg）　" + D.bun("mcp-dekigoto-kazu", n=1)])
        # 第10期の計画の策定は、入力の確定済みの記録（3件。人が内容を確認した質問）と、読み取り（1件）
        e = self.bun("event", "event=kaigo-dai10ki-sakutei")
        self.assertIn("\n## " + D.bun("mcp-midashi-event-konkyo", n=4) + "\n", e)
        self.assertEqual(e.count("\n  - " + D.bun("shitsumon-kakutei") + "\n"), 3)
        self.assertEqual(e.count("\n  - " + D.kotoba("質問と事項の対応の表 question") + "\n"), 1)
        e = self.bun("event", "event=konwakai")
        self.assertIn("\n## " + D.bun("mcp-midashi-event-konkyo", n=18) + "\n", e)
        self.assertIn(D.bun("mcp-issue-gikai-setsumei", short="この出来事"), e)
        self.assertNotIn("event=keikaku-an", self.data["outou"]["event"])
        # 計画（案）と、名前の表に無い名前（子ども・子育て会議など）の行は、どの応答にも出さない
        self.assertNotIn("子ども・子育て会議（event", "\n".join(self.data["bun"]))

    def test_issue_chu_gaibu(self):
        # 外部の公的な資料を、もとの資料にした注は、確認した日を出す
        t = "\n".join(self.issue_pages("hiyo"))
        self.assertIn(D.bun("mcp-issue-kakunin-bi", hi="2026年11月18日"), t)
        self.assertIn("総務省自治財政局財務調査課「", t)

    def test_field(self):
        """一般質問の題と、総合計画の分野（SCHEMA.md 7.11。2026-11-28）。"""
        o = self.data["outou"]["field"]
        # 引数なし、分野34、分野に無い話題17
        self.assertEqual(len([k for k in o if "page" not in k]), 1 + 34 + 17)
        t = self.bun("field", "")
        self.assertIn("## 柱1 未来を担うひとづくり\n- ①子ども・子育て（field：①）　" + D.bun("bunya-kazu", n=103), t)
        self.assertIn("## " + D.kotoba("質問の題と分野の対応の表 wadai") + "\n", t)
        self.assertIn("- 国民健康保険と医療保険制度（field：wadai-kokuho）　" + D.bun("bunya-kazu", n=20), t)
        # 分野：基本施策は入力の字のまま。題ごとに、読みの言葉、会議録の URL。発言者の名前は出さない
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o.items()) if k.startswith("field=①&page="))
        self.assertIn("## 基本施策\n- (1)出産前から育児への切れ目のない支援の推進\n", t)
        self.assertIn("\n## " + D.bun("bunya-midashi-dai", n=103) + "\n", t)
        self.assertEqual(t.count("\n  - " + D.bun("bunya-link") + "："), 103)
        self.assertIn("（issue：", t)
        self.assertNotIn("議員", t)
        # 中心の分野の言葉は、分野の題にだけ付ける。話題の題には付けない
        self.assertIn(D.kotoba("質問の題と分野の対応の表 chushin が「一致」"), t)
        w = self.bun("field", "field=wadai-kokuho")
        self.assertNotIn(D.kotoba("質問の題と分野の対応の表 chushin が空"), w)
        # theme（引数なし）に、分野ごとの一覧があることの文
        self.assertIn(D.bun("mcp-hani-bunya", keikaku="第6次日野町総合計画"), self.bun("theme", ""))

    def test_field_ronten(self):
        """総合計画の分野の論点（SCHEMA.md 7.9・7.10。2026-11-28）。field に分野の番号を付けた応答の論点の一覧と、issue。"""
        o = self.data["outou"]
        kei = "第6次日野町総合計画"
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["field"].items()) if k.startswith("field=㉕&page="))
        a, b, c = t.index("## 基本施策"), t.index("## " + D.bun("mcp-midashi-ronten")), t.index("## " + D.bun("kensho-midashi"))
        self.assertTrue(a < b < c < t.index("## 一般質問の題"))
        self.assertIn(D.bun("mcp-ronten-setsumei-bunya", keikaku=kei) + "\n" + D.bun("ronten-kazu-setsumei")
                      + "\n### (1)利用しやすい公共交通の充実\n"
                      "- 利用しやすい公共交通の充実（issue：b25-k1）　" + D.bun("ronten-kihon-jishin") + "　質問 ", t)
        # まとまりの名前が計画の見出しの字のものは、その資料とページを示す（2026-11-28）
        self.assertIn("#### 運賃体系の再編（issue：b25-k1:運賃体系の再編）\n"
                      + D.bun("ronten-matome-setsumei-moto", moto="日野町地域公共交通計画 38ページ") + "\n", t)
        self.assertIn("#### チョイソコひのの運行（issue：b25-k1:チョイソコひのの運行）\n" + D.bun("ronten-matome-setsumei-an") + "\n", t)
        self.assertIn("- チョイソコひのの導入（issue：b25-23）　種類：取り組み　質問 ", t)
        self.assertIn("## " + D.kotoba("資料と出来事の名前の表 shu が「出来事」"), t)
        self.assertIn("（event：b25-e", t)
        # 読んでいない分野（①）は、題の一覧の題に付いたテーマの論点を、テーマごとに並べる
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["field"].items()) if k.startswith("field=①&page="))
        self.assertIn("## " + D.bun("mcp-midashi-ronten") + "\n" + D.bun("mcp-ronten-bunya-yomanai") + "\n### ", t)
        self.assertIn("\n### 幼児教育・保育施設の再編\n- ", t)
        # 基本施策の論点：ほかの論点に入らない部分だけを出すことの文。範囲の文は、読んだ題の数
        k1 = self.bun("issue", "issue=b25-k1")
        self.assertIn(D.bun("mcp-issue-kihon", keikaku=kei), k1)
        self.assertIn("「㉕公共交通」のうち、利用しやすい公共交通の充実について", k1)
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["issue"].items()) if k.startswith("issue=b25-23&page="))
        self.assertNotIn(D.bun("mcp-issue-kihon", keikaku=kei), t)
        self.assertIn("「㉕公共交通」を中心の分野とした題46（2017年3月〜2026年3月）", t)
        self.assertIn(D.kotoba("質問と事項の対応の表 question"), t)
        # テーマの論点に、分野の読み取りの質問が入ったときの文
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["issue"].items()) if k.startswith("issue=kokyo32&page="))
        self.assertIn(D.bun("mcp-issue-hani-bunya-hoka", keikaku=kei), t)
        # theme の応答には、分野のテーマを並べない
        self.assertNotIn("（theme：b", self.bun("theme", ""))

    def test_kensho(self):
        """総合戦略の施策検証結果報告書の記述（SCHEMA.md 7.12。2026-11-28）。field の町の検証と、review。"""
        o = self.data["outou"]
        self.assertEqual(len([k for k in o["review"] if "page" not in k]), 40)
        e008 = "取り組み8 子どもの読書活動と学習活動の支援（review：node:senryaku2/e008）"
        # 分野⑤：基本施策のあと、題の一覧の前に、町の検証。2人が最初に書いた分野には中身を出す
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["field"].items()) if k.startswith("field=⑤&page="))
        a, b, c = t.index("## 基本施策"), t.index("## " + D.bun("kensho-midashi")), t.index("## 一般質問の題")
        self.assertTrue(a < b < c)
        self.assertIn("### " + e008 + "\n- " + D.bun("kensho-tantou", tantou="図書館"), t)
        self.assertIn("- 検証結果：B（46〜47ページ）", t)
        self.assertIn("- KPIの達成度【KPIが複数の場合は、平均点】：41.3%（46〜47ページ）", t)
        self.assertIn("(2)子どもの読書活動の推進（" + D.kotoba("施策検証の取り組みと分野の対応の表 yomi が「一致」") + "）", t)
        self.assertIn("https://www.town.shiga-hino.lg.jp/cmsfiles/contents/0000004/4666/70.pdf#page=46", t)
        self.assertNotIn(D.bun("kensho-hoka"), t)
        # 分野②：2つめの組として結び付いた取り組みは、名前と ID と読みの言葉だけ
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["field"].items()) if k.startswith("field=②&page="))
        hoka = t[t.index("### " + D.bun("kensho-hoka")):t.index("## 一般質問の題")]
        self.assertIn("- " + e008 + "　かかわる基本施策：(3)豊かな心の育成（", hoka)
        self.assertNotIn("### " + e008, t)
        # 取り組みが結び付いていない基本施策の文
        t = "\n".join(self.data["bun"][i] for k, i in sorted(o["field"].items()) if k.startswith("field=①&page="))
        self.assertIn("- " + D.bun("kensho-nai", shisaku="(2)子どもが安心して生活できる仕組みづくり"), t)
        # 話題の応答には出さない
        self.assertNotIn(D.bun("kensho-midashi"), self.bun("field", "field=wadai-kokuho"))
        # review：KPI は報告書の表のまま、文の欄は全部、検証結果の意味は報告書の字
        r = "\n".join(self.data["bun"][i] for k, i in sorted(o["review"].items())
                      if k.startswith("review=node:senryaku2/e008&page="))
        self.assertTrue(r.split("\n")[1] == "# " + e008)
        self.assertIn("- 令和7年度　目標 52回　実績 30回　達成率 57.7%", r)          # 入力の tani を付ける
        self.assertIn("- 基準値【R2】：3.7 回", r)
        self.assertIn("## 内部検証（町が書いたもの）\n### 取り組み状況（46〜47ページ）\n", r)
        self.assertIn(D.bun("kensho-hito"), r)          # 入力の検収の台帳に人の印が無い
        self.assertIn("### 実施が困難なこと（46〜47ページ）\n- 「特にありません。」", r)
        self.assertIn("    - 「Ｂ 実施できている １８点 ～ １３点」（8ページ）", r)
        self.assertEqual(r.count("\n### コメント（46〜47ページ）\n"), 1)
        self.assertEqual(sum(1 for x in r.split("\n") if x.startswith("- 「")), 10 + 6 + 12 + 1 + 1 + 5 + 3 + 7)
        # 目標2・実績1で達成率100.0% の行も、字のまま（2026-11-28 の依頼者の決定）
        r = self.bun("review", "review=node:senryaku2/e017")
        self.assertIn("目標 2　実績 1　達成率 100.0%", r)
        # 欄の見出しがシートによって違う欄は、そのシートの字
        r = "\n".join(self.data["bun"][i] for k, i in sorted(o["review"].items())
                      if k.startswith("review=node:senryaku2/e010&page="))
        self.assertIn("### 実施できていないこと・困難なこと（50〜51ページ）\n", r)
        self.assertNotIn("### 実施が困難なこと", r)
        # 担当部署と取り組みの方向は、シートの字。本編と違うときは、本編の字も添える
        r = self.bun("review", "review=node:senryaku2/e038")
        self.assertIn("- " + D.bun("kensho-tantou", tantou="R3：住民課、R4：交通環境政策課・建設計画課") + "\n  - "
                      + D.bun("kensho-tantou-honpen", tantou="交通環境政策課・建設計画課"), r)
        r = self.bun("review", "review=node:senryaku2/e009")
        self.assertIn("取り組みの方向（施策検証シート）「子育てにやさしい風土づくり」\n  - "
                      + D.bun("kensho-houkou-honpen", houkou="生涯にわたる学びと活躍の推進"), r)
        r = self.bun("review", "review=node:senryaku2/e008")
        self.assertNotIn(D.bun("kensho-tantou-honpen", tantou="図書館"), r)

    def test_repo_json(self):
        # リポジトリの JSON は、いまの表から作ったものと同じ（違えば、作り直していない）
        path = bm.OUT_PATH
        if not os.path.exists(path):
            self.skipTest("mcp/data/outou.json がまだ無い")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), bm.dumps(self.data))


if __name__ == "__main__":
    unittest.main()
