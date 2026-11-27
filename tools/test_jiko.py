"""tools/jiko.py のテスト。"""
import unittest

import jiko


def row(**kw):
    r = dict(id="a", theme="hoiku", name="A", shurui="kadai", taikei="nashi", betsumei="", jotai="案", chu="")
    r.update(kw)
    return r


class JikoTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(jiko.check([row(), row(id="b", name="B", shurui="atai", taikei="tk:x/1")], {"tk:x/1"}), [])

    def test_bad(self):
        rows = [row(), row(name="B", shurui="shiryo", taikei="tk:x/9", jotai="確定")]
        self.assertEqual(len(jiko.check(rows, {"tk:x/1"})), 4)

    def test_repo(self):
        self.assertEqual(jiko.main(), 0)


if __name__ == "__main__":
    unittest.main()
