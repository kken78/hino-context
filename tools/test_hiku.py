"""tools/hiku.py のテスト。"""
import contextlib
import gzip
import io
import json
import os
import tempfile
import unittest

import hiku

DATA = dict(tools=[dict(name="issue", args=[dict(name="issue"), dict(name="page")]), dict(name="field", args=[dict(name="field"), dict(name="page")])],
            nai={"issue": "無い（issue）", "field": "無い（field）"},
            outou={"issue": {"issue=a": 0, "issue=a&page=1": 0, "issue=a&page=2": 1}, "field": {"": 2}}, bun=["A1", "A2", "F"])


class HikuTest(unittest.TestCase):
    def test_hiku(self):
        # MCP サーバーと同じ引き方（ツールの引数の順に「名前=値」を「&」でつなぐ）
        self.assertEqual(hiku.hiku(DATA, "issue", {"issue": "a"}), "A1")
        self.assertEqual(hiku.hiku(DATA, "issue", {"page": "2", "issue": " a "}), "A2")
        self.assertEqual(hiku.hiku(DATA, "issue", {"issue": "b"}), "無い（issue）")
        self.assertEqual(hiku.hiku(DATA, "field", {}), "F")

    def test_hikisu(self):
        t = DATA["tools"][0]
        self.assertEqual(hiku.hikisu(t, ["a", "2"]), {"issue": "a", "page": "2"})
        self.assertEqual(hiku.hikisu(t, ["page=2", "a"]), {"issue": "a", "page": "2"})
        self.assertEqual(hiku.hikisu(t, ["b33-k1:職員の育成と人事評価"]), {"issue": "b33-k1:職員の育成と人事評価"})
        with self.assertRaises(ValueError):
            hiku.hikisu(t, ["a", "2", "3"])

    def test_main(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(DATA, f, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(hiku.main(["--json", p, "issue", "a", "page=2"]), 0)
            self.assertEqual(out.getvalue(), "A2\n")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(hiku.main(["--json", p, "x"]), 2)
            # .gz で終わるファイルは展開して読む
            g = os.path.join(d, "o.json.gz")
            with gzip.open(g, "wt", encoding="utf-8") as f:
                json.dump(DATA, f, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(hiku.main(["--json", g, "issue", "a", "page=2"]), 0)
            self.assertEqual(out.getvalue(), "A2\n")


if __name__ == "__main__":
    unittest.main()
