"""生成AIの2回の読み取りの結果（taio/yomi-yosan/）から、予算の事業と事項の対応の表（taio/yosan.tsv）を作る（SCHEMA.md 7.16）。

使い方：
  python3 -B tools/yosan.py            taio/yosan.tsv を作る
  python3 -B tools/yosan.py --kensa    作り直した行が taio/yosan.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの（taio/yomi-yosan/）：
  taba.json          束の並び（束ごとに、番号 taba、種類 kind（hosei、jisshi、fuhyo）、事業の ID の並び jigyo、読み手に渡した
                     事業の字の sha256、附表の束は、まとまり（fu-）ごとの年度ごとの事業の ID の並び members）
  <読み手>-<束の番号2桁>.tsv  列 jigyo、jiko、name、mayoi、riyu（読み手は a と b）
入力（どれも lock の版。読むだけ）：
  hino-town-docs の data/struct/hosei-kai.tsv、hosei-maru.tsv、hosei-jiko.tsv、hosei-shiryo.tsv、audit/hosei-r*.tsv
  shiga-hino-plans の data/plans/jisshi.json と data/text_raw/jisshi/honpen.txt、data/fuhyo/fuhyo-r*.json、
  data/audit_log/jisshi.tsv と fuhyo-r*.tsv、data/sources_index.tsv
  hino-ronten の links/fuhyo-years.tsv（status が confirmed の行だけ）

行を作る決まり（SCHEMA.md 7.16）：
  事業と事項の組ごとに、2回とも付けた組を yomi「一致」、片方だけが付けた組を、読み手ごとに yomi「1回だけ」の行にする。
  附表のまとまり（fu-）は、まとまりの中の年度ごとの事業（fh:）に開いて、事業ごとに行を持つ。「無い」の行は表に持たない。
  手で行を書かない。
読み手に渡した事業の字は、入力の lock の版で作り直し、束ごとの sha256 が同じであることを確認する（違えば止まる）。
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
import shogo  # noqa: E402

YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi-yosan")
PATH = os.path.join(inputs.ROOT, "taio", "yosan.tsv")
COLS = ["jigyo", "jiko", "yomi", "chu"]
FILE_COLS = ["jigyo", "jiko", "name", "mayoi", "riyu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
NASHI = "無い"
KAKUNIN = "✓"
# 読み手に渡した材料の場所。材料の字（束の頭の「この束で使う論点の一覧：」の行）に書かれているので、作り直すときに同じ字を使う
ZAIRYO = "/home/claude/yomi/yosan"
TABA_KAZU = {"hosei": 50, "jisshi": 50, "fuhyo": 50}     # 束の事業の数（材料を作ったときの数）
SHURUI_JUN = ("hosei", "jisshi", "fuhyo")
STRUCT = "data/struct"
HOSEI_FILES = ("hosei-kai.tsv", "hosei-maru.tsv", "hosei-jiko.tsv", "hosei-shiryo.tsv")
FUHYO_YEARS = "links/fuhyo-years.tsv"
RE_FILE = re.compile(r"^([ab])-([0-9]{2})\.tsv$")
RE_TSUKENAI = re.compile(r"付けなかった (\S+?)：.+")
RE_PSRC = re.compile(r"(\S+) p\.(\d+)(?:-(\d+))?")
# 材料の字の種類（make.py の KIND）と区分
KIND = {"maru": "補正予算の主な内容（一般会計の○の行）", "toku": "補正予算の主な内容（特別会計・企業会計）",
        "kurikoshi": "繰越明許費", "saimu": "債務負担行為", "chihosai": "地方債"}
KUBUN = {"tsuika": "追加", "henko": "変更", "haishi": "廃止", "": ""}
# 出すときの種類（docs/design.md 3節の「予算の事業と事項の対応の表 jigyo が …」の行に当たる）。並べる順でもある
SHU = ("fuhyo", "maru", "toku", "kurikoshi", "saimu", "chihosai", "jisshi")


# 読み手に渡した材料の、額が「－」の行の字（make.py の字のまま。sha256 の照合のため変えない。\u539f\u5178 は2字の語）
KINGAKU_NASHI = "（\u539f\u5178の金額は「－」）"


class YosanError(ValueError):
    """読み取りの結果、材料、入力の誤り。件数と該当を示して止める。"""


def tsv(inp, repo, path):
    return inputs.read_tsv(inp.read_bytes(repo, path), f"{repo} {path}")


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def kingaku(v, unit):
    if v == "":
        return KINGAKU_NASHI
    return f"{int(v):,}{unit}"


# ---- 入力の事業 ----

def kensho_zumi(inp):
    """検収の台帳（hino-town-docs data/struct/audit/hosei-r*.tsv）で ✓ の (表, 行) の集まり。"""
    ok = set()
    for p in sorted(inp.files(inputs.TD, f"{STRUCT}/audit/hosei-r*.tsv")):
        for r in tsv(inp, inputs.TD, p):
            if r["table"] in ("hosei-maru", "hosei-jiko") and r["checked"] == KAKUNIN:
                ok.add((r["table"], r["row"]))
    return ok


def hosei_jigyo(inp):
    """補正予算の事業（主な内容の行と、繰越明許費・債務負担行為・地方債の事項）→ dict の並び（回の id の順、回の中はもとの資料の順）。
    検収の台帳で ✓ でない行があれば YosanError。回と資料のページの対応（hosei-shiryo.tsv）に、行の資料が無くても YosanError。"""
    kai = {r["id"]: r for r in tsv(inp, inputs.TD, f"{STRUCT}/hosei-kai.tsv")}
    shiryo = {(r["kai"], r["doc"]) for r in tsv(inp, inputs.TD, f"{STRUCT}/hosei-shiryo.tsv")}
    ok = kensho_zumi(inp)
    out, nashi, bad = [], [], []
    for table, pre in (("hosei-maru", "hj"), ("hosei-jiko", "hz")):
        for r in tsv(inp, inputs.TD, f"{STRUCT}/{table}.tsv"):
            row = f"{r['kai']}/{r['key']}"
            if (table, row) not in ok:
                nashi.append(f"{table} {row}")
                continue
            if (r["kai"], r["doc"]) not in shiryo:
                bad.append(f"{table} {row}：資料 {r['doc']} が、回と資料のページの対応に無い")
            k = kai[r["kai"]]
            d = dict(id=f"{pre}:{row}", kai=r["kai"], key=r["key"], nendo=f"{k['fiscal_year']}年度",
                     fy=int(k["fiscal_year"]), kai_title=k["title"], name=r["name"], gaku=kingaku(r["amount"], r["unit"]),
                     amount=r["amount"], unit=r["unit"], doc=r["doc"], page=int(r["page"]),
                     shiryo=f"{r['doc']} {r['page']}ページ", shurui=KIND[r["kind"]], shu=r["kind"])
            if table == "hosei-maru":
                d.update(desc=r["desc"], sub=r["sub"], kubun="")
            else:
                kb = KUBUN[r["kubun"]]
                d["shurui"] += f"（{kb}）" if kb else ""
                d.update(desc="", sub="", kaikei=r["kaikei_raw"], kubun=kb)
            out.append(d)
    if nashi:
        raise YosanError(f"補正予算の行のうち、検収の台帳で ✓ でない行がある（{len(nashi)}）：{nashi[:5]}")
    if bad:
        raise YosanError(f"補正予算の行の資料が合わない（{len(bad)}）：{bad[:5]}")
    # 名前だけの行（繰越明許費・債務負担行為・地方債）に、同じ回の同じ事業名の○の行の説明を添える（材料の字。make.py と同じ決まり）
    maru = {}
    for d in out:
        if d["id"].startswith("hj:") and d["desc"]:
            maru.setdefault((d["kai"], norm(d["name"])), []).append(d)
    for d in out:
        if not d["id"].startswith("hz:"):
            continue
        cands = [norm(d["name"])]
        m = re.fullmatch(r"[^（]+?（(.+)）", d["name"].strip())
        if m:
            cands.append(norm(m.group(1)))
        for c in cands:
            hit = maru.get((d["kai"], c))
            if hit:
                d["soeru"] = [(h["id"], h["desc"]) for h in hit]
                break
    out.sort(key=lambda d: (d["kai"], d["id"][:2] == "hz", d["key"]))
    return out


def jisshi_jigyo(inp):
    """実施計画の事業 → dict の並び（JSON の順）。ページは、出典が1ページならそのページ、2ページ以上なら、事業の名前が
    もとの資料から取り出した文字にあるページ（1つに決まらなければ YosanError）。PDF のページ ＝ 出典のページ ＋ pdf_page_offset。"""
    p = inp.plan("jisshi")
    src = {s["id"]: s for s in p["sources"]}
    pages = (inp.pt_text("jisshi", "honpen", "text_raw") or "").split("\f")
    out = []
    for t in p["tabs"]:
        for b in t["blocks"]:
            if b["type"] != "programs":
                continue
            m = RE_PSRC.fullmatch(b["source"])
            sid, a, z = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
            off = src[sid]["pdf_page_offset"]
            for g in b["groups"]:
                no = g["no"].replace("分野", "")
                for it in g["items"]:
                    if a == z:
                        pg = a + off
                    else:
                        hit = [x + off for x in range(a, z + 1) if norm(it["name"]) in norm(pages[x + off - 1])]
                        if len(hit) != 1:
                            raise YosanError(f"実施計画の事業 {it['key']} のページが決まらない（{hit}）")
                        pg = hit[0]
                    c = it["cost"]
                    out.append(dict(id=f"node:jisshi/{it['key']}", key=it["key"], bunya=no, theme=jiko.bunya_theme(no),
                                    name=it["name"], desc=it["desc"], nendo="、".join(it["years"]), years=list(it["years"]),
                                    gaku=f"{c['label']} {int(c['amount']):,}{c['unit']}", amount=str(c["amount"]),
                                    unit=c["unit"], label=c["label"], sid=sid, block_src=b["source"],
                                    shiryo=f"pt:jisshi/{sid}/{pg}（{src[sid]['label']}）", page=pg, shu="jisshi",
                                    shurui=f"実施計画の事業（分野{no} {g['name']}）", kubun=""))
    return out


def fuhyo_items(inp):
    """附表の事業 → (fh の ID → 事業の dict, もとの資料の順の ID の並び, 附表の id → 附表の JSON)。附表は data/fuhyo/fuhyo-r*.json
    （検査用の見本 _fuhyotest.json は読まない）。"""
    items, jun, docs = {}, [], {}
    for path in sorted(inp.files(inputs.SP, "data/fuhyo/*.json")):
        if not re.fullmatch(r"data/fuhyo/fuhyo-r[0-9]+\.json", path):
            continue
        d = inp.read_json(inputs.SP, path)
        docs[d["id"]] = d
        for p_ in d["pillars"]:
            for it in p_["items"]:
                fid = f"fh:{d['id']}/{it['key']}"
                items[fid] = dict(it, fid=fid, nendo=d["fiscal_year"]["label"], year=d["fiscal_year"]["year"], doc=d["id"])
                jun.append(fid)
    return items, jun, docs


def fuhyo_jigyo(inp):
    """附表の事業 → (まとまりの並び, 附表の事業の数)。まとまりは、年度をまたぐ同じ事業（hino-ronten links/fuhyo-years.tsv の
    確定の行でつながる事業の組）の中で、名前・概要（desc）・内訳（details）の字が同じ事業。材料を作ったときと同じ決まり。"""
    items, jun, _ = fuhyo_items(inp)
    oya = {x: x for x in items}

    def ne(x):
        while oya[x] != x:
            oya[x] = oya[oya[x]]
            x = oya[x]
        return x
    for r in inp.ronten_tsv(FUHYO_YEARS):
        if r["status"] != inputs.CONFIRMED:
            continue
        if r["from"] not in items or r["to"] not in items:
            raise YosanError(f"年度の台帳の行の事業が附表に無い（{r['from']} {r['to']}）")
        a, b = ne(r["from"]), ne(r["to"])
        if a != b:
            oya[b] = a
    units = {}
    for fid in jun:
        it = items[fid]
        units.setdefault((ne(fid), it["name"], it["desc"], tuple(it["details"])), []).append(it)
    out = []
    for n, (_, mem) in enumerate(units.items(), 1):
        it = mem[0]
        out.append(dict(id=f"fu-{n:04d}", name=it["name"], desc=it["desc"], details=list(it["details"]),
                        members=[dict(fid=m["fid"], nendo=m["nendo"], kubun="・".join(m["kubun"]), kan=m["kan"],
                                      gaku=f"{int(m['amount']):,}千円", dept="・".join(m["dept"]),
                                      shiryo=f"{m['doc']} {m['page']}ページ") for m in mem]))
    return out, len(items)


# ---- 読み手に渡した材料（作り直して sha256 を照合する） ----

def jigyo_md(n, kind, js, ronten_files):
    """束の事業の字（読み手に渡した jigyo/<束>.md と同じ字）。"""
    title = {"hosei": "補正予算の事業", "jisshi": "実施計画の事業", "fuhyo": "当初予算の附表の事業"}[kind]
    L = [f"# 束 {n:02d}（{title}、{len(js)}件）", "",
         "`### ` の行が事業の ID（jigyo に書く字）です。", "",
         "この束で使う論点の一覧：" + "、".join(f"{ZAIRYO}/{x}" for x in ronten_files), ""]
    if kind == "fuhyo":
        L += ["附表の事業は、年度をまたぐ同じ事業のうち、名前・概要・内訳の字が同じものを1つにまとめています（ID は fu- で始まる）。"
              "まとめた年度ごとの行（年度、区分、額など）は、事業を見分けるための字です。", ""]
    for d in js:
        L += [f"### {d['id']}"]
        if kind == "fuhyo":
            L.append(f"- 名前：{d['name']}")
            if d["desc"]:
                L.append(f"- 概要：{d['desc']}")
            for x in d["details"]:
                L.append(f"- 内訳：{x}")
            for m in d["members"]:
                kb = f"　区分：{m['kubun']}" if m["kubun"] else ""
                L.append(f"- {m['nendo']}：{m['fid']}　款：{m['kan']}　額：{m['gaku']}　担当課：{m['dept']}{kb}　資料：{m['shiryo']}")
            L.append("")
            continue
        L.append(f"- 種類：{d['shurui']}")
        if d.get("kaikei"):
            L.append(f"- 会計の見出し：{d['kaikei']}")
        L.append(f"- 名前：{d['name']}")
        if d["desc"]:
            L.append(f"- 説明：{d['desc']}")
        if d.get("sub"):
            L.append(f"- 内訳：{d['sub']}")
        for hid, desc in d.get("soeru", []):
            L.append(f"- 同じ回の同じ事業名の○の行（{hid}）の説明：{desc}")
        if "kai_title" in d:
            L.append(f"- 年度と回：{d['nendo']}　{d['kai_title']}")
        else:
            L.append(f"- 実施計画年度：{d['nendo']}")
        L += [f"- 額：{d['gaku']}", f"- 資料：{d['shiryo']}", ""]
    return "\n".join(L)


def zairyo(inp):
    """入力の lock の版で、束の並びを作り直す → 束ごとに dict(taba, kind, jigyo, sha256, members)。"""
    hosei, jisshi = hosei_jigyo(inp), jisshi_jigyo(inp)
    fuhyo, _ = fuhyo_jigyo(inp)
    taba = []
    for kind, js in (("hosei", hosei), ("jisshi", jisshi), ("fuhyo", fuhyo)):
        size = TABA_KAZU[kind]
        for i in range(0, len(js), size):
            taba.append((kind, js[i:i + size]))
    out = []
    for n, (kind, js) in enumerate(taba, 1):
        text = jigyo_md(n, kind, js, ["ronten/zen.md"])
        e = dict(taba=n, kind=kind, jigyo=[d["id"] for d in js], sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
        if kind == "fuhyo":
            e["members"] = {d["id"]: [m["fid"] for m in d["members"]] for d in js}
        out.append(e)
    return out


def read_taba(yomi_dir=None):
    path = os.path.join(yomi_dir or YOMI_DIR, "taba.json")
    if not os.path.exists(path):
        raise YosanError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_taba(inp, taba):
    """束の記録と、入力の lock の版で作り直した束が、番号・種類・事業の並び・まとまりの中身・sha256 で同じか → 問題の並び。"""
    bad = []
    mae = zairyo(inp)
    if len(mae) != len(taba):
        return [f"束の数が違う（束の記録 {len(taba)}、作り直し {len(mae)}）"]
    for t, z in zip(taba, mae):
        for k in ("taba", "kind", "jigyo", "sha256"):
            if t.get(k) != z[k]:
                bad.append(f"束 {t.get('taba')}：{k} が、入力の lock の版で作り直した材料と違う")
        if t.get("members", {}) != z.get("members", {}):
            bad.append(f"束 {t.get('taba')}：附表のまとまりの中身が、作り直した材料と違う")
    return bad


# ---- 読み取りの結果 ----

def read_yomi(taba, yomi_dir=None):
    """束の並び → 読み手の行（読み手 yomite、束 taba、ファイル file、行 gyo を付けたもの）の並び。ファイルが無いか、
    束に当たらないファイルがあるか、列が違えば YosanError。"""
    yomi_dir = yomi_dir or YOMI_DIR
    out, names = [], set()
    for t in taba:
        for y in YOMITE:
            fn = f"{y}-{t['taba']:02d}.tsv"
            names.add(fn)
            path = os.path.join(yomi_dir, fn)
            if not os.path.exists(path):
                raise YosanError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
            with open(path, encoding="utf-8", newline="") as f:
                rd = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                if rd.fieldnames != FILE_COLS:
                    raise YosanError(f"{fn} の列が違う（{rd.fieldnames}）")
                for g, r in enumerate(rd, 2):
                    if None in r or any(v is None for v in r.values()):
                        raise YosanError(f"{fn} {g} 行目：列の数が違う")
                    out.append(dict(r, yomite=y, gyo=g, taba=t["taba"], file=fn))
    hoka = sorted(os.path.basename(p) for p in glob.glob(os.path.join(yomi_dir, "*.tsv"))
                  if os.path.basename(p) not in names)
    if hoka:
        raise YosanError(f"束の記録に当たらない読み取りの結果のファイルがある（{'、'.join(hoka)}）")
    return out


def erabu(inp, jiko_rows):
    """読み手が選べた事項の ID → 名前（事項の表の行のうち、基本施策そのものの行を除く。SCHEMA.md 7.16）。"""
    kihon = jiko.kihon_gyo(jiko_rows, jiko.kihon_names_of(inp))
    return {r["id"]: r["name"] for r in jiko_rows if r["id"] not in kihon}


def check_yomi(yomi, taba, names):
    """読み手の行の検査（読み手に渡した形の検査 kensa.py と同じ決まり）→ 問題の並び。names は選べる事項の ID → 名前。"""
    bad, seen, per = [], set(), {}
    ids = {t["taba"]: set(t["jigyo"]) for t in taba}
    for r in yomi:
        w = f"{r['file']} {r['gyo']} 行目"
        j, k = r["jigyo"], r["jiko"]
        if j not in ids[r["taba"]]:
            bad.append(f"{w}：jigyo が束 {r['taba']} の事業に無い（{j}）")
            continue
        per.setdefault((r["yomite"], j), set()).add(k)
        if (r["yomite"], j, k) in seen:
            bad.append(f"{w}：同じ jigyo と jiko の行が2つある（{j} {k}）")
        seen.add((r["yomite"], j, k))
        if k == NASHI:
            if r["name"]:
                bad.append(f"{w}：jiko が「無い」の行は name を空にする")
        elif k not in names:
            bad.append(f"{w}：jiko が、選べる事項（基本施策そのものの行を除く）に無い（{k}）")
        elif r["name"] != names[k]:
            bad.append(f"{w}：name が {k} の名前と違う（「{r['name']}」。正しくは「{names[k]}」）")
        if r["mayoi"] not in ("", "1"):
            bad.append(f"{w}：mayoi は空か 1")
        if r["mayoi"] == "1" and not r["riyu"].strip():
            bad.append(f"{w}：mayoi が 1 なのに riyu が空")
        if r["mayoi"] == "" and r["riyu"].strip():
            for part in r["riyu"].split("；"):
                m = RE_TSUKENAI.fullmatch(part.strip())
                if not m or m.group(1) not in names:
                    bad.append(f"{w}：mayoi が空の行の riyu が「付けなかった <事項の ID>：<理由>」の形でない（「{part}」）")
    for t in taba:
        for j in t["jigyo"]:
            for y in YOMITE:
                ks = per.get((y, j))
                if not ks:
                    bad.append(f"{y}-{t['taba']:02d}.tsv：事業 {j} の行が無い")
                elif NASHI in ks and len(ks) > 1:
                    bad.append(f"{y}-{t['taba']:02d}.tsv：事業 {j} に「無い」の行と事項の行が両方ある")
    return bad


def chu_of(yomite, mayoi):
    out = []
    if yomite:
        out.append(f"読み手 {yomite} だけが付けた")
    if mayoi:
        out.append(f"迷いの印：読み手 {mayoi}")
    return "。".join(out)


def make_rows(yomi, taba, jiko_rows):
    """読み手の行 → 表の行（SCHEMA.md 7.16）。附表のまとまりは、年度ごとの事業（fh:）に開く。並びは、束の順（補正予算、実施計画、
    附表。束の中は事業の順。附表は、まとまりの中の年度ごとの事業の順）、事項の表の順、yomi の順、読み手の順。"""
    members = {}
    jun = {}
    for t in taba:
        for j in t["jigyo"]:
            jun[j] = len(jun)
            members[j] = t.get("members", {}).get(j, [j])
    jiko_jun = {r["id"]: i for i, r in enumerate(jiko_rows)}
    tsuke, mayoi = {}, {}
    for r in yomi:
        if r["jiko"] == NASHI:
            continue
        k = (r["jigyo"], r["jiko"])
        tsuke.setdefault(k, set()).add(r["yomite"])
        if r["mayoi"] == "1":
            mayoi.setdefault(k, set()).add(r["yomite"])
    gyo = []
    for (j, k), ys in tsuke.items():
        m = "、".join(sorted(mayoi.get((j, k), ())))
        if len(ys) == 2:
            nar = [(ICCHI, "")]
        else:
            nar = [(IKKAI, y) for y in YOMITE if y in ys]
        for yomi_, y in nar:
            for i, fid in enumerate(members[j]):
                gyo.append(((jun[j], i, jiko_jun[k], YOMI.index(yomi_), y),
                            dict(jigyo=fid, jiko=k, yomi=yomi_, chu=chu_of(y, m))))
    return [r for _, r in sorted(gyo, key=lambda x: x[0])]


# ---- 出すときの事業の中身 ----

def fuhyo_doc(fuhyo_id):
    """附表の id（fuhyo-r8）→ hino-town-docs の資料の id（yosan-r8-fuhyo）。"""
    m = re.fullmatch(r"fuhyo-(r[0-9]+)", fuhyo_id)
    return f"yosan-{m.group(1)}-fuhyo" if m else None


def check_fuhyo_doc(inp, docs):
    """附表の PDF が、hino-town-docs の資料と同じファイルか（sources_index.tsv と sources.tsv の sha256 とページの数が同じか）
    → 問題の並び。同じなら、附表の事業のページは、hino-town-docs の資料のページ（doc:）で指す（SCHEMA.md 7.16）。"""
    si = {r["id"]: r for r in inp.sources_index()}
    td = inp.docs()
    bad = []
    for fid, d in docs.items():
        s, t = si.get(d["source"]["id"]), td.get(fuhyo_doc(fid) or "")
        if s is None or t is None:
            bad.append(f"附表 {fid}：sources_index.tsv か hino-town-docs の sources.tsv に行が無い")
        elif s["sha256"] != t["sha256"] or s["pages"] != t["pages"]:
            bad.append(f"附表 {fid}：hino-town-docs の {t['id']} と sha256 かページの数が違う")
    return bad


def audit_rows(inp, plan_id):
    """shiga-hino-plans の検収の台帳（data/audit_log/<id>.tsv）の行（注の行を除く）。"""
    path = f"data/audit_log/{plan_id}.tsv"
    if path not in inp.files(inputs.SP, "data/audit_log/*.tsv"):
        return []
    lines = [x for x in inp.read_text(inputs.SP, path).splitlines() if x and not x.startswith("#")]
    return inputs.read_tsv("\n".join(lines) + "\n", f"{inputs.SP} {path}")


def jigyo_naka(inp):
    """出す事業の ID → 中身（SCHEMA.md 7.16）。中身は dict(id, shu（docs/design.md の種類）, kubun（区分の字）, nendo（並べる年度。
    西暦）, nendo_ji（年度と回の字）, name, gaku（額の字。入力の字のまま）, tani, setsumei（(欄, 字) の並び）, source（資料の
    ページの ID）, kakunin（額の検収の印が ✓ か）, jun（入力の順）)。"""
    out = {}
    for d in hosei_jigyo(inp):
        setsumei = []
        if d["desc"]:
            setsumei.append(("desc", d["desc"]))
        if d["sub"]:
            setsumei.append(("sub", d["sub"]))
        out[d["id"]] = dict(id=d["id"], shu=d["shu"], kubun=d["kubun"], nendo=d["fy"], nendo_ji=d["kai_title"],
                            fy=d["fy"], name=d["name"], gaku=d["amount"], tani=d["unit"], setsumei=setsumei,
                            source=f"doc:{d['doc']}/{d['page']}", kakunin=True, jun=len(out))
    jaudit = {(r["label"], r["value"], r["source"]) for r in audit_rows(inp, "jisshi")
              if r["btype"] == "programs.cost" and r["checked"] == KAKUNIN}
    js = jisshi_jigyo(inp)
    jban = {}
    for d in js:
        jban.setdefault(d["name"], []).append(d["id"])
    for d in js:
        fs = jban[d["name"]]
        ban = f"(同じ名前の{fs.index(d['id']) + 1}件目)" if len(fs) > 1 else ""
        k = (f"{d['name']}{ban}/{d['label']}", d["amount"], d["block_src"])
        nendo = min(int(y[1:]) for y in d["years"]) + 2018 if d["years"] else 0
        out[d["id"]] = dict(id=d["id"], shu="jisshi", kubun="", nendo=nendo, nendo_ji="、".join(d["years"]), fy=None,
                            name=d["name"], gaku=d["amount"], tani=d["unit"], label=d["label"],
                            setsumei=[("desc", d["desc"])] if d["desc"] else [],
                            source=f"pt:jisshi/{d['sid']}/{d['page']}", kakunin=k in jaudit, jun=len(out))
    items, jun, docs = fuhyo_items(inp)
    bad = check_fuhyo_doc(inp, docs)
    if bad:
        raise YosanError(f"附表の資料が合わない（{len(bad)}）：{bad[:5]}")
    faudit = {}
    for fid_doc, d in docs.items():
        f = d["source"]["file"].rsplit(".", 1)[0]
        faudit[fid_doc] = ({(r["label"], r["value"], r["source"]) for r in audit_rows(inp, fid_doc)
                            if r["btype"] == "fuhyo.amount" and r["checked"] == KAKUNIN}, f,
                           {r["unit"] for r in audit_rows(inp, fid_doc) if r["btype"] == "fuhyo.amount"})
    # 検収の台帳の label は、同じ附表に同じ名前の事業が2つ以上あるとき「<名前>(同じ名前の<N>件目)」（もとの資料の順）
    onaji, nban = {}, {}
    for fid in jun:
        onaji.setdefault((items[fid]["doc"], items[fid]["name"]), []).append(fid)
    for fs in onaji.values():
        for i, fid in enumerate(fs, 1):
            nban[fid] = f"(同じ名前の{i}件目)" if len(fs) > 1 else ""
    for fid in jun:
        it = items[fid]
        au, f, tani = faudit[it["doc"]]
        if len(tani) != 1:
            raise YosanError(f"附表 {it['doc']} の検収の台帳の予算額の単位が1つでない（{sorted(tani)}）")
        setsumei = ([("desc", it["desc"])] if it["desc"] else []) + [("details", x) for x in it["details"]]
        out[fid] = dict(id=fid, shu="fuhyo", kubun="・".join(it["kubun"]), nendo=it["year"], nendo_ji=it["nendo"],
                        fy=it["year"], name=it["name"], gaku=str(it["amount"]), tani=next(iter(tani)), setsumei=setsumei,
                        source=f"doc:{fuhyo_doc(it['doc'])}/{it['page']}",
                        kakunin=(f"{it['name']}{nban[fid]}/予算額", str(it["amount"]), f"{f} p.{it['page']}") in au, jun=len(out))
    return out


def shogo_naka(inp, naka):
    """事業の中身の名前と説明の字を、もとの資料の文字と照合する（SCHEMA.md §3）。名前の検収が無い事業（実施計画と附表）は名前も
    照合する。→ 照合できなかった (事業の ID, 欄) の集まり。欄は name か、setsumei の番号。"""
    rows = []
    for d in naka.values():
        if d["shu"] in ("jisshi", "fuhyo"):
            rows.append(dict(where=(d["id"], "name"), source=d["source"], quote=d["name"]))
        for i, (_, t) in enumerate(d["setsumei"]):
            rows.append(dict(where=(d["id"], i), source=d["source"], quote=t))
    res = shogo.check_quotes(inp, rows)
    return {m["where"] for m in res.mismatched}


def check(rows, naka, jiko_rows, names):
    """表の行の検査 → 問題の並び。"""
    bad = []
    by = {r["id"]: r for r in jiko_rows}
    seen = set()
    for i, r in enumerate(rows, 2):
        w = f"taio/yosan.tsv {i} 行目"
        if r["jigyo"] not in naka:
            bad.append(f"{w}：jigyo が入力の事業に無い（{r['jigyo']}）")
        if r["jiko"] not in by:
            bad.append(f"{w}：jiko が事項の表に無い（{r['jiko']}）")
        elif r["jiko"] not in names:
            bad.append(f"{w}：jiko が基本施策そのものの行（{r['jiko']}）")
        if r["yomi"] not in YOMI:
            bad.append(f"{w}：yomi が {YOMI} のどれでもない（{r['yomi']}）")
        k = (r["jigyo"], r["jiko"], r["yomi"], r["chu"])
        if k in seen:
            bad.append(f"{w}：同じ行がある")
        seen.add(k)
    return bad


def dumps(rows):
    return "\t".join(COLS) + "\n" + "".join("\t".join(r[c] for c in COLS) + "\n" for r in rows)


def read(path=PATH):
    """taio/yosan.tsv の行。表が無ければ空。列が違えば InputError。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), COLS)


