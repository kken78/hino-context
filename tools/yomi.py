"""生成AIの2回の読み取りの結果（taio/yomi-<テーマ>/）から、質問と事項の対応の表（taio/shudai.tsv）と、質問が取り上げた
資料と出来事の表（taio/konkyo.tsv）の読み取りの行を作る（SCHEMA.md 7.10）。テーマごとに読み、行はテーマの順
（事項の表でテーマが最初に出る順）に並べる。

使い方：
  python3 -B tools/yomi.py            taio/shudai.tsv を作る（taio/konkyo.tsv は tools/konkyo.py が作る）
  python3 -B tools/yomi.py --kensa    作り直した行が taio/shudai.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの（taio/yomi-<テーマ>/。テーマは事項の表の theme）：
  taba.json                 束の並び。束ごとに、読んだ一般質問の sid の並び（0から数える）
  <読み手>-<束>-shudai.tsv  列 question、point、hani、mayoi、riyu（読み手は a と b）
  <読み手>-<束>-konkyo.tsv  列 question、aite、hani
  <読み手>-<束>-kouho.tsv   列 question、hani、namae
  chu.tsv                   無くてもよい。列 question、chu。その質問の行の全部の chu に足す、読み取りについての注

行を作る決まり（SCHEMA.md 7.10）：
  質問と事項（資料と出来事は名前）の組ごとに、段落を1つずつに分け、2回とも付けた段落を yomi「一致」の行に、
  片方だけが付けた段落を、読み手ごとに yomi「1回だけ」の行にする。段落は発言の順に並べ、続いた段落は範囲にまとめる。
  事項は、事項の表（teigi/jiko.tsv）の、そのテーマの行の name から ID を引く。資料と出来事の名前は、資料と出来事の
  名前の表（teigi/konkyo-namae.tsv）の、そのテーマの行で、betsumei（別の字）を namae に直してから、資料の ID がある
  名前だけを ID にし、ほかは名前のまま持つ。ID にするのは、その名前の資料のうち、資料の日付が質問の日より前か同じ日の
  もので、いちばん新しい資料だけ。当たる資料が無ければ名前のまま持つ。
  手で行を書かない。
  候補（kouho。事項の表に無い話題）は、候補の名前と扱いの対応の表（teigi/kouho.tsv）の、そのテーマの行で扱いを決める。「事項に入れる」の候補の
  段落は、入れる先の事項に読み手が付けた段落として、「資料を取り上げた部分にする」の候補の段落は、入れる先の資料の名前に
  読み手が付けた段落として、ほかの段落と合わせてから行を作る（kouho_ni_ireru）。出さない扱いは置かない。
  表に無い候補の名前があれば止まる。
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

TAIO_DIR = os.path.join(inputs.ROOT, "taio")
YOMI_HEAD = "yomi-"          # 読み取りの結果の保存先は taio/yomi-<テーマ>/
BUNYA = "bunya"              # taio/yomi-bunya/ は、一般質問の題に総合計画の分野を付けた読み取り（tools/bunya.py。SCHEMA.md 7.11）で、テーマではない
KENSHO = "kensho"            # taio/yomi-kensho/ は、施策検証シートの読み取り（tools/kensho.py。SCHEMA.md 7.12）で、テーマではない
KISAI = "kisai"              # taio/yomi-kisai/ は、資料の段落の読み取り（tools/kisai.py。SCHEMA.md 7.13）で、テーマではない
YOSAN = "yosan"              # taio/yomi-yosan/ は、予算の事業の読み取り（tools/yosan.py。SCHEMA.md 7.16）で、テーマではない
PATH = os.path.join(inputs.ROOT, "taio", "shudai.tsv")
NAMAE_PATH = os.path.join(inputs.ROOT, "teigi", "konkyo-namae.tsv")
KOUHO_PATH = os.path.join(inputs.ROOT, "teigi", "kouho.tsv")
KOUHO_COLS = ["theme", "namae", "atsukai", "saki", "chu"]
JIKO_NI, SHIRYO_NI = "事項に入れる", "資料を取り上げた部分にする"
ATSUKAI = (JIKO_NI, SHIRYO_NI)       # 出さない扱いは置かない（SCHEMA.md 7.10。2026-11-28）
COLS = ["question", "n", "theme", "jiko", "hani", "yomi", "chu"]
NAMAE_COLS = ["theme", "namae", "shu", "id", "setsumei", "kohyo", "betsumei", "chu"]
CHU_COLS = ["question", "chu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
SHIRYO, DEKIGOTO = "資料", "出来事"
FILE_COLS = {"shudai": ["question", "point", "hani", "mayoi", "riyu"],
             "konkyo": ["question", "aite", "hani"],
             "kouho": ["question", "hani", "namae"]}
# 総合計画の分野の読み取り（taio/yomi-b<分野の番号>/。SCHEMA.md 7.10。2026-11-28）の読み手のファイルは、題の番号の列 n を持つ
FILE_COLS_BUNYA = {k: v[:1] + ["n"] + v[1:] for k, v in FILE_COLS.items()}


class YomiError(ValueError):
    """読み取りの結果のファイルが無いか、形が違う。"""


def yomi_dir(theme):
    """テーマの読み取りの結果の保存先（taio/yomi-<テーマ>/）。"""
    return os.path.join(TAIO_DIR, YOMI_HEAD + theme)


def taba_path(theme):
    return os.path.join(yomi_dir(theme), "taba.json")


def themes(jiko_rows=None):
    """読み取りの結果があるテーマの並び。事項の表でテーマが最初に出る順。事項の表に無いテーマの保存先があれば YomiError。"""
    jiko_rows = jiko.read() if jiko_rows is None else jiko_rows
    jun = jiko.theme_jun(jiko_rows)
    ths = sorted(d[len(YOMI_HEAD):] for d in os.listdir(TAIO_DIR)
                 if d.startswith(YOMI_HEAD) and os.path.isdir(os.path.join(TAIO_DIR, d))
                 and d not in (YOMI_HEAD + BUNYA, YOMI_HEAD + KENSHO, YOMI_HEAD + KISAI, YOMI_HEAD + YOSAN))
    bad = [t for t in ths if t not in jun]
    if bad:
        raise YomiError(f"読み取りの結果の保存先のテーマが、事項の表に無い（{'、'.join(bad)}）")
    return sorted(ths, key=jun.index)


def read_taba(path):
    """束の並び → 束ごとの、(質問の ID（iq:<sid>）, 題の番号) の並び。テーマの読み取りの束（sid の並び）の題の番号は空。
    分野の読み取りの束（SCHEMA.md 7.10。2026-11-28）は、question（iq:<sid>）と n（題の番号）の並び。"""
    with open(path, encoding="utf-8") as f:
        taba = json.load(f)
    return [[(x["question"], x["n"]) if isinstance(x, dict) else (f"iq:{x}", "") for x in t] for t in taba]


def dai(theme):
    """読んだ (質問, 題の番号) の並び（束の順）。テーマの読み取りの題の番号は空。"""
    return [k for t in read_taba(taba_path(theme)) for k in t]


def shitsumon(theme=None):
    """読んだ質問の ID の並び（束の順。重ねない）。theme が None なら、全部のテーマ（テーマの順）。"""
    ths = themes() if theme is None else [theme]
    return list(dict.fromkeys(q for th in ths for q, _ in dai(th)))


def shitsumon_theme():
    """読んだ質問 → 読んだテーマの並び（テーマの順）。1つの質問を、2つ以上のテーマで読むことがある（テーマごとの決まりで
    読むため。SCHEMA.md 7.10。2026-11-28）。1つのテーマの束に、同じ質問（分野の読み取りは、同じ質問と題の番号）が2回あれば
    YomiError。"""
    out = {}
    for th in themes():
        seen = set()
        for k in dai(th):
            if k in seen:
                raise YomiError(f"質問 {k[0]}（題の番号 {k[1] or 'なし'}）が、テーマ {th} の束に2回ある")
            seen.add(k)
            if th not in out.get(k[0], []):
                out.setdefault(k[0], []).append(th)
    return out


def read_chu(theme):
    """taio/yomi-<テーマ>/chu.tsv → 質問 → 注。ファイルが無ければ空。読んだ質問に無い質問の行があれば YomiError。"""
    path = os.path.join(yomi_dir(theme), "chu.tsv")
    if not os.path.exists(path):
        return {}
    rows = _read(path, CHU_COLS)
    qs = set(shitsumon(theme))
    bad = [r["question"] for r in rows if r["question"] not in qs or not r["chu"]]
    if bad:
        raise YomiError(f"{os.path.relpath(path, inputs.ROOT)}：読んだ質問に無いか、chu が空（{'、'.join(bad)}）")
    return {r["question"]: r["chu"] for r in rows}


def _read(path, cols):
    if not os.path.exists(path):
        raise YomiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != cols:
            raise YomiError(f"{os.path.relpath(path, inputs.ROOT)} の列が違う（{rd.fieldnames}）")
        return list(rd)


def read_yomi(yomi_dir, taba_path, bunya=False):
    """→ {種類: [行（読み手 yomite を付けたもの）]}。束の外の質問（分野の読み取りは、質問と題の番号）の行があれば YomiError。
    bunya が真なら、分野の読み取りの読み手のファイル（列 n がある）を読む。行の n は、テーマの読み取りでは空。"""
    out = {k: [] for k in FILE_COLS}
    bad = []
    fcols = FILE_COLS_BUNYA if bunya else FILE_COLS
    for n, qs in enumerate(read_taba(taba_path)):
        qs = set(qs)
        for y in YOMITE:
            for k, cols in fcols.items():
                for i, r in enumerate(_read(os.path.join(yomi_dir, f"{y}-{n}-{k}.tsv"), cols), 2):
                    r = dict(r, n=r.get("n", ""))
                    if (r["question"], r["n"]) not in qs:
                        bad.append(f"{y}-{n}-{k}.tsv {i} 行目：質問 {r['question']}（題の番号 {r['n'] or 'なし'}）が束 {n} に無い")
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
    """読み手の行 → 組（質問, 題の番号, 相手）ごとの、一致の行と、読み手ごとの1回だけの行。col は相手の列、key_of は
    (相手, 質問) → 表の字。題の番号は、分野の読み取りの行だけにある（テーマの読み取りは空）。
    → [(question, n, 相手の字, hani, yomi, 読み手の字, 迷いの読み手, 候補から入れた読み手)]"""
    paras, mayoi, kouho_ps = {}, {}, {}
    for r in rows:
        k = (r["question"], r.get("n", ""), key_of(r[col], r["question"]))
        ps = set(keys.paras_of(r["hani"]))
        paras.setdefault(k, {y: set() for y in YOMITE})[r["yomite"]] |= ps
        if r.get("mayoi", "").strip() == "1":
            mayoi.setdefault(k, set()).add(r["yomite"])
        if r.get("kouho"):
            kouho_ps.setdefault(k, {y: set() for y in YOMITE})[r["yomite"]] |= ps
    out = []
    for (q, n, a), ps in paras.items():
        m = "、".join(sorted(mayoi.get((q, n, a), ())))
        ko = kouho_ps.get((q, n, a), {y: set() for y in YOMITE})

        def kw(gyo):
            return "、".join(y for y in YOMITE if ko[y] & gyo)
        both = ps["a"] & ps["b"]
        if both:
            out.append((q, n, a, matomeru(both), ICCHI, "", m, kw(both)))
        for y in YOMITE:
            only = ps[y] - ps[[x for x in YOMITE if x != y][0]]
            if only:
                out.append((q, n, a, matomeru(only), IKKAI, y, m, kw(only)))
    return out


def yomi_awase(mae, ato):
    """同じ質問と相手（事項か、資料と出来事）の、同じ段落に、2つのテーマの読み取りの行があるとき（SCHEMA.md 7.10）、
    出す yomi。どちらかが「一致」なら「一致」（そのテーマの2回の読みが一致した段落のため）。ほかは ato。mae が None なら ato。"""
    return ICCHI if ICCHI in (mae, ato) else ato


def futatsu(rows, col):
    """→ 2つ以上のテーマの読み取りの行がある、質問と相手（col の列）の組の並び。"""
    kumi = {}
    for r in rows:
        kumi.setdefault((r["question"], r[col]), set()).add(r["theme"])
    return sorted(k for k, ths in kumi.items() if len(ths) > 1)


def chu_of(yomite, mayoi, kouho="", tsuki=""):
    """chu の字。tsuki は、その質問の読み取りについての注（taio/yomi-<テーマ>/chu.tsv）。"""
    out = []
    if yomite:
        out.append(f"読み手 {yomite} だけが付けた")
    if mayoi:
        out.append(f"迷いの印：読み手 {mayoi}")
    if kouho:
        out.append(f"候補の名前から入れた段落がある：読み手 {kouho}")
    if tsuki:
        out.append(tsuki)
    return "。".join(out)


def read_kouho(path=KOUHO_PATH):
    """候補の名前と扱いの対応の表 → 行の並び（全部のテーマ）。"""
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), KOUHO_COLS)


def of_theme(rows, theme):
    """表の行のうち、theme の列がそのテーマの行（候補の表と名前の表。事項の表は jiko.of_theme）。"""
    return [r for r in rows if r["theme"] == theme]


def check_kouho(rows, yomi, jiko_ids, namae_rows):
    """候補の名前と扱いの対応の表の、1つのテーマの行の検査（SCHEMA.md 7.10）→ 問題の並び。rows・jiko_ids・namae_rows は
    そのテーマの行、yomi はそのテーマの読み取りの結果。namae が重ならず、atsukai が2つのどちらかで、saki が atsukai に合い、
    読み取りの結果の候補の名前の全部に行があり、読み取りの結果に無い名前の行が無いこと（出さない候補を作らない）。"""
    bad = []
    shiryo = {r["namae"] for r in namae_rows if r["shu"] == SHIRYO}
    seen = set()
    for i, r in enumerate(rows, 2):
        if r["namae"] in seen or not r["namae"]:
            bad.append(f"{i} 行目：namae が重なっているか空（{r['namae']}）")
        seen.add(r["namae"])
        a, s = r["atsukai"], r["saki"]
        if a not in ATSUKAI:
            bad.append(f"{i} 行目：atsukai が {ATSUKAI} のどれでもない（{a}）")
        elif a == JIKO_NI and s not in jiko_ids:
            bad.append(f"{i} 行目：saki が事項の表の id に無い（{s}）")
        elif a == SHIRYO_NI and s not in shiryo:
            bad.append(f"{i} 行目：saki が資料と出来事の名前の表の資料の名前に無い（{s}）")
    yn = {r["namae"] for r in yomi["kouho"]}
    bad += [f"候補の名前「{n}」が、候補の名前と扱いの対応の表に無い" for n in sorted(yn - seen)]
    bad += [f"候補の名前と扱いの対応の表の「{n}」が、読み取りの結果に無い" for n in sorted(seen - yn)]
    return bad


def kouho_ni_ireru(yomi, kouho_rows, jiko_rows):
    """候補の段落を、扱いに従って、読み手の shudai と konkyo の行に足した読み取りの結果を返す（SCHEMA.md 7.10）。
    足した行には kouho（候補の名前）を付ける。"""
    jname = {r["id"]: r["name"] for r in jiko_rows}
    at = {r["namae"]: r for r in kouho_rows}
    out = {k: list(v) for k, v in yomi.items()}
    for r in yomi["kouho"]:
        x = at[r["namae"]]
        base = dict(question=r["question"], n=r.get("n", ""), hani=r["hani"], yomite=r["yomite"], taba=r["taba"],
                    kouho=r["namae"])
        if x["atsukai"] == JIKO_NI:
            out["shudai"].append(dict(base, point=jname[x["saki"]], mayoi="", riyu=""))
        elif x["atsukai"] == SHIRYO_NI:
            out["konkyo"].append(dict(base, aite=x["saki"]))
    return out


def yomi_ireta(theme, jiko_rows=None, namae_rows=None):
    """テーマの読み取りの結果を読み、候補の名前と扱いの対応の表のそのテーマの行を検査してから、候補の段落を入れた結果を返す。
    → (読み取りの結果, そのテーマの候補の行)。合わなければ YomiError。jiko_rows と namae_rows は全部のテーマの行でよい。"""
    yomi = read_yomi(yomi_dir(theme), taba_path(theme), jiko.is_bunya(theme))
    jiko_rows = jiko.of_theme(jiko.read() if jiko_rows is None else jiko_rows, theme)
    namae_rows = of_theme(read_namae() if namae_rows is None else namae_rows, theme)
    kr = of_theme(read_kouho(), theme)
    bad = check_kouho(kr, yomi, {r["id"] for r in jiko_rows}, namae_rows)
    if bad:
        raise YomiError(f"候補の名前と扱いの対応の表（{theme}）：{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return kouho_ni_ireru(yomi, kr, jiko_rows), kr


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


def namae_of(r):
    """名前の表の行の、namae と betsumei（「;」で区切った別の字）の並び。"""
    return [r["namae"]] + [x for x in r.get("betsumei", "").split(";") if x]


def check_namae(rows, bunsho, hiduke=None):
    """資料と出来事の名前の表の検査 → 問題の並び。theme が空でなく、shu が2つのどちらかで、資料の id は資料の一覧の表にあり、
    出来事の id は空でなく ID の形（英小文字・数字・ハイフン）で、出来事の id がテーマをまたいで重ならず、資料の id が
    同じテーマの中で重ならないこと。同じテーマの中で namae が重なるのは、どれも shu が資料で id があり、setsumei と
    betsumei が同じで、資料の日付が違う行だけ（版ごとの行）。betsumei の字は、同じテーマのほかの名前（namae と betsumei）と
    重ならないこと。hiduke（資料の ID → 資料の一覧の表の hiduke）を渡したときは、資料の id のある行に、hiduke か kohyo の
    片方だけに日付があることも確認する。"""
    import re
    bad = []
    by = {}
    for i, r in enumerate(rows, 2):
        if not r["namae"] or not r["theme"]:
            bad.append(f"{i} 行目：theme か namae が空")
        by.setdefault((r["theme"], r["namae"]), []).append(r)
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
    for (th, n), rs in by.items():
        if len(rs) < 2:
            continue
        if (any(not (r["shu"] == SHIRYO and r["id"]) for r in rs) or len({r["setsumei"] for r in rs}) > 1
                or len({r.get("betsumei", "") for r in rs}) > 1):
            bad.append(f"namae が重なっている行が、どれも資料の id のある行で setsumei と betsumei が同じ、になっていない（{th} {n}）")
        elif hiduke is not None:
            his = [hi_of(shiryo_hi(r, hiduke)) for r in rs]
            if len(set(his)) < len(his):
                bad.append(f"namae が重なっている行に、資料の日付が同じ行がある（{th} {n}）")
    for th in dict.fromkeys(r["theme"] for r in rows):
        moji = {}
        for (t, n), rs in by.items():
            if t == th:
                for x in namae_of(rs[0]):
                    moji.setdefault(x, set()).add(n)
        bad += [f"名前の字「{x}」が、同じテーマ（{th}）の2つの名前（{'、'.join(sorted(ns))}）にある"
                for x, ns in moji.items() if len(ns) > 1]
        ids = [r["id"] for r in rows if r["theme"] == th and r["shu"] == SHIRYO and r["id"]]
        bad += [f"資料の id が、同じテーマ（{th}）の中で重なっている（{x}）" for x in sorted({x for x in ids if ids.count(x) > 1})]
    ev = [r["id"] for r in rows if r["shu"] == DEKIGOTO and r["id"]]
    bad += [f"出来事の id が重なっている（{x}）" for x in sorted({x for x in ev if ev.count(x) > 1})]
    return bad


def q_hi(q):
    """質問の ID → 質問の日（質問の ID の発言の日。YYYY-MM-DD）。"""
    return keys.sid_date(keys.sid_of(q))


def aite_of(namae_rows, hiduke=None):
    """(名前, 質問) → konkyo.tsv の aite の字。namae_rows は1つのテーマの行。名前の表の betsumei の字は namae に直す。
    資料の ID がある名前は、その名前の資料のうち、資料の日付が質問の日より前か同じ日のもので、いちばん新しい資料の ID。
    当たる資料が無い名前と、ほかの名前は、名前のまま（SCHEMA.md 7.10）。
    hiduke は、資料の ID → 資料の一覧の表の hiduke（None なら読む）。"""
    if hiduke is None:
        import konkyo
        hiduke = konkyo.bunsho_hiduke()
    to, naosu = {}, {}
    for r in namae_rows:
        for x in namae_of(r):
            naosu[x] = r["namae"]
        if r["shu"] == SHIRYO and r["id"]:
            to.setdefault(r["namae"], []).append((hi_of(shiryo_hi(r, hiduke)), r["id"]))

    def f(n, q):
        n = naosu.get(n, n)
        qh = q_hi(q)
        mae = sorted(x for x in to.get(n, []) if x[0] <= qh)
        return mae[-1][1] if mae else n
    return f


def shudai_rows(yomi, jiko_rows, tsuki=None, theme=""):
    """→ (taio/shudai.tsv の行, 問題の並び)。jiko_rows は1つのテーマの行。事項の名前がそのテーマの事項の表に無ければ問題。
    tsuki は、質問 → 読み取りについての注（read_chu）。theme は、読んだテーマ（行の theme）。"""
    tsuki = tsuki or {}
    by = {r["name"]: r["id"] for r in jiko_rows}
    jun = {r["id"]: i for i, r in enumerate(jiko_rows)}
    bad = sorted({f"事項の名前「{r['point']}」が事項の表に無い（{r['yomite']}-{r['taba']}）"
                  for r in yomi["shudai"] if r["point"] not in by})
    if bad:
        return [], bad
    rows = [dict(question=q, n=n, theme=theme, jiko=a, hani=h, yomi=y, chu=chu_of(w, m, k, tsuki.get(q, "")))
            for q, n, a, h, y, w, m, k in kumi_gyo(yomi["shudai"], "point", lambda x, q: by.get(x))]
    rows.sort(key=lambda r: (r["question"], _n(r["n"]), jun[r["jiko"]], YOMI.index(r["yomi"]), r["chu"]))
    return rows, []


def konkyo_rows(yomi, namae_rows, hiduke=None, theme="", tsuki=None):
    """→ taio/konkyo.tsv の、1つのテーマの読み取りの行（tools/konkyo.py が、入力の確定済みの行と合わせて表にする）。
    namae_rows は、そのテーマの名前の表の行。"""
    tsuki = tsuki or {}
    rows = [dict(question=q, n=n, theme=theme, aite=a, hani=h, yomi=y, chu=chu_of(w, m, k, tsuki.get(q, "")))
            for q, n, a, h, y, w, m, k in kumi_gyo(yomi["konkyo"], "aite", aite_of(namae_rows, hiduke))]
    return rows


def _n(n):
    """題の番号の並べ方（空はいちばん前。数は数の順）。"""
    return (0, 0) if not n else (1, int(n))


def kouho(yomi):
    """候補の名前 → (段落の数（2人の読み手の段落を合わせた数）, 読み手の字)。名前の順。"""
    out = {}
    for r in yomi["kouho"]:
        ps, ys = out.setdefault(r["namae"], (set(), set()))
        ps |= set(keys.paras_of(r["hani"]))
        ys.add(r["yomite"])
    return {n: (len(ps), "、".join(sorted(ys))) for n, (ps, ys) in sorted(out.items())}


def check(inp, rows, questions, jiko_ids):
    """taio/shudai.tsv の行の検査（SCHEMA.md 7.10）→ 問題の並び。question が、行の theme のテーマで読んだ質問にあり、
    発言があること、jiko が事項の表にあること、yomi が決めた字であること、hani の段落が発言にあること。
    questions は、読んだ質問 → 読んだテーマの並び。jiko_ids は、事項の ID → テーマの並び。jiko のテーマに、行の theme が
    あること（事項の theme の列には、テーマを2つ書ける。SCHEMA.md 7.9）。"""
    bad = []
    for i, r in enumerate(rows, 2):
        if r["theme"] not in questions.get(r["question"], []):
            bad.append(f"{i} 行目：question が、テーマ {r['theme']} で読んだ質問（taio/yomi-<テーマ>/taba.json）に無い"
                       f"（{r['question']}）")
        elif inp.statement_text(keys.sid_of(r["question"])) is None:
            bad.append(f"{i} 行目：question の発言が会議録に無い（{r['question']}）")
        if r["jiko"] not in jiko_ids:
            bad.append(f"{i} 行目：jiko が事項の表に無い（{r['jiko']}）")
        elif r["theme"] not in jiko_ids[r["jiko"]]:
            bad.append(f"{i} 行目：jiko のテーマ（{','.join(jiko_ids[r['jiko']])}）に、行の theme（{r['theme']}）が無い")
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


def nashi_dai(theme, rows=None):
    """分野の読み取りで読んだ題（質問と題の番号）のうち、質問と事項の対応の表に、そのテーマで読んだ行が無い題（どの論点に
    関する部分も付かなかった題）。rows は taio/shudai.tsv の行（None なら読む）。"""
    rows = read() if rows is None else rows
    aru = {(r["question"], r["n"]) for r in rows if r["theme"] == theme}
    return [k for k in dai(theme) if k not in aru]


def nashi_shitsumon(theme, rows=None, jiko_rows=None):
    """そのテーマで読んだ質問のうち、質問と事項の対応の表に、そのテーマで読んだ行が無い質問（読んだが、当たる論点が
    無かった質問。SKILL.md 4.4 の G5）。rows は taio/shudai.tsv の行（None なら読む）。jiko_rows は使わない（呼ぶ側を変えないために残している）。"""
    rows = read() if rows is None else rows
    aru = {r["question"] for r in rows if r["theme"] == theme}
    return [q for q in shitsumon(theme) if q not in aru]


def main(argv=None):
    p = argparse.ArgumentParser(description="生成AIの2回の読み取りの結果から、質問と事項の対応の表を作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    import konkyo
    try:
        inp = inputs.Inputs()
        jiko_rows = jiko.read()
        namae = read_namae()
        hiduke = konkyo.bunsho_hiduke()
        bunsho = set(hiduke)
        ths = themes(jiko_rows)
        qth = shitsumon_theme()
        per = {}
        for th in ths:
            per[th] = yomi_ireta(th, jiko_rows, namae) + (read_chu(th),)
    except (inputs.InputError, YomiError, ValueError, OSError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    rows, bad = [], []
    for th in ths:
        r, b = shudai_rows(per[th][0], jiko.of_theme(jiko_rows, th), per[th][2], th)
        rows += r
        bad += [f"{th}：{x}" for x in b]
    bad += check_namae(namae, bunsho, hiduke)
    if not bad:
        bad += check(inp, rows, qth, {r["id"]: jiko.themes_of(r) for r in jiko_rows})
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    for th in ths:
        yomi, kouho_rows, tsuki = per[th]
        trows = [r for r in rows if r["theme"] == th]
        nm = of_theme(namae, th)
        kr = konkyo_rows(yomi, nm, hiduke, th, tsuki)
        shu = {x: r for r in nm for x in namae_of(r)}
        dasanai = {}
        for r in kr:
            if r["aite"] in bunsho:
                continue
            x = shu.get(r["aite"])
            why = ("出来事" if x and x["shu"] == DEKIGOTO else
                   "資料の日付が質問の日より後か、資料の ID が無い名前（" + r["aite"] + "）" if x
                   else "資料と出来事の名前の表に無い名前（" + r["aite"] + "）")
            dasanai[why] = dasanai.get(why, 0) + 1
        n = {y: sum(r["yomi"] == y for r in trows) for y in YOMI}
        nk = {y: sum(r["yomi"] == y for r in kr) for y in YOMI}
        if jiko.is_bunya(th):
            nd = nashi_dai(th, rows)
            print(f"[{th}] 読んだ題 {len(dai(th))}（質問 {len(shitsumon(th))}。どの論点に関する部分も付かなかった題 {len(nd)}）")
            dasanai = {k.split("（")[0]: sum(v for kk, v in dasanai.items() if kk.split("（")[0] == k.split("（")[0])
                       for k in dasanai}
        else:
            nashi = nashi_shitsumon(th, rows, jiko_rows)
            print(f"[{th}] 読んだ質問 {len(shitsumon(th))}（当たる論点が無かった質問 {len(nashi)}"
                  + (f"：{'、'.join(nashi)}" if nashi else "") + "）")
        print(f"[{th}] 質問と事項の対応 {len(trows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）。"
              f"質問 {len({r['question'] for r in trows})}、事項 {len({r['jiko'] for r in trows})}")
        print(f"[{th}] 質問が取り上げた資料と出来事の、読み取りの行 {len(kr)}（一致 {nk[ICCHI]}、1回だけ {nk[IKKAI]}）")
        for why, c in sorted(dasanai.items(), key=lambda x: (-x[1], x[0])):
            print(f"  資料の ID でない行：{why} {c}")
        ko = kouho(yomi)
        at = {r["namae"]: r["atsukai"] for r in kouho_rows}
        print(f"[{th}] 候補（事項の表に無い話題）{len(ko)}：" + "、".join(f"{x} {sum(at[k] == x for k in ko)}" for x in ATSUKAI))
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    print(f"質問と事項の対応 {len(rows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）")
    f2 = futatsu(rows, "jiko")
    print(f"2つのテーマの読み取りの行がある、質問と事項の組 {len(f2)}" + (f"：{'、'.join(f'{q} / {j}' for q, j in f2)}" if f2 else ""))
    if a.kensa:
        moto = None
        if os.path.exists(PATH):
            with open(PATH, encoding="utf-8") as f:
                moto = f.read()
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
