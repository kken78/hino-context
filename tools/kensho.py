"""総合戦略の施策検証結果報告書の施策検証シートの記述（SCHEMA.md 7.12）。

施策検証シートの表（シート、KPI、文の項目）と検収の台帳は、入力の hino-town-docs の構造化の層にある
（data/struct/senryaku-sheet.tsv、senryaku-kpi.tsv、senryaku-bun.tsv、audit/senryaku.tsv。DOCS_SCHEMA.md §13.17）。
このツールは、それを読むだけで、シートの字と本文の照合はしない（入力の側の段1 が行っている）。
このリポジトリで作るのは、取り組みと、第6次日野町総合計画の分野・基本施策の対応の表（taio/kensho-bunya.tsv）だけで、
生成AIの2回の読み取りの結果（taio/yomi-kensho/ の bunya）から作る。MCP の応答（tools/build_mcp.py の field と review）と
試作のページ（tools/build_bunya.py）は、matome で、入力の表とこの表をまとめて使う。

使い方：
  python3 -B tools/kensho.py            taio/kensho-bunya.tsv を作る
  python3 -B tools/kensho.py --kensa    作り直した行が taio/kensho-bunya.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの：
  taio/yomi-kensho/taba.json、<読み手>-p<3桁>.json   読み手（a と b）の出力。使うのは kihon_no、no と bunya だけ
  teigi/kensho-ran.tsv                    施策検証の欄の表（欄の見出しの字。報告書の字のまま）
  teigi/kensho-kekka.tsv                  検証結果の説明の表（報告書の「２．検証方法」の文）
  入力：hino-town-docs の施策検証シートの表と検収の台帳、報告書の文字（検証結果の説明の照合）、
  shiga-hino-plans の総合戦略（data/plans/senryaku2.json と本編の文字）、第6次日野町総合計画（data/plans/sogo6.json）

合わないものがあれば、件数と該当を示して止まる。手で行を書かない。
"""
import argparse
import json
import os
import re
import sys

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
DEPT_SEP = "・"                      # 担当課・担当部署の、課の区切り（本編の dept と、入力のシートの tantou）
YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi-kensho")
RAN_PATH = os.path.join(inputs.ROOT, "teigi", "kensho-ran.tsv")
KEKKA_PATH = os.path.join(inputs.ROOT, "teigi", "kensho-kekka.tsv")
PATH = os.path.join(inputs.ROOT, "taio", "kensho-bunya.tsv")
BUNYA_COLS = ["torikumi", "bunya", "shisaku", "saisho", "yomi", "chu"]
RAN_COLS = ["ran", "kubun", "midashi", "chu"]
KEKKA_COLS = ["shu", "kekka", "inyo", "tokoro", "chu"]
# 入力の表（hino-town-docs DOCS_SCHEMA.md §13.17）
SHEET_PATH = "data/struct/senryaku-sheet.tsv"
KPI_PATH = "data/struct/senryaku-kpi.tsv"
BUN_PATH = "data/struct/senryaku-bun.tsv"
AUDIT_PATH = "data/struct/audit/senryaku.tsv"
SHEET_COLS = ["doc", "page", "insatsu_page", "kihon_no", "kihon", "no", "name", "houkou", "tantou", "tasseido", "kekka",
              "note"]
KPI_COLS = ["doc", "page", "no", "shihyo_n", "shihyo", "nendo", "mokuhyo", "jisseki", "tasseiritsu", "tani", "note"]
BUN_COLS = ["doc", "page", "no", "ran", "n", "line", "note"]
AUDIT_COLS = ["key", "table", "row", "cols", "value", "unit", "source", "checked", "reviewer", "date", "note"]
TABLES = (("senryaku-sheet", "sheet", SHEET_PATH, SHEET_COLS), ("senryaku-kpi", "kpi", KPI_PATH, KPI_COLS),
          ("senryaku-bun", "bun", BUN_PATH, BUN_COLS))
