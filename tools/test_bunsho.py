"""文書と報告の書き方の検査（SKILL.md §3）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bunsho  # noqa: E402


class TestTable(unittest.TestCase):
    def test_read(self):
        table = bunsho.read_table()
        self.assertGreaterEqual(len(table), 20)
        for rx, src, use in table:
            self.assertTrue(src and use)


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.table = bunsho.read_table()

    def found(self, text):
        return [f for _, f, _, _ in bunsho.check_text(text, self.table)]

    def test_hit(self):
        for text in ("比べの結果を示す", "比べについて", "同じ問いで比べ、差を示す", "足す形と比べる", "確かめの記録", "原文で確かめる", "11月15日の調べでは",
                     "引用を原文と照らす", "照らし合わせの結果", "表の升に書く", "答える役が探した", "鍵になる材料が入った",
                     "置き場を決める", "道具が止まる", "2人読みの結果", "どう動いてきたか", "数の動き", "ここに入る話",
                     "落ちの探しを行う", "決まりの穴を出す", "文字の取り出しが乱れている", "見立ては外れる",
                     "いまの形と直した形", "これは依頼者の番。", "事項に当てるとき", "段の終わりに伝える", "議会だよりとの見比べ"):
            self.assertTrue(self.found(text), text)

    def test_no_hit(self):
        for text in ("同じ問いで比較し、差を数で示す", "原文で確認する",
                     "入力を調べる", "調べた範囲に見つからない", "段落の番号", "段階ごとに行う", "手段のひとつ", "条件に当てはまる",
                     "数値の推移", "比較の結果", "照合の結果", "順番に行う"):
            self.assertEqual(self.found(text), [], text)

    def test_mask(self):
        # 「」の中と `…` の中は調べない
        self.assertEqual(self.found("「比べ」と書かず、「比較」と書く"), [])
        self.assertEqual(self.found("`置き場` という列"), [])

    def test_table_rows_skipped(self):
        text = bunsho.HEAD + "\n| --- | --- |\n| `道具` | ツール |\n\n道具を作る"
        self.assertEqual(self.found(text), ["道具"])
        # docs/design.md 2節の言葉の表（画面と応答で使わない言葉の表）の行も調べない
        text = "| 使わない | 使う | 確認する所 |\n| --- | --- | --- |\n| 道具 | ツール | 文 |\n\n道具を作る"
        self.assertEqual(self.found(text), ["道具"])


class TestRepo(unittest.TestCase):
    def test_repo_clean(self):
        hits = bunsho.check_repo(bunsho.read_table())
        self.assertEqual(hits, [], "\n".join(f"{w}：「{f}」→ {u}" for w, f, u, _ in hits))


if __name__ == "__main__":
    unittest.main()
