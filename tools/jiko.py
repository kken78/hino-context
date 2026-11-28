"""事項の表（teigi/jiko.tsv）の検査（SCHEMA.md 7.9）。

使い方：
  python3 -B tools/jiko.py
合わない行があると、件数と行を示して止まる（終了コード 1）。
"""
import collections
import csv
import os
import re
import sys
import unicodedata

import inputs
import ronten

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "teigi", "jiko.tsv")
COLS = ["id", "theme", "name", "shurui", "taikei", "kihon", "matome", "betsumei", "jotai", "chu"]
SHURUI = {"kadai": "課題", "torikumi": "取り組み", "atai": "対象の属性と値"}
JOTAI = ("案", "決定")
MOKUTEKI = "目的と手段"
HOKA = "ほかの分野にかかわる話題"    # この matome の事項は、どのテーマの論点の一覧でも最後に並べる（SCHEMA.md 7.9。2026-11-28）
THEME_MAX = 2                      # theme の列に書ける、分野でないテーマの数（SCHEMA.md 7.9。2026-11-28）
RE_BUNYA = re.compile(r"b(0[1-9]|[12][0-9]|3[0-4])")   # 総合計画の分野のテーマの ID（b と分野の番号の2桁。SCHEMA.md 7.9。2026-11-28）


def is_bunya(theme):
    """テーマの ID が、総合計画の分野のテーマ（b02 など）か。"""
    return bool(RE_BUNYA.fullmatch(theme))


def bunya_theme(no):
    """分野の番号（入力の字。①〜㉞）→ 分野のテーマの ID（①は b01）。"""
    return f"b{int(unicodedata.numeric(no)):02d}"


def kihon_of(r):
    """事項の行の kihon の列 → 基本施策の並び（分野の番号と基本施策の番号の字。例「㉕(1)」）。"""
    return [k.strip() for k in r.get("kihon", "").split(",") if k.strip()]


def kihon_bunya(k):
    """基本施策の字（「㉕(1)」）→ (分野の番号, 基本施策の番号)。"""
    i = k.index("(")
    return k[:i], k[i:]


def themes_of(r):
    """事項の行の theme の列 → テーマの ID の並び（「,」で区切る。SCHEMA.md 7.9）。"""
    return [t.strip() for t in r["theme"].split(",")]


def of_theme(rows, theme):
    """事項の表の行のうち、theme の列にそのテーマがある行（表の順）。"""
    return [r for r in rows if theme in themes_of(r)]


def theme_jun(rows):
    """事項の表のテーマの並び。分野でないテーマを、表でテーマが最初に出る順に並べ、そのあとに分野のテーマを、分野の番号の順に
    並べる（2026-11-28）。"""
    jun = list(dict.fromkeys(t for r in rows for t in themes_of(r)))
    return [t for t in jun if not is_bunya(t)] + sorted(t for t in jun if is_bunya(t))


def read(path=PATH):
    """事項の表の全部の行（表の順）。"""
    with open(path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        if rd.fieldnames != COLS:
            raise ValueError(f"teigi/jiko.tsv の列が違う（{rd.fieldnames}）")
        return list(rd)


def check(rows, taikei_ids, kihon_names=None):
    """→ 合わない行の説明の並び。taikei_ids は、入力の章立ての表にある ID の集まり。kihon_names は、基本施策の字（「㉕(1)」）
    → 入力の基本施策の名前（None なら kihon の列を入力と照合しない）。"""
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
        if (not all(ths) or len(set(ths)) != len(ths) or len([t for t in ths if not is_bunya(t)]) > THEME_MAX):
            bad.append(f"{r['id']}：theme が空か、テーマが重なっているか、分野でないテーマが {THEME_MAX} つより多い（{r['theme']!r}）")
        ks = kihon_of(r)
        if len(set(ks)) != len(ks):
            bad.append(f"{r['id']}：kihon が重なっている（{r['kihon']!r}）")
        for k in ks:
            if "(" not in k or kihon_bunya(k)[0] == "" or (kihon_names is not None and k not in kihon_names):
                bad.append(f"{r['id']}：kihon が、入力の総合計画の基本施策に無い（{k!r}）")
            elif bunya_theme(kihon_bunya(k)[0]) not in ths:
                bad.append(f"{r['id']}：kihon の分野（{k}）が、theme の列に無い")
    return bad


def kihon_gyo(rows, kihon_names):
    """基本施策そのものの行（kihon が1つで、name が入力のその基本施策の名前と同じ行）の ID の集まり（SCHEMA.md 7.9。2026-11-28）。"""
    return {r["id"] for r in rows if len(kihon_of(r)) == 1 and kihon_names.get(kihon_of(r)[0]) == r["name"]}


def kihon_names_of(inp):
    """入力の総合計画の基本施策 → 字（「㉕(1)」）→ 名前。"""
    import bunya as bu
    kk = bu.keikaku(inp)
    return {x["no"] + no: name for h in kk["hashira"] for x in h["bunya"] for no, name in x["shisaku"]}


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
    kn = kihon_names_of(inp)
    bad = check(rows, taikei_ids(inp), kn)
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
              + f"ほかのテーマと共通の事項 {sum(len(themes_of(r)) > 1 for r in rs)}"
              + (f"。基本施策の行 {len(kihon_gyo(rs, kn))}、基本施策に入る論点 {sum(bool(kihon_of(r)) for r in rs) - len(kihon_gyo(rs, kn))}"
                 if is_bunya(th) else ""))
    print(f"問題は無い（事項 {len(rows)}：" + "、".join(f"{SHURUI[k]} {c[k]}" for k in SHURUI)
          + f"。計画の章立てに入らない事項 {nashi}。"
          + f"入力の「目的と手段」の組 {zen} のうち、両端が事項の表にある組 {len(ari)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
