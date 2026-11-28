"""生成AIの2回の読み取りの結果（taio/yomi-kisai/）から、資料の段落と事項の対応の表（taio/kisai.tsv）を作る（SCHEMA.md 7.13）。

使い方：
  python3 -B tools/kisai.py            taio/kisai.tsv を作る
  python3 -B tools/kisai.py --kensa    作り直した行が taio/kisai.tsv と同じかを確認する（違えば終了コード 1。書き換えない）
  python3 -B tools/kisai.py --kouho    候補（kouho）の名前ごとに、テーマ、資料のページと段落と読み手を出す（表には行を作らない）

読むもの（taio/yomi-kisai/）。読み取りは2つある（SCHEMA.md 7.13）：
  行政運営の読み取り（2026-11-28 の最初の読み取り。テーマ b33）
    taba.json          読んだページの並び（ページごとに shiryo、danraku（段落の数）、sha256（段落の字を改行でつないだもの））
    <読み手>-kisai.tsv 列 shiryo、hani、point、kouho、mayoi、riyu（読み手は a と b）
  計画の読み取り（総合計画の分野ごと。分野の番号 B は2桁。①は 01）
    taba-<B>.json      束の並び（束の番号 N の位置に、束のページの並び。使わない番号は null）。ページごとに shiryo、danraku、
                       sha256、hyo（計画ライブラリの指標の表の目印の数）
    <B>-<N>-<読み手>.tsv 列 shiryo、hani、point、kouho、mayoi、riyu、hyo（hyo は、指標の表の段落だけの行なら 1）
    wariate.tsv        総合計画の関連する個別計画に名前が無い計画を、どの分野で読んだか（作業者の案。列 plan、bunya、riyu）
teigi/kisai-kouho.tsv（資料の段落の候補の名前と扱いの対応の表）で、候補の段落を、入れる先の事項の段落として合わせる。

行を作る決まり（SCHEMA.md 7.13）：
  資料のページ、読んだテーマ、事項の組ごとに、段落を1つずつに分け、2回とも付けた段落を yomi「一致」の行に、片方だけが付けた
  段落を、読み手ごとに yomi「1回だけ」の行にする。段落は番号の順に並べ、続いた段落は範囲にまとめる。事項は、事項の表
  （teigi/jiko.tsv）の、読んだテーマの行の name から ID を引く。指標の表の段落（その段落を付けた読み手の行が、どれも hyo が 1）
  は、hyo が 1 の行に分ける。手で行を書かない。
段落は、町の資料は hino-town-docs の data/text_raw のページを danraku で分け、計画は shiga-hino-plans の data/text_raw の
ページを同じ決まりで分け、第6次日野町総合計画（pt:sogo6）は sogo6.json の、出典が1ページのブロックの字から sogo6_danraku で
作る。読み手に渡した段落と同じであることを、束の記録の段落の数と sha256 で確認する。
"""
import argparse
import csv
import glob
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
COLS = ["shiryo", "theme", "jiko", "hani", "yomi", "hyo", "chu"]
FILE_COLS = ["shiryo", "hani", "point", "kouho", "mayoi", "riyu"]
FILE_COLS_KEIKAKU = FILE_COLS + ["hyo"]
WARIATE_COLS = ["plan", "bunya", "riyu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
THEME = "b33"                 # 行政運営の読み取り（2026-11-28 の最初の読み取り）で読んだテーマ（分野㉝行政運営）
# 計画の読み取りで、分野の論点の一覧ではなく、テーマの論点の一覧を使った分野（4つのテーマの中心の分野。SCHEMA.md 7.13）
THEME_OF_BUNYA = {"01": "hoiku", "18": "kaigo", "30": "chiiki", "32": "kokyo"}
SOGO6 = "sogo6"
RE_SHIRYO = re.compile(r"^(doc:([a-z0-9-]+)|pt:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_.-]+))/([0-9]+)$")
RE_HANI = re.compile(r"^([0-9]+)(?:-([0-9]+))?$")
RE_TABA = re.compile(r"^taba-([0-9]{2})\.json$")
RE_FILE = re.compile(r"^([0-9]{2})-([0-9]+)-([ab])\.tsv$")
RE_PSRC = re.compile(r"(\S+) p\.([0-9]+)(?:-([0-9]+))?")
SHIHYO = ("kpi_grid", "targets")     # 計画ライブラリの指標の表のブロックの型（SCHEMA.md 7.13）

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


def plan_of(shiryo):
    """計画のページの ID → 計画の id。計画でなければ None。"""
    m = RE_SHIRYO.match(shiryo)
    return m.group(3) if m and m.group(3) else None


def bunsho_of(shiryo, ids=None):
    """資料のページの ID → 資料の一覧の表の資料の ID。形が違えば None。
    町の資料は doc:<id>、第6次日野町総合計画は plan:sogo6。ほかの計画は、資料の一覧の表（ids。省くと teigi/bunsho.tsv）に
    pt:<計画>/<ファイル> の行があればその ID、無ければ plan:<計画>（計画ごとの行。SCHEMA.md 7.1。2026-11-28）。"""
    m = RE_SHIRYO.match(shiryo)
    if not m:
        return None
    if m.group(2):
        return f"doc:{m.group(2)}"
    if m.group(3) == SOGO6:
        return f"plan:{SOGO6}"
    pt = f"pt:{m.group(3)}/{m.group(4)}"
    ids = bunsho_ids() if ids is None else ids
    return pt if pt in ids or f"plan:{m.group(3)}" not in ids else f"plan:{m.group(3)}"


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


def theme_of_bunya(b):
    """分野の番号の2桁 → 読んだテーマ（SCHEMA.md 7.13）。"""
    return THEME_OF_BUNYA.get(b, f"b{b}")


def bunya_of_theme(theme):
    """読んだテーマ → 分野の番号（入力の字。①〜㉞）。分野に当たらなければ None。"""
    rev = {v: k for k, v in THEME_OF_BUNYA.items()}
    b = rev.get(theme) or (theme[1:] if jiko.is_bunya(theme) else None)
    return chr(0x2460 + int(b) - 1) if b and int(b) <= 20 else (chr(0x3251 + int(b) - 21) if b else None)


def read_taba(yomi_dir=None):
    """読んだ束の並び。束ごとに dict(theme, ki（束の名前）, pages（ページの並び）, files（読み手 → ファイルの名前）,
    keikaku（計画の読み取りの束か）)。束の記録が無いか、形が違えば KisaiError。"""
    yomi_dir = yomi_dir or YOMI_DIR
    path = os.path.join(yomi_dir, "taba.json")
    if not os.path.exists(path):
        raise KisaiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8") as f:
        out = [dict(theme=THEME, ki="taba.json", pages=json.load(f), files={y: f"{y}-kisai.tsv" for y in YOMITE},
                    keikaku=False)]
    for path in sorted(glob.glob(os.path.join(yomi_dir, "taba-*.json"))):
        m = RE_TABA.match(os.path.basename(path))
        if not m:
            raise KisaiError(f"束の記録の名前の形が違う（{os.path.basename(path)}）")
        with open(path, encoding="utf-8") as f:
            for n, pages in enumerate(json.load(f)):
                if pages is None:
                    continue
                out.append(dict(theme=theme_of_bunya(m.group(1)), ki=f"{m.group(1)}-{n}", pages=pages,
                                files={y: f"{m.group(1)}-{n}-{y}.tsv" for y in YOMITE}, keikaku=True))
    return out


def taba_pages(taba):
    """束の並び → ページの ID → ページの記録（同じページを2つの束で読んでいても1つ）。"""
    out = {}
    for t in taba:
        for p in t["pages"]:
            out.setdefault(p["shiryo"], p)
    return out


def read_yomi(taba, yomi_dir=None):
    """束の並び → 読み手の行（読み手 yomite、テーマ theme、束 ki、ファイル file、行 gyo を付けたもの）の並び。
    ファイルが無いか、束に当たらないファイルがあるか、列が違えば KisaiError。"""
    yomi_dir = yomi_dir or YOMI_DIR
    out, names = [], set()
    for i, t in enumerate(taba):
        cols = FILE_COLS_KEIKAKU if t["keikaku"] else FILE_COLS
        for y in YOMITE:
            fn = t["files"][y]
            names.add(fn)
            path = os.path.join(yomi_dir, fn)
            if not os.path.exists(path):
                raise KisaiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
            with open(path, encoding="utf-8", newline="") as f:
                rd = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                if rd.fieldnames != cols:
                    raise KisaiError(f"{fn} の列が違う（{rd.fieldnames}）")
                for g, r in enumerate(rd, 2):
                    if None in r or any(v is None for v in r.values()):
                        raise KisaiError(f"{fn} {g} 行目：列の数が違う")
                    out.append(dict(r, hyo=r.get("hyo", ""), yomite=y, gyo=g, theme=t["theme"], ki=i, file=fn))
    hoka = sorted(os.path.basename(p) for p in glob.glob(os.path.join(yomi_dir, "*.tsv"))
                  if os.path.basename(p) not in names and os.path.basename(p) != "wariate.tsv")
    if hoka:
        raise KisaiError(f"束の記録に当たらない読み取りの結果のファイルがある（{'、'.join(hoka)}）")
    return out


def check_taba(inp, taba):
    """束のページごとに、段落を作り直し、数と sha256 が同じかを確認する → 問題の並び。同じテーマで同じページを2つの束で
    読んでいないことも確認する。"""
    bad, seen = [], {}
    for t in taba:
        for p in t["pages"]:
            k = (t["theme"], p["shiryo"])
            if k in seen:
                bad.append(f"{t['ki']}：{p['shiryo']} を、同じテーマ {t['theme']} の束 {seen[k]} でも読んでいる")
            seen[k] = t["ki"]
    for s, p in taba_pages(taba).items():
        ps = page_danraku(inp, s)
        if ps is None:
            bad.append(f"束の記録：{s} のページか文字が、入力に無い")
        elif len(ps) != p["danraku"] or sha(ps) != p["sha256"]:
            bad.append(f"束の記録：{s} の段落が、読み手に渡したものと違う（数 {p['danraku']} → {len(ps)}）")
    return bad


def check_yomi(yomi, taba, names):
    """読み手の行の検査 → 問題の並び。names は、テーマ → そのテーマの事項の name の集まり（集まり1つなら、どのテーマも同じ）。"""
    bad = []
    seen = set()
    for r in yomi:
        w = f"{r.get('file', r['yomite'] + '-kisai.tsv')} {r['gyo']} 行目"
        pages = {p["shiryo"]: p for p in taba[r.get("ki", 0)]["pages"]}
        if r["shiryo"] not in pages:
            bad.append(f"{w}：shiryo が束のページに無い（{r['shiryo']}）")
            continue
        th = r.get("theme", THEME)
        nm = names.get(th, set()) if isinstance(names, dict) else names
        p, k = r["point"].strip(), r["kouho"].strip()
        if bool(p) == bool(k):
            bad.append(f"{w}：point と kouho のちょうど1つが空でない、になっていない")
        if p and r["point"] not in nm:
            bad.append(f"{w}：point が事項の表の {th} の行の name に無い（{r['point']}）")
        if r["mayoi"] not in ("", "1"):
            bad.append(f"{w}：mayoi が空か 1 でない")
        hy = r.get("hyo", "")
        if hy not in ("", "1") or (hy == "1" and not pages[r["shiryo"]].get("hyo")):
            bad.append(f"{w}：hyo が空か 1 でないか、指標の表の目印の無いページで 1")
        key = (r.get("ki", 0), r["yomite"], r["shiryo"], p, k)
        if key in seen:
            bad.append(f"{w}：同じ読み手、ページ、論点（候補）の行が2つある")
        seen.add(key)
        try:
            ns = bangou(r["hani"])
        except KisaiError as e:
            bad.append(f"{w}：{e}")
            continue
        if not ns or ns[0] < 1 or ns[-1] > pages[r["shiryo"]]["danraku"]:
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
    """資料の段落の候補の名前と扱いの対応の表の検査 → 問題の並び。jiko_ids は、テーマ → そのテーマの事項の表の id の集まり
    （集まり1つなら、テーマ b33 の id）。"""
    if not isinstance(jiko_ids, dict):
        jiko_ids = {THEME: jiko_ids}
    bad = []
    seen = set()
    for i, r in enumerate(rows, 2):
        w = f"teigi/kisai-kouho.tsv {i} 行目"
        k = (r["theme"], r["namae"])
        if k in seen or not r["namae"]:
            bad.append(f"{w}：theme と namae の組が重なっているか、namae が空（{r['theme']} {r['namae']}）")
        seen.add(k)
        if r["theme"] not in jiko_ids:
            bad.append(f"{w}：theme が、読み取りのテーマでない（{r['theme']}）")
        elif r["atsukai"] != JIKO_NI:
            bad.append(f"{w}：atsukai が「{JIKO_NI}」でない（{r['atsukai']}）")
        elif r["saki"] not in jiko_ids[r["theme"]]:
            bad.append(f"{w}：saki が事項の表の {r['theme']} の行の id に無い（{r['saki']}）")
    yn = {(r.get("theme", THEME), r["kouho"].strip()) for r in yomi if r["kouho"].strip()}
    bad += [f"候補の名前「{t} {n}」が、teigi/kisai-kouho.tsv に無い" for t, n in sorted(yn - seen)]
    bad += [f"teigi/kisai-kouho.tsv の「{t} {n}」が、読み取りの結果に無い" for t, n in sorted(seen - yn)]
    return bad


def read_wariate(path=None):
    """計画を読んだ分野の割り当ての表（taio/yomi-kisai/wariate.tsv。作業者の案）の行。"""
    path = path or os.path.join(YOMI_DIR, "wariate.tsv")
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), WARIATE_COLS)


