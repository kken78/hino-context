"""生成AIの2回の読み取りの結果（taio/yomi-kisai/）から、資料の段落と事項の対応の表（taio/kisai.tsv）を作る（SCHEMA.md 7.13）。

使い方：
  python3 -B tools/kisai.py            taio/kisai.tsv を作る
  python3 -B tools/kisai.py --kensa    作り直した行が taio/kisai.tsv と同じかを確認する（違えば終了コード 1。書き換えない）
  python3 -B tools/kisai.py --kouho    候補（kouho）の名前ごとに、資料のページと段落と読み手を出す（表には行を作らない）

読むもの（taio/yomi-kisai/）：
  taba.json          読んだページの並び（ページごとに shiryo、danraku（段落の数）、sha256（段落の字を改行でつないだもの））
  <読み手>-kisai.tsv 列 shiryo、hani、point、kouho、mayoi、riyu（読み手は a と b）
teigi/kisai-kouho.tsv（資料の段落の候補の名前と扱いの対応の表）で、候補の段落を、入れる先の事項の段落として合わせる。

行を作る決まり（SCHEMA.md 7.13）：
  資料のページと事項の組ごとに、段落を1つずつに分け、2回とも付けた段落を yomi「一致」の行に、片方だけが付けた段落を、
  読み手ごとに yomi「1回だけ」の行にする。段落は番号の順に並べ、続いた段落は範囲にまとめる。事項は、事項の表
  （teigi/jiko.tsv）の、読んだテーマ（THEME）の行の name から ID を引く。手で行を書かない。
段落は、町の資料は hino-town-docs の data/text_raw のページを danraku で分け、第6次日野町総合計画（pt:sogo6）は
sogo6.json の、出典が1ページのブロックの字から sogo6_danraku で作る。読み手に渡した段落と同じであることを、
taba.json の段落の数と sha256 で確認する。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import jiko  # noqa: E402

YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi-kisai")
PATH = os.path.join(inputs.ROOT, "taio", "kisai.tsv")
KOUHO_PATH = os.path.join(inputs.ROOT, "teigi", "kisai-kouho.tsv")
KOUHO_COLS = ["theme", "namae", "atsukai", "saki", "chu"]
JIKO_NI = "事項に入れる"
COLS = ["shiryo", "theme", "jiko", "hani", "yomi", "chu"]
FILE_COLS = ["shiryo", "hani", "point", "kouho", "mayoi", "riyu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
THEME = "b33"                 # 2026-11-28 の読み取りで読んだテーマ（分野㉝行政運営）
SOGO6 = "sogo6"
RE_SHIRYO = re.compile(r"^(doc:([a-z0-9-]+)|pt:([a-z0-9-]+)/([a-z0-9-]+))/([0-9]+)$")
RE_HANI = re.compile(r"^([0-9]+)(?:-([0-9]+))?$")

# 段落の決め方（SCHEMA.md 7.13）
SHIRUSHI = re.compile(r"^(?:[○〇◯●◎□■◆※≪《【]|・\S|[①-⑳]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]|[（(][0-9０-９]+[）)]|[0-9０-９]+[．.、 　]\S)")
TOJI = "」』》）)】≫"
HIRAKI = "「『《（(【≪"

# 段落の字を確認した記録（「人が PDF で確認」か「生成AIが画像を2回読んで一致」）がある段落（SCHEMA.md 7.13）。
# 記録の持ち方は、記録を作るときに決める。いまは無いので、第6次日野町総合計画の段落の行は出さない
KAKUNIN = {}


class KisaiError(ValueError):
    """読み取りの結果のファイルが無いか、形が違う。"""


def _owari_maru(l):
    s = l.rstrip()
    while s and s[-1] in TOJI:
        s = s[:-1]
    return s.endswith("。")


def _tojite(s):
    n = 0
    for c in s:
        if c in HIRAKI:
            n += 1
        elif c in TOJI:
            n -= 1
    return n <= 0


def danraku(page):
    """町の資料のページの文字（data/text_raw の1ページ）→ 段落の字の並び（SCHEMA.md 7.13 の段落の決まり）。"""
    lines = [l.rstrip() for l in page.split("\n") if l.strip()]
    if lines and re.fullmatch(r"[0-9]+", unicodedata.normalize("NFKC", lines[0]).strip()):
        lines = lines[1:]
    out = []
    for l in lines:
        if not out:
            out.append([l])
            continue
        cur = out[-1]
        prev = cur[-1]
        ji = "".join(cur)
        tojite = _tojite(ji)
        midashi = SHIRUSHI.match(cur[0]) and "。" not in ji and not prev.endswith("、") and tojite
        if (_owari_maru(prev) and tojite) or SHIRUSHI.match(l) or midashi:
            out.append([l])
        else:
            cur.append(l)
    return ["".join(d) for d in out]


def sogo6_danraku(plan, file, page):
    """第6次日野町総合計画（sogo6.json）の、出典が「<file> p.<page>」のブロックの字 → 段落の字の並び（SCHEMA.md 7.13）。"""
    src = f"{file} p.{page}"
    out = []
    for tab in plan["tabs"]:
        for b in tab["blocks"]:
            if b.get("source") != src:
                continue
            t = b["type"]
            if t == "programs":
                for g in b["groups"]:
                    for sg in g.get("subgroups", []):
                        for it in sg.get("items", []):
                            out.append(f"{it['no']} {it['name']}")
                            out += [x for x in it.get("desc", "").split("\n") if x.strip()]
                        for ib in sg.get("intro", []):
                            out += [ib["h"], ib["b"]]
            elif t == "narrative":
                out += [x for x in b["text"].split("\n") if x.strip()]
            elif t == "bullets":
                out += list(b["items"])
            elif t == "aims":
                for it in b["items"]:
                    out.append(f"{it['no']} {it['title']}")
                    if it.get("desc"):
                        out.append(it["desc"])
    return out


def page_of(shiryo):
    """資料のページの ID → ページの番号。"""
    return int(RE_SHIRYO.match(shiryo).group(5))


def bunsho_of(shiryo):
    """資料のページの ID → 資料の一覧の表の資料の ID（pt:sogo6 のページは plan:sogo6）。形が違えば None。"""
    m = RE_SHIRYO.match(shiryo)
    if not m:
        return None
    if m.group(2):
        return f"doc:{m.group(2)}"
    return f"plan:{SOGO6}" if m.group(3) == SOGO6 else f"pt:{m.group(3)}/{m.group(4)}"


_CACHE = {}


def page_danraku(inp, shiryo):
    """資料のページの ID → 段落の字の並び。ページか文字が無ければ None。入力ごとに覚えておく。"""
    k = (id(inp), shiryo)
    if k not in _CACHE:
        _CACHE[k] = _page_danraku(inp, shiryo)
    return _CACHE[k]


def _page_danraku(inp, shiryo):
    m = RE_SHIRYO.match(shiryo)
    if not m:
        return None
    p = int(m.group(5))
    if m.group(2):
        t = inp.doc_text(m.group(2), "text_raw")
    elif m.group(3) == SOGO6:
        plan = inp.plan(SOGO6)
        return (sogo6_danraku(plan, m.group(4), p) or None) if plan else None
    else:
        t = inp.pt_text(m.group(3), m.group(4), "text_raw")
    if t is None:
        return None
    pages = t.split("\f")
    if not 1 <= p <= len(pages) or not pages[p - 1].strip():
        return None
    return danraku(pages[p - 1])


def sha(paras):
    return hashlib.sha256("\n".join(paras).encode("utf-8")).hexdigest()


def kakunin_ari(shiryo):
    """段落の字を、出してよいか（SCHEMA.md 7.13）。町の資料と、文字が字になっている計画は、もとの資料の文字なので出す。
    第6次日野町総合計画は、字を確認した記録があるページだけ。"""
    return not shiryo.startswith(f"pt:{SOGO6}/") or shiryo in KAKUNIN


def bangou(hani):
    """hani の字 → 段落の番号の並び（番号の順）。形が違えば KisaiError。"""
    out = set()
    for part in hani.split(","):
        m = RE_HANI.match(part)
        if not m:
            raise KisaiError(f"hani の形が違う（{hani}）")
        a, z = int(m.group(1)), int(m.group(2) or m.group(1))
        if z < a:
            raise KisaiError(f"hani の範囲が逆（{hani}）")
        out.update(range(a, z + 1))
    return sorted(out)


def matomeru(ns):
    """段落の番号の集まり → 「3-5,8」の字。"""
    out = []
    for i in sorted(ns):
        if out and out[-1][1] == i - 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return ",".join(str(a) if a == z else f"{a}-{z}" for a, z in out)


def hanchi(hani):
    """hani の字 → 続いた段落の範囲 (始め, 終わり) の並び。"""
    out = []
    for i in bangou(hani):
        if out and out[-1][1] == i - 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(x) for x in out]


def read_taba(path=None):
    path = path or os.path.join(YOMI_DIR, "taba.json")
    if not os.path.exists(path):
        raise KisaiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_yomi(yomi_dir=None):
    """読み手のファイル → 行（読み手 yomite を付けたもの）の並び。列が違えば KisaiError。"""
    yomi_dir = yomi_dir or YOMI_DIR
    out = []
    for y in YOMITE:
        path = os.path.join(yomi_dir, f"{y}-kisai.tsv")
        if not os.path.exists(path):
            raise KisaiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
        with open(path, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f, delimiter="\t")
            if rd.fieldnames != FILE_COLS:
                raise KisaiError(f"{y}-kisai.tsv の列が違う（{rd.fieldnames}）")
            out += [dict(r, yomite=y, gyo=i) for i, r in enumerate(rd, 2)]
    return out


def check_taba(inp, taba):
    """taba.json のページごとに、段落を作り直し、数と sha256 が同じかを確認する → 問題の並び。"""
    bad = []
    for t in taba:
        ps = page_danraku(inp, t["shiryo"])
        if ps is None:
            bad.append(f"taba.json：{t['shiryo']} のページか文字が、入力に無い")
        elif len(ps) != t["danraku"] or sha(ps) != t["sha256"]:
            bad.append(f"taba.json：{t['shiryo']} の段落が、読み手に渡したものと違う（数 {t['danraku']} → {len(ps)}）")
    return bad


def check_yomi(yomi, taba, names):
    """読み手の行の検査 → 問題の並び。names は、読んだテーマの事項の name の集まり。"""
    pages = {t["shiryo"]: t["danraku"] for t in taba}
    bad = []
    seen = set()
    for r in yomi:
        w = f"{r['yomite']}-kisai.tsv {r['gyo']} 行目"
        if r["shiryo"] not in pages:
            bad.append(f"{w}：shiryo が taba.json に無い（{r['shiryo']}）")
            continue
        p, k = r["point"].strip(), r["kouho"].strip()
        if bool(p) == bool(k):
            bad.append(f"{w}：point と kouho のちょうど1つが空でない、になっていない")
        if p and r["point"] not in names:
            bad.append(f"{w}：point が事項の表の {THEME} の行の name に無い（{r['point']}）")
        if r["mayoi"] not in ("", "1"):
            bad.append(f"{w}：mayoi が空か 1 でない")
        key = (r["yomite"], r["shiryo"], p, k)
        if key in seen:
            bad.append(f"{w}：同じ読み手、ページ、論点（候補）の行が2つある")
        seen.add(key)
        try:
            ns = bangou(r["hani"])
        except KisaiError as e:
            bad.append(f"{w}：{e}")
            continue
        if not ns or ns[0] < 1 or ns[-1] > pages[r["shiryo"]]:
            bad.append(f"{w}：{r['shiryo']} に無い段落がある（{r['hani']}）")
    return bad


def chu_of(yomite, mayoi, kouho=""):
    out = []
    if yomite:
        out.append(f"読み手 {yomite} だけが付けた")
    if mayoi:
        out.append(f"迷いの印：読み手 {mayoi}")
    if kouho:
        out.append(f"候補の名前から入れた段落がある：読み手 {kouho}")
    return "。".join(out)


def read_kouho(path=KOUHO_PATH):
    """資料の段落の候補の名前と扱いの対応の表（SCHEMA.md 7.13）の行。表が無ければ空。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), KOUHO_COLS)


