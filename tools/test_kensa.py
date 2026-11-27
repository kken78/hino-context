"""まとめて行う検査（tools/kensa.py）が、失敗した所で止まって終了コード 1 を返すこと。"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kensa  # noqa: E402

OK = [sys.executable, "-c", "print('ok')"]
NG = [sys.executable, "-c", "import sys; print('ng'); sys.exit(3)"]


class TestKensa(unittest.TestCase):
    def test_all_ok(self):
        out = io.StringIO()
        self.assertEqual(kensa.run([("a", OK), ("b", OK)], out=out), 0)
        self.assertIn("検査は全部通った", out.getvalue())

    def test_stops_at_failure(self):
        out = io.StringIO()
        self.assertEqual(kensa.run([("a", OK), ("b", NG), ("c", OK)], out=out), 1)
        text = out.getvalue()
        self.assertIn("止めた：b が失敗した（終了コード 3）", text)
        self.assertNotIn("通った：c", text)
        self.assertNotIn("検査は全部通った", text)

    def test_steps(self):
        # 19の検査が、決まった順に入っている。テストの中からは、全部の検査を動かさない（テストが自分を呼ぶため）
        self.assertEqual([n for n, _ in kensa.STEPS],
                         ["書き方の検査", "全部のテスト", "表の検査", "事項の表の検査",
                          "質問が取り上げた資料と出来事の表の検査", "設計の物と関係に当たる表の検査", "試作のページの作成（幼保）",
                          "試作のページの作成（高齢者福祉・介護）", "試作のページの作成（公共施設の再編）",
                          "試作のページの作成（地域のあり方・自治会活動）", "数値のページの作成",
                          "資料の表のページの作成（再編整備計画の表4）",
                          "資料の表のページの作成（子ども・子育て支援事業計画の表4）",
                          "資料の表のページの作成（再編整備計画 令和7年3月の版の表6）",
                          "資料の表のページの作成（懇話会の提言の表4）",
                          "資料の表のページの作成（基本構想の表4）",
                          "資料の表のページの作成（子ども・子育て支援事業計画の表37）",
                          "テーマのページの作成（幼保）", "MCP の応答の作成と比較"])


if __name__ == "__main__":
    unittest.main()