def check_wariate(rows, taba, kanren):
    """割り当ての表の検査 → 問題の並び。kanren は、分野の番号（入力の字）→ 総合計画の関連する個別計画に結び付いた計画の id の
    集まり。計画の読み取りの束で読んだ（計画, 分野）の組は、関連する個別計画か、割り当ての表のどちらかにあること。割り当ての表の
    行は、読んだ組で、関連する個別計画に無いこと。"""
    bad, yonda = [], set()
    for t in taba:
        if t["keikaku"]:
            b = bunya_of_theme(t["theme"])
            yonda |= {(plan_of(p["shiryo"]), b) for p in t["pages"]}
    wa = set()
    for i, r in enumerate(rows, 2):
        k = (r["plan"], r["bunya"])
        if k in wa or not r["riyu"].strip():
            bad.append(f"wariate.tsv {i} 行目：plan と bunya の組が重なっているか、riyu が空")
        wa.add(k)
        if k not in yonda:
            bad.append(f"wariate.tsv {i} 行目：{r['plan']} を分野 {r['bunya']} で読んだ束が無い")
        if r["plan"] in kanren.get(r["bunya"], set()):
            bad.append(f"wariate.tsv {i} 行目：{r['plan']} は、分野 {r['bunya']} の関連する個別計画に結び付いている")
    for p, b in sorted(yonda - wa):
        if p not in kanren.get(b, set()):
            bad.append(f"{p} を分野 {b} で読んだが、関連する個別計画にも、割り当ての表にも無い")
    return bad


