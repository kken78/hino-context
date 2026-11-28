"""tools/jiko.py のテスト。"""
import unittest

import jiko


def row(**kw):
    r = dict(id="a", theme="hoiku", name="A", shurui="kadai", taikei="nashi", matome="", betsumei="", jotai="案", chu="")
    r.update(kw)
    return r


class JikoTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(jiko.check([row(), row(id="b", name="B", shurui="atai", taikei="tk:x/1")], {"tk:x/1"}), [])

    def test_bad(self):
        rows = [row(), row(name="B", shurui="shiryo", taikei="tk:x/9", jotai="確定")]
        self.assertEqual(len(jiko.check(rows, {"tk:x/1"})), 4)
        # matome は、taikei が nashi の行にだけ書ける（2026-11-28）
        self.assertEqual(jiko.check([row(matome="M")], set()), [])
        self.assertEqual(len(jiko.check([row(taikei="tk:x/1", matome="M")], {"tk:x/1"})), 1)

    def test_theme(self):
        # theme の列には、テーマを「,」でつないで2つまで書ける（2026-11-28）
        rows = [row(id="a", theme="k"), row(id="b", name="B", theme="k,c"), row(id="c", name="C", theme="c")]
        self.assertEqual(jiko.check(rows, set()), [])
        self.assertEqual([r["id"] for r in jiko.of_theme(rows, "c")], ["b", "c"])
        self.assertEqual(jiko.theme_jun(rows), ["k", "c"])
        self.assertEqual(jiko.themes_of(rows[1]), ["k", "c"])
        for th in ("", "k,", "k,k", "k,c,h"):
            self.assertEqual(len(jiko.check([row(theme=th)], set())), 1, th)

    def test_matome_jun(self):
        rows = [row(id="a", matome="M2"), row(id="b"), row(id="c", matome="M1"), row(id="d", matome="M2")]
        self.assertEqual({k: [r["id"] for r in v] for k, v in jiko.matome_jun(rows).items()},
                         {"M2": ["a", "d"], "M1": ["c"]})
        self.assertEqual(list(jiko.matome_jun(rows)), ["M2", "M1"])

    def test_repo(self):
        self.assertEqual(jiko.main(), 0)


if __name__ == "__main__":
    unittest.main()
