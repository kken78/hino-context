"""総合戦略の施策検証結果報告書の施策検証シートの記述（SCHEMA.md 7.12）。

読むのは、令和3〜7年度の5冊の報告書（DOCS。新しい年度から）。取り組みは、5冊とも、総合戦略の取り組みに、基本目標の番号と
取り組みの番号と名前で結び付ける（合わないシートは結び付けず、止まる）。

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

DOCS = tuple(f"hyoka-r{n}-senryaku-kensho" for n in (7, 6, 5, 4, 3))   # hino-town-docs の報告書の id。新しい年度から
DOC = DOCS[0]                        # いちばん新しい報告書。分野の読み取り（taio/yomi-kensho/）と、検証結果の説明の表の tokoro
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
KPI_COLS = ["doc", "page", "no", "shihyo_n", "shihyo", "shu", "nendo", "mokuhyo", "jisseki", "tasseiritsu", "tani", "note"]
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
SHU = ("kijun", "mokuhyochi", "nendo", "mokuhyochi_shita")   # 入力の KPI の shu（基準値の行、基準値の下の目標値の行、年度の
                                                              # 行、年度の行の下の目標値の行）。この順に並ぶ
NENDO = "nendo"
RE_NENDO_NO = re.compile(r"令和([0-9]+)年度")    # 年度の行の nendo の字（§3 の正規化のあと）→ 年度の番号
NIKAI = "2人の読みが違う"              # 入力の行の note の、起票の2人の読みが違ったため値を書いていないことの字
RE_NIKAI = re.compile(r"([a-z_]+|項目) は2人の読みが違う")   # その列（項目の表は「項目」の字で line を指す）
RE_DAN1 = re.compile(r"要人確認:段1 (.*?)(?:。要人確認:|$)")   # 検収の台帳の note の、段1 で合わない列と理由の部分
RE_DAN1_COL = re.compile(r"(?:^|・)([a-z_]+)：")                 # その部分の列の名前
KEY_COLS = ("doc", "page", "kihon_no", "kihon", "no", "name", "note")   # シートの行のうち、出さないことにできない列
MIDASHI_KAKKO = "●《》≪≫"            # 欄の見出しの頭と終わりの字（入力の note の字に付いている。令和3年度は《》≪≫）
RE_HOKOKU_NENDO = re.compile(r"（(令和[^（）]+年度)）$")   # 資料の一覧の表の namae の、報告書の年度の字
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
    """入力の施策検証シートの表と検収の台帳 → dict(sheet, kpi, bun, audit)。5冊の報告書（DOCS）の行だけ。"""
    out = {}
    for _, key, path, cols in TABLES:
        rows = inputs.read_tsv(inp.read_bytes(inputs.TD, path), f"{inputs.TD} {path}", cols)
        out[key] = [r for r in rows if r["doc"] in DOCS]
    rows = inputs.read_tsv(inp.read_bytes(inputs.TD, AUDIT_PATH), f"{inputs.TD} {AUDIT_PATH}", AUDIT_COLS)
    out["audit"] = [r for r in rows if r["row"].split("/", 1)[0] in DOCS]
    return out


def row_id(table, r):
    """入力の表の行 → 検収の台帳の row の字（DOCS_SCHEMA.md §13.17）。"""
    if table == "senryaku-sheet":
        return f"{r['doc']}/{r['page']}"
    if table == "senryaku-kpi":
        return f"{r['doc']}/{r['page']}/{r['shihyo_n']}/{r['shu']}/{r['nendo']}"
    return f"{r['doc']}/{r['page']}/{r['ran']}/{r['n']}"


def dan1_cols(note):
    """検収の台帳の note → 段1 で合わない列の名前の並び（「要人確認:段1 tasseido：…」の tasseido）。"""
    m = RE_DAN1.search(note or "")
    return RE_DAN1_COL.findall(m.group(1)) if m else []


def nikai_cols(note):
    """入力の行の note → 起票の2人の読みが違ったため値を書いていない列の並び（項目の表の「項目」は line）。"""
    return list(dict.fromkeys("line" if c == "項目" else c for c in RE_NIKAI.findall(note or "")))


def kenshu(st):
    """入力の表と台帳 → (表 → 出す行の並び, 出さない行の数, 問題の並び, (doc, page) → 人の確認が済んでいるか)。
    出す行は、入力の行の写しに、_mada（出さない列。シートの行で、検収の台帳で checked が空のときの、段1 で合わない列）と
    _chigau（起票の2人の読みが違ったため空の列）を足したもの。検収の台帳で checked が空の行は、次のとおり（SCHEMA.md 7.12）。
      シートの行：段1 で合わない列だけを空にして出す（列が分からないか、シートを決める列なら問題）。
      KPI と項目の行：入力の note に「2人の読みが違う」があり、段1 で合わない列がその列と note だけなら、空のまま出す。
      ほかは出さない（出さない行の数は (doc, page) → 表 → 数）。
    台帳に行が無い表の行があれば問題。人の確認が済んでいるシートは、そのシートの全部の行（シート、KPI、文の項目）の台帳の
    reviewer が、auto: で始まらない（人の印）もの。"""
    au = {(r["table"], r["row"]): r for r in st["audit"]}
    out, nashi, bad, hito = {}, {}, [], {}
    for table, key, _, _ in TABLES:
        out[key] = []
        for r in st[key]:
            a = au.get((table, row_id(table, r)))
            if a is None:
                bad.append(f"{table} の行 {row_id(table, r)} が、検収の台帳に無い")
                continue
            sp = (r["doc"], r["page"])
            hito[sp] = hito.get(sp, True) and not a["reviewer"].startswith(AUTO)
            x = dict(r, _mada=[], _chigau=nikai_cols(r["note"]) if NIKAI in r["note"] else [])
            if any(x[c] for c in x["_chigau"]):
                bad.append(f"{table} の行 {row_id(table, r)}：2人の読みが違うと note にある列に、値がある")
            if a["checked"] == CHECKED:
                out[key].append(x)
                continue
            cols = dan1_cols(a["note"])
            if table == "senryaku-sheet":
                if not cols or any(c not in SHEET_COLS or c in KEY_COLS for c in cols):
                    bad.append(f"{table} の行 {row_id(table, r)}：検収の台帳で checked が空で、段1 で合わない列が分からないか、"
                               f"シートを決める列（{'、'.join(cols)}）")
                    continue
                x["_mada"] = cols
                for c in cols:
                    x[c] = ""
                out[key].append(x)
            elif x["_chigau"] and set(cols) <= {"note"} | set(x["_chigau"]):
                out[key].append(x)
            else:
                d = nashi.setdefault(sp, {})
                d[key] = d.get(key, 0) + 1
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
    """入力のシートの行（5冊）→ ((doc, page) → 総合戦略の取り組みの ID, 問題の並び)。報告書ごとに、基本目標の番号と取り組みの
    番号で総合戦略の取り組みに結び付け、基本目標と取り組みの名前が §3 の正規化で同じであること。番号か名前が合わないシートは
    結び付けず（推し量って結ばない）、問題として、報告書とページと、シートの番号と名前を出す。報告書ごとに、総合戦略の
    取り組みのうちシートが無いものか、同じ取り組みのシートが2つあっても止まる。"""
    out, bad = {}, []
    for doc in DOCS:
        seen = {}
        for r in (x for x in sheets if x["doc"] == doc):
            s = sr.get((r["kihon_no"], r["no"]))
            if s is None or norm(s["name"]) != norm(r["name"]) or norm(s["kihon"]) != norm(r["kihon"]):
                bad.append(f"{doc} のシート {r['page']}：総合戦略（{PLAN}）の取り組みと、基本目標の番号、取り組みの番号と名前が"
                           f"合わない（基本目標{r['kihon_no']} 取り組み{r['no']} {r['name']}）。結び付けていない")
                continue
            if not s["honpen"]:
                bad.append(f"{doc} のシート {r['page']}：総合戦略の本編に、取り組みの名前と担当課の字があるページが見つからない")
            k = (r["kihon_no"], r["no"])
            if k in seen:
                bad.append(f"{doc} のシート {seen[k]} と {r['page']}：同じ取り組み（基本目標{k[0]} 取り組み{k[1]}）のシート")
            seen[k] = r["page"]
            out[(doc, r["page"])] = f"node:{PLAN}/{s['key']}"
        bad += [f"{doc}：総合戦略の取り組み（基本目標{k[0]} 取り組み{k[1]}）のシートが、入力の表に無い"
                for k in sorted(set(sr) - set(seen))]
    return out, bad


def maisu(sheets):
    """入力のシートの行 → (doc → シート1枚のページの数（1か2）, 問題の並び)。報告書ごとに、シートの page の間隔で決める
    （全部が1なら1ページ、全部が2なら2ページ。DOCS_SCHEMA.md §13.17）。"""
    out, bad = {}, []
    for doc in DOCS:
        ps = sorted(int(r["page"]) for r in sheets if r["doc"] == doc)
        d = {b - a for a, b in zip(ps, ps[1:])}
        if len(d) != 1 or not d <= {1, 2}:
            bad.append(f"{doc}：シートのページの間隔が、どれも1か、どれも2でない（{sorted(d)}）")
            continue
        out[doc] = d.pop()
    return out, bad


def midashi_ji(ji):
    """欄の見出しの字 → 頭と終わりの「●」「《》」「≪≫」を除いた字。"""
    return ji.strip(MIDASHI_KAKKO)


def midashi(sheet, ran_tbl, text=""):
    """入力のシートの行と、そのシートのページの文字（§3 の正規化のあと）→ (欄の ID → そのシートの欄の見出しの字,
    問題の並び)。入力の note の「欄の見出しが決まりと違う：」の注にある見出しの字（「●」「《》」「≪≫」を除く）が、施策検証の
    欄の表の候補にあれば、その欄の見出しにする（候補に無ければ問題）。ほかの文の欄（RAN）は、候補のうち、そのシートの
    ページの文字にある最初のもの、どれも無ければ決まりの字（最初の候補）。ほかの欄は、決まりの字。"""
    out = {r["ran"]: kohos(r)[0] for r in ran_tbl}
    bad, kimata = [], set()
    note = sheet["note"]
    if CHIGAU in note:
        part = note.split(CHIGAU, 1)[1].split("。", 1)[0]
        for ji in RE_KAKKO.findall(part):
            ji = midashi_ji(ji)
            hit = [r for r in ran_tbl if ji in kohos(r)]
            if not hit:
                bad.append(f"{sheet['doc']} のシート {sheet['page']}：欄の見出し「{ji}」が、施策検証の欄の表の候補に無い")
            for r in hit:
                out[r["ran"]] = ji
                kimata.add(r["ran"])
    for r in ran_tbl:
        if r["ran"] in RAN and r["ran"] not in kimata:
            out[r["ran"]] = next((x for x in kohos(r) if norm(x) in text), kohos(r)[0])
    return out, bad


def hokoku_nendo(namae):
    """資料の一覧の表の報告書の namae → 報告書の年度の字（「…（令和７年度）」の「令和７年度」）。無ければ None。"""
    m = RE_HOKOKU_NENDO.search(namae or "")
    return m.group(1) if m else None


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
    key_of, more = musubi(tbl["sheet"], sr)
    bad += more
    mai, more = maisu(tbl["sheet"])
    bad += more
    sheets = [r for r in tbl["sheet"] if r["doc"] == DOC]
    rows, more = bunya_rows(read_yomi(), sheets, {p: k for (d, p), k in key_of.items() if d == DOC}, sogo_shisaku(inp))
    bad += more
    return rows, bad, dict(tbl=tbl, nashi=nashi, hito=hito, sr=sr, key_of=key_of, maisu=mai, ran=ran_tbl, kekka=kekka_tbl)


def nendo_no(nendo):
    """年度の行の nendo の字 → 年度の番号（「令和３年度」→ 3）。形が違えば None。"""
    m = RE_NENDO_NO.fullmatch(norm(nendo))
    return int(m.group(1)) if m else None


def hikaku(kpi_of):
    """取り組み1つの {doc: [(shihyo_n, 行の並び)]} → 指標の並び。指標ごとに dict(shihyo（いちばん新しい報告書の字）,
    nendo（[(年度の番号, [(行, その字の報告書の並び)])]。年度の古い順）)。指標名が §3 の正規化で同じものを同じ指標とし、
    年度の行（shu が nendo）を年度ごとに集めて、目標・実績・達成率の字が §3 の正規化で同じ行をまとめる（起票の2人の読みが
    違って空の列がある行は、まとめない）。行は、まとめた中でいちばん新しい報告書の行。計算しない（SCHEMA.md 7.12）。"""
    out, idx = [], {}
    for doc in DOCS:
        for _, rows in kpi_of.get(doc, []):
            k = norm(rows[0]["shihyo"])
            if k not in idx:
                idx[k] = dict(shihyo=rows[0]["shihyo"], nendo={})
                out.append(idx[k])
            for r in rows:
                if r["shu"] != NENDO:
                    continue
                g = idx[k]["nendo"].setdefault(nendo_no(r["nendo"]), {})
                key = (norm(r["mokuhyo"]), norm(r["jisseki"]), norm(r["tasseiritsu"]), tuple(r["_chigau"]))
                g.setdefault(key, [r, []])[1].append(doc)
    for x in out:
        x["nendo"] = [(n, [tuple(v) for v in g.values()]) for n, g in sorted(x["nendo"].items())]
    return out


def chigai(hk):
    """hikaku の並び → (同じ年度の行が報告書で違う指標の数, そのうち実績の字が違う指標の数)。2人の読みが違って空の列がある
    行は数えない。"""
    n = j = 0
    for x in hk:
        gs = [[(r, ds) for r, ds in g if not r["_chigau"]] for _, g in x["nendo"]]
        n += any(len(g) > 1 for g in gs)
        j += any(len({norm(r["jisseki"]) for r, _ in g}) > 1 for g in gs)
    return n, j


def check_setsumei(inp, kekka_tbl):
    """検証結果の説明の表の inyo が、ほかの報告書（令和3〜6年度）の同じページにもあるか → 問題の並び。"""
    rows = [dict(where=f"teigi/kensho-kekka.tsv {i} 行目（{doc}）", source=f"doc:{doc}/" + r["tokoro"].rsplit("/", 1)[1],
                 quote=r["inyo"]) for i, r in enumerate(kekka_tbl, 2) for doc in DOCS[1:]]
    return [f"{m['where']}：{m['reason']}（{m['source']}）" for m in shogo.check_quotes(inp, rows).mismatched]


def sheet_text(inp, doc, page, n):
    """報告書のシートのページ（page から n ページ）の text_raw の文字（§3 の正規化のあと）。"""
    t = inp.doc_text(doc, "text_raw") or ""
    return norm("".join(t.split("\f")[page - 1:page - 1 + n]))


# ---- 出すときのまとめ（MCP の応答と試作のページで共通） ----

def matome(inp):
    """→ (まとめ, 問題の並び)。taio/kensho-bunya.tsv が作り直した行と同じかを確認してから、まとめる。
    まとめ：tori（取り組みの ID → いちばん新しい報告書のシートの行。シートの順）、sheet（ID → doc → シートの行）、
    maisu（doc → シート1枚のページの数）、sr（ID → 総合戦略の行。senryaku の形）、
    kpi（ID → doc → 指標の並び。指標ごとに (shihyo_n, 行の並び（入力の順。shu の順に並ぶ）)）、
    bun（ID → doc → [(欄の ID, そのシートの見出しの字, 行の並び, 見出しの字がシートのページの文字にあるか)]。欄の表の順。
    無いのは、入力が、見出しの無い欄の項目をその欄に入れたシート）、hikaku（ID → hikaku の並び）、
    nashi（ID → doc → 表 → 出さない行の数）、hito（ID → doc → 人の確認が済んでいるか）、
    bunya（ID → 対応の表の行の並び）、naka（ID → 中身を出す分野の番号）、ran（欄の ID → 欄の表の行）、
    kekka（検証結果の説明の表の行）、nashi_kei（出さない行の数の合計）。
    行は、入力の行の写しに _mada と _chigau を足したもの（kenshu）。"""
    rows, bad, x = tsukuru(inp)
    bad += check_setsumei(inp, x["kekka"])
    if bad:
        return None, bad
    have = read()
    if dumps(rows) != dumps(have):
        return None, ["taio/kensho-bunya.tsv が、読み取りの結果から作り直した行と違う。python3 -B tools/kensho.py で"
                      "作り直して、コミットする"]
    key_of, tbl, mai = x["key_of"], x["tbl"], x["maisu"]
    sr = {f"node:{PLAN}/{s['key']}": s for s in x["sr"].values()}
    sheet, kpi, bun, bunya, naka, nashi, hito = {}, {}, {}, {}, {}, {}, {}
    for r in tbl["sheet"]:
        sheet.setdefault(key_of[(r["doc"], r["page"])], {})[r["doc"]] = r
    tori = {k: v[DOC] for k, v in sheet.items() if DOC in v}
    for r in tbl["kpi"]:
        k = key_of[(r["doc"], r["page"])]
        kpi.setdefault(k, {}).setdefault(r["doc"], {}).setdefault(r["shihyo_n"], []).append(r)
    kpi = {k: {d: [(n, v[n]) for n in sorted(v, key=int)] for d, v in dv.items()} for k, dv in kpi.items()}
    for r in tbl["bun"]:
        bun.setdefault(key_of[(r["doc"], r["page"])], {}).setdefault(r["doc"], {}).setdefault(r["ran"], []).append(r)
    for k, dv in sheet.items():
        for d, t in dv.items():
            mi, more = midashi(t, x["ran"], sheet_text(inp, d, int(t["page"]), mai[d]))
            bad += more
            b = bun.get(k, {}).get(d, {})
            text = sheet_text(inp, d, int(t["page"]), mai[d])
            bun.setdefault(k, {})[d] = [(ran, mi[ran], b[ran], norm(mi[ran]) in text) for ran in RAN if ran in b]
    for (d, p), v in x["nashi"].items():
        nashi.setdefault(key_of[(d, p)], {})[d] = v
    for (d, p), v in x["hito"].items():
        if (d, p) in key_of:
            hito.setdefault(key_of[(d, p)], {})[d] = v
    for r in have:
        bunya.setdefault(r["torikumi"], []).append(r)
        if r["saisho"] == ICCHI:
            naka[r["torikumi"]] = r["bunya"]
    if bad:
        return None, bad
    return dict(tori=tori, sheet=sheet, maisu=mai, sr=sr, kpi=kpi, bun=bun, hikaku={k: hikaku(v) for k, v in kpi.items()},
                nashi=nashi, hito=hito, bunya=bunya, naka=naka, ran={r["ran"]: r for r in x["ran"]}, kekka=x["kekka"],
                nashi_kei=sum(n for v in x["nashi"].values() for n in v.values())), []


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
    nashi = sum(v for d in x["nashi"].values() for v in d.values())
    mada = sum(bool(r["_mada"]) for r in t["sheet"])
    chigau = sum(bool(r["_chigau"]) for k in ("kpi", "bun") for r in t[k])
    print(f"入力の表（{len(DOCS)}冊）：シート {len(t['sheet'])}、KPI の行 {len(t['kpi'])}、文の項目 {len(t['bun'])}（検収の台帳で"
          f" checked が空のため出さない行 {nashi}、列を空にして出すシート {mada}、2人の読みが違って空の列のある行 {chigau}。"
          f"人の確認が済んだシート {sum(x['hito'].values())}）。結び付けた取り組み {len(set(x['key_of'].values()))}。"
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