def kanren_plans(inp, bunsho_rows):
    """分野の番号（入力の字）→ 総合計画の関連する個別計画に結び付いた計画の id の集まり（tools/sogo_kanren.py）。"""
    import sogo_kanren as sk
    return {no: {pid for k in (x["kanren"] or {}).get("keikaku", []) for pid, _, _ in k["plans"]}
            for no, x in sk.matome(inp, bunsho_rows).items()}


def make_rows(yomi, taba, jiko_rows, bunsho_jun, kouho_rows=()):
    """読み手の行 → 表の行（SCHEMA.md 7.13）。並びは、資料の一覧の表の順、ページの順、テーマの順、事項の表の順。
    候補の行は、資料の段落の候補の名前と扱いの対応の表（kouho_rows）の入れる先の事項に、読み手が付けた段落として合わせる。
    指標の表の段落（その段落を付けた読み手の行が、どれも hyo が 1）は、hyo が 1 の行に分ける。"""
    ids = {}
    for r in jiko_rows:
        for th in jiko.themes_of(r):
            ids.setdefault(th, {})[r["name"]] = r["id"]
    saki = {(r["theme"], r["namae"]): r["saki"] for r in kouho_rows}
    jiko_jun = {r["id"]: i for i, r in enumerate(jiko_rows)}
    theme_jun = {th: i for i, th in enumerate(dict.fromkeys(t["theme"] for t in taba))}
    paras, mayoi, kps, hyo, nohyo = {}, {}, {}, {}, {}

    def em():
        return {y: set() for y in YOMITE}
    for r in yomi:
        th = r.get("theme", THEME)
        if r["point"].strip():
            k = (r["shiryo"], th, ids[th][r["point"]])
        elif (th, r["kouho"].strip()) in saki:
            k = (r["shiryo"], th, saki[(th, r["kouho"].strip())])
            kps.setdefault(k, em())[r["yomite"]] |= set(bangou(r["hani"]))
        else:
            continue
        ns = set(bangou(r["hani"]))
        paras.setdefault(k, em())[r["yomite"]] |= ns
        (hyo if r.get("hyo") == "1" else nohyo).setdefault(k, set()).update(ns)
        if r["point"].strip() and r["mayoi"] == "1":
            mayoi.setdefault(k, set()).add(r["yomite"])
    out = []
    for (s, th, j), ps in paras.items():
        m = "、".join(sorted(mayoi.get((s, th, j), ())))
        ko = kps.get((s, th, j), em())
        hy = hyo.get((s, th, j), set()) - nohyo.get((s, th, j), set())

        def kw(gyo):
            return "、".join(y for y in YOMITE if ko[y] & gyo)

        def gyo(ns, yomi_, yomite):
            for h, sub in (("", ns - hy), ("1", ns & hy)):
                if sub:
                    out.append(dict(shiryo=s, theme=th, jiko=j, hani=matomeru(sub), yomi=yomi_, hyo=h,
                                    chu=chu_of(yomite, m, kw(sub))))
        gyo(ps["a"] & ps["b"], ICCHI, "")
        for y in YOMITE:
            gyo(ps[y] - ps[[x for x in YOMITE if x != y][0]], IKKAI, y)
    page_no = {}
    for t in taba:
        for p in t["pages"]:
            page_no.setdefault(p["shiryo"], len(page_no))
    bj = {b: i for i, b in enumerate(bunsho_jun)}

    def jun(r):
        b = bunsho_of(r["shiryo"], bj)
        return (bj.get(b, len(bj)), page_no[r["shiryo"]], theme_jun[r["theme"]], jiko_jun[r["jiko"]],
                YOMI.index(r["yomi"]), r["hyo"], r["chu"])
    return sorted(out, key=jun)