def check_kouho(rows, yomi, jiko_ids):
    """資料の段落の候補の名前と扱いの対応の表の検査 → 問題の並び。jiko_ids は、THEME の事項の表の id の集まり。"""
    bad = []
    seen = set()
    for i, r in enumerate(rows, 2):
        w = f"teigi/kisai-kouho.tsv {i} 行目"
        if r["namae"] in seen or not r["namae"]:
            bad.append(f"{w}：namae が重なっているか空（{r['namae']}）")
        seen.add(r["namae"])
        if r["theme"] != THEME:
            bad.append(f"{w}：theme が {THEME} でない（{r['theme']}）")
        if r["atsukai"] != JIKO_NI:
            bad.append(f"{w}：atsukai が「{JIKO_NI}」でない（{r['atsukai']}）")
        elif r["saki"] not in jiko_ids:
            bad.append(f"{w}：saki が事項の表の {THEME} の行の id に無い（{r['saki']}）")
    yn = {r["kouho"].strip() for r in yomi if r["kouho"].strip()}
    bad += [f"候補の名前「{n}」が、teigi/kisai-kouho.tsv に無い" for n in sorted(yn - seen)]
    bad += [f"teigi/kisai-kouho.tsv の「{n}」が、読み取りの結果に無い" for n in sorted(seen - yn)]
    return bad


