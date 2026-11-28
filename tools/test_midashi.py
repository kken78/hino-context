"""tools/midashi.py のテスト。"""
import unittest

import inputs
import jiko
import midashi


class MidashiTest(unittest.TestCase):
    def test_repo(self):
        # 2026-11-28 のまとまりの案を入れたあと、論点が12を超える見出しは無い（入れる前は37）
        zen, ooi = midashi.kazoeru(inputs.Inputs())
        self.assertEqual(jiko.MIDASHI_JOGEN, 12)
        self.assertEqual(ooi, [])
        self.assertEqual(zen, 376)


if __name__ == "__main__":
    unittest.main()