def kouho(yomi):
    """候補の行 → (テーマ, 候補の名前) ごとの、(読み手, ページ, 段落の範囲, 迷い, 理由) の並び（最初に出る順）。"""
    out = {}
    for r in yomi:
        if r["kouho"].strip():
            out.setdefault((r.get("theme", THEME), r["kouho"].strip()), []).append(
                (r["yomite"], r["shiryo"], r["hani"], r["mayoi"], r["riyu"]))
    return out


def check(inp, rows, jiko_rows, bunsho):
    """表の行の検査 → 問題の並び。"""
    bad = []
    themes = jiko.theme_jun(jiko_rows)
    by = {r["id"]: r for r in jiko_rows}
    for i, r in enumerate(rows, 2):
        w = f"taio/kisai.tsv {i} 行目"
        b = bunsho_of(r["shiryo"], bunsho)
        if b is None or b not in bunsho:
            bad.append(f"{w}：shiryo の資料が、資料の一覧の表に無い（{r['shiryo']}）")
        if r["theme"] not in themes:
            bad.append(f"{w}：theme が事項の表のテーマに無い（{r['theme']}）")
        if r["jiko"] not in by or r["theme"] not in jiko.themes_of(by[r["jiko"]]):
            bad.append(f"{w}：jiko が事項の表に無いか、その theme の列に {r['theme']} が無い（{r['jiko']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{w}：yomi が {YOMI} のどれでもない（{r['yomi']}）")
        if r["hyo"] not in ("", "1"):
            bad.append(f"{w}：hyo が空か 1 でない（{r['hyo']}）")
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