_NAKA = {}


def naka_of(inp):
    """出す事業の中身と、照合できなかった欄（覚えておく）。"""
    k = id(inp)
    if k not in _NAKA:
        naka = jigyo_naka(inp)
        _NAKA[k] = (naka, shogo_naka(inp, naka))
    return _NAKA[k]


def of_jiko(inp, jiko_ids, rows=None):
    """表の行のうち、事項が jiko_ids にある行 → 事項の ID → 出す事業の並び（SCHEMA.md 7.16）。事業ごとに、中身（jigyo_naka）に、
    yomi と、照合できなかった欄（nashi。name か、setsumei の番号の集まり）を足したもの。同じ事業と事項に「一致」と「1回だけ」の
    行が両方あることは無い（make_rows）。1回だけの行が2つ（読み手 a と b）になることも無い。"""
    rows = read() if rows is None else rows
    naka, ng = naka_of(inp)
    out = {}
    for r in rows:
        if r["jiko"] not in jiko_ids:
            continue
        d = naka[r["jigyo"]]
        x = dict(d, yomi=r["yomi"], nashi={w for j, w in ng if j == d["id"]})
        out.setdefault(r["jiko"], []).append(x)
    return out


def kakutei_ni_aru(x, kiroku):
    """事業 x が、確定済みの記録（町の資料の記述の、生成AIの読み取りでない行）にあるか（SCHEMA.md 7.16）。資料のページが同じで、
    記録の引用（§3 の正規化）に、事業の名前か説明の字（§3 の正規化）が入っている記録があれば、ある。"""
    ji = [shogo.norm(t) for t in [x["name"]] + [t for _, t in x["setsumei"]]]
    for k in kiroku:
        if k.get("yomi") or k["source"] != x["source"]:
            continue
        q = shogo.norm(k["quote"])
        if any(j and j in q for j in ji):
            return True
    return False