def make_rows(yomi, taba, jiko_rows, bunsho_jun, kouho_rows=()):
    """読み手の行 → 表の行（SCHEMA.md 7.13）。並びは、資料の一覧の表の順、ページの順、事項の表の順。
    候補の行は、資料の段落の候補の名前と扱いの対応の表（kouho_rows）の入れる先の事項に、読み手が付けた段落として合わせる。"""
    ids = {r["name"]: r["id"] for r in jiko.of_theme(jiko_rows, THEME)}
    saki = {r["namae"]: r["saki"] for r in kouho_rows}
    jiko_jun = [r["id"] for r in jiko_rows]
    paras, mayoi, kps = {}, {}, {}
    for r in yomi:
        if r["point"].strip():
            k = (r["shiryo"], ids[r["point"]])
        elif r["kouho"].strip() in saki:
            k = (r["shiryo"], saki[r["kouho"].strip()])
            kps.setdefault(k, {y: set() for y in YOMITE})[r["yomite"]] |= set(bangou(r["hani"]))
        else:
            continue
        paras.setdefault(k, {y: set() for y in YOMITE})[r["yomite"]] |= set(bangou(r["hani"]))
        if r["point"].strip() and r["mayoi"] == "1":
            mayoi.setdefault(k, set()).add(r["yomite"])
    out = []
    for (s, j), ps in paras.items():
        m = "、".join(sorted(mayoi.get((s, j), ())))
        ko = kps.get((s, j), {y: set() for y in YOMITE})

        def kw(gyo):
            return "、".join(y for y in YOMITE if ko[y] & gyo)
        both = ps["a"] & ps["b"]
        if both:
            out.append(dict(shiryo=s, theme=THEME, jiko=j, hani=matomeru(both), yomi=ICCHI, chu=chu_of("", m, kw(both))))
        for y in YOMITE:
            only = ps[y] - ps[[x for x in YOMITE if x != y][0]]
            if only:
                out.append(dict(shiryo=s, theme=THEME, jiko=j, hani=matomeru(only), yomi=IKKAI,
                                chu=chu_of(y, m, kw(only))))
    page_no = {t["shiryo"]: i for i, t in enumerate(taba)}

    def jun(r):
        b = bunsho_of(r["shiryo"])
        return (bunsho_jun.index(b) if b in bunsho_jun else len(bunsho_jun), page_no[r["shiryo"]],
                jiko_jun.index(r["jiko"]), YOMI.index(r["yomi"]), r["chu"])
    return sorted(out, key=jun)


