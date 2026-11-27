"""事項の表（teigi/jiko.tsv）の検査（SCHEMA.md 7.9）。

使い方：
  python3 -B tools/jiko.py
合わない行があると、件数と行を示して止まる（終了コード 1）。
"""
import collections
import csv
import os
import sys

import inputs
import ronten

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "teigi", "jiko.tsv")
COLS = ["id", "theme", "name", "shurui", "taikei", "betsumei", "jotai", "chu"]
SHURUI = {"kadai": "課題", "torikumi": "取り組み", "atai": "対象の属性と値"}
JOTAI = ("案", "決定")
TAIKEI = "ref/taikei.tsv"
TSUNAGARI = "records/tsunagari.tsv"
MOKUTEKI = "目的と手段"


def read(path=PATH):
    with open(path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        if rd.fieldnames != COLS:
            raise ValueError(f"teigi/jiko.tsv の列が違う（{rd.fieldnames}）")
        return list(rd)


def check(rows, taikei_ids):
    """→ 合わない行の説明の並び。taikei_ids は、入力の章立ての表にある ID の集まり。"""
    bad = []
    for col in ("id", "name"):
        for v, n in collections.Counter(r[col] for r in rows).items():
            if n > 1 or not v:
                bad.append(f"{col} が重なっているか空（{v!r}）")
    for r in rows:
        if r["shurui"] not in SHURUI:
            bad.append(f"{r['id']}：shurui が3つのどれでもない（{r['shurui']!r}）")
        if r["taikei"] != "nashi" and r["taikei"] not in taikei_ids:
            bad.append(f"{r['id']}：taikei が入力の章立ての表に無い（{r['taikei']!r}）")
        if r["jotai"] not in JOTAI:
            bad.append(f"{r['id']}：jotai が違う（{r['jotai']!r}）")
        if not r["theme"]:
            bad.append(f"{r['id']}：theme が空")
    return bad


def taikei_ids(inp):
    return {f"tk:{r['taikei']}/{r['n']}" for r in inp.ronten_tsv(TAIKEI)}


def mokuteki(inp, rows):
    """入力のつながりの記録（確定済み）の「目的と手段」の組（目的, 手段）のうち、両端が事項の表にあるもの。"""
    names = {r["name"] for r in rows}
    kumi = {(r["upper"], r["lower"]) for r in ronten._confirmed(inp, TSUNAGARI) if r["link"] == MOKUTEKI}
    return sorted(k for k in kumi if k[0] in names and k[1] in names), len(kumi)


def main():
    inp = inputs.Inputs()
    rows = read()
    bad = check(rows, taikei_ids(inp))
    if bad:
        print(f"止めた：事項の表に合わない行がある（{len(bad)} 件）")
        print("\n".join("  - " + b for b in bad))
        return 1
    c = collections.Counter(r["shurui"] for r in rows)
    nashi = sum(r["taikei"] == "nashi" for r in rows)
    ari, zen = mokuteki(inp, rows)
    print(f"問題は無い（事項 {len(rows)}：" + "、".join(f"{SHURUI[k]} {c[k]}" for k in SHURUI)
          + f"。計画の章立てに入らない事項 {nashi}。入力の「目的と手段」の組 {zen} のうち、両端が事項の表にある組 {len(ari)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
