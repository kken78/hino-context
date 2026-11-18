"""鍵の読み書き（SCHEMA.md §2・§4）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keys  # noqa: E402

SID = "0000008116_20240917_0015"


class TestParse(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(keys.parse(f"sp:{SID}"), ("sp", (SID,)))
        self.assertEqual(keys.parse(f"sp:{SID}/5"), ("para", (SID, "5", None)))
        self.assertEqual(keys.parse(f"sp:{SID}/5-7"), ("para", (SID, "5", "7")))
        self.assertEqual(keys.parse(f"iq:{SID}")[0], "iq")
        self.assertEqual(keys.parse(f"sq:{SID}")[0], "sq")
        self.assertEqual(keys.parse("doc:koho-no792-04/1"), ("doc", ("koho-no792-04", "1")))
        self.assertEqual(keys.parse("pt:youho/honpen-202503/4"), ("pt", ("youho", "honpen-202503", "4")))
        self.assertEqual(keys.parse("plan:youho")[0], "plan")
        self.assertEqual(keys.parse("gi:0000008942/議第115号"), ("gi", ("0000008942", "議第115号")))
        self.assertEqual(keys.parse("node:jisshi/e008"), ("node", ("jisshi", "e008")))

    def test_sid_with_hyphen_and_mokuji(self):
        self.assertEqual(keys.parse("sp:0000008211_6.12mokuji_0000/2")[0], "para")

    def test_bad(self):
        for k in ("", "sp:123", f"sp:{SID}/0", f"sp:{SID}/7-5", f"sp:{SID}/5-5", "doc:koho/0", "doc:Koho/1",
                  "pt:youho/honpen", f"xx:{SID}", f"sp:{SID} "):
            with self.assertRaises(keys.KeyFormError, msg=k):
                keys.parse(k)


class TestWrite(unittest.TestCase):
    def test_para_roundtrip(self):
        self.assertEqual(keys.para(SID, 5), f"sp:{SID}/5")
        self.assertEqual(keys.para(SID, 5, 5), f"sp:{SID}/5")
        self.assertEqual(keys.para(SID, 5, 7), f"sp:{SID}/5-7")
        with self.assertRaises(keys.KeyFormError):
            keys.para(SID, 7, 5)
        for k in (keys.para(SID, 3), keys.para(SID, 3, 9)):
            self.assertEqual(keys.parse(k)[0], "para")

    def test_paras_of(self):
        other = "0000008116_20240917_0016"
        self.assertEqual(keys.paras_of(f"sp:{SID}/5-7,sp:{other}/2"),
                         [(SID, 5), (SID, 6), (SID, 7), (other, 2)])
        with self.assertRaises(keys.KeyFormError):
            keys.paras_of(f"sp:{SID}")       # 段落の無い発言の鍵
        with self.assertRaises(keys.KeyFormError):
            keys.paras_of("")

    def test_sid_and_dates(self):
        self.assertEqual(keys.sid_of(f"iq:{SID}"), SID)
        self.assertEqual(keys.sid_of(f"sp:{SID}/3"), SID)
        self.assertEqual(keys.sid_date(SID), "2024-09-17")
        self.assertEqual(keys.sid_date("0000008211_6.12mokuji_0000"), "")
        self.assertEqual(keys.ymd("2024-09-07"), "2024年9月7日")
        self.assertEqual(keys.ymd("2024-09"), "2024年9月")

    def test_search_url(self):
        self.assertEqual(keys.search_url(SID), f"https://kken78.github.io/hino-council-search/#sid={SID}")
        self.assertEqual(keys.search_url(SID, 5), f"https://kken78.github.io/hino-council-search/#sid={SID}&p=5")



class TestExt(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(keys.parse("ext:soumu-tekiseikanri-20251118/2"), ("ext", ("soumu-tekiseikanri-20251118", "2")))
        for bad in ("ext:/2", "ext:Soumu/2", "ext:soumu", "ext:soumu/a"):
            with self.assertRaises(keys.KeyFormError):
                keys.parse(bad)

    def test_name_url_and_text(self):
        import shogo

        class Fake:
            def gaibu(self):
                return [dict(id="a-1", name="題", hakkou="総務省", hiduke="令和7年1月1日", url="https://example.jp/a.pdf",
                             kakunin="2026-11-18", page="2", ji="充当率９０％")]
        inp = Fake()
        self.assertEqual(keys.source_name(inp, "ext:a-1/2"), "総務省「題」（令和7年1月1日） 2ページ")
        self.assertEqual(keys.source_url(inp, "ext:a-1/2"), "https://example.jp/a.pdf")
        self.assertEqual(keys.source_name(inp, "ext:a-1/3"), "")
        res = shogo.check_quotes(inp, [dict(where="w", source="ext:a-1/2", quote="90%"),
                                       dict(where="w", source="ext:a-1/2", quote="50%"),
                                       dict(where="w", source="ext:b/1", quote="90%")])
        self.assertEqual((res.total, res.matched), (3, 1))


if __name__ == "__main__":
    unittest.main()