def kouho(yomi):
    """候補の行 → 候補の名前ごとの、(読み手, ページ, 段落の範囲, 迷い, 理由) の並び（名前は、最初に出る順）。"""
    out = {}
    for r in yomi:
        if r["kouho"].strip():
            out.setdefault(r["kouho"].strip(), []).append((r["yomite"], r["shiryo"], r["hani"], r["mayoi"], r["riyu"]))
    return out


def check(inp, rows, jiko_rows, bunsho):
    """表の行の検査 → 問題の並び。"""
    bad = []
    themes = jiko.theme_jun(jiko_rows)
    by = {r["id"]: r for r in jiko_rows}
    for i, r in enumerate(rows, 2):
        w = f"taio/kisai.tsv {i} 行目"
        b = bunsho_of(r["shiryo"])
        if b is None or b not in bunsho:
            bad.append(f"{w}：shiryo の資料が、資料の一覧の表に無い（{r['shiryo']}）")
        if r["theme"] not in themes:
            bad.append(f"{w}：theme が事項の表のテーマに無い（{r['theme']}）")
        if r["jiko"] not in by or r["theme"] not in jiko.themes_of(by[r["jiko"]]):
            bad.append(f"{w}：jiko が事項の表に無いか、その theme の列に {r['theme']} が無い（{r['jiko']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{w}：yomi が {YOMI} のどれでもない（{r['yomi']}）")
        ps = page_danraku(inp, r["shiryo"])
        try:
            ns = bangou(r["hani"])
        except KisaiError as e:
            bad.append(f"{w}：{e}")
            continue
        if ps is None or not ns or ns[-1] > len(ps):
            bad.append(f"{w}：{r['shiryo']} に無い段落がある（{r['hani']}）")
    return bad


def dumps(rows):
    return "\t".join(COLS) + "\n" + "".join("\t".join(r[c] for c in COLS) + "\n" for r in rows)