CHECKED = "✓"                        # 検収の台帳の checked（段1・段2 が通った行）
AUTO = "auto:"                       # 検収の台帳の reviewer のうち、ツールの印の頭の字。これで始まらない reviewer は人の印
CHIGAU = "欄の見出しが決まりと違う："    # 入力のシートの note の、欄の見出しが決まりと違うことの注の頭の字
RE_KAKKO = re.compile(r"「([^「」]+)」")
MARU = "●"                           # ④⑤の欄の見出しの頭の字（入力の note の字に付いている）
RE_KAZU = re.compile(r"[0-9][0-9,.]*")
RE_NENDO = re.compile(r"令和")       # 入力の KPI の nendo の字のうち、年度の行の頭の字。ほかは基準値の行（「基準値【R2】」）
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
RAN_KUBUN = ("sheet", "kpi", "naibu", "gaibu")
NAIBU = ("jokyo", "kongo", "seika", "dekiteinai", "konnan", "fumaete", "kadai")      # 入力の ran（報告書の②〜⑤の順）
GAIBU = ("comment",)
RAN = NAIBU + GAIBU
SHEET_RAN = ("kihon", "houkou", "tantou", "kpi", "shihyo", "mokuhyo", "jisseki", "tasseiritsu", "tasseido", "naibu",
             "gaibu", "kekka")        # 画面に出す、シートの欄の見出し
KEKKA_SHU = ("kekka", "tasseido")
BUNYA_MAX = 3                        # 1つの取り組みに付ける分野の数の上限（読み手への指示）


class KenshoError(ValueError):
    """読み取りの結果、表、入力が、決まりに合わない。"""


def norm(s):
    """資料どうしの字を照合するときの正規化（SCHEMA.md §3。総合戦略の本編と報告書の字の照合）。"""
    return shogo.norm(s)


def read_tsv(path, cols):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), cols)


def read_ran(path=RAN_PATH):
    return read_tsv(path, RAN_COLS)


def read_kekka(path=KEKKA_PATH):
    return read_tsv(path, KEKKA_COLS)


def read(path=PATH):
    """taio/kensho-bunya.tsv の行。"""
    return read_tsv(path, BUNYA_COLS)


def kohos(r):
    """欄の表の行 → 見出しの字の候補の並び（最初が、決まりの字）。"""
    return [x.strip() for x in r["midashi"].split(";") if x.strip()]


