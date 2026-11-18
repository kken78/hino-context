"""正規化・段落の数え方・引用の照合（SCHEMA.md §2・§3）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inputs  # noqa: E402
import shogo  # noqa: E402

SID = "0000008211_20241213_0156"


class FakeInputs:
    """テスト用の入力。Inputs と同じ名前の読み口だけを持つ。"""

    def __init__(self, statements=None, docs=None, doc_texts=None, plans=None, sources_index=None, pt_texts=None,
                 ronten=None):
        self._st = statements or {}          # sid → (name, text)
        self._docs = docs or {}              # id → sources.tsv の行
        self._doc_texts = doc_texts or {}    # (id, layer) → 本文
        self._plans = plans or {}            # id → 計画の json
        self._si = sources_index or []
        self._pt = pt_texts or {}            # (id, name, layer) → 本文
        self._ronten = ronten or {}          # path → 行の並び
        self._cache = {}

    def statement_text(self, sid):
        return self._st[sid][1] if sid in self._st else None

    def speaker(self, sid):
        return self._st.get(sid, ("", ""))[0]

    def docs(self):
        return self._docs

    def doc_text(self, did, layer):
        return self._doc_texts.get((did, layer))

    def plan(self, pid):
        return self._plans.get(pid)

    def sources_index(self):
        return self._si

    def pt_text(self, pid, name, layer):
        return self._pt.get((pid, name, layer))

    def ronten_tsv(self, path):
        return [dict(r) for r in self._ronten.get(path, [])]


def sample():
    return FakeInputs(
        statements={SID: ("森弘一郎", "　答弁の始め。\n\n2,800平方メートルを想定しております。\n　 \n終わり。")},
        docs={"koho-1": {"id": "koho-1", "title": "広報", "url": "https://example.jp/k.pdf", "archive_url": ""}},
        doc_texts={("koho-1", "text"): "1ページ目\f用地は 図書館の\n東側", ("koho-1", "text_raw"): "x\fy"},
        plans={"youho": {"meta": {"name": "再編整備計画"}}},
        sources_index=[{"id": "youho", "file": "honpen.pdf", "url": "https://example.jp/p.pdf"}],
        pt_texts={("youho", "honpen", "text_raw"): "a\f本計画の計画期間は、令和6年から"})


class TestNorm(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(shogo.norm("ＡＢＣ　１２３"), "ABC123")          # NFKC と全角の空白
        self.assertEqual(shogo.norm("前\n12-3後"), "前後")                  # 改行に続くページ番号
        self.assertEqual(shogo.norm("前-12-後"), "前後")                    # 「-数字-」
        self.assertEqual(shogo.norm(" a\tb\nc　d﻿"), "abcd")


class TestParagraphs(unittest.TestCase):
    def test_count(self):
        self.assertEqual(inputs.paragraphs("一\n\n二\n　 \n三"), ["一", "二", "三"])
        self.assertEqual(inputs.paragraphs("改行の無い本文"), ["改行の無い本文"])
        self.assertEqual(inputs.paragraphs(""), [])
        self.assertEqual(inputs.paragraphs("\n一\n"), ["一"])


class TestQuotes(unittest.TestCase):
    def test_match_and_mismatch(self):
        inp = sample()
        rows = [dict(where="1", source=f"sp:{SID}", quote="2,800平方メートル"),
                dict(where="2", source=f"sp:{SID}", quote="2,900平方メートル"),       # 1字違い
                dict(where="3", source="doc:koho-1/2", quote="用地は図書館の東側"),   # 空白・改行をまたぐ
                dict(where="4", source="doc:koho-1/3", quote="用地"),                # ページが無い
                dict(where="5", source="pt:youho/honpen/2", quote="計画期間は、令和6年"),  # text_raw だけにある
                dict(where="6", source="", quote="何か"),                            # 資料が無い
                dict(where="7", source=f"sp:{SID}", quote="")]
        res = shogo.check_quotes(inp, rows)
        self.assertEqual((res.total, res.matched), (7, 3))
        self.assertEqual([m["where"] for m in res.mismatched], ["2", "4", "6", "7"])
        self.assertEqual(res.mismatched[0]["reason"], "引用が資料の本文に無い")

    def test_paras(self):
        inp = sample()
        res = shogo.check_paras(inp, [dict(where="a", hani=f"sp:{SID}/1-3"), dict(where="b", hani=f"sp:{SID}/4"),
                                      dict(where="c", hani="sp:0000000000_20240101_0001/1"),
                                      dict(where="d", hani=f"sp:{SID}")])
        self.assertEqual((res.total, res.matched), (6, 3))
        self.assertEqual([m["where"] for m in res.mismatched], ["b", "c", "d"])

    def test_para_of_quote(self):
        t = sample().statement_text(SID)
        self.assertEqual(shogo.para_of_quote(t, "2,800平方メートル"), 2)
        self.assertIsNone(shogo.para_of_quote(t, "答弁の始め。2,800"))   # 段落をまたぐ
        self.assertIsNone(shogo.para_of_quote(t, "無い字"))
        self.assertIsNone(shogo.para_of_quote("あい\nあい", "あい"))       # 2か所


if __name__ == "__main__":
    unittest.main()
