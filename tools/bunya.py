"""一般質問の題と、第6次日野町総合計画の基本計画の分野の対応の表（taio/bunya.tsv。SCHEMA.md 7.11）を、生成AIの2回の
読み取りの結果（taio/yomi-bunya/）から作る。分野に無い話題の名前は、分野に無い話題の名前の表（teigi/bunya-wadai.tsv）で
まとめる。MCP の応答（tools/build_mcp.py の field）と試作のページ（tools/build_bunya.py）は、この表と入力から作る。

使い方：
  python3 -B tools/bunya.py            taio/bunya.tsv を作る
  python3 -B tools/bunya.py --kensa    作り直した行が taio/bunya.tsv と同じかを確認する（違えば終了コード 1。書き換えない）

読むもの：
  taio/yomi-bunya/taba.json             束の並び。束ごとに、読んだ一般質問の台帳の from の並び（0から数える）
  taio/yomi-bunya/<読み手>-<束>-bunya.tsv  列 from、n、bunya、wadai、mayoi、riyu（読み手は a と b）
  入力の一般質問の台帳（hino-council-search data/ippan.tsv）と、第6次日野町総合計画（shiga-hino-plans data/plans/sogo6.json）

行を作る決まり（SCHEMA.md 7.11）：
  題（from と n）ごと・分野ごとに1行。2人とも付けた分野は yomi「一致」、1人だけが付けた分野は「1回だけ」。
  chushin は、2人とも最初に書いた分野（中心の分野）なら「一致」、1人だけなら「1回だけ」、ほかは空。
  分野を空にした読みは、話題の行（列 wadai に、分野に無い話題の名前の表でまとめた名前）にする。2人とも空で、まとめた名前が
  同じなら「一致」、ほかは読み手ごとに「1回だけ」。手で行を書かない。
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import keys  # noqa: E402

PLAN = "sogo6"                       # 第6次日野町総合計画（shiga-hino-plans data/plans/sogo6.json）
TAB_BUNYA = "mokuhyo"                # 分野と基本施策の tab（programs の groups。no が分野の番号）
TAB_HASHIRA = "kousou"               # 柱・政策・分野の tab（programs の groups の no が「柱」で始まる block）
HASHIRA = "柱"
YOMI_DIR = os.path.join(inputs.ROOT, "taio", "yomi-bunya")
PATH = os.path.join(inputs.ROOT, "taio", "bunya.tsv")
WADAI_PATH = os.path.join(inputs.ROOT, "teigi", "bunya-wadai.tsv")
COLS = ["from", "n", "bunya", "wadai", "chushin", "yomi", "chu"]
WADAI_COLS = ["namae", "matome", "id", "chu"]
FILE_COLS = ["from", "n", "bunya", "wadai", "mayoi", "riyu"]
YOMITE = ("a", "b")
ICCHI, IKKAI = "一致", "1回だけ"
YOMI = (ICCHI, IKKAI)
BUNYA_MAX = 3                         # 1つの題に付ける分野の数の上限（SKILL.md 4.7 の B3）
RE_WADAI_ID = re.compile(r"wadai-[a-z0-9]+(?:-[a-z0-9]+)*")
RE_SOURCE = re.compile(r"([a-z0-9-]+) p\.([0-9]+)(?:-([0-9]+))?")


class BunyaError(ValueError):
    """読み取りの結果、表、入力の総合計画が、決まりに合わない。"""


# ---- 入力：総合計画の分野 ----

def keikaku(inp):
    """→ dict(id, name, hashira)。hashira は柱の並び。柱ごとに no、name、bunya（分野の並び）。分野ごとに no、name、
    seisaku（政策の no と name）、midashi（基本施策の見出しの字）、shisaku（基本施策の (no, name) の並び）、
    tokoro（基本施策のページの pt の ID の並び）。分野と基本施策は tab mokuhyo の programs、柱と政策は tab kousou の
    programs（groups の no が「柱」で始まるもの）から取る。2つの分野の番号と名前が合わなければ BunyaError。"""
    p = inp.plan(PLAN)
    if p is None:
        raise BunyaError(f"入力に data/plans/{PLAN}.json が無い")
    tabs = {t["id"]: t for t in p["tabs"]}
    bunya = {}
    for b in tabs[TAB_BUNYA]["blocks"]:
        if b.get("type") != "programs":
            continue
        m = RE_SOURCE.fullmatch(b.get("source", ""))
        if not m:
            raise BunyaError(f"分野の block の source の形が違う（{b.get('source')}）")
        f, a, z = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        for g in b["groups"]:
            if len(g["subgroups"]) != 1:
                raise BunyaError(f"分野 {g['no']} の subgroups が1つでない")
            sg = g["subgroups"][0]
            bunya[g["no"]] = dict(no=g["no"], name=g["name"], midashi=sg["name"],
                                  shisaku=[(i["no"], i["name"]) for i in sg["items"]],
                                  tokoro=[f"pt:{PLAN}/{f}/{x}" for x in range(a, z + 1)])
    hashira, seen = [], []
    for b in tabs[TAB_HASHIRA]["blocks"]:
        if b.get("type") != "programs" or not all(g["no"].startswith(HASHIRA) for g in b["groups"]):
            continue
        for g in b["groups"]:
            hs = dict(no=g["no"], name=g["name"], bunya=[])
            for sg in g["subgroups"]:
                for i in sg["items"]:
                    x = bunya.get(i["no"])
                    if x is None or x["name"] != i["name"]:
                        raise BunyaError(f"柱と政策の表の分野 {i['no']} {i['name']} が、分野と基本施策の表に無いか、名前が違う")
                    hs["bunya"].append(dict(x, seisaku=(sg["no"], sg["name"])))
                    seen.append(i["no"])
            hashira.append(hs)
    if sorted(seen) != sorted(bunya) or len(seen) != len(set(seen)):
        raise BunyaError("柱と政策の表の分野と、分野と基本施策の表の分野が合わない")
    return dict(id=f"plan:{PLAN}", name=p["meta"]["name"], hashira=hashira)


def bunya_jun(kk):
    """分野の番号 → 柱の中の順の番号（0から）。"""
    return {x["no"]: i for i, x in enumerate(x for h in kk["hashira"] for x in h["bunya"])}


# ---- 表を読む ----

def read_wadai(path=WADAI_PATH):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), WADAI_COLS)


def check_wadai(rows):
    """分野に無い話題の名前の表の検査 → 問題の並び。namae が空でなく重ならないこと、matome と id が空でないこと、id の形、
    同じ matome の行の id が同じで、id が別の matome に使われていないこと。"""
    bad, m2i, i2m, seen = [], {}, {}, set()
    for i, r in enumerate(rows, 2):
        if not r["namae"] or r["namae"] in seen:
            bad.append(f"{i} 行目：namae が空か重なっている（{r['namae']}）")
        seen.add(r["namae"])
        if not r["matome"] or not RE_WADAI_ID.fullmatch(r["id"]):
            bad.append(f"{i} 行目：matome が空か、id の形が違う（{r['id']}）")
            continue
        if m2i.setdefault(r["matome"], r["id"]) != r["id"] or i2m.setdefault(r["id"], r["matome"]) != r["matome"]:
            bad.append(f"{i} 行目：同じ matome の行の id が違うか、id が別の matome にも使われている（{r['matome']} {r['id']}）")
    return bad


def wadai_ichiran(rows):
    """分野に無い話題の名前の表 → [(id, まとめた名前)]（表で最初に出る順）。"""
    return list(dict.fromkeys((r["id"], r["matome"]) for r in rows))


def read_taba(path=None):
    with open(path or os.path.join(YOMI_DIR, "taba.json"), encoding="utf-8") as f:
        return json.load(f)


def read_yomi(yomi_dir=YOMI_DIR):
    """→ {(from, n): {読み手: 行}}。束の外の題、同じ読み手の同じ題の2行、列の違いは BunyaError。"""
    out, bad = {}, []
    for t, froms in enumerate(read_taba(os.path.join(yomi_dir, "taba.json"))):
        for y in YOMITE:
            path = os.path.join(yomi_dir, f"{y}-{t}-bunya.tsv")
            if not os.path.exists(path):
                raise BunyaError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
            with open(path, encoding="utf-8") as f:
                rows = inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), FILE_COLS)
            for i, r in enumerate(rows, 2):
                k = (r["from"], r["n"])
                if r["from"] not in froms:
                    bad.append(f"{y}-{t}-bunya.tsv {i} 行目：題 {k} が束 {t} に無い")
                if y in out.get(k, {}):
                    bad.append(f"{y}-{t}-bunya.tsv {i} 行目：同じ題 {k} の行がほかにもある")
                out.setdefault(k, {})[y] = r
    if bad:
        raise BunyaError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return out


def bunya_list(r):
    """読み手の行の bunya → 分野の番号の並び（書いた順。最初が中心の分野）。"""
    return [x.strip() for x in r["bunya"].split(",") if x.strip()]


def check_yomi(yomi, dai, nos, wadai_rows):
    """読み取りの結果の検査 → 問題の並び。dai は台帳の題の (from, n) の並び、nos は入力の分野の番号の集まり。
    台帳の題の全部に、2人の読み手の行があり、台帳に無い題の行が無いこと。分野の番号が入力にあり、重ならず、BUNYA_MAX
    までであること。分野が空の行に話題があり、その名前が分野に無い話題の名前の表にあること。表の名前の全部が読み取りの結果に
    あること（出さない名前を作らない）。"""
    bad = []
    names = {r["namae"] for r in wadai_rows}
    used = set()
    for k in dai:
        for y in YOMITE:
            if y not in yomi.get(k, {}):
                bad.append(f"題 {k} の、読み手 {y} の行が無い")
    for k in sorted(set(yomi) - set(dai)):
        bad.append(f"題 {k} が、一般質問の台帳に無い")
    for k, d in yomi.items():
        for y, r in d.items():
            bs = bunya_list(r)
            if any(b not in nos for b in bs) or len(set(bs)) != len(bs) or len(bs) > BUNYA_MAX:
                bad.append(f"題 {k} 読み手 {y}：分野の書き方が違う（{r['bunya']}）")
            if not bs:
                if r["wadai"] not in names:
                    bad.append(f"題 {k} 読み手 {y}：話題「{r['wadai']}」が、分野に無い話題の名前の表に無い")
                used.add(r["wadai"])
    bad += [f"分野に無い話題の名前の表の「{n}」が、読み取りの結果に無い" for n in sorted(names - used)]
    return bad


# ---- 行を作る ----

def chu_of(*parts):
    return "。".join(p for p in parts if p)


def make_rows(yomi, dai, wadai_rows, jun):
    """→ taio/bunya.tsv の行。dai は台帳の題の (from, n) の並び（台帳の順）、jun は分野の番号 → 順。"""
    matome = {r["namae"]: r["matome"] for r in wadai_rows}
    out = []
    for k in dai:
        d = yomi[k]
        bs = {y: bunya_list(d[y]) for y in YOMITE}
        mayoi = "、".join(y for y in YOMITE if d[y]["mayoi"].strip() == "1")
        m = f"迷いの印：読み手 {mayoi}" if mayoi else ""
        ichi = []
        for x in sorted({b for y in YOMITE for b in bs[y]}, key=lambda b: jun[b]):
            ys = [y for y in YOMITE if x in bs[y]]
            cs = [y for y in YOMITE if bs[y] and bs[y][0] == x]
            yomi_ = ICCHI if len(ys) == 2 else IKKAI
            chushin = ICCHI if len(cs) == 2 else IKKAI if cs else ""
            chu = chu_of(f"読み手 {ys[0]} だけが付けた" if yomi_ == IKKAI else "",
                         f"中心の分野にしたのは読み手 {cs[0]} だけ" if chushin == IKKAI else "", m)
            ichi.append(({ICCHI: 0, IKKAI: 1, "": 2}[chushin], jun[x],
                         dict(zip(COLS, (k[0], k[1], x, "", chushin, yomi_, chu)))))
        out += [r for _, _, r in sorted(ichi, key=lambda t: (t[0], t[1]))]
        ws = {y: matome[d[y]["wadai"]] for y in YOMITE if not bs[y]}
        if len(ws) == 2 and ws["a"] == ws["b"]:
            out.append(dict(zip(COLS, (k[0], k[1], "", ws["a"], "", ICCHI, m))))
        else:
            for y, w in ws.items():
                out.append(dict(zip(COLS, (k[0], k[1], "", w, "", IKKAI, chu_of(f"読み手 {y} だけが付けた", m)))))
    return out


def dai_list(inp):
    """一般質問の台帳の題の (from, n) の並び（台帳の順）。"""
    return [(r["from"], r["n"]) for rs in inp.ippan().values() for r in rs]


def check(rows, dai, nos, wadai_rows):
    """taio/bunya.tsv の行の検査 → 問題の並び。台帳の題の全部に行が1つ以上あること、分野の番号が入力にあること、
    話題の名前が分野に無い話題の名前の表の matome にあること、yomi と chushin が決めた字であること。"""
    bad = []
    have = {(r["from"], r["n"]) for r in rows}
    bad += [f"題 {k} に、分野の行も話題の行も無い" for k in dai if k not in have]
    mt = {r["matome"] for r in wadai_rows}
    for i, r in enumerate(rows, 2):
        if bool(r["bunya"]) == bool(r["wadai"]):
            bad.append(f"{i} 行目：bunya と wadai の、どちらか1つだけを書く")
        if r["bunya"] and r["bunya"] not in nos:
            bad.append(f"{i} 行目：分野の番号が入力の総合計画に無い（{r['bunya']}）")
        if r["wadai"] and r["wadai"] not in mt:
            bad.append(f"{i} 行目：話題の名前が、分野に無い話題の名前の表に無い（{r['wadai']}）")
        if r["yomi"] not in YOMI or r["chushin"] not in YOMI + ("",) or (r["wadai"] and r["chushin"]):
            bad.append(f"{i} 行目：yomi か chushin の字が違う（{r['yomi']} {r['chushin']}）")
    return bad


def dumps(rows):
    return "\t".join(COLS) + "\n" + "".join("\t".join(r[c] for c in COLS) + "\n" for r in rows)


def read(path=PATH):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), COLS)


def tsukuru(inp):
    """→ (行, 問題の並び, 計画)。読み取りの結果と表と入力を読んで、検査してから行を作る。"""
    kk = keikaku(inp)
    nos = set(bunya_jun(kk))
    wadai_rows = read_wadai()
    bad = check_wadai(wadai_rows)
    yomi = read_yomi()
    dai = dai_list(inp)
    bad += check_yomi(yomi, dai, nos, wadai_rows)
    bad += start_problems(inp)
    if bad:
        return [], bad, kk
    rows = make_rows(yomi, dai, wadai_rows, bunya_jun(kk))
    return rows, check(rows, dai, nos, wadai_rows), kk


# ---- 出すときのまとめ（MCP の応答と試作のページで共通） ----

def matome(inp, rows, wadai_rows, kk):
    """→ dict(dai：題の (from, n) → 台帳の行, of：題 → 表の行の並び, by：分野の番号か話題の ID → 題の並び（日付の新しい順。
    同じ日は台帳の順）, bunya：分野の番号 → 分野（keikaku の分野）, wadai：[(話題の ID, まとめた名前)], m2id：まとめた名前 → ID)。
    分野の番号と話題の ID は、field の引数に使う ID（docs/mcp.md）。"""
    ip = {(r["from"], r["n"]): r for rs in inp.ippan().values() for r in rs}
    m2id = {r["matome"]: r["id"] for r in wadai_rows}
    of, by = {}, {}
    for r in rows:
        k = (r["from"], r["n"])
        of.setdefault(k, []).append(r)
        f = r["bunya"] or m2id[r["wadai"]]
        if k not in by.setdefault(f, []):
            by[f].append(k)
    jun = {k: i for i, k in enumerate(ip)}
    for f in by:
        by[f].sort(key=lambda k: jun[k])
        by[f].sort(key=lambda k: ip[k]["date"], reverse=True)
    bunya = {x["no"]: dict(x, hashira=h) for h in kk["hashira"] for x in h["bunya"]}
    return dict(dai=ip, of=of, by=by, bunya=bunya, wadai=wadai_ichiran(wadai_rows), m2id=m2id)


def start_of(r):
    """台帳の行の start（「sid:段落」）→ (sid, 段落の番号)。"""
    sid, p = r["start"].split(":")
    return sid, int(p)


def start_problems(inp):
    """台帳の題の全部で、start の発言が会議録にあり、その番号の段落があること。→ 問題の並び。"""
    bad = []
    for rs in inp.ippan().values():
        for r in rs:
            try:
                sid, p = start_of(r)
            except ValueError:
                bad.append(f"題 {(r['from'], r['n'])}：start の形が違う（{r['start']}）")
                continue
            t = inp.statement_text(sid)
            if t is None or not 1 <= p <= len(inputs.paragraphs(t)):
                bad.append(f"題 {(r['from'], r['n'])}：start の発言か段落が会議録に無い（{r['start']}）")
    return bad


# ---- 論点とのつながり ----

def turn_index(inp):
    """発言の sid → その発言を turns に含む台帳の題の (from, n) の並び。"""
    out = {}
    for f, rs in inp.ippan().items():
        for r in rs:
            for t in r["turns"].split(";"):
                if t:
                    out.setdefault(t.split(":")[0], []).append((f, r["n"]))
    return out


def dai_of_question(inp, q, sids, turn=None):
    """質問（iq の ID）と、出すものに付いた段落の発言の sid の集まり → 台帳の題の (from, n) の並び（SCHEMA.md 7.11）。
    質問の発言を含む議員の区切り（台帳の from）の題のうち、sids の発言を turns に含む題。当たる題が無いときは、質問の発言が
    from なら、その区切りの題の全部（テーマの定義に無い質問の題と同じ決め方。SCHEMA.md 7.10）、from でなければ、質問の発言を
    turns に含む題。台帳に無い質問は空。"""
    turn = turn_index(inp) if turn is None else turn
    ip = inp.ippan()
    sid = keys.sid_of(q)
    f = sid if sid in ip else (turn.get(sid) or [(None, None)])[0][0]
    if f is None:
        return []
    rs = ip[f]
    ate = [r for r in rs if {t.split(":")[0] for t in r["turns"].split(";") if t} & set(sids)]
    if not ate:
        ate = rs if sid == f else [r for r in rs if (f, r["n"]) in turn.get(sid, [])]
    return [(f, r["n"]) for r in ate]


def ronten_of_dai(inp, pages):
    """pages（テーマ → (論点の仮の表, build_note.Page)。tools/build_mcp.py の tk.note と同じ形）→ 題の (from, n) →
    論点の (名前, ID, テーマ) の並び。論点の質問（Page.ronten の qs。確定済みの記録と、質問と事項の対応の表）のうち一般質問を、
    dai_of_question で題に結び付ける。論点ごとに、名前、ID、テーマ（その論点を最初に見つけたテーマ）。並びは、テーマの順と
    論点の順。同じ ID は1つにする。"""
    turn = turn_index(inp)
    out = {}
    for theme, (T, pg) in pages.items():
        for P, slug, _, _ in T["topics"]:
            for q in pg.ronten(P)["qs"]:
                if q["sitsugi"]:
                    continue
                for k in dai_of_question(inp, q["question"], {sid for sid, _, _ in q["paras"]}, turn):
                    if slug not in [s for _, s, _ in out.get(k, [])]:
                        out.setdefault(k, []).append((P, slug, theme))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="一般質問の題と、総合計画の分野の対応の表を作る")
    p.add_argument("--kensa", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        rows, bad, kk = tsukuru(inp)
    except (inputs.InputError, BunyaError, OSError, ValueError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    if bad:
        print(f"止めた：合わないものがある（{len(bad)} 件）", file=sys.stderr)
        print("\n".join("  - " + b for b in bad), file=sys.stderr)
        return 1
    s = dumps(rows)
    b = [r for r in rows if r["bunya"]]
    w = [r for r in rows if r["wadai"]]
    n = {y: sum(r["yomi"] == y for r in b) for y in YOMI}
    nw = {y: sum(r["yomi"] == y for r in w) for y in YOMI}
    nc = {y: sum(r["chushin"] == y for r in b) for y in YOMI}
    print(f"題 {len({(r['from'], r['n']) for r in rows})}。分野の行 {len(b)}（一致 {n[ICCHI]}、1回だけ {n[IKKAI]}。"
          f"中心の分野 一致 {nc[ICCHI]}、1回だけ {nc[IKKAI]}）。話題の行 {len(w)}（一致 {nw[ICCHI]}、1回だけ {nw[IKKAI]}）")
    if a.kensa:
        moto = None
        if os.path.exists(PATH):
            with open(PATH, encoding="utf-8") as f:
                moto = f.read()
        if moto != s:
            print("止めた：作り直した行が taio/bunya.tsv と違う。python3 -B tools/bunya.py で作り直して、コミットする。",
                  file=sys.stderr)
            return 1
        print(f"taio/bunya.tsv と同じ（{len(rows)} 行）")
        return 0
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"taio/bunya.tsv（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