def narabe(xs):
    """出す事業の並び（SCHEMA.md 7.16）→ 種類ごとの (種類, 事業の並び) の並び。種類は SHU の順。種類の中は、対象の年度の
    新しい順。同じ年度の補正予算は、新しい回から（回の id の逆順）。ほかは入力の順。"""
    out = []
    for shu in SHU:
        rs = [x for x in xs if x["shu"] == shu]
        if not rs:
            continue
        kai = sorted({x["id"].split(":")[1].split("/")[0] for x in rs if x["id"].startswith(("hj:", "hz:"))})
        rank = {k: i for i, k in enumerate(kai)}

        def jun(x):
            k = x["id"].split(":")[1].split("/")[0]
            return (-x["nendo"], -rank.get(k, 0), x["jun"])
        out.append((shu, sorted(rs, key=jun)))
    return out


def saisho(xs, m):
    """種類の中の事業の並び xs → (1回めの応答に出す事業, 続きに回す事業)。対象の年度ごとに、最初の m つまでを1回めに出す。"""
    mae, ato, kazu = [], [], {}
    for x in xs:
        kazu[x["nendo"]] = kazu.get(x["nendo"], 0) + 1
        (mae if kazu[x["nendo"]] <= m else ato).append(x)
    return mae, ato


def main(argv=None):
    p = argparse.ArgumentParser(description="生成AIの2回の読み取りの結果から、予算の事業と事項の対応の表を作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        jiko_rows = jiko.read()
        taba = read_taba()
        yomi = read_yomi(taba)
        names = erabu(inp, jiko_rows)
        bad = check_taba(inp, taba) + check_yomi(yomi, taba, names)
        naka, ng = naka_of(inp)
    except (inputs.InputError, YosanError, OSError, ValueError, KeyError) as e:
        print(f"止めた：lock と入力、または読み取りの結果を読めない\n{e}", file=sys.stderr)
        return 1
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad[:200]), file=sys.stderr)
        return 1
    rows = make_rows(yomi, taba, jiko_rows)
    bad = check(rows, naka, jiko_rows, names)
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad[:200]), file=sys.stderr)
        return 1
    s = dumps(rows)
    n = {y: sum(r["yomi"] == y for r in rows) for y in YOMI}
    print(f"予算の事業と事項の対応 {len(rows)} 行（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}）。事業 "
          f"{len({r['jigyo'] for r in rows})}、事項 {len({r['jiko'] for r in rows})}")
    for shu in SHU:
        rs = [r for r in rows if naka[r["jigyo"]]["shu"] == shu]
        print(f"  {shu}：{len(rs)} 行（一致 {sum(r['yomi'] == ICCHI for r in rs)}、1回だけ "
              f"{sum(r['yomi'] == IKKAI for r in rs)}）。事業 {len({r['jigyo'] for r in rs})}")
    nk = sum(1 for d in naka.values() if not d["kakunin"])
    print(f"入力の事業 {len(naka)}。額の検収の印が ✓ でない事業 {nk}。もとの資料の文字と照合できなかった欄 {len(ng)}"
          f"（行のある事業では {len({w for w in ng if w[0] in {r['jigyo'] for r in rows}})}）")
    if a.kensa:
        cur = None
        if os.path.exists(PATH):
            with open(PATH, encoding="utf-8") as f:
                cur = f.read()
        if cur != s:
            print("止めた：taio/yosan.tsv が、読み取りの結果から作り直した行と違う（python3 -B tools/yosan.py で作り直す）",
                  file=sys.stderr)
            return 1
        print("taio/yosan.tsv は、読み取りの結果から作り直した行と同じ")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"{os.path.relpath(PATH, inputs.ROOT)} を書いた")
    return 0


if __name__ == "__main__":
    sys.exit(main())