def read(path=PATH):
    """taio/kisai.tsv の行。表が無ければ空。列が違えば InputError。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), COLS)


def kijutsu(inp, rows, hiduke):
    """表の行 → 出す記述の並び（SCHEMA.md 7.13）。行の続いた段落の範囲ごとに1つ。段落の字は、段落ごとに改行でつなぐ。
    字を確認した記録が無いページ（第6次日野町総合計画）の行は除く。
    記述は、jiko、source（資料のページの ID）、quote、source_date（資料の一覧の表の hiduke）、value（空）、yomi、hani、
    jun（並べる順に使う、資料の ID、ページ、範囲の始めの段落）。
    → (記述の並び, 出さない行の数)"""
    out, dasanai = [], 0
    for r in rows:
        if not kakunin_ari(r["shiryo"]):
            dasanai += 1
            continue
        ps = page_danraku(inp, r["shiryo"])
        for a, z in hanchi(r["hani"]):
            out.append(dict(jiko=r["jiko"], source=r["shiryo"], quote="\n".join(ps[a - 1:z]),
                            source_date=hiduke.get(bunsho_of(r["shiryo"]), ""), value="", kind="", yomi=r["yomi"],
                            hani=f"{a}" if a == z else f"{a}-{z}", jun=(bunsho_of(r["shiryo"]), page_of(r["shiryo"]), a)))
    return out, dasanai


def bunsho_hiduke():
    """資料の一覧の表の ID → hiduke。"""
    import suji as sj
    with open(os.path.join(inputs.ROOT, "teigi", "bunsho.tsv"), encoding="utf-8") as f:
        return {r["bunsho"]: r["hiduke"] for r in sj.read_bunsho(f.read())[0]}


def of_jiko(inp, jiko_rows, rows=None):
    """表の行のうち、事項が jiko_rows（そのテーマの事項の表の行）にある行の、出す記述（kijutsu）。記述ごとに point（事項の
    name）を付ける。どのテーマで読んだかによらない（SCHEMA.md 7.13）。表が無ければ空。"""
    rows = read() if rows is None else rows
    names = {r["id"]: r["name"] for r in jiko_rows}
    out, _ = kijutsu(inp, [r for r in rows if r["jiko"] in names], bunsho_hiduke())
    return [dict(x, point=names[x["jiko"]]) for x in out]


def main(argv=None):
    p = argparse.ArgumentParser(description="生成AIの2回の読み取りの結果から、資料の段落と事項の対応の表を作る")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--kensa", action="store_true")
    g.add_argument("--kouho", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    import suji as sj
    try:
        inp = inputs.Inputs()
        jiko_rows = jiko.read()
        with open(os.path.join(inputs.ROOT, "teigi", "bunsho.tsv"), encoding="utf-8") as f:
            bunsho = [r["bunsho"] for r in sj.read_bunsho(f.read())[0]]
        taba = read_taba()
        yomi = read_yomi()
    except (inputs.InputError, KisaiError, OSError, ValueError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    names = {r["name"] for r in jiko.of_theme(jiko_rows, THEME)}
    try:
        kouho_rows = read_kouho()
    except inputs.InputError as e:
        print(f"止めた：資料の段落の候補の名前と扱いの対応の表を読めない\n{e}", file=sys.stderr)
        return 1
    bad = check_taba(inp, taba) + check_yomi(yomi, taba, names) \
        + check_kouho(kouho_rows, yomi, {r["id"] for r in jiko.of_theme(jiko_rows, THEME)})
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    if a.kouho:
        for nm, xs in kouho(yomi).items():
            print(nm)
            for y, s, h, m, riyu in xs:
                print(f"  {y}　{s}　{h}" + (f"　迷い：{riyu}" if m == "1" else ""))
        return 0
    rows = make_rows(yomi, taba, jiko_rows, bunsho, kouho_rows)
    bad = check(inp, rows, jiko_rows, set(bunsho))
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    nd = sum(not kakunin_ari(r["shiryo"]) for r in rows)
    ko = kouho(yomi)
    print(f"資料の段落と事項の対応 {len(rows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）。ページ {len({r['shiryo'] for r in rows})}、"
          f"事項 {len({r['jiko'] for r in rows})}。字を確認した記録が無いので出さない行 {nd}。候補の名前 {len(ko)}"
          f"（事項に入れた {len(kouho_rows)}）")
    if a.kensa:
        cur = None
        if os.path.exists(PATH):
            with open(PATH, encoding="utf-8") as f:
                cur = f.read()
        if cur != s:
            print("止めた：taio/kisai.tsv が、読み取りの結果から作り直した行と違う（python3 -B tools/kisai.py で作り直す）",
                  file=sys.stderr)
            return 1
        print("taio/kisai.tsv は、読み取りの結果から作り直した行と同じ")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"{os.path.relpath(PATH, inputs.ROOT)} を書いた")
    return 0


if __name__ == "__main__":
    sys.exit(main())
