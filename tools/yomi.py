"""生成AIの2回の読み取りの結果（taio/yomi/）から、質問と事項の対応の表（taio/shudai.tsv）と、質問が取り上げた資料と
出来事の表（taio/konkyo.tsv）の読み取りの行を作る（SCHEMA.md 7.10）。

使い方：
  python3 -B tools/yomi.py            taio/shudai.tsv を作る（taio/konkyo.tsv は tools/konkyo.py が作る）
  python3 -B tools/yomi.py --kensa    作り直した行が taio/shudai.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの（taio/yomi/）：
  taba.json                 束の並び。束ごとに、読んだ一般質問の sid の並び（0から数える）
  <読み手>-<束>-shudai.tsv  列 question、point、hani、mayoi、riyu（読み手は a と b）
  <読み手>-<束>-konkyo.tsv  列 question、aite、hani
  <読み手>-<束>-kouho.tsv   列 question、hani、namae

行を作る決まり（SCHEMA.md 7.10）：
  質問と事項（資料と出来事は名前）の組ごとに、段落を1つずつに分け、2回とも付けた段落を yomi「一致」の行に、
  片方だけが付けた段落を、読み手ごとに yomi「1回だけ」の行にする。段落は発言の順に並べ、続いた段落は範囲にまとめる。
  事項は、事項の表（teigi/jiko.tsv）の name から ID を引く。資料と出来事の名前は、資料と出来事の名前の表
  （teigi/konkyo-namae.tsv）で、資料の ID がある名前だけを ID にし、ほかは名前のまま持つ。ID にするのは、その名前の
  資料のうち、資料の日付が質問の日より前か同じ日のもので、いちばん新しい資料だけ。当たる資料が無ければ名前のまま持つ。
  手で行を書かない。候補（kouho）は表にせず、名前と段落の数の一覧を出すだけにする。
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402
import shogo  # noqa: E402

YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi")
TABA = os.path.join(YOMI_DIR, "taba.json")
PATH = os.path.join(inputs.ROOT, "taio", "shudai.tsv")
NAMAE_PATH = os.path.join(inputs.ROOT, "teigi", "konkyo-namae.tsv")
COLS = ["question", "jiko", "hani", "yomi", "chu"]
NAMAE_COLS = ["namae", "shu", "id", "setsumei", "kohyo", "chu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
SHIRYO, DEKIGOTO = "資料", "出来事"
FILE_COLS = {"shudai": ["question", "point", "hani", "mayoi", "riyu"],
             "konkyo": ["question", "aite", "hani"],
             "kouho": ["question", "hani", "namae"]}


class YomiError(ValueError):
    """読み取りの結果のファイルが無いか、形が違う。"""


def read_taba(path=TABA):
    """束の並び → 束ごとの、質問の ID（iq:<sid>）の並び。"""
    with open(path, encoding="utf-8") as f:
        taba = json.load(f)
    return [[f"iq:{s}" for s in t] for t in taba]


def shitsumon(path=TABA):
    """読んだ質問の ID の並び（束の順）。"""
    return [q for t in read_taba(path) for q in t]


def _read(path, cols):
    if not os.path.exists(path):
        raise YomiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != cols:
            raise YomiError(f"{os.path.relpath(path, inputs.ROOT)} の列が違う（{rd.fieldnames}）")
        return list(rd)


def read_yomi(yomi_dir=YOMI_DIR, taba_path=TABA):
    """→ {種類: [行（読み手 yomite を付けたもの）]}。束の外の質問の行があれば YomiError。"""
    out = {k: [] for k in FILE_COLS}
    bad = []
    for n, qs in enumerate(read_taba(taba_path)):
        for y in YOMITE:
            for k, cols in FILE_COLS.items():
                for i, r in enumerate(_read(os.path.join(yomi_dir, f"{y}-{n}-{k}.tsv"), cols), 2):
                    if r["question"] not in qs:
                        bad.append(f"{y}-{n}-{k}.tsv {i} 行目：質問 {r['question']} が束 {n} に無い")
                    out[k].append(dict(r, yomite=y, taba=n))
    if bad:
        raise YomiError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return out


def matomeru(paras):
    """(sid, 段落の番号) の集まり → 段落の ID を「,」でつないだ字（発言の順。続いた段落は範囲にまとめる）。"""
    out = []
    for sid, i in sorted(paras):
        if out and out[-1][0] == sid and out[-1][2] == i - 1:
            out[-1][2] = i
        else:
            out.append([sid, i, i])
    return ",".join(keys.para(s, a, b) for s, a, b in out)


def kumi_gyo(rows, col, key_of):
    """読み手の行 → 組（質問, 相手）ごとの、一致の行と、読み手ごとの1回だけの行。col は相手の列、key_of は
    (相手, 質問) → 表の字。→ [(question, 相手の字, hani, yomi, 読み手の字, 迷いの読み手)]"""
    paras, mayoi = {}, {}
    for r in rows:
        k = (r["question"], key_of(r[col], r["question"]))
        paras.setdefault(k, {y: set() for y in YOMITE})[r["yomite"]] |= set(keys.paras_of(r["hani"]))
        if r.get("mayoi", "").strip() == "1":
            mayoi.setdefault(k, set()).add(r["yomite"])
    out = []
    for (q, a), ps in paras.items():
        m = "、".join(sorted(mayoi.get((q, a), ())))
        both = ps["a"] & ps["b"]
        if both:
            out.append((q, a, matomeru(both), ICCHI, "", m))
        for y in YOMITE:
            only = ps[y] - ps[[x for x in YOMITE if x != y][0]]
            if only:
                out.append((q, a, matomeru(only), IKKAI, y, m))
    return out


def chu_of(yomite, mayoi):
    out = []
    if yomite:
        out.append(f"読み手 {yomite} だけが付けた")
    if mayoi:
        out.append(f"迷いの印：読み手 {mayoi}")
    return "。".join(out)


def read_namae(path=NAMAE_PATH):
    """資料と出来事の名前の表 → 行の並び。"""
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), NAMAE_COLS)


RE_HI = r"[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?"


def hi_of(h):
    """資料の日付（YYYY-MM か YYYY-MM-DD）→ 比較に使う YYYY-MM-DD。月までの日付は、その月の1日とする（SCHEMA.md 7.10）。"""
    return h + "-01" if len(h) == 7 else h


def shiryo_hi(r, hiduke):
    """資料と出来事の名前の表の、資料の行 → 資料の日付（資料の一覧の表の hiduke。空なら kohyo）。無ければ空。"""
    return (hiduke or {}).get(r["id"]) or r.get("kohyo", "")


def check_namae(rows, bunsho, hiduke=None):
    """資料と出来事の名前の表の検査 → 問題の並び。shu が2つのどちらかで、資料の id は資料の一覧の表にあり、
    出来事の id は空でなく ID の形（英小文字・数字・ハイフン）で、id が重ならないこと。namae が重なるのは、どれも
    shu が資料で id があり、setsumei が同じで、資料の日付が違う行だけ（版ごとの行）。hiduke（資料の ID → 資料の一覧の表の
    hiduke）を渡したときは、資料の id のある行に、hiduke か kohyo の片方だけに日付があることも確認する。"""
    import re
    bad = []
    by = {}
    for i, r in enumerate(rows, 2):
        if not r["namae"]:
            bad.append(f"{i} 行目：namae が空")
        by.setdefault(r["namae"], []).append(r)
        if r["shu"] not in (SHIRYO, DEKIGOTO):
            bad.append(f"{i} 行目：shu が「{SHIRYO}」「{DEKIGOTO}」のどちらでもない（{r['shu']}）")
        elif r["shu"] == SHIRYO and r["id"] and r["id"] not in bunsho:
            bad.append(f"{i} 行目：資料の id が資料の一覧の表に無い（{r['id']}）")
        elif r["shu"] == DEKIGOTO and not re.fullmatch(r"[a-z0-9-]+", r["id"]):
            bad.append(f"{i} 行目：出来事の id が空か、形が違う（{r['id']}）")
        if r.get("kohyo") and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", r["kohyo"]):
            bad.append(f"{i} 行目：kohyo の形が違う（{r['kohyo']}）")
        if r.get("kohyo") and not (r["shu"] == SHIRYO and r["id"]):
            bad.append(f"{i} 行目：kohyo があるのに、資料の id が無い（{r['namae']}）")
        if hiduke is not None and r["shu"] == SHIRYO and r["id"] in bunsho:
            h = hiduke.get(r["id"]) or ""
            if bool(re.fullmatch(RE_HI, h)) == bool(r.get("kohyo")):
                bad.append(f"{i} 行目：資料の日付が、資料の一覧の表の hiduke と kohyo の片方だけにない（{r['id']}）")
    for n, rs in by.items():
        if len(rs) < 2:
            continue
        if any(not (r["shu"] == SHIRYO and r["id"]) for r in rs) or len({r["setsumei"] for r in rs}) > 1:
            bad.append(f"namae が重なっている行が、どれも資料の id のある行で setsumei が同じ、になっていない（{n}）")
        elif hiduke is not None:
            his = [hi_of(shiryo_hi(r, hiduke)) for r in rs]
            if len(set(his)) < len(his):
                bad.append(f"namae が重なっている行に、資料の日付が同じ行がある（{n}）")
    ids = [r["id"] for r in rows if r["id"]]
    bad += [f"id が重なっている（{x}）" for x in sorted({x for x in ids if ids.count(x) > 1})]
    return bad


def q_hi(q):
    """質問の ID → 質問の日（質問の ID の発言の日。YYYY-MM-DD）。"""
    return keys.sid_date(keys.sid_of(q))


def aite_of(namae_rows, hiduke=None):
    """(名前, 質問) → konkyo.tsv の aite の字。資料の ID がある名前は、その名前の資料のうち、資料の日付が質問の日より前か
    同じ日のもので、いちばん新しい資料の ID。当たる資料が無い名前と、ほかの名前は、名前のまま（SCHEMA.md 7.10）。
    hiduke は、資料の ID → 資料の一覧の表の hiduke（None なら読む）。"""
    if hiduke is None:
        import konkyo
        hiduke = konkyo.bunsho_hiduke()
    to = {}
    for r in namae_rows:
        if r["shu"] == SHIRYO and r["id"]:
            to.setdefault(r["namae"], []).append((hi_of(shiryo_hi(r, hiduke)), r["id"]))

    def f(n, q):
        qh = q_hi(q)
        mae = sorted(x for x in to.get(n, []) if x[0] <= qh)
        return mae[-1][1] if mae else n
    return f


def shudai_rows(yomi, jiko_rows):
    """→ (taio/shudai.tsv の行, 問題の並び)。事項の名前が事項の表に無ければ問題。"""
    by = {r["name"]: r["id"] for r in jiko_rows}
    jun = {r["id"]: i for i, r in enumerate(jiko_rows)}
    bad = sorted({f"事項の名前「{r['point']}」が事項の表に無い（{r['yomite']}-{r['taba']}）"
                  for r in yomi["shudai"] if r["point"] not in by})
    if bad:
        return [], bad
    rows = [dict(question=q, jiko=a, hani=h, yomi=y, chu=chu_of(w, m))
            for q, a, h, y, w, m in kumi_gyo(yomi["shudai"], "point", lambda n, q: by.get(n))]
    rows.sort(key=lambda r: (r["question"], jun[r["jiko"]], YOMI.index(r["yomi"]), r["chu"]))
    return rows, []


def konkyo_rows(yomi, namae_rows, hiduke=None):
    """→ taio/konkyo.tsv の、読み取りの行（tools/konkyo.py が、入力の確定済みの行と合わせて表にする）。"""
    rows = [dict(question=q, aite=a, hani=h, yomi=y, chu=chu_of(w, m))
            for q, a, h, y, w, m in kumi_gyo(yomi["konkyo"], "aite", aite_of(namae_rows, hiduke))]
    return rows


def kouho(yomi):
    """候補の名前 → (段落の数（2人の読み手の段落を合わせた数）, 読み手の字)。名前の順。"""
    out = {}
    for r in yomi["kouho"]:
        ps, ys = out.setdefault(r["namae"], (set(), set()))
        ps |= set(keys.paras_of(r["hani"]))
        ys.add(r["yomite"])
    return {n: (len(ps), "、".join(sorted(ys))) for n, (ps, ys) in sorted(out.items())}


def check(inp, rows, questions, jiko_ids):
    """taio/shudai.tsv の行の検査（SCHEMA.md 7.10）→ 問題の並び。question が読んだ質問にあり、発言があること、
    jiko が事項の表にあること、yomi が決めた字であること、hani の段落が発言にあること。"""
    bad = []
    for i, r in enumerate(rows, 2):
        if r["question"] not in questions:
            bad.append(f"{i} 行目：question が、読んだ質問（taio/yomi/taba.json）に無い（{r['question']}）")
        elif inp.statement_text(keys.sid_of(r["question"])) is None:
            bad.append(f"{i} 行目：question の発言が会議録に無い（{r['question']}）")
        if r["jiko"] not in jiko_ids:
            bad.append(f"{i} 行目：jiko が事項の表に無い（{r['jiko']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{i} 行目：yomi が {YOMI} のどれでもない（{r['yomi']}）")
    res = shogo.check_paras(inp, [dict(where=f"{i} 行目 {r['question']} / {r['jiko']}", hani=r["hani"])
                                  for i, r in enumerate(rows, 2)])
    bad += [f"{m['where']}：{m['reason']}（{m['source']}）" for m in res.mismatched]
    return bad


def dumps(rows, cols=COLS):
    return "\t".join(cols) + "\n" + "".join("\t".join(r[c] for c in cols) + "\n" for r in rows)


def read(path=PATH):
    """taio/shudai.tsv の行。列が違えば InputError。"""
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), COLS)


def main(argv=None):
    p = argparse.ArgumentParser(description="生成AIの2回の読み取りの結果から、質問と事項の対応の表を作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    import konkyo
    try:
        inp = inputs.Inputs()
        yomi = read_yomi()
        jiko_rows = jiko.read()
        namae = read_namae()
        hiduke = konkyo.bunsho_hiduke()
        bunsho = set(hiduke)
    except (inputs.InputError, YomiError, ValueError, OSError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    rows, bad = shudai_rows(yomi, jiko_rows)
    bad += check_namae(namae, bunsho, hiduke)
    if not bad:
        bad += check(inp, rows, set(shitsumon()), {r["id"] for r in jiko_rows})
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    kr = konkyo_rows(yomi, namae, hiduke)
    shu = {r["namae"]: r for r in namae}
    dasanai = {}
    for r in kr:
        if r["aite"] in bunsho:
            continue
        x = shu.get(r["aite"])
        why = ("出来事" if x and x["shu"] == DEKIGOTO else
               "資料の日付が質問の日より後の名前（" + r["aite"] + "）" if x else "資料と出来事の名前の表に無い名前")
        dasanai[why] = dasanai.get(why, 0) + 1
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    nk = {y: sum(r["yomi"] == y for r in kr) for y in YOMI}
    print(f"質問と事項の対応 {len(rows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）。"
          f"質問 {len({r['question'] for r in rows})}、事項 {len({r['jiko'] for r in rows})}")
    print(f"質問が取り上げた資料と出来事の、読み取りの行 {len(kr)}（一致 {nk[ICCHI]}、1回だけ {nk[IKKAI]}）")
    for why, c in sorted(dasanai.items(), key=lambda x: -x[1]):
        print(f"  資料の ID でない行：{why} {c}")
    ko = kouho(yomi)
    print(f"候補（事項の表に無い話題）{len(ko)}：" + "、".join(f"{k}（{c}段落。読み手 {y}）" for k, (c, y) in ko.items()))
    if a.kensa:
        moto = open(PATH, encoding="utf-8").read() if os.path.exists(PATH) else None
        if moto != s:
            print("止めた：作り直した行が taio/shudai.tsv と違う。python3 -B tools/yomi.py で作り直して、コミットする。",
                  file=sys.stderr)
            return 1
        print(f"taio/shudai.tsv と同じ（{len(rows)} 行）")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"taio/shudai.tsv（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
