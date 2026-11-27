"""tools/sekkei.py と、tools/bunsho.py の節の検査のテスト。"""
import unittest

import bunsho
import sekkei

HOSHIN = """### 4.2 オントロジー

**物の種類**

| 種類 | 何か |
| --- | --- |
| 課題 | 問題 |
| 取り組み | 施策 |

**物どうしの関係**

| 関係 | 例 |
| --- | --- |
| 取り組みが、課題に対処する | a |

### 4.3 持ち方
| x | y |
"""


class SekkeiTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(sekkei.hoshin_names(HOSHIN), ["課題", "取り組み", "取り組みが、課題に対処する"])

    def rows(self, *r):
        return [dict(zip(("shu", "name", "hyo", "chu"), x)) for x in r]

    def test_ok_and_nai(self):
        rows = self.rows(("mono", "課題", "無い", ""), ("mono", "取り組み", "teigi/a.tsv", ""),
                         ("kankei", "取り組みが、課題に対処する", "入力:x/y.tsv", ""))
        bad, nai, _ = sekkei.check(rows, sekkei.hoshin_names(HOSHIN), lambda p: p == "teigi/a.tsv")
        self.assertEqual((bad, nai), ([], ["課題"]))

    def test_missing_row_and_file(self):
        rows = self.rows(("mono", "課題", "teigi/b.tsv", ""), ("mono", "別の物", "無い", ""))
        bad, _, _ = sekkei.check(rows, sekkei.hoshin_names(HOSHIN), lambda p: False)
        self.assertEqual(len(bad), 4)

    def test_repo(self):
        self.assertEqual(sekkei.main(), 0)


class SetsuTest(unittest.TestCase):
    M = ["設計での位置", "決定との照合", "入力にすでにあるもの"]
    K = ["文案", "伺いたいこと"]

    def test_not_target(self):
        self.assertEqual(bunsho.check_setsu("結果を報告します。", self.M, self.K), [])

    def test_missing(self):
        t = "## 伺いたいこと\nこれでよいか。\n## 設計での位置\n事項の話。"
        self.assertEqual(bunsho.check_setsu(t, self.M, self.K), ["決定との照合", "入力にすでにあるもの"])

    def test_all(self):
        t = "文案です。\n## 設計での位置\n## 決定との照合\n### 入力にすでにあるもの\n"
        self.assertEqual(bunsho.check_setsu(t, self.M, self.K), [])

    def test_skill(self):
        m, k = bunsho.setsu_kimari()
        self.assertEqual(m, self.M)
        self.assertIn("よいでしょうか", k)


if __name__ == "__main__":
    unittest.main()