# ---- 指標の表（SCHEMA.md 7.13。2026-11-28） ----

def pdf_pages(plan, file, src):
    """ブロックの source（「<ファイル> p.<印刷のページ>[-<印刷のページ>]」）→ PDF のページの集まり（計画の sources の
    pdf_page_offset か pdf_page_offsets で読み替える）。ファイルが違えば空。"""
    m = RE_PSRC.fullmatch(src or "")
    if not m or m.group(1) != file:
        return set()
    s = next((x for x in plan.get("sources", []) if x["id"] == file), None)
    if s is None:
        return set()
    out = set()
    for pr in range(int(m.group(2)), int(m.group(3) or m.group(2)) + 1):
        if s.get("pdf_page_offsets"):
            for e in s["pdf_page_offsets"]:
                if pr >= e["from"] and (e.get("to") is None or pr <= e["to"]):
                    out.add(pr + e["offset"])
        else:
            out.add(pr + s.get("pdf_page_offset", 0))
    return out


AUDIT_KAKUNIN = "✓"


def audit_of(inp, pid):
    """計画の検収の台帳（shiga-hino-plans data/audit_log/<計画>.tsv）→ (tab, block_no, btype, label, value) → checked。
    台帳が無ければ空。"""
    k = ("audit", pid)
    if k not in _CACHE:
        path = f"data/audit_log/{pid}.tsv"
        out = {}
        if path in inp.files(inputs.SP, "data/audit_log/*.tsv"):
            text = "\n".join(l for l in inp.read_text(inputs.SP, path).split("\n") if not l.startswith("#"))
            for r in csv.DictReader(text.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE):
                out[(r["tab"], r["block_no"], r["btype"], r["label"], r["value"])] = r["checked"]
        _CACHE[k] = out
    return _CACHE[k]


