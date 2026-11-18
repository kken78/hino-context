"""論点ノートの試作のページを作る道具：作る前の検査と、止まる条件。"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_note as bn  # noqa: E402
import inputs  # noqa: E402
import ronten  # noqa: E402
from test_shogo import FakeInputs  # noqa: E402

TODAY = datetime.date(2026, 11, 18)
Q = "0000008211_20241213_0154"
A1 = "0000008211_20241213_0156"
P = "新こども園の面積"


def fake_ronten():
    return {
        ronten.THEMES: [
            dict(theme="hoiku", kind="事柄", value=P, source="", views="", reviewer="", date="", note=""),
            dict(theme="hoiku", kind="問い", value=f"iq:{Q}",
                 source="令和6年第7回（12月）定例会会議録 2024-12-13 5番 柚木記久雄 問1「認定こども園等」",
                 views="", reviewer="", date="", note="")],
        ronten.KOTOGARA: [
            dict(point=P, source=f"sp:{A1}", source_date="2024-12-13", quote="2,800平方メートル", value="",
                 kind="いまのこと", status="confirmed"),
            dict(point=P, source="doc:koho-1/2", source_date="2025-08", quote="約3,200㎡と同程度", value="3,200",
                 kind="済んだこと", status="confirmed"),
            dict(point=P, source="doc:koho-1/2", source_date="2025-08", quote="未確認の行", value="",
                 kind="予定", status="candidate")],
        ronten.KATEI: [dict(theme="hoiku", step="1", name="基本構想の策定", **{"from": "2025-08"}, to="2025-08",
                            sources="doc:koho-1/1", quote="令和7年8月", status="confirmed")],
        ronten.TAIO: [dict(question=f"iq:{Q}", point=P, hani=f"sp:{A1}/1-2", status="confirmed"),
                      dict(question=f"iq:{Q}", point=P, hani=f"sp:{A1}/9", status="candidate")],
    }


def fake_inputs(ron=None):
    return FakeInputs(
        statements={A1: ("森弘一郎", "面積については、\n2,800平方メートルを想定しております。"), Q: ("柚木記久雄", "問い")},
        docs={"koho-1": {"id": "koho-1", "title": "基本構想", "url": "https://example.jp/k.pdf",
                         "archive_url": "https://web.archive.org/web/1id_/https://example.jp/k.pdf"}},
        doc_texts={("koho-1", "text"): "令和7年8月\f園舎は約3,200㎡と同程度"},
        ronten=ron or fake_ronten())


def teigi(setsumei="新こども園の園舎や敷地の面積"):
    return dict(theme="幼児教育・保育施設の再編", setsumei="町立の園の再編",
                topics=[(P, "menseki", "面積", setsumei)], junbi=["待機児童数"], words=["今後"], units=[])


def kinds(stop):
    return {k for k, _ in stop.problems}


class TestFake(unittest.TestCase):
    def setUp(self):
        self.kotoba = bn.read_kotoba()

    def build(self, inp, t=None):
        return bn.build(inp, t or teigi(), "hoiku", self.kotoba, TODAY)

    def test_ok(self):
        page, info = self.build(fake_inputs())
        self.assertEqual(info["counts"], [(P, 2, 1)])           # candidate の行は使わない
        self.assertEqual(info["questions"], 1)
        self.assertEqual((info["quotes"].total, info["quotes"].matched), (3, 3))
        self.assertEqual((info["paras"].total, info["paras"].matched), (2, 2))
        self.assertNotIn(bn.A, page)
        self.assertNotIn(bn.B, page)
        self.assertIn("https://web.archive.org/web/1id_/https://example.jp/k.pdf#page=2", page)
        self.assertIn(f"#sid={A1}&amp;p=2", page)
        self.assertIn("数値：3,200（資料に単位の記述なし）", page)

    def test_stop_quote_changed(self):
        ron = fake_ronten()
        ron[ronten.KOTOGARA][0]["quote"] = "2,900平方メートル"     # 1字変える
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(ron))
        self.assertEqual(kinds(c.exception), {"(a) 引用が原典に無い"})
        self.assertEqual(len(c.exception.problems), 1)

    def test_stop_katei_quote_changed(self):
        ron = fake_ronten()
        ron[ronten.KATEI][0]["quote"] = "令和7年9月"
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(ron))
        self.assertEqual(kinds(c.exception), {"(a) 引用が原典に無い"})

    def test_stop_paragraph_missing(self):
        ron = fake_ronten()
        ron[ronten.TAIO][0]["hani"] = f"sp:{A1}/2-3"
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(ron))
        self.assertEqual(kinds(c.exception), {"(a) 引用が原典に無い"})

    def test_stop_source_removed(self):
        for led, col in ((ronten.KOTOGARA, "source"), (ronten.KATEI, "sources"), (ronten.TAIO, "hani")):
            ron = fake_ronten()
            ron[led][0][col] = ""
            with self.assertRaises(bn.Stop, msg=led) as c:
                self.build(fake_inputs(ron))
            self.assertIn("(b) 出典の無い記述", kinds(c.exception), led)

    def test_stop_source_unknown(self):
        ron = fake_ronten()
        ron[ronten.KOTOGARA][1]["source"] = "doc:nai/2"
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(ron))
        self.assertIn("(b) 出典の無い記述", kinds(c.exception))

    def test_stop_word(self):
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(), teigi("新こども園の面積の記載"))
        self.assertEqual(kinds(c.exception), {"(c) 使わない言葉"})

    def test_word_in_quote_is_allowed(self):
        ron = fake_ronten()
        inp = fake_inputs(ron)
        inp._st[A1] = ("森弘一郎", "面積については、\n2,800平方メートルという値を想定しております。")
        ron[ronten.KOTOGARA][0]["quote"] = "2,800平方メートルという値"
        page, _ = self.build(inp)
        self.assertIn("という値", page)

    def test_topic_not_defined(self):
        t = teigi()
        t["topics"] = [("無い論点", "nai", "無い", "無い論点の説明")]
        with self.assertRaises(bn.Stop) as c:
            self.build(fake_inputs(), t)
        self.assertEqual(kinds(c.exception), {"定義"})


class TestTeigi(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_read(self):
        head = "kind\tkey\tname\tshort\tsetsumei\n"
        t = bn.read_teigi(self.write(head + "テーマ\thoiku\t名前\t\t説明\n論点\ta\t論点A\tA\tAの説明\n準備中\t\t次\t\t\n"
                                     "単位\tdoc:yosan-\t千円\t\t\n"), "hoiku")
        self.assertEqual(t["topics"], [("論点A", "a", "A", "Aの説明")])
        self.assertEqual(t["units"], [("doc:yosan-", "千円")])
        for bad in (head + "論点\ta\t論点A\tA\tAの説明\n",                                  # テーマが無い
                    head + "テーマ\thoiku\t名前\t\t説明\n論点\ta\t論点A\t\tAの説明\n",        # short が空
                    head + "テーマ\thoiku\t名前\t\t説明\n論点\ta\t論点A\tA\tA\n種類\t\t\t\t\n",  # 知らない kind
                    "kind\tkey\tname\n"):                                                 # 列が違う
            with self.assertRaises(inputs.InputError):
                bn.read_teigi(self.write(bad), "hoiku")

    def test_real_table(self):
        t = bn.read_teigi(os.path.join(inputs.ROOT, "teigi", "note-hoiku.tsv"), "hoiku")
        self.assertEqual([x[1] for x in t["topics"]], ["hiyo", "menseki", "yochi", "teiin"])


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.jp", "-c", "commit.gpgsign=false",
                    *args], cwd=cwd, check=True, capture_output=True)


class TestLock(unittest.TestCase):
    """(d) lock と入力が合わない。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.shas = {}
        for repo in inputs.REPOS:
            d = os.path.join(root, "ronten" if repo == inputs.RT else os.path.join("in", repo))
            os.makedirs(d)
            git(d, "init", "-q")
            with open(os.path.join(d, "a.txt"), "w") as f:
                f.write(repo)
            git(d, "add", "a.txt")
            git(d, "commit", "-q", "-m", "x")
            self.shas[repo] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True,
                                             text=True).stdout.strip()
        self.env = mock.patch.dict(os.environ, {"HINO_CONTEXT_INPUTS": os.path.join(root, "in"),
                                                "HINO_CONTEXT_RONTEN": os.path.join(root, "ronten")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def lock(self, **sha):
        return {r: {"sha": sha.get(r.replace("-", "_"), self.shas[r]), "files": ["a.txt"]} for r in inputs.REPOS}

    def test_match(self):
        inputs.check_heads(self.lock())
        self.assertEqual(inputs.Inputs(self.lock()).read_text(inputs.HS, "a.txt"), inputs.HS)

    def test_mismatch(self):
        with self.assertRaises(inputs.InputError) as c:
            inputs.Inputs(self.lock(hino_town_docs="0" * 40))
        self.assertIn("hino-town-docs", str(c.exception))
        self.assertIn("1 件", str(c.exception))

    def test_not_git_or_missing(self):
        d = os.path.join(self.tmp.name, "in", inputs.CD)
        subprocess.run(["rm", "-rf", os.path.join(d, ".git")], check=True)
        os.rename(os.path.join(self.tmp.name, "in", inputs.SP), os.path.join(self.tmp.name, "in", "x"))
        with self.assertRaises(inputs.InputError) as c:
            inputs.check_heads(self.lock())
        self.assertIn("2 件", str(c.exception))

    def test_lock_form(self):
        p = os.path.join(self.tmp.name, "lock.json")
        bad = self.lock()
        del bad[inputs.RT]
        with open(p, "w") as f:
            json.dump(bad, f)
        with self.assertRaises(inputs.InputError):
            inputs.load_lock(p)

    def test_path_outside_files(self):
        with self.assertRaises(inputs.InputError):
            inputs.Inputs(self.lock()).read_bytes(inputs.HS, "b.txt")

    def test_main_stops_without_writing(self):
        out = os.path.join(bn.OUT_DIR, "hoiku.html")
        before = os.path.getmtime(out) if os.path.exists(out) else None
        with mock.patch("sys.stderr"):
            self.assertEqual(bn.main(["hoiku"]), 1)     # 本物の lock と、この一時の入力は合わない
        self.assertEqual(os.path.getmtime(out) if os.path.exists(out) else None, before)


def real_inputs():
    try:
        return inputs.Inputs()
    except inputs.InputError:
        return None


class Wrap:
    """本物の入力の、hino-ronten の表だけを差し替える。"""

    def __init__(self, inp, change):
        self._inp, self._change = inp, change

    def __getattr__(self, name):
        return getattr(self._inp, name)

    def ronten_tsv(self, path):
        rows = [dict(r) for r in self._inp.ronten_tsv(path)]
        return self._change(path, rows) or rows


class TestReal(unittest.TestCase):
    """lock の版の入力で、試作のページ（hoiku）を作る。入力が lock と合わなければ飛ばす。"""

    @classmethod
    def setUpClass(cls):
        cls.inp = real_inputs()
        if cls.inp is None:
            raise unittest.SkipTest("lock の版の入力が無い")
        cls.teigi = bn.read_teigi(os.path.join(inputs.ROOT, "teigi", "note-hoiku.tsv"), "hoiku")
        cls.kotoba = bn.read_kotoba()

    def build(self, inp, t=None):
        return bn.build(inp, t or self.teigi, "hoiku", self.kotoba, TODAY)

    def test_counts(self):
        _, info = self.build(self.inp)
        self.assertEqual([(n, k) for _, n, k in info["counts"]], [(13, 5), (9, 4), (8, 4), (6, 3)])
        self.assertEqual(info["questions"], 6)
        self.assertEqual(info["quotes"].mismatched, [])
        self.assertEqual(info["paras"].mismatched, [])

    def first_point_row(self, path, rows, col, f):
        r = next(r for r in rows if r["status"] == "confirmed" and r.get("point") == "新こども園の面積")
        r[col] = f(r[col])
        return rows

    def test_stop_quote_one_char(self):
        def change(path, rows):
            if path == ronten.KOTOGARA:
                return self.first_point_row(path, rows, "quote", lambda q: q[:-1] + ("あ" if q[-1] != "あ" else "い"))
        with self.assertRaises(bn.Stop) as c:
            self.build(Wrap(self.inp, change))
        self.assertEqual([k for k, _ in c.exception.problems], ["(a) 引用が原典に無い"])

    def test_stop_source_removed(self):
        def change(path, rows):
            if path == ronten.KOTOGARA:
                return self.first_point_row(path, rows, "source", lambda s: "")
        with self.assertRaises(bn.Stop) as c:
            self.build(Wrap(self.inp, change))
        self.assertIn("(b) 出典の無い記述", kinds(c.exception))

    def test_chu(self):
        page, _ = self.build(self.inp)
        self.assertEqual(page.count("<div class='chu'>作成者の注："), 2)   # 説明の移り変わりの表と、質問の該当の部分
        self.assertIn("作成者が補った説明", page)

    def with_chu(self, **kw):
        t = dict(self.teigi)
        t["chu"] = [dict(self.teigi["chu"][0], **kw)]
        return t

    def test_stop_chu_target_missing(self):
        with self.assertRaises(bn.Stop) as c:
            self.build(self.inp, self.with_chu(part="どの記述にも無い字"))
        self.assertIn("定義", kinds(c.exception))

    def test_stop_chu_fragment_not_in_source(self):
        with self.assertRaises(bn.Stop) as c:
            self.build(self.inp, self.with_chu(text="表では「この字は資料に無い」とあります。"))
        self.assertIn("(a) 引用が原典に無い", kinds(c.exception))

    def test_stop_chu_source_unknown(self):
        with self.assertRaises(bn.Stop) as c:
            self.build(self.inp, self.with_chu(moto="doc:sonzai-shinai/1"))
        self.assertTrue({"(a) 引用が原典に無い", "(b) 出典の無い記述"} & set(kinds(c.exception)))

    def test_stop_word(self):
        t = dict(self.teigi)
        t["topics"] = [(P_, s, sh, se + "の記載" if s == "menseki" else se) for P_, s, sh, se in t["topics"]]
        with self.assertRaises(bn.Stop) as c:
            self.build(self.inp, t)
        self.assertEqual(kinds(c.exception), {"(c) 使わない言葉"})


if __name__ == "__main__":
    unittest.main()