def check_ran(rows):
    """欄の表の検査 → 問題の並び。ran が重ならず、kubun が決めた字で、midashi が空でないこと。入力の欄と、画面に出す
    シートの欄の見出しが、全部あること。"""
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
    shu と kekka の組が重ならないこと。"""
    bad, seen = [], set()
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

def read_struct(inp):
    """入力の施策検証シートの表と検収の台帳 → dict(sheet, kpi, bun, audit)。報告書（DOC）の行だけ。"""
    out = {}
    for _, key, path, cols in TABLES:
        rows = inputs.read_tsv(inp.read_bytes(inputs.TD, path), f"{inputs.TD} {path}", cols)
        out[key] = [r for r in rows if r["doc"] == DOC]
    rows = inputs.read_tsv(inp.read_bytes(inputs.TD, AUDIT_PATH), f"{inputs.TD} {AUDIT_PATH}", AUDIT_COLS)
    out["audit"] = [r for r in rows if r["row"].startswith(DOC + "/")]
    return out


def row_id(table, r):
    """入力の表の行 → 検収の台帳の row の字（DOCS_SCHEMA.md §13.17）。"""
    if table == "senryaku-sheet":
        return f"{r['doc']}/{r['page']}"
    if table == "senryaku-kpi":
        return f"{r['doc']}/{r['page']}/{r['shihyo_n']}/{r['nendo']}"
    return f"{r['doc']}/{r['page']}/{r['ran']}/{r['n']}"


def kenshu(st):
    """入力の表と台帳 → (表 → 出す行の並び, 出さない行（台帳の checked が空の行）の数, 問題の並び, ページ → 人の確認が
    済んでいるか)。台帳に行が無い表の行があれば問題。人の確認が済んでいるシートは、そのシートの全部の行（シート、KPI、
    文の項目）の台帳の reviewer が、auto: で始まらない（人の印）もの。"""
    au = {(r["table"], r["row"]): r for r in st["audit"]}
    out, nashi, bad, hito = {}, 0, [], {}
    for table, key, _, _ in TABLES:
        out[key] = []
        for r in st[key]:
            a = au.get((table, row_id(table, r)))
            if a is None:
                bad.append(f"{table} の行 {row_id(table, r)} が、検収の台帳に無い")
                continue
            hito[r["page"]] = hito.get(r["page"], True) and not a["reviewer"].startswith(AUTO)
            if a["checked"] != CHECKED:
                nashi += 1
                continue
            out[key].append(r)
    return out, nashi, bad, hito


def senryaku(inp):
    """総合戦略の取り組み → {(基本目標の番号, 取り組みの番号): dict(key, kihon, houkou, no, name, dept, honpen)}。
    基本目標の番号と名前は、取り組みの tab の heading（「基本目標1 …」）から、取り組みの方向は groups の name から取る。
    honpen は、取り組みの名前（本編の「※」の印を除いて照合する）と担当課の字（課ごと）がある本編のページ（pt の ID）。
    block の source の印刷のページの範囲に、sources の pdf_page_offset を足した PDF のページから探す。"""
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


def musubi(sheets, sr):
    """入力のシートの行 → (ページ → 総合戦略の取り組みの ID, 問題の並び)。基本目標の番号と取り組みの番号で、総合戦略の
    取り組みに結び付け、基本目標と取り組みの名前が §3 の正規化で同じであること。総合戦略の取り組みのうち、シートが無いもの
    があっても止まる。"""
    out, bad, seen = {}, [], set()
    for r in sheets:
        s = sr.get((r["kihon_no"], r["no"]))
        if s is None or norm(s["name"]) != norm(r["name"]) or norm(s["kihon"]) != norm(r["kihon"]):
            bad.append(f"シート {r['page']}：総合戦略（{PLAN}）の取り組みと、基本目標の番号、取り組みの番号と名前が合わない"
                       f"（基本目標{r['kihon_no']} 取り組み{r['no']} {r['name']}）")
            continue
        if not s["honpen"]:
            bad.append(f"シート {r['page']}：総合戦略の本編に、取り組みの名前と担当課の字があるページが見つからない")
        out[r["page"]] = f"node:{PLAN}/{s['key']}"
        seen.add((r["kihon_no"], r["no"]))
    bad += [f"総合戦略の取り組み（基本目標{k[0]} 取り組み{k[1]}）のシートが、入力の表に無い" for k in sorted(set(sr) - seen)]
    return out, bad


def midashi(sheet, ran_tbl):
    """入力のシートの行 → 欄の ID → そのシートの欄の見出しの字。入力の note の「欄の見出しが決まりと違う：」の注にある
    見出しの字（「●」を除く）が、施策検証の欄の表の候補にあれば、その欄の見出しにする。ほかは、決まりの字（最初の候補）。"""
    out = {r["ran"]: kohos(r)[0] for r in ran_tbl}
    note = sheet["note"]
    if CHIGAU in note:
        part = note.split(CHIGAU, 1)[1].split("。", 1)[0]
        for ji in RE_KAKKO.findall(part):
            ji = ji.lstrip(MARU)
            for r in ran_tbl:
                if ji in kohos(r):
                    out[r["ran"]] = ji
    return out


def tani_tsuki(v, tani):
    """入力の KPI の値と tani → 値が数（数字・「,」・「.」）だけなら、数のあとに単位を付けた字。ほかは値のまま。"""
    return v + tani if tani and RE_KAZU.fullmatch(v) else v


def onaji(a, b):
    """シートの字と本編の字が、§3 の正規化で同じか。"""
    return norm(a) == norm(b)


# ---- 読み取りの結果（分野と基本施策） ----

def read_taba(yomi_dir=YOMI_DIR):
    with open(os.path.join(yomi_dir, "taba.json"), encoding="utf-8") as f:
        return json.load(f)


def read_yomi(yomi_dir=YOMI_DIR):
    """→ {最初のページ（字）: {読み手: 出力}}（束の順）。ファイルが無い、読めない、pages が違う、同じシートが2回あれば
    KenshoError。"""
    out, bad = {}, []
    for t in read_taba(yomi_dir):
        for p in t:
            if str(p) in out:
                bad.append(f"シート {p} が、束に2回ある")
            out[str(p)] = {}
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
                out[str(p)][y] = d
    if bad:
        raise KenshoError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return out


def bunya_rows(yomi, sheets, key_of, ss):
    """読み取りの結果 → (taio/kensho-bunya.tsv の行, 問題の並び)。読み手の基本目標の番号と取り組みの番号が、入力のシートの
    行と同じであること。分野の番号と基本施策が入力の総合計画にあり、最初に書いた組が2人で同じであること。"""
    out, bad = [], []
    sh = {r["page"]: r for r in sheets}
    if set(yomi) != set(sh):
        bad.append(f"読み取りの結果のシート（{len(yomi)}）と、入力のシート（{len(sh)}）が合わない")
    for p, d in yomi.items():
        r = sh.get(p)
        if r is None or p not in key_of:
            continue
        a, b = d["a"], d["b"]
        w = f"シート {p}（{key_of[p]}）"
        if any((x["kihon_no"], x["no"]) != (r["kihon_no"], r["no"]) for x in (a, b)):
            bad.append(f"{w}：読み取りの結果の基本目標の番号か取り組みの番号が、入力のシートと違う")
        ba = [(x["no"], x["shisaku"]) for x in a["bunya"]]
        bb = [(x["no"], x["shisaku"]) for x in b["bunya"]]
        for y, bs in (("a", ba), ("b", bb)):
            if len(bs) > BUNYA_MAX or len(set(bs)) != len(bs):
                bad.append(f"{w}：読み手 {y} の分野の書き方が違う")
            for no, s in bs:
                if s not in ss.get(no, set()):
                    bad.append(f"{w}：読み手 {y} の分野 {no} の基本施策 {s} が、入力の総合計画に無い")
        if not ba or ba[:1] != bb[:1]:
            bad.append(f"{w}：最初に書いた分野と基本施策が、2人の読みで違う")
        mayoi = "、".join(y for y, d_ in (("a", a), ("b", b)) if any(x.get("mayoi", "").strip() == "1" for x in d_["bunya"]))
        for x in list(dict.fromkeys(ba + bb)):
            ys = [y for y, bs in (("a", ba), ("b", bb)) if x in bs]
            saisho = [y for y, bs in (("a", ba), ("b", bb)) if bs[:1] == [x]]
            c = "。".join(t for t in (f"読み手 {ys[0]} だけが付けた" if len(ys) == 1 else "",
                                      f"迷いの印：読み手 {mayoi}" if mayoi else "") if t)
            out.append(dict(torikumi=key_of[p], bunya=x[0], shisaku=x[1],
                            saisho=ICCHI if len(saisho) == 2 else IKKAI if saisho else "",
                            yomi=ICCHI if len(ys) == 2 else IKKAI, chu=c))
    return out, bad


def dumps(rows, cols=BUNYA_COLS):
    """行 → TSV の字。値にタブか改行があれば KenshoError（字を変えない）。"""
    for r in rows:
        for c in cols:
            if "\t" in r[c] or "\n" in r[c]:
                raise KenshoError(f"{r.get('torikumi')} の {c} に、タブか改行がある")
    return "\t".join(cols) + "\n" + "".join("\t".join(r[c] for c in cols) + "\n" for r in rows)


def tsukuru(inp):
    """→ (taio/kensho-bunya.tsv の行, 問題の並び, 中間のもの)。入力と表を読んで、検査してから行を作る。"""
    ran_tbl, kekka_tbl = read_ran(), read_kekka()
    bad = check_ran(ran_tbl) + check_kekka(inp, kekka_tbl)
    st = read_struct(inp)
    tbl, nashi, more, hito = kenshu(st)
    bad += more
    sr = senryaku(inp)
    key_of, more = musubi(st["sheet"], sr)
    bad += more
    rows, more = bunya_rows(read_yomi(), st["sheet"], key_of, sogo_shisaku(inp))
    bad += more
    return rows, bad, dict(tbl=tbl, nashi=nashi, hito=hito, sr=sr, key_of=key_of, ran=ran_tbl, kekka=kekka_tbl)


# ---- 出すときのまとめ（MCP の応答と試作のページで共通） ----

def matome(inp):
    """→ (まとめ, 問題の並び)。taio/kensho-bunya.tsv が作り直した行と同じかを確認してから、まとめる。
    まとめ：tori（取り組みの ID → 入力のシートの行。シートの順）、sr（取り組みの ID → 総合戦略の行。senryaku の形）、
    kpi（ID → 指標の並び。指標ごとに (基準値の行（無ければ None）, 年度の行の並び（入力の順）)）、
    bun（ID → [(欄の ID, そのシートの見出しの字, 行の並び)]。欄の表の順）、bunya（ID → 対応の表の行の並び）、
    naka（ID → 中身を出す分野の番号）、ran（欄の ID → 欄の表の行）、kekka（検証結果の説明の表の行）、
    hito（ID → 人の確認が済んでいるか）、nashi（検収の台帳で checked が空のため出さない行の数）。"""
    rows, bad, x = tsukuru(inp)
    if bad:
        return None, bad
    have = read()
    if dumps(rows) != dumps(have):
        return None, ["taio/kensho-bunya.tsv が、読み取りの結果から作り直した行と違う。python3 -B tools/kensho.py で"
                      "作り直して、コミットする"]
    key_of, tbl = x["key_of"], x["tbl"]
    sr = {f"node:{PLAN}/{s['key']}": s for s in x["sr"].values()}
    tori = {key_of[r["page"]]: r for r in tbl["sheet"]}
    kpi, bun, bunya, naka = {}, {}, {}, {}
    for r in tbl["kpi"]:
        sh = kpi.setdefault(key_of[r["page"]], {}).setdefault(r["shihyo_n"], [None, []])
        if not RE_NENDO.match(r["nendo"]):
            sh[0] = r
        else:
            sh[1].append(r)
    kpi = {k: [tuple(v[n]) for n in sorted(v, key=int)] for k, v in kpi.items()}
    for r in tbl["bun"]:
        bun.setdefault(key_of[r["page"]], {}).setdefault(r["ran"], []).append(r)
    mi = {key_of[r["page"]]: midashi(r, x["ran"]) for r in tbl["sheet"]}
    bun = {k: [(ran, mi[k][ran], v[ran]) for ran in RAN if ran in v] for k, v in bun.items()}
    for r in have:
        bunya.setdefault(r["torikumi"], []).append(r)
        if r["saisho"] == ICCHI:
            naka[r["torikumi"]] = r["bunya"]
    hito = {key_of[p]: v for p, v in x["hito"].items() if p in key_of}
    return dict(tori=tori, sr=sr, kpi=kpi, bun=bun, bunya=bunya, naka=naka, ran={r["ran"]: r for r in x["ran"]},
                kekka=x["kekka"], hito=hito, nashi=x["nashi"]), []


def main(argv=None):
    ap = argparse.ArgumentParser(description="取り組みと総合計画の分野の対応の表を作る")
    ap.add_argument("--kensa", action="store_true")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        rows, bad, x = tsukuru(inp)
    except (inputs.InputError, KenshoError, bu.BunyaError, OSError, ValueError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    t = x["tbl"]
    print(f"入力の表：シート {len(t['sheet'])}、KPI の行 {len(t['kpi'])}、文の項目 {len(t['bun'])}（検収の台帳で checked が空の"
          f"ため出さない行 {x['nashi']}。人の確認が済んだシート {sum(x['hito'].values())}）。"
          f"分野との対応 {len(rows)}（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）")
    s = dumps(rows)
    if a.kensa:
        moto = None
        if os.path.exists(PATH):
            with open(PATH, encoding="utf-8") as f:
                moto = f.read()
        if moto != s:
            print("止めた：作り直した行が taio/kensho-bunya.tsv と違う。python3 -B tools/kensho.py で作り直して、コミットする。",
                  file=sys.stderr)
            return 1
        print(f"taio/kensho-bunya.tsv と同じ（{len(rows)} 行）")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"taio/kensho-bunya.tsv（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
