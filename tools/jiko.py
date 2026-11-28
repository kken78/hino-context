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
COLS = ["id", "theme", "name", "shurui", "taikei", "matome", "betsumei", "jotai", "chu"]
SHURUI = {"kadai": "課題", "torikumi": "取り組み", "atai": "対象の属性と値"}
JOTAI = ("案", "決定")
MOKUTEKI = "目的と手段"
HOKA = "ほかの分野にかかわる話題"    # この matome の事項は、どのテーマの論点の一覧でも最後に並べる（SCHEMA.md 7.9。2026-11-28）
THEME_MAX = 2                      # theme の列に書けるテーマの数（SCHEMA.md 7.9。2026-11-28）


def themes_of(r):
    """事項の行の theme の列 → テーマの ID の並び（「,」で区切る。SCHEMA.md 7.9）。"""
    return [t.strip() for t in r["theme"].split(",")]


def of_theme(rows, theme):
    """事項の表の行のうち、theme の列にそのテーマがある行（表の順）。"""
    return [r for r in rows if theme in themes_of(r)]


def theme_jun(rows):
    """事項の表のテーマの並び。表でテーマが最初に出る順。"""
    return list(dict.fromkeys(t for r in rows for t in themes_of(r)))


def read(path=PATH):
    """事項の表の全部の行（表の順）。"""
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
        if r["matome"] and r["taikei"] != "nashi":
            bad.append(f"{r['id']}：matome は、taikei が nashi の行にだけ書ける（{r['matome']!r}）")
        if r["jotai"] not in JOTAI:
            bad.append(f"{r['id']}：jotai が違う（{r['jotai']!r}）")
        ths = themes_of(r)
        if not all(ths) or len(set(ths)) != len(ths) or len(ths) > THEME_MAX:
            bad.append(f"{r['id']}：theme が空か、テーマが重なっているか、{THEME_MAX} つより多い（{r['theme']!r}）")
    return bad


def matome_jun(rows):
    """matome の字 → その事項の行の並び。まとまりは、表で最初に出る順（SCHEMA.md 7.9）。"""
    out = {}
    for r in rows:
        if r["matome"]:
            out.setdefault(r["matome"], []).append(r)
    return out


def taikei_ids(inp):
    return set(ronten.taikei(inp))


def mokuteki(inp, rows):
    """入力のつながりの記録（確定済み）の「目的と手段」の組（目的, 手段）のうち、両端が事項の表にあるもの。"""
    names = {r["name"] for r in rows}
    kumi = {(r["upper"], r["lower"]) for r in ronten.tsunagari(inp, MOKUTEKI)}
    return sorted(k for k in kumi if k[0] in names and k[1] in names), len(kumi)


def mokuteki_gyo(inp, rows):
    """入力のつながりの記録（確定済み）の「目的と手段」の行のうち、両端が事項の表にある行（SCHEMA.md 7.9）。"""
    names = {r["name"] for r in rows}
    return [r for r in ronten.tsunagari(inp, MOKUTEKI) if r["upper"] in names and r["lower"] in names]


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
    for th in theme_jun(rows):
        rs = of_theme(rows, th)
        ct = collections.Counter(r["shurui"] for r in rs)
        mt = "、".join(f"{k} {len(v)}" for k, v in matome_jun(rs).items()) or "無い"
        print(f"[{th}] 事項 {len(rs)}：" + "、".join(f"{SHURUI[k]} {ct[k]}" for k in SHURUI)
              + f"。計画の章立てに入らない事項 {sum(r['taikei'] == 'nashi' for r in rs)}（資料の外のまとまり：{mt}）。"
              + f"ほかのテーマと共通の事項 {sum(len(themes_of(r)) > 1 for r in rs)}")
    print(f"問題は無い（事項 {len(rows)}：" + "、".join(f"{SHURUI[k]} {c[k]}" for k in SHURUI)
          + f"。計画の章立てに入らない事項 {nashi}。"
          + f"入力の「目的と手段」の組 {zen} のうち、両端が事項の表にある組 {len(ari)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
