"""質問が取り上げた資料と出来事の表（taio/konkyo.tsv。SCHEMA.md 7.10）を作る。行は、入力の確定済みの記録から作れる行と、
生成AIの2回の読み取りの結果（taio/yomi-<テーマ>/。tools/yomi.py の konkyo_rows）から作る行の2つ。行ごとに、
質問のテーマ（theme）を持つ。

使い方：
  python3 -B tools/konkyo.py            taio/konkyo.tsv を作る
  python3 -B tools/konkyo.py --kensa    作り直した行が taio/konkyo.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

行を作る決まり（SCHEMA.md 7.10）：hino-ronten の質問と事項の対応の記録（records/taio.tsv。確定済み）のうち、point が
どのテーマの論点（事項の表の name と、論点の仮の表の論点の name）でもない行について、次の順に決める。
(1) point の名前が、質問があるテーマ（テーマの定義の問い・質疑。定義の順）の、資料と出来事の名前の表の名前（namae か
betsumei）にあれば、そのテーマの行にする。aite は、読み取りの行と同じ決め方（tools/yomi.py の aite_of）。
(2) 無ければ、point の名前に、つながりの記録
（records/tsunagari.tsv。確定済み）の upper_ref か lower_ref があり、その ID がどれも、資料の一覧の表にある1つの資料の
1ページめ（pt と doc）か、資料そのもの（plan）を指すもの。aite はその資料の ID、hani は対応の記録の hani のまま。
theme は、質問があるテーマ（定義の順の最初）。
作れない point は、理由とともに出す（止めない）。手で行を書かない。
読み取りの行は、入力の確定済みの行のあとに、tools/yomi.py の順のまま置く。aite は、資料の ID か、資料と出来事の名前の表
（teigi/konkyo-namae.tsv）の名前か、その表に無い名前（読み手が発言の言葉で書いた名前）。資料の ID にするのは、資料の日付が
質問の日より前か同じ日の資料のうち、いちばん新しいものだけ（tools/yomi.py の aite_of）。名前ごとに、資料の ID ごとの
結び付いた行の数と、結び付かなかった行の数を出す。
議案への質疑の読み取りの行（tools/shitsugi.py）は、一般質問の読み取りの行のあとに置く。
読み取りの結果には、候補の名前と扱いの対応の表（teigi/kouho.tsv）で「資料を取り上げた部分にする」とした候補の段落を、
入れる先の資料の名前の段落として入れる（tools/yomi.py の yomi_ireta）。
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
COLS = ["question", "n", "theme", "aite", "hani", "yomi", "chu"]
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


def q_themes(inp):
    """質問 → その質問を問い・質疑に持つテーマの並び（テーマの定義の順）。"""
    out = {}
    for r in inp.ronten_tsv(ronten.THEMES):
        if r["kind"] in ("問い", "質疑"):
            out.setdefault(r["value"], [])
            if r["theme"] not in out[r["value"]]:
                out[r["value"]].append(r["theme"])
    return out


def tsukuru(inp, bunsho, names, namae=None, hiduke=None):
    """→ (行の並び, 作れなかった point と理由の並び)。bunsho は資料の一覧の表の ID の集まり、names は論点の名前の集まり、
    namae は資料と出来事の名前の表の行（None なら名前の表から作る行を作らない）、hiduke は資料の ID → hiduke。"""
    qth = q_themes(inp)
    namae = namae or []
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
        ths = qth.get(t["question"], [])
        hit = next((th for th in ths if any(P in ym.namae_of(r) for r in ym.of_theme(namae, th))), None)
        if hit:
            nm = ym.of_theme(namae, hit)
            moto = next(r["namae"] for r in nm if P in ym.namae_of(r))
            rows.append(dict(question=t["question"], n="", theme=hit, aite=ym.aite_of(nm, hiduke)(P, t["question"]),
                             hani=t["hani"], yomi=NYURYOKU,
                             chu=f"入力：records/taio.tsv の point「{P}」（確定済み）。資料と出来事の名前の表の {hit} の"
                                 f"「{moto}」の行から"))
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
        rows.append(dict(question=t["question"], n="", theme=(ths or [""])[0], aite=b.pop(), hani=t["hani"], yomi=NYURYOKU,
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


def check(rows, bunsho, hiduke=None, namae=None):
    """行の検査（SCHEMA.md 7.10）→ 問題の並び。theme が空でないこと、aite が資料の一覧の表にあるか、資料の ID の形でない
    名前であること（入力の確定済みの行は、資料の一覧の表にあるか、そのテーマの名前の表の出来事の namae であること）、
    yomi が決めた字であること、hani があること。hiduke（資料の ID → 資料の一覧の表の hiduke）と namae（資料と出来事の
    名前の表の行）を渡したときは、aite が名前の表の資料の ID の行の、資料の日付（hiduke か kohyo）が質問の日より後で
    ないことも確認する（入力の確定済みの行は、名前の表から作った行だけ）。"""
    bad = []
    hi = {}
    namae = namae or []
    if hiduke is not None:
        hi = {r["id"]: ym.hi_of(ym.shiryo_hi(r, hiduke)) for r in namae if r["shu"] == ym.SHIRYO and r["id"]}
    ev = {(r["theme"], r["namae"]) for r in namae if r["shu"] == ym.DEKIGOTO}
    for i, r in enumerate(rows, 2):
        if not r["theme"]:
            bad.append(f"{i} 行目：theme が空")
        nyu = r["yomi"] == NYURYOKU and "資料と出来事の名前の表" not in r["chu"]
        if not nyu and r["aite"] in hi and r["question"] and hi[r["aite"]] > ym.q_hi(r["question"]):
            bad.append(f"{i} 行目：資料の日付（{hi[r['aite']]}）が質問の日（{ym.q_hi(r['question'])}）より後（{r['aite']}）")
        if r["aite"] not in bunsho and (r["yomi"] == NYURYOKU and (r["theme"], r["aite"]) not in ev
                                        or not r["aite"] or ":" in r["aite"]):
            bad.append(f"{i} 行目：aite が資料の一覧の表にも、そのテーマの出来事の名前にも無い（{r['aite']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{i} 行目：yomi が {YOMI} のどれでもない（{r['yomi']}）")
        if not (r["question"] and r["hani"]):
            bad.append(f"{i} 行目：question か hani が空")
    return bad


def bunsho_hiduke():
    """資料の一覧の表の ID → hiduke。"""
    with open(os.path.join(sj.TEIGI_DIR, "bunsho.tsv"), encoding="utf-8") as f:
        return {r["bunsho"]: r["hiduke"] for r in sj.read_bunsho(f.read())[0]}


def bunsho_ids():
    """資料の一覧の表の ID の集まり。"""
    return set(bunsho_hiduke())


def uchiwake(rows, namae):
    """読み取りの行のうち、資料と出来事の名前の表の資料の名前の行 → [(テーマ, 名前, {資料の ID: 行の数}, 結び付かなかった行の数)]。
    名前の表の順。資料の ID が無い名前は、全部の行が結び付かなかった行。"""
    of = {(r["theme"], r["id"]): r["namae"] for r in namae if r["shu"] == ym.SHIRYO and r["id"]}
    out = {}
    for r in namae:
        if r["shu"] == ym.SHIRYO:
            ids = out.setdefault((r["theme"], r["namae"]), ({}, [0]))[0]
            if r["id"]:
                ids[r["id"]] = 0
    for r in rows:
        if r["yomi"] == NYURYOKU:
            continue
        if (r["theme"], r["aite"]) in of:
            out[(r["theme"], of[(r["theme"], r["aite"])])][0][r["aite"]] += 1
        elif (r["theme"], r["aite"]) in out:
            out[(r["theme"], r["aite"])][1][0] += 1
    return [(th, n, ids, c[0]) for (th, n), (ids, c) in out.items()]


def main(argv=None):
    p = argparse.ArgumentParser(description="質問が取り上げた資料と出来事の表を、入力の確定済みの記録から作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        hiduke = bunsho_hiduke()
        bunsho = set(hiduke)
        namae = ym.read_namae()
        theme_jun = list(dict.fromkeys(r["theme"] for r in inp.ronten_tsv(ronten.THEMES)))
        rows, dekinai = tsukuru(inp, bunsho, ronten_names(theme_jun), namae, hiduke)
        for th in ym.themes():
            rows += ym.konkyo_rows(ym.yomi_ireta(th, namae_rows=namae)[0], ym.of_theme(namae, th), hiduke, th,
                                   ym.read_chu(th))
        # 議案への質疑の読み取りの行（tools/shitsugi.py。SCHEMA.md 7.10。2026-11-28）は、一般質問の読み取りの行のあと
        import shitsugi as st
        rows += st.tsukuru(inp, namae=namae, hiduke=hiduke)["konkyo"]
    except (inputs.InputError, ym.YomiError, ValueError) as e:
        print(f"止めた：lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    bad = check(rows, bunsho, hiduke, namae) + ym.check_namae(namae, bunsho, hiduke)
    if bad:
        print(f"止めた：作った行に合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    for P, why in dekinai:
        print(f"行を作れない point「{P}」：{why}")
    uw = uchiwake(rows, namae)
    print(f"読み取りの行のうち、資料の名前の行で、資料の ID を付けなかった行 {sum(c for _, _, _, c in uw)}"
          "（資料の日付が質問の日より後か、資料の ID が無い名前）")
    for th, n, ids, c in uw:
        print(f"  {th} {n}：" + "".join(f"{k} {v}行、" for k, v in ids.items()) + f"ID を付けなかった行 {c}")
    ev = {(r["theme"], r["namae"]) for r in namae if r["shu"] == ym.DEKIGOTO}
    kazu = {}
    for r in rows:
        if (r["theme"], r["aite"]) in ev:
            kazu.setdefault((r["theme"], r["aite"]), []).append(r["yomi"])
    for (th, n), ys in kazu.items():
        print(f"  {th} 出来事 {n}：{len(ys)}行（" + "、".join(f"{y} {ys.count(y)}" for y in YOMI if ys.count(y)) + "）")
    shu = {(r["theme"], r["namae"]) for r in namae}
    nai = {}
    for r in rows:
        if r["aite"] not in bunsho and (r["theme"], r["aite"]) not in shu:
            nai[(r["theme"], r["aite"])] = nai.get((r["theme"], r["aite"]), 0) + 1
    print(f"  資料と出来事の名前の表に無い名前の行 {sum(nai.values())}（名前 {len(nai)}）")
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
