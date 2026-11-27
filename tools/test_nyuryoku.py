"""入力の全部を検索するツール（tools/nyuryoku.py）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nyuryoku  # noqa: E402


class TestNyuryoku(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for rel, body in (("data/plans/p.json", '{"pdf_page_offset": 2, "x": [{"source": "honpen p.32"}]}\n'),
                          ("data/plans/q.json", '{"x": [{"source": "honpen p.32"}]}\n'),
                          ("records/a.tsv", "fa:a\tpt:p/honpen/34\n別の行\n"),
                          ("data/text/p/honpen.txt", "pt:p/honpen/34 と同じ字\n"),
                          (".git/x.tsv", "pt:p/honpen/34\n")):
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sagasu_ji(self):
        plans = os.path.join(self.root, "data", "plans")
        self.assertEqual(nyuryoku.sagasu_ji("言葉"), [("言葉", None)])
        self.assertEqual(nyuryoku.sagasu_ji("doc:d/3"), [("doc:d/3", None), ("d/3", None)])
        # 計画の ID は、印刷のページ番号の形でも探す（その計画のファイルの中だけ）
        self.assertEqual(nyuryoku.sagasu_ji("pt:p/honpen/34", plans),
                         [("pt:p/honpen/34", None), ("p/honpen/34", None), ("honpen p.32", "/p.")])
        # pdf_page_offset が無い計画と、改正前のファイルは、印刷のページ番号の形を作らない
        self.assertEqual(len(nyuryoku.sagasu_ji("pt:q/honpen/34", plans)), 2)
        self.assertEqual(len(nyuryoku.sagasu_ji("pt:p/honpen-202503/34", plans)), 2)

    def test_sagasu(self):
        terms = nyuryoku.sagasu_ji("pt:p/honpen/34", os.path.join(self.root, "data", "plans"))
        hits = nyuryoku.sagasu(self.root, terms)
        # .git と、もとの資料から取り出した文字は調べない。印刷のページ番号の形は、その計画のファイルだけ
        self.assertEqual([(rel, n) for rel, n, _ in hits], [("data/plans/p.json", 1), ("records/a.tsv", 1)])
        hits = nyuryoku.sagasu(self.root, terms, honbun=True)
        self.assertIn("data/text/p/honpen.txt", [rel for rel, _, _ in hits])


if __name__ == "__main__":
    unittest.main()
