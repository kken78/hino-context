"""総合戦略の施策検証結果報告書（令和7年度）の施策検証シートの記述を、生成AIの2回の読み取りの結果（taio/yomi-kensho/）から、
表にする（SCHEMA.md 7.12）。MCP の応答（tools/build_mcp.py の field と review）と試作のページ（tools/build_bunya.py）は、
この表と入力から作る。

使い方：
  python3 -B tools/kensho.py            4つの表（taio/kensho.tsv、kensho-kpi.tsv、kensho-bun.tsv、kensho-bunya.tsv）を作る
  python3 -B tools/kensho.py --kensa    作り直した行が4つの表と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの：
  taio/yomi-kensho/taba.json              束の並び。束ごとに、読んだシートの最初のページ（PDF のページ）の並び
  taio/yomi-kensho/<読み手>-p<3桁>.json   読み手（a と b）の出力。シート1つは、そのページと次のページ
  teigi/kensho-ran.tsv                    施策検証の欄の表（欄の見出しの字。報告書の字のまま）
  teigi/kensho-kekka.tsv                  検証結果の説明の表（報告書の「２．検証方法」の文）
  入力：hino-town-docs の報告書の文字（data/text と data/text_raw）、shiga-hino-plans の総合戦略（data/plans/senryaku2.json と
  本編の文字）、第6次日野町総合計画（data/plans/sogo6.json）

行を作る決まり（SCHEMA.md 7.12）。手で行を書かない。合わないものがあれば、件数と該当を示して止まる。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bunya as bu  # noqa: E402
import inputs  # noqa: E402
import shogo  # noqa: E402

DOC = "hyoka-r7-senryaku-kensho"     # hino-town-docs の報告書の id
SHIRYO = f"doc:{DOC}"
PLAN = "senryaku2"                   # 総合戦略（shiga-hino-plans data/plans/senryaku2.json）
TAB = "torikumi"                     # 取り組みの tab（programs の groups が取り組みの方向、items が取り組み）
HONPEN = "honpen"                    # 本編の source の id（programs の block の source「honpen p.14-16」）
KIHON = "基本目標"                    # 取り組みの tab の heading の頭の字（「基本目標1 …」）
KOME = "※"                           # 本編の、用語の説明を示す印（「創業・※コミュニティビジネスへの支援」）。ページを探すときだけ除く
MARU = "●"                           # 施策検証シートの④⑤の欄の見出しの頭の字
DEPT_SEP = "・"                      # 総合戦略の担当課（dept）の、課の区切り。本編では、課ごとに行が分かれている
YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi-kensho")
RAN_PATH = os.path.join(inputs.ROOT, "teigi", "kensho-ran.tsv")
KEKKA_PATH = os.path.join(inputs.ROOT, "teigi", "kensho-kekka.tsv")
PATHS = dict(torikumi=os.path.join(inputs.ROOT, "taio", "kensho.tsv"),
             kpi=os.path.join(inputs.ROOT, "taio", "kensho-kpi.tsv"),
             bun=os.path.join(inputs.ROOT, "taio", "kensho-bun.tsv"),
             bunya=os.path.join(inputs.ROOT, "taio", "kensho-bunya.tsv"))
COLS = ["torikumi", "kihon_no", "kihon", "no", "name", "houkou", "tantou", "tasseido", "kekka", "shiryo", "honpen",
        "chu"]
KPI_COLS = ["torikumi", "shihyo_n", "shihyo", "kijun_midashi", "kijun", "nendo_ji", "nendo", "mokuhyo", "jisseki",
            "tasseiritsu", "shiryo", "yomi", "chu"]
BUN_COLS = ["torikumi", "ran", "n", "midashi", "bun", "shiryo", "yomi", "chu"]
BUNYA_COLS = ["torikumi", "bunya", "shisaku", "saisho", "yomi", "chu"]
RAN_COLS = ["ran", "kubun", "midashi", "chu"]
KEKKA_COLS = ["shu", "kekka", "inyo", "tokoro", "chu"]
ALL_COLS = dict(torikumi=COLS, kpi=KPI_COLS, bun=BUN_COLS, bunya=BUNYA_COLS)
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
RAN_KUBUN = ("sheet", "kpi", "naibu", "gaibu")
NAIBU = ("jokyo", "kongo", "seika", "dekiteinai", "konnan", "fumaete", "kadai")      # 読み手の naibu の欄（報告書の②〜⑤の順）
GAIBU = ("comment",)
RAN = NAIBU + GAIBU
SHEET_RAN = ("kihon", "houkou", "tantou", "kpi", "shihyo", "mokuhyo", "jisseki", "tasseiritsu", "tasseido", "naibu",
             "gaibu", "kekka")        # どのシートにもある欄の見出し（無ければ止まる）
SCALAR = ("kihon_no", "kihon", "no", "name", "houkou", "tantou", "tasseido")
KEKKA_SHU = ("kekka", "tasseido")
BUNYA_MAX = 3                        # 1つの取り組みに付ける分野の数の上限（読み手への指示）
RE_NENDO = re.compile(r"令和([0-9]+)年度")
REIWA = 2018                         # 令和の年 + REIWA = 西暦


class KenshoError(ValueError):
    """読み取りの結果、表、入力が、決まりに合わない。"""


def norm(s):
    """資料どうしの字を照合するときの正規化（SCHEMA.md §3。総合戦略の本編と報告書の字の照合）。"""
    return shogo.norm(s)


def nw(s):
    """読み手の字を、シートの本文と照合するときの正規化。空白と改行を除くだけ（SCHEMA.md 7.12）。§3 の正規化は、
    行の頭の「3-2」をページ番号として除くので、使わない。"""
    return re.sub(shogo.WHITESPACE, "", s or "")


def read_tsv(path, cols):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), cols)


def read_ran(path=RAN_PATH):
    return read_tsv(path, RAN_COLS)


def read_kekka(path=KEKKA_PATH):
    return read_tsv(path, KEKKA_COLS)


def read(name):
    """作った表（name は torikumi、kpi、bun、bunya）の行。"""
    return read_tsv(PATHS[name], ALL_COLS[name])


def read_all():
    return {k: read(k) for k in PATHS}


def kohos(r):
    """欄の表の行 → 見出しの字の候補の並び。"""
    return [x.strip() for x in r["midashi"].split(";") if x.strip()]


def check_ran(rows):
    """欄の表の検査 → 問題の並び。ran が重ならず、kubun が決めた字で、midashi が空でないこと。読み手の欄と、どのシートにも
    ある欄の見出しが、全部あること。"""
    bad, seen = [], set()
    for i, r in enumerate(rows, 2):
        if not r["ran"] or r["ran"] in seen:
            bad.append(f"teigi/kensho-ran.tsv {i} 行目：ran が空か重なっている（{r['ran']}）")
        seen.add(r["ran"])
        if r["kubun"] not in RAN_KUBUN or not kohos(r):
            bad.append(f"teigi/kensho-ran.tsv {i} 行目：kubun か midashi が違う（{r['kubun']} {r['midashi']}）")
    bad += [f"teigi/kensho-ran.tsv：欄 {x} の行が無い" for x in RAN + SHEET_RAN if x not in seen]
    return bad


def check_kekka(inp, rows):
    """検証結果の説明の表の検査 → 問題の並び。shu が決めた字で、inyo が tokoro のページの本文にあること（SCHEMA.md §3）、
    kekka が重ならないこと。"""
    bad = []
    seen = set()
    for i, r in enumerate(rows, 2):
        if r["shu"] not in KEKKA_SHU or not r["inyo"] or not r["tokoro"].startswith(SHIRYO + "/"):
            bad.append(f"teigi/kensho-kekka.tsv {i} 行目：shu、inyo、tokoro のどれかが違う")
            continue
        if (r["shu"], r["kekka"]) in seen:
            bad.append(f"teigi/kensho-kekka.tsv {i} 行目：同じ shu と kekka の行がほかにもある")
        seen.add((r["shu"], r["kekka"]))
    res = shogo.check_quotes(inp, [dict(where=f"teigi/kensho-kekka.tsv {i} 行目", source=r["tokoro"], quote=r["inyo"])
                                   for i, r in enumerate(rows, 2) if r["tokoro"]])
    bad += [f"{m['where']}：{m['reason']}（{m['source']}）" for m in res.mismatched]
    return bad


# ---- 入力 ----

def sheet_text(inp, p, layer="text_raw"):
    """シート（最初のページ p）の2ページの本文の並び。無ければ KenshoError。"""
    t = inp.doc_text(DOC, layer)
    if t is None:
        raise KenshoError(f"入力に hino-town-docs の data/{layer}/{DOC}.txt が無い")
    ps = t.split("\f")
    if p + 1 > len(ps):
        raise KenshoError(f"報告書に {p + 1} ページが無い")
    return [ps[p - 1], ps[p]]


def senryaku(inp):
    """総合戦略の取り組み → {(基本目標の番号, 取り組みの番号): dict(key, kihon, houkou, no, name, dept, honpen)}。
    基本目標の番号と名前は、取り組みの tab の heading（「基本目標1 …」）から、取り組みの方向は groups の name から取る。
    honpen は、取り組みの名前（本編の「※」の印を除いて照合する）と担当課の字（課ごと）がある本編のページ（pt の ID）。block の source の印刷のページの範囲に、
    sources の pdf_page_offset を足した PDF のページから探す。"""
    p = inp.plan(PLAN)
    if p is None:
        raise KenshoError(f"入力に data/plans/{PLAN}.json が無い")
    off = {s["id"]: s.get("pdf_page_offset", 0) for s in p.get("sources", [])}
    tx = {lay: inp.pt_text(PLAN, HONPEN, lay) for lay in ("text", "text_raw")}
    if not any(tx.values()):
        raise KenshoError(f"入力に {PLAN} の {HONPEN} の文字が無い")
    pages = {lay: (t.split("\f") if t else []) for lay, t in tx.items()}
    tab = next((t for t in p["tabs"] if t["id"] == TAB), None)
    if tab is None:
        raise KenshoError(f"{PLAN}.json に tab {TAB} が無い")
    out, kihon = {}, None
    for b in tab["blocks"]:
        if b.get("type") == "heading" and b.get("text", "").startswith(KIHON):
            m = re.fullmatch(KIHON + r"([0-9]+) (.+)", b["text"])
            if not m:
                raise KenshoError(f"{PLAN}.json の heading の形が違う（{b['text']}）")
            kihon = (m.group(1), m.group(2))
        if b.get("type") != "programs":
            continue
        m = bu.RE_SOURCE.fullmatch(b.get("source", ""))
        if kihon is None or not m or m.group(1) != HONPEN:
            raise KenshoError(f"{PLAN}.json の programs の基本目標か source が分からない（{b.get('source')}）")
        a, z = int(m.group(2)) + off.get(HONPEN, 0), int(m.group(3) or m.group(2)) + off.get(HONPEN, 0)
        for g in b["groups"]:
            for it in g["items"]:
                depts = [norm(d) for d in it["dept"].split(DEPT_SEP) if d.strip()]
                hit = [x for x in range(a, z + 1)
                       if any(len(ps) >= x and norm(it["name"]) in norm(ps[x - 1].replace(KOME, ""))
                              and all(d in norm(ps[x - 1]) for d in depts) for ps in pages.values())]
                k = (kihon[0], it["no"])
                if k in out:
                    raise KenshoError(f"{PLAN}.json に、基本目標{k[0]}の取り組み{k[1]}が2つある")
                out[k] = dict(key=it["key"], kihon=kihon[1], houkou=g["name"], no=it["no"], name=it["name"],
                              dept=it["dept"], honpen=f"pt:{PLAN}/{HONPEN}/{hit[0]}" if hit else "")
    return out


def sogo_shisaku(inp):
    """第6次日野町総合計画の分野の番号 → 基本施策の番号の集まり（tools/bunya.py の keikaku）。"""
    kk = bu.keikaku(inp)
    return {x["no"]: {no for no, _ in x["shisaku"]} for h in kk["hashira"] for x in h["bunya"]}


# ---- 読み取りの結果 ----

def read_taba(yomi_dir=YOMI_DIR):
    with open(os.path.join(yomi_dir, "taba.json"), encoding="utf-8") as f:
        return json.load(f)


def read_yomi(yomi_dir=YOMI_DIR):
    """→ {最初のページ: {読み手: 出力}}（束の順）。ファイルが無い、読めない、pages が違う、同じシートが2回あれば KenshoError。"""
    out, bad = {}, []
    for t in read_taba(yomi_dir):
        for p in t:
            if p in out:
                bad.append(f"シート {p} が、束に2回ある")
            out[p] = {}
            for y in YOMITE:
                path = os.path.join(yomi_dir, f"{y}-p{p:03d}.json")
                try:
                    with open(path, encoding="utf-8") as f:
                        d = json.load(f)
                except (OSError, ValueError) as e:
                    bad.append(f"{os.path.relpath(path, inputs.ROOT)} を読めない（{e}）")
                    continue
                if d.get("pages") != [p, p + 1]:
                    bad.append(f"{os.path.relpath(path, inputs.ROOT)}：pages が [{p}, {p + 1}] でない")
                out[p][y] = d
    if bad:
        raise KenshoError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return out


def kpi_key(k):
    return (nw(k["shihyo"]), nw(k["kijun_midashi"]), nw(k["kijun"]),
            tuple((nw(r["nendo"]), nw(r["mokuhyo"]), nw(r["jisseki"]), nw(r["tasseiritsu"])) for r in k["rows"]))


def midashi_of(r, text):
    """欄の表の行と、シートの本文（nw で正規化したもの）→ 本文にある見出しの字の並び。「●」を前に付けた字が本文にある
    候補があれば、その候補だけにする（④⑤の欄の見出しは「●」で始まる。項目の文の中の同じ字を見出しとしない）。
    ほかの候補の一部であるものは除く（「実施できていないこと」と「実施できていないこと・困難なこと」）。"""
    hit = [m for m in kohos(r) if nw(MARU + m) in text] or [m for m in kohos(r) if nw(m) in text]
    return [m for m in hit if not any(m != x and nw(m) in nw(x) for x in hit)]


def nendo_of(ji):
    """年度の字（「令和３年度」）→ 西暦の年度の字。形が違えば空。"""
    m = RE_NENDO.fullmatch(unicodedata.normalize("NFKC", ji).replace(" ", ""))
    return str(int(m.group(1)) + REIWA) if m else ""


def ran_rows(p, key, ran, ya, yb, midashi, src):
    """1つの欄の、2人の読み → (文の表の行の並び, 問題の並び)。2人の項目が同じなら、どれも「一致」。字が同じで区切りだけが
    違うときは、項目の数が多いほうの区切りを使い、もう1人の読みにもある項目を「一致」、ほかを「1回だけ」にする。
    字が違えば止まる。項目の字は、シートの2ページの本文（src。正規化したもの）にあること。"""
    bad = []
    na, nb = [nw(x) for x in ya], [nw(x) for x in yb]
    if na == nb:
        use, tsuki, chu = ya, None, ""
    elif "".join(na) == "".join(nb):
        use, other, ow = (ya, nb, "b") if len(na) >= len(nb) else (yb, na, "a")
        tsuki = set(other)
        chu = f"項目の区切りが、2人の読みで違う（読み手 {ow} の項目の数 {len(other)}）。項目の数が多いほうの区切りを使った"
    else:
        return [], [f"シート {p}（{key}）の欄 {ran}：2人の読みの項目の字が違う"]
    out = []
    for n, x in enumerate(use, 1):
        q = nw(x)
        pages = [pp for pp, t in zip((p, p + 1), src[1]) if q and q in t]
        if not q or q not in src[0]:
            bad.append(f"シート {p}（{key}）の欄 {ran} の項目 {n}：字が、シートの2ページの本文に無い（「{x[:30]}」）")
            continue
        yomi = ICCHI if tsuki is None or q in tsuki else IKKAI
        chu_ = chu
        if not pages:
            chu_ = "。".join(c for c in (chu, "字が2ページにまたがる") if c)
        out.append(dict(torikumi=key, ran=ran, n=str(n), midashi=midashi, bun=x,
                        shiryo=f"{SHIRYO}/{pages[0] if pages else p}", yomi=yomi, chu=chu_))
    return out, bad


def make(inp, yomi, ran_tbl, kekka_tbl):
    """→ (表の名前 → 行の並び, 問題の並び)。"""
    sr = senryaku(inp)
    ss = sogo_shisaku(inp)
    rans = {r["ran"]: r for r in ran_tbl}
    kekka_ok = {r["kekka"] for r in kekka_tbl if r["shu"] == "kekka" and r["kekka"]}
    out = {k: [] for k in PATHS}
    bad = []
    seen_key = {}
    for p, d in yomi.items():
        a, b = d["a"], d["b"]
        raw = sheet_text(inp, p)
        txt = sheet_text(inp, p, "text")
        src_all = nw(raw[0] + raw[1])
        src = (src_all, [nw(x) for x in raw])
        kazu_src = nw(raw[0] + raw[1]) + "\n" + nw(txt[0] + txt[1])
        w = f"シート {p}"
        for k in SCALAR:
            if nw(a.get(k, "")) != nw(b.get(k, "")):
                bad.append(f"{w}：{k} が、2人の読みで違う（{a.get(k)} / {b.get(k)}）")
        if a["gaibu"]["kekka"] != b["gaibu"]["kekka"]:
            bad.append(f"{w}：検証結果が、2人の読みで違う")
        s = sr.get((a["kihon_no"], a["no"]))
        if s is None or norm(s["name"]) != norm(a["name"]) or norm(s["kihon"]) != norm(a["kihon"]):
            bad.append(f"{w}：総合戦略（{PLAN}）の取り組みと、基本目標の番号、取り組みの番号と名前が合わない"
                       f"（基本目標{a['kihon_no']} 取り組み{a['no']} {a['name']}）")
            continue
        key = f"node:{PLAN}/{s['key']}"
        if key in seen_key:
            bad.append(f"{w}：取り組み {key} が、シート {seen_key[key]} にもある")
        seen_key[key] = p
        if not s["honpen"]:
            bad.append(f"{w}：総合戦略の本編に、取り組みの名前と担当課の字があるページが見つからない（{key}）")
        w = f"シート {p}（{key}）"
        for k in ("kihon", "name", "houkou", "tantou"):
            if a[k] and nw(a[k]) not in src_all:
                bad.append(f"{w}：{k} の字が、シートの本文に無い")
        for r in SHEET_RAN:
            if not midashi_of(rans[r], src_all):
                bad.append(f"{w}：欄の見出し「{rans[r]['midashi']}」が、シートの本文に無い")
        if a["gaibu"]["kekka"] not in kekka_ok:
            bad.append(f"{w}：検証結果「{a['gaibu']['kekka']}」が、検証結果の説明の表に無い")
        for v in (a["tasseido"], a["gaibu"]["kekka"]):
            if nw(v) not in kazu_src:
                bad.append(f"{w}：「{v}」が、シートの本文に無い")
        chu = []
        if norm(a["tantou"]) not in norm(s["dept"]):
            chu.append(f"シートの担当部署の字（{a['tantou']}）が、総合戦略の担当課の字（{s['dept']}）に無い")
        if norm(a["houkou"]) != norm(s["houkou"]):
            chu.append(f"シートの取り組みの方向の字（{a['houkou']}）が、総合戦略の取り組みの方向（{s['houkou']}）と違う")
        out["torikumi"].append(dict(torikumi=key, kihon_no=a["kihon_no"], kihon=a["kihon"], no=a["no"], name=a["name"],
                                    houkou=a["houkou"], tantou=a["tantou"], tasseido=a["tasseido"],
                                    kekka=a["gaibu"]["kekka"], shiryo=f"{SHIRYO}/{p}", honpen=s["honpen"],
                                    chu="。".join(chu)))
        # KPI
        if [kpi_key(x) for x in a["kpi"]] != [kpi_key(x) for x in b["kpi"]]:
            bad.append(f"{w}：KPI が、2人の読みで違う")
        for i, k in enumerate(a["kpi"], 1):
            if nw(k["shihyo"]) not in kazu_src:
                bad.append(f"{w}：指標 {i} の名前が、シートの本文に無い")
            for v in (k["kijun_midashi"], k["kijun"]):
                if nw(v) and nw(v) not in kazu_src:
                    bad.append(f"{w}：指標 {i} の「{v}」が、シートの本文に無い")
            for r in k["rows"]:
                ny = nendo_of(r["nendo"])
                if not ny:
                    bad.append(f"{w}：指標 {i} の年度の形が違う（{r['nendo']}）")
                for c in ("mokuhyo", "jisseki", "tasseiritsu"):
                    if nw(r[c]) and nw(r[c]) not in kazu_src:
                        bad.append(f"{w}：指標 {i} の {r['nendo']} の {c}「{r[c]}」が、シートの本文に無い")
                out["kpi"].append(dict(torikumi=key, shihyo_n=str(i), shihyo=k["shihyo"], kijun_midashi=k["kijun_midashi"],
                                       kijun=k["kijun"], nendo_ji=r["nendo"], nendo=ny, mokuhyo=r["mokuhyo"],
                                       jisseki=r["jisseki"], tasseiritsu=r["tasseiritsu"], shiryo=f"{SHIRYO}/{p}",
                                       yomi=ICCHI, chu=""))
        # 文の欄
        for ran in RAN:
            sec = "gaibu" if ran in GAIBU else "naibu"
            ya, yb = a[sec].get(ran), b[sec].get(ran)
            if not isinstance(ya, list) or not isinstance(yb, list):
                bad.append(f"{w}：欄 {ran} が並びでない")
                continue
            ms = midashi_of(rans[ran], src_all)
            if not ya and not yb:
                continue
            if len(ms) != 1:
                bad.append(f"{w}：欄 {ran} の見出しが、シートの本文に1つに決まらない（{'、'.join(ms) or '無い'}）")
                continue
            rows, more = ran_rows(p, key, ran, ya, yb, ms[0], src)
            out["bun"] += rows
            bad += more
        # 分野と基本施策
        ba = [(x["no"], x["shisaku"]) for x in a["bunya"]]
        bb = [(x["no"], x["shisaku"]) for x in b["bunya"]]
        for y, bs in (("a", ba), ("b", bb)):
            if len(bs) > BUNYA_MAX or len(set(bs)) != len(bs):
                bad.append(f"{w}：読み手 {y} の分野の書き方が違う")
            for no, sh in bs:
                if sh not in ss.get(no, set()):
                    bad.append(f"{w}：読み手 {y} の分野 {no} の基本施策 {sh} が、入力の総合計画に無い")
        if not ba or ba[:1] != bb[:1]:
            bad.append(f"{w}：最初に書いた分野と基本施策が、2人の読みで違う")
        mayoi = "、".join(y for y, d_ in (("a", a), ("b", b)) if any(x.get("mayoi", "").strip() == "1" for x in d_["bunya"]))
        for x in list(dict.fromkeys(ba + bb)):
            ys = [y for y, bs in (("a", ba), ("b", bb)) if x in bs]
            saisho = [y for y, bs in (("a", ba), ("b", bb)) if bs[:1] == [x]]
            c = "。".join(t for t in (f"読み手 {ys[0]} だけが付けた" if len(ys) == 1 else "",
                                      f"迷いの印：読み手 {mayoi}" if mayoi else "") if t)
            out["bunya"].append(dict(torikumi=key, bunya=x[0], shisaku=x[1],
                                     saisho=ICCHI if len(saisho) == 2 else IKKAI if saisho else "",
                                     yomi=ICCHI if len(ys) == 2 else IKKAI, chu=c))
    want = set(sr)
    have = {(r["kihon_no"], r["no"]) for r in out["torikumi"]}
    bad += [f"総合戦略の取り組み（基本目標{k[0]} 取り組み{k[1]}）のシートが、読み取りの結果に無い" for k in sorted(want - have)]
    return out, bad


def dumps(rows, cols):
    """行 → TSV の字。値にタブか改行があれば KenshoError（字を変えない）。"""
    for r in rows:
        for c in cols:
            if "\t" in r[c] or "\n" in r[c]:
                raise KenshoError(f"{r.get('torikumi')} の {c} に、タブか改行がある")
    return "\t".join(cols) + "\n" + "".join("\t".join(r[c] for c in cols) + "\n" for r in rows)


def tsukuru(inp):
    """→ (表の名前 → 行の並び, 問題の並び)。読み取りの結果と表と入力を読んで、検査してから行を作る。"""
    ran_tbl, kekka_tbl = read_ran(), read_kekka()
    bad = check_ran(ran_tbl) + check_kekka(inp, kekka_tbl)
    if bad:
        return {}, bad
    out, more = make(inp, read_yomi(), ran_tbl, kekka_tbl)
    return out, bad + more


def check(inp, tbl):
    """作った表（read_all の形）の検査 → 問題の並び。MCP の応答と試作のページを作るときに使う。作り直した行と同じこと。"""
    out, bad = tsukuru(inp)
    if bad:
        return bad
    return [f"{os.path.relpath(PATHS[k], inputs.ROOT)} が、読み取りの結果から作り直した行と違う。python3 -B tools/kensho.py で"
            "作り直して、コミットする" for k in PATHS if dumps(out[k], ALL_COLS[k]) != dumps(tbl[k], ALL_COLS[k])]


# ---- 出すときのまとめ（MCP の応答と試作のページで共通） ----

def matome(inp, tbl=None):
    """→ (まとめ, 問題の並び)。tbl は read_all の形（None なら読む）。表を作り直して同じかを確認してから、まとめる。
    まとめ：tori（取り組みの ID → 取り組みの表の行。表の順）、sr（取り組みの ID → 総合戦略の行。senryaku の形）、
    kpi（ID → 指標の並び。指標ごとに (指標の最初の行, 年度の行の並び（nendo の順）)）、bun（ID → [(欄の ID, 見出し, 行の並び)]。
    欄の表の順）、bunya（ID → 取り組みと分野の対応の表の行の並び）、naka（ID → 中身を出す分野の番号）、
    ran（欄の ID → 欄の表の行）、kekka（検証結果の説明の表の行）。"""
    tbl = read_all() if tbl is None else tbl
    bad = check(inp, tbl)
    if bad:
        return None, bad
    sr = {f"node:{PLAN}/{x['key']}": x for x in senryaku(inp).values()}
    ran = {r["ran"]: r for r in read_ran()}
    tori = {r["torikumi"]: r for r in tbl["torikumi"]}
    kpi, bun, bunya, naka = {}, {}, {}, {}
    for r in tbl["kpi"]:
        sh = kpi.setdefault(r["torikumi"], {})
        sh.setdefault(r["shihyo_n"], []).append(r)
    kpi = {k: [(rs[0], sorted(rs, key=lambda r: r["nendo"])) for _, rs in sorted(v.items(), key=lambda x: int(x[0]))]
           for k, v in kpi.items()}
    for r in tbl["bun"]:
        bun.setdefault(r["torikumi"], {}).setdefault(r["ran"], []).append(r)
    bun = {k: [(x, v[x][0]["midashi"], v[x]) for x in RAN if x in v] for k, v in bun.items()}
    for r in tbl["bunya"]:
        bunya.setdefault(r["torikumi"], []).append(r)
        if r["saisho"] == ICCHI:
            naka[r["torikumi"]] = r["bunya"]
    return dict(tori=tori, sr=sr, kpi=kpi, bun=bun, bunya=bunya, naka=naka, ran=ran, kekka=read_kekka()), []


def main(argv=None):
    ap = argparse.ArgumentParser(description="施策検証結果報告書の記述の表を作る")
    ap.add_argument("--kensa", action="store_true")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        out, bad = tsukuru(inp)
    except (inputs.InputError, KenshoError, bu.BunyaError, OSError, ValueError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    t, k, bn_, by = out["torikumi"], out["kpi"], out["bun"], out["bunya"]
    n = {y: sum(r["yomi"] == y for r in by) for y in YOMI}
    nb = {y: sum(r["yomi"] == y for r in bn_) for y in YOMI}
    print(f"取り組み {len(t)}（注のある行 {sum(bool(r['chu']) for r in t)}）。KPI の指標 "
          f"{len({(r['torikumi'], r['shihyo_n']) for r in k})}、行 {len(k)}。文の項目 {len(bn_)}（一致 {nb[ICCHI]}、"
          f"1回だけ {nb[IKKAI]}）。分野との対応 {len(by)}（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）")
    if a.kensa:
        diff = []
        for name, path in PATHS.items():
            moto = None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    moto = f.read()
            if moto != dumps(out[name], ALL_COLS[name]):
                diff.append(os.path.relpath(path, inputs.ROOT))
        if diff:
            print(f"止めた：作り直した行が {'、'.join(diff)} と違う。python3 -B tools/kensho.py で作り直して、コミットする。",
                  file=sys.stderr)
            return 1
        print("4つの表と同じ")
        return 0
    for name, path in PATHS.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(dumps(out[name], ALL_COLS[name]))
        print(f"{os.path.relpath(path, inputs.ROOT)}（{len(out[name])} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