def shihyo_of(inp, shiryo):
    """計画のページの ID → そのページを出典とする、計画ライブラリの指標の表（kpi_grid、targets）の並び。表ごとに
    dict(type, source, items, key（計画、tab、ブロックの番号）)。items は、指標ごとに dict(label, unit, asof, value, base, base_asof, target, target_asof,
    kakunin)。数値は JSON の数の字のまま。kakunin は、検収の台帳で、その指標の値の全部に確認の印（✓）があるか。
    計画のページでなければ空。"""
    m = RE_SHIRYO.match(shiryo)
    if not m or not m.group(3) or m.group(3) == SOGO6:
        return []
    pid, file, pg = m.group(3), m.group(4), int(m.group(5))
    path = f"data/plans/{pid}.json"
    if path not in inp.files(inputs.SP, "data/plans/*.json"):
        return []
    plan = json.loads(inp.read_text(inputs.SP, path), parse_float=str, parse_int=str)
    au = audit_of(inp, pid)
    out = []
    for t in plan["tabs"]:
        for i, b in enumerate(t["blocks"]):
            if b.get("type") not in SHIHYO or pg not in pdf_pages(inp.plan(pid), file, b.get("source")):
                continue
            items = []
            for it in b["items"]:
                if b["type"] == "kpi_grid":
                    vs = [("kpi", it.get("value", ""))]
                    x = dict(label=it["label"], unit=it.get("unit", ""), asof=it.get("asof", ""),
                             value=str(it.get("value", "")))
                else:
                    ba, ta = it.get("base") or {}, it.get("target") or {}
                    vs = [("target.base", ba.get("v", "")), ("target.target", ta.get("v", ""))]
                    x = dict(label=it["label"], unit=it.get("unit", ""), base=str(ba.get("v", "")),
                             base_asof=ba.get("asof", ""), target=str(ta.get("v", "")), target_asof=ta.get("asof", ""))
                x["kakunin"] = all(au.get((t["id"], str(i), bt, it["label"], str(v))) == AUDIT_KAKUNIN for bt, v in vs)
                items.append(x)
            out.append(dict(type=b["type"], source=b["source"], items=items, key=(pid, t["id"], i)))
    return out


