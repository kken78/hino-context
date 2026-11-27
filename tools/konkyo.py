"""質問が取り上げた資料と出来事の表（taio/konkyo.tsv。SCHEMA.md 7.10）を作る。行は、入力の確定済みの記録から作れる行と、
生成AIの2回の読み取りの結果（taio/yomi/。tools/yomi.py の konkyo_rows）から作る行の2つ。

使い方：
  python3 -B tools/konkyo.py            taio/konkyo.tsv を作る
  python3 -B tools/konkyo.py --kensa    作り直した行が taio/konkyo.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

行を作る決まり（SCHEMA.md 7.10）：hino-ronten の質問と事項の対応の記録（records/taio.tsv。確定済み）のうち、point が
どのテーマの論点（事項の表の name と、論点の仮の表の論点の name）でもない行で、point の名前に、つながりの記録
（records/tsunagari.tsv。確定済み）の upper_ref か lower_ref があり、その ID がどれも、資料の一覧の表にある1つの資料の
1ページめ（pt と doc）か、資料そのもの（plan）を指すもの。aite はその資料の ID、hani は対応の記録の hani のまま。
作れない point は、理由とともに出す（止めない）。手で行を書かない。
読み取りの行は、入力の確定済みの行のあとに、tools/yomi.py の順のまま置く。aite は、資料の ID か、資料と出来事の名前の表
（teigi/konkyo-namae.tsv）の名前か、その表に無い名前（読み手が発言の言葉で書いた名前）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402
import ronten  # noqa: E402
import suji as sj  # noqa: E402
import yomi as ym  # noqa: E402

PATH = os.path.join(inputs.ROOT, "taio", "konkyo.tsv")
COLS = ["question", "aite", "hani", "yomi", "chu"]
YOMI = ("一致", "1回だけ", "入力の確定済み")
NYURYOKU = "入力の確定済み"     # 生成AIが読んだのではなく、hino-ronten の確定済みの記録から、このツールが作った行


def ronten_names(theme_jun):
    """どのテーマの論点でもあるかを見る名前の集まり：事項の表の name と、論点の仮の表（teigi/note-*.tsv）の論点の name。"""
    names = {r["name"] for r in jiko.read()}
    for theme in theme_jun:
        path = os.path.join(inputs.ROOT, "teigi", f"note-{theme}.tsv")
        if os.path.exists(path):
            names |= {P for P, _, _, _ in bn.read_teigi(path, theme)["topics"]}
    return names


def _shiryo_jishin(ref, bunsho):
    """つながりの記録の ref → それが資料そのもの（plan）か、資料の1ページめ（pt、doc）を指すときの資料の ID。ほかは None。"""
    b = sj.bunsho_of(ref)
    if b not in bunsho:
        return None
    if b == ref:
        return b
    try:
        kind, _ = keys.parse(ref)
    except keys.KeyFormError:
        return None
    return b if kind in ("pt", "doc") and ref == f"{b}/1" else None


def tsukuru(inp, bunsho, names):
    """→ (行の並び, 作れなかった point と理由の並び)。bunsho は資料の一覧の表の ID の集まり、names は論点の名前の集まり。"""
    refs = {}
    for r in ronten._confirmed(inp, ronten.TSUNAGARI):
        for gawa in ("upper", "lower"):
            if r[gawa + "_ref"]:
                refs.setdefault(r[gawa], {})[r[gawa + "_ref"]] = gawa + "_ref"
    rows, dekinai = [], {}
    for t in ronten._confirmed(inp, ronten.TAIO):
        P = t["point"]
        if P in names:
            continue
        rs = refs.get(P, {})
        if not rs:
            dekinai[P] = "つながりの記録に、この名前の upper_ref か lower_ref が無い"
            continue
        aite = {ref: _shiryo_jishin(ref, bunsho) for ref in rs}
        b = set(aite.values())
        if len(b) != 1 or None in b:
            dekinai[P] = ("ID が、資料の一覧の表にある1つの資料の1ページめか、資料そのものを指していない（"
                          + "、".join(sorted(rs)) + "）")
            continue
        ref = sorted(rs)[0]
        rows.append(dict(question=t["question"], aite=b.pop(), hani=t["hani"], yomi=NYURYOKU,
                         chu=f"入力：records/taio.tsv の point「{P}」（確定済み）。資料の ID は records/tsunagari.tsv の "
                             f"{rs[ref]}「{ref}」（確定済み）から"))
    rows.sort(key=lambda r: (r["aite"], r["question"]))
    return rows, sorted(dekinai.items())


def dumps(rows):
    return "\t".join(COLS) + "\n" + "".join("\t".join(r[c] for c in COLS) + "\n" for r in rows)


def read(path=PATH):
    """taio/konkyo.tsv の行。列が違えば InputError。"""
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), COLS)


def check(rows, bunsho):
    """行の検査（SCHEMA.md 7.10）→ 問題の並び。aite が資料の一覧の表にあるか、資料の ID の形でない名前であること
    （入力の確定済みの行は、資料の一覧の表にあること）、yomi が決めた字であること、hani があること。"""
    bad = []
    for i, r in enumerate(rows, 2):
        if r["aite"] not in bunsho and (r["yomi"] == NYURYOKU or not r["aite"] or ":" in r["aite"]):
            bad.append(f"{i} 行目：aite が資料の一覧の表に無い（{r['aite']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{i} 行目：yomi が {YOMI} のどれでもない（{r['yomi']}）")
        if not (r["question"] and r["hani"]):
            bad.append(f"{i} 行目：question か hani が空")
    return bad


def bunsho_ids():
    """資料の一覧の表の ID の集まり。"""
    with open(os.path.join(sj.TEIGI_DIR, "bunsho.tsv"), encoding="utf-8") as f:
        return {r["bunsho"] for r in sj.read_bunsho(f.read())[0]}


def main(argv=None):
    p = argparse.ArgumentParser(description="質問が取り上げた資料と出来事の表を、入力の確定済みの記録から作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        bunsho = bunsho_ids()
        theme_jun = list(dict.fromkeys(r["theme"] for r in inp.ronten_tsv(ronten.THEMES)))
        rows, dekinai = tsukuru(inp, bunsho, ronten_names(theme_jun))
        rows += ym.konkyo_rows(ym.read_yomi(), ym.read_namae())
    except (inputs.InputError, ym.YomiError) as e:
        print(f"止めた：lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    bad = check(rows, bunsho)
    if bad:
        print(f"止めた：作った行に合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    for P, why in dekinai:
        print(f"行を作れない point「{P}」：{why}")
    if a.kensa:
        moto = open(PATH, encoding="utf-8").read() if os.path.exists(PATH) else None
        if moto != s:
            print("止めた：作り直した行が taio/konkyo.tsv と違う。python3 -B tools/konkyo.py で作り直して、コミットする。",
                  file=sys.stderr)
            return 1
        print(f"taio/konkyo.tsv と同じ（{len(rows)} 行。作れない point {len(dekinai)}）")
        return 0
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"taio/konkyo.tsv（{len(rows)} 行。作れない point {len(dekinai)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
