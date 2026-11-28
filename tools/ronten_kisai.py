"""hino-ronten の構造にしていない記載（records/kisai.tsv。確定済み）を、事項、資料、出来事に対応づける（SCHEMA.md 7.14）。

使い方：
  python3 -B tools/ronten_kisai.py            対応づけた行の数を、対応づけた先の種類ごとと、事項・資料・出来事ごとに出す
  python3 -B tools/ronten_kisai.py --nokori   どれにも当たらない行の about と行の数の一覧（Markdown）を出す

対応づける決まり（SCHEMA.md 7.14）：status が confirmed の行だけを使う。
(1) about が事項の表（teigi/jiko.tsv）の name と同じなら、その事項（論点）。betsumei は使わない（SCHEMA.md 7.9）。
(2) 当たらなければ、about が、資料の一覧の表（teigi/bunsho.tsv）の namae か、資料と出来事の名前の表
    （teigi/konkyo-namae.tsv。テーマを問わない）の、id のある行の namae か betsumei と同じとき、その id を候補にする。
    候補が1つならその資料か出来事。2つ以上なら、行の source の資料（ページを除いた ID）が候補にあるときだけ、その資料。
(3) どれにも当たらない行は出さない。推し量って対応づけない。
手で行を書かない。対応づけた結果は表に持たず、ツールが入力から毎回作る。
"""
import argparse
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import jiko  # noqa: E402
import ronten  # noqa: E402
import shogo  # noqa: E402
import suji as sj  # noqa: E402
import yomi as ym  # noqa: E402

JIKO, SHIRYO, DEKIGOTO = "jiko", "document", "event"


def kouho_of(bunsho, namae):
    """資料の一覧の表の行と、資料と出来事の名前の表の行 → 名前 → [(種類, ID)]（重ねない。表の順）。"""
    out = {}

    def tasu(n, x):
        if x not in out.setdefault(n, []):
            out[n].append(x)
    for b in bunsho:
        tasu(b["namae"], (SHIRYO, b["bunsho"]))
    for r in namae:
        if not r["id"]:
            continue
        x = (DEKIGOTO if r["shu"] == ym.DEKIGOTO else SHIRYO, r["id"])
        for n in ym.namae_of(r):
            tasu(n, x)
    return out


def ateru(rows, jiko_rows, bunsho, namae):
    """記載の行（確定済み）→ 行ごとの対応づけた先の並び。対応づけた先は (JIKO, 事項の name)、(SHIRYO, 資料の ID)、
    (DEKIGOTO, 出来事の ID) か None。"""
    names = {r["name"] for r in jiko_rows}
    kouho = kouho_of(bunsho, namae)
    out = []
    for r in rows:
        a = r["about"]
        if a in names:
            out.append((JIKO, a))
            continue
        ks = kouho.get(a, [])
        if len(ks) == 1:
            out.append(ks[0])
            continue
        b = sj.bunsho_of(r["source"])
        hit = [x for x in ks if x == (SHIRYO, b)]
        out.append(hit[0] if hit else None)
    return out


def jiko_kiroku(inp, points, kotogara):
    """about が points（事項の name）のどれかの記載の行を、事柄の記録の行と同じ形の辞書にする（tools/build_note.py の collect）。
    同じ事項、資料、引用（SCHEMA.md §3 の正規化のあと）の事柄の記録の行がある記載の行は除く（1つにする）。
    → (行の並び, 除いた行の数)。"""
    onaji = {(r["point"], r["source"], shogo.norm(r["quote"])) for r in kotogara}
    out, nozoku = [], 0
    for r in ronten.kisai(inp):
        if r["about"] not in points:
            continue
        if (r["about"], r["source"], shogo.norm(r["quote"])) in onaji:
            nozoku += 1
            continue
        out.append(kiroku_gyo(r, r["about"]))
    return out, nozoku


def kiroku_gyo(r, point):
    """記載の行 → 事柄の記録の行と同じ列を持つ辞書（value と kind は空。記載の kind は、事柄の記録の kind と違う値なので入れない）。"""
    return dict(point=point, source=r["source"], source_date=r["source_date"], quote=r["quote"], value="",
                target=r["target"], kind="", title=r["title"], daicho="kisai")


def shiryo_kiroku(inp, jiko_rows, bunsho, namae):
    """資料か出来事に当たる記載の行 → {(種類, ID): [事柄の記録と同じ形の辞書]}（入力の順）。"""
    rows = ronten.kisai(inp)
    out = {}
    for r, x in zip(rows, ateru(rows, jiko_rows, bunsho, namae)):
        if x and x[0] != JIKO:
            out.setdefault(x, []).append(kiroku_gyo(r, r["about"]))
    return out


def nokori_md(rows, ate):
    """どれにも当たらない行の about ごとの行の数 → Markdown の字。"""
    c = Counter(r["about"] for r, x in zip(rows, ate) if x is None)
    lines = ["# hino-ronten の町の資料の記載のうち、事項にも資料にも出来事にも当たらないもの", "",
             "hino-context の tools/ronten_kisai.py --nokori が出した一覧。hino-ronten の records/kisai.tsv（確定済み）の行のうち、"
             "about が、事項の表の name にも、資料の一覧の表の namae にも、資料と出来事の名前の表の namae と betsumei にも"
             "当たらない行（SCHEMA.md 7.14）。出していない。推し量って事項に入れていない。", "",
             f"行の数：{sum(c.values())}。名前の数：{len(c)}。", "",
             "| about | 行の数 |", "| --- | --- |"]
    lines += [f"| {a or '（空）'} | {n} |" for a, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nokori", action="store_true", help="どれにも当たらない行の一覧を出す")
    a = ap.parse_args(argv)
    try:
        inp = inputs.Inputs()
        rows = ronten.kisai(inp)
    except inputs.InputError as e:
        print(f"入力を読めない：{e}", file=sys.stderr)
        return 1
    import build_theme as bt
    tables, _ = bt.read_tables()
    ate = ateru(rows, jiko.read(), tables["bunsho"], ym.read_namae())
    if a.nokori:
        sys.stdout.write(nokori_md(rows, ate))
        return 0
    c = Counter(x[0] if x else "なし" for x in ate)
    print(f"確定済みの行 {len(rows)}：事項 {c[JIKO]}、資料 {c[SHIRYO]}、出来事 {c[DEKIGOTO]}、当たらない {c['なし']}")
    for (shu, k), n in sorted(Counter(x for x in ate if x).items(), key=lambda kv: (kv[0][0], -kv[1])):
        print(f"  {shu}\t{k}\t{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