def kijutsu(inp, rows, hiduke, wariate=None):
    """表の行 → 出す記述の並び（SCHEMA.md 7.13）。行の続いた段落の範囲ごとに1つ。段落の字は、段落ごとに改行でつなぐ。
    字を確認した記録が無いページ（第6次日野町総合計画）の行は除く。どのテーマで読んだかによらず、同じ事項、ページ、範囲、
    読みの言葉の記述は1つにする。
    記述は、jiko、source（資料のページの ID）、quote、source_date（資料の一覧の表の hiduke）、value（空）、yomi、hani、
    jun（並べる順に使う、資料の ID、ページ、範囲の始めの段落）、bunsho（資料の一覧の表の ID）、hyo（指標の表の段落の行なら、
    そのページの指標の表の並び（shihyo_of）。ページで結べなければ空の並び。ほかは None）、wariate（読んだ分野を作成者が
    決めた計画なら、その計画の id。ほかは空）。wariate は、(計画の id, 分野の番号) の集まり。
    → (記述の並び, 出さない行の数)"""
    out, dasanai, seen = [], 0, set()
    ids = set(hiduke)
    for r in rows:
        if not kakunin_ari(r["shiryo"]):
            dasanai += 1
            continue
        ps = page_danraku(inp, r["shiryo"])
        b = bunsho_of(r["shiryo"], ids)
        pid = plan_of(r["shiryo"])
        wa = pid if pid and wariate and (pid, bunya_of_theme(r["theme"])) in wariate else ""
        for a, z in hanchi(r["hani"]):
            k = (r["jiko"], r["shiryo"], a, z, r["yomi"], r.get("hyo", ""))
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(jiko=r["jiko"], source=r["shiryo"], quote="\n".join(ps[a - 1:z]),
                            source_date=hiduke.get(b, ""), value="", kind="", yomi=r["yomi"],
                            hani=f"{a}" if a == z else f"{a}-{z}", jun=(b, page_of(r["shiryo"]), a), bunsho=b,
                            hyo=shihyo_of(inp, r["shiryo"]) if r.get("hyo") == "1" else None, wariate=wa))
    # 指標の表の段落で、表の字を出す記述は、事項と表（2ページ以上を出典とする表は、どのページでも同じ表）ごとに1つにする
    # （同じ表を2回出さない）。記述のページは、最初のページ。同じページの段落の範囲はつなぎ、読みの言葉は、
    # どれかが「一致」なら「一致」。引用の照合に使う quote は、最初の範囲の字（2026-11-28）
    hy, keep = {}, []
    for x in out:
        if x["hyo"]:
            k = (x["jiko"], tuple(b["key"] for b in x["hyo"]))
            if k in hy:
                y = hy[k]
                if x["source"] == y["source"]:
                    y["hani"] = matomeru(set(bangou(y["hani"])) | set(bangou(x["hani"])))  # quote は最初の範囲の字のまま
                if x["yomi"] == ICCHI:
                    y["yomi"] = ICCHI
                continue
            hy[k] = x
        keep.append(x)
    return keep, dasanai


def bunsho_rows():
    import suji as sj
    with open(os.path.join(inputs.ROOT, "teigi", "bunsho.tsv"), encoding="utf-8") as f:
        return sj.read_bunsho(f.read())[0]


def bunsho_ids():
    """資料の一覧の表の ID の集まり。"""
    if "bunsho_ids" not in _CACHE:
        _CACHE["bunsho_ids"] = {r["bunsho"] for r in bunsho_rows()}
    return _CACHE["bunsho_ids"]


def bunsho_hiduke():
    """資料の一覧の表の ID → hiduke。"""
    return {r["bunsho"]: r["hiduke"] for r in bunsho_rows()}


def wariate_set():
    """割り当ての表の (計画の id, 分野の番号) の集まり。表が無ければ空。"""
    path = os.path.join(YOMI_DIR, "wariate.tsv")
    return {(r["plan"], r["bunya"]) for r in read_wariate(path)} if os.path.exists(path) else set()


def of_jiko(inp, jiko_rows, rows=None):
    """表の行のうち、事項が jiko_rows（そのテーマの事項の表の行）にある行の、出す記述（kijutsu）。記述ごとに point（事項の
    name）を付ける。どのテーマで読んだかによらない（SCHEMA.md 7.13）。表が無ければ空。"""
    rows = read() if rows is None else rows
    names = {r["id"]: r["name"] for r in jiko_rows}
    out, _ = kijutsu(inp, [r for r in rows if r["jiko"] in names], bunsho_hiduke(), wariate_set())
    return [dict(x, point=names[x["jiko"]]) for x in out]


def main(argv=None):
    p = argparse.ArgumentParser(description="生成AIの2回の読み取りの結果から、資料の段落と事項の対応の表を作る")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--kensa", action="store_true")
    g.add_argument("--kouho", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        jiko_rows = jiko.read()
        brows = bunsho_rows()
        bunsho = [r["bunsho"] for r in brows]
        taba = read_taba()
        yomi = read_yomi(taba)
        kouho_rows = read_kouho()
        wariate = read_wariate()
        kanren = kanren_plans(inp, brows)
    except (inputs.InputError, KisaiError, OSError, ValueError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001  sogo_kanren.KanrenError など
        print(f"止めた：総合計画の関連する個別計画を読めない\n{e}", file=sys.stderr)
        return 1
    themes = sorted({t["theme"] for t in taba})
    names = {th: {r["name"] for r in jiko.of_theme(jiko_rows, th)} for th in themes}
    jids = {th: {r["id"] for r in jiko.of_theme(jiko_rows, th)} for th in themes}
    bad = check_taba(inp, taba) + check_yomi(yomi, taba, names) + check_kouho(kouho_rows, yomi, jids) \
        + check_wariate(wariate, taba, kanren)
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad[:200]), file=sys.stderr)
        return 1
    if a.kouho:
        for (th, nm), xs in kouho(yomi).items():
            print(f"{th}　{nm}")
            for y, s, h, m, riyu in xs:
                print(f"  {y}　{s}　{h}" + (f"　迷い：{riyu}" if m == "1" else ""))
        return 0
    rows = make_rows(yomi, taba, jiko_rows, bunsho, kouho_rows)
    bad = check(inp, rows, jiko_rows, set(bunsho))
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad[:200]), file=sys.stderr)
        return 1
    s = dumps(rows)
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    nd = sum(not kakunin_ari(r["shiryo"]) for r in rows)
    ko = kouho(yomi)
    print(f"資料の段落と事項の対応 {len(rows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}。指標の表の段落の行 "
          f"{sum(r['hyo'] == '1' for r in rows)}）。ページ {len({r['shiryo'] for r in rows})}、"
          f"事項 {len({r['jiko'] for r in rows})}。字を確認した記録が無いので出さない行 {nd}。候補の名前 {len(ko)}"
          f"（事項に入れた {len(kouho_rows)}）")
    for th in themes:
        rs = [r for r in rows if r["theme"] == th]
        print(f"  {th}：{len(rs)} 行（一致 {sum(r['yomi'] == ICCHI for r in rs)}、1回だけ {sum(r['yomi'] == IKKAI for r in rs)}）")
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
