"""論点ノートの試作のページを作る。

実行：python3 -B tools/build_note.py <テーマ>   （例 hoiku → build/note/hoiku.html）
テーマの名前・論点・準備中の論点などは teigi/note-<テーマ>.tsv（試作のための仮の表。SCHEMA.md §8）から読む。
事項の表（teigi/jiko.tsv。SCHEMA.md 7.9）にそのテーマの行があるテーマは、論点の一覧を事項の表から作る（jiko_ni_suru）。
記述は hino-ronten の確定した記録（SCHEMA.md §1）から取る。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 引用がもとの資料に無い行（段落の ID が発言の段落を指していない行を含む）
  (b) 出典の無い記述
  (c) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの引用の中は除く）
  (d) lock と入力が合わない
"""
import datetime
import html
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402
import ronten  # noqa: E402
import shogo  # noqa: E402
import yomi as ym  # noqa: E402

TEIGI_COLUMNS = ["kind", "key", "name", "short", "setsumei"]
TEIGI_KINDS = ("テーマ", "論点", "準備中", "抜き出しの語", "単位", "注")
DESIGN_PATH = os.path.join(inputs.ROOT, "docs", "design.md")
DESIGN_SETSU = "## 2. 画面に出す言葉"   # 言葉の表を読む節の見出し
OUT_DIR = os.path.join(inputs.ROOT, "build", "note")
SITE = "日野町 論点ノート（非公式・試作）"
NOKOSU = "- 次の言葉の一部として出る場合も、残っていると見ない："   # docs/design.md 2節

# 資料からの文（引用・会議録の段落・資料の題・発言者の名前）の始めと終わりの印。言葉の検査で除き、書き出す前に消す。
A, B = "", ""


class Stop(Exception):
    """作る前の検査に当たった。problems は (区分, 該当の文) の並び。"""

    def __init__(self, problems):
        super().__init__(f"{len(problems)} 件")
        self.problems = problems


def E(s):
    return html.escape(s)


def S(s):
    """資料からの文：エスケープして印で囲む。"""
    return A + html.escape(s) + B


def S_kagi(s):
    """「」の中だけを資料からの文とする（問いの題など）。"""
    return re.sub(r"「[^」]*」", lambda m: A + m.group(0) + B, html.escape(s))


# ---- 項目の表と言葉の表 ----

def read_teigi(path, theme):
    with open(path, encoding="utf-8") as f:
        rows = inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), TEIGI_COLUMNS)
    errs = [f"{i} 行目：kind が {TEIGI_KINDS} のどれでもない（{r['kind']}）"
            for i, r in enumerate(rows, 2) if r["kind"] not in TEIGI_KINDS]
    t = [r for r in rows if r["kind"] == "テーマ"]
    if len(t) != 1 or t[0]["key"] != theme:
        errs.append(f"テーマの行が1行でないか、key が {theme} でない")
    tp = [r for r in rows if r["kind"] == "論点"]
    if not tp or any(not (r["key"] and r["name"] and r["short"] and r["setsumei"]) for r in tp):
        errs.append("論点の行が無いか、key・name・short・setsumei に空がある")
    if errs:
        raise inputs.InputError(f"{path}：{len(errs)} 件\n" + "\n".join(f"  - {e}" for e in errs))
    return dict(theme=t[0]["name"], setsumei=t[0]["setsumei"],
                topics=[(r["name"], r["key"], r["short"], r["setsumei"]) for r in tp],
                junbi=[r["name"] for r in rows if r["kind"] == "準備中"],
                words=[r["name"] for r in rows if r["kind"] == "抜き出しの語"],
                units=[(r["key"], r["name"]) for r in rows if r["kind"] == "単位"],
                chu=[dict(source=r["key"], part=r["name"], moto=r["short"], text=r["setsumei"])
                     for r in rows if r["kind"] == "注"])


def shudai_of(theme, jiko_rows=None, shudai=None):
    """質問と事項の対応の表（taio/shudai.tsv。生成AIの2回の読み取り）のうち、事項がそのテーマの行の行。
    ほかのテーマと共通の事項（SCHEMA.md 7.9）は、どのテーマで読んだ行も入れる。
    行ごとに point（事項の name）を付ける。表が無ければ空。"""
    jiko_rows = jiko.read() if jiko_rows is None else jiko_rows
    if shudai is None:
        shudai = ym.read() if os.path.exists(ym.PATH) else []
    names = {r["id"]: r["name"] for r in jiko.of_theme(jiko_rows, theme)}
    return [dict(r, point=names[r["jiko"]]) for r in shudai if r["jiko"] in names]


def ippan_src(inp, q, paras=None):
    """テーマの定義に無い一般質問の、題の字（qhead_parts で読める形）。一般質問の台帳（hino-council-search の
    data/ippan.tsv）の、議員の名前と題名から作る。台帳に無ければ空。
    paras（出すものに付いた段落。発言の sid と段落の番号の組の集まり）を渡したときは、その段落が範囲に入る題の題名だけを
    並べる（dai_gyo）。当たる題が無ければ、全部の題名を並べる（SCHEMA.md 7.10。2026-11-28）。"""
    rs = inp.ippan().get(keys.sid_of(q), [])
    if not rs:
        return ""
    if paras:
        rs = dai_gyo(inp, q, paras) or rs
    return f"{inp.role(keys.sid_of(q)) or '0番'} {rs[0]['member']} " + "".join(f"「{r['title']}」" for r in rs)


def dai_gyo(inp, q, paras):
    """質問と、出すものに付いた段落の集まり → 台帳の題の行の並び（inputs.Inputs.ippan_dai）。議案への質疑と、台帳に無い
    質問は空。論点の応答（issue）と試作のページ、資料と出来事の応答の題（dai_of）と、分野の応答（field）の論点の添え方
    （tools/bunya.py の dai_of_question）が、この関数で題を決める（SCHEMA.md 7.10・7.11。2026-11-28）。"""
    if not q.startswith("iq:"):
        return []
    return inp.ippan_dai(keys.sid_of(q), paras)[1]


def dai_of(inp, q, qsrc, paras, nashi):
    """質問の題。一般質問の台帳にある質問は、テーマの定義にあるかどうかにかかわらず、paras の段落が範囲に入る題の題名
    （dai_gyo。当たる題が無いときの扱いは inputs.Inputs.ippan_dai）を「」で囲んで並べる。題名が空の題は nashi の文
    （docs/design.md の bunya-dai-nashi）。台帳に無い質問（議案への質疑など）は qsrc の字から（SCHEMA.md 7.10）。"""
    rs = dai_gyo(inp, q, paras)
    if rs:
        return "".join(f"「{r['title']}」" if r["title"].strip() else nashi for r in rs)
    return qhead_parts(qsrc.get(q, ""))[1]


def jiko_ni_suru(inp, teigi, theme, rows=None, shudai=None):
    """事項の表にそのテーマの行があれば、論点の一覧を事項の表から作る（SCHEMA.md 7.9。2026-11-27 の依頼者の決定）。

    teigi["jiko"] に、事項の表の行（表の順）を入れ、行ごとに aru（確定済みの事柄の記録か、そのテーマの質問・質疑との
    確定済みの対応の記録が、name にあるか）を付ける。teigi["topics"] は aru の行だけにする（論点のページと issue を作る行）。
    short と setsumei は、仮の表の論点の行に同じ key があればその字、無ければ name。行が無いテーマは何もしない。
    合わないもの（仮の表の論点の key が事項の表に無いか name が違う、準備中の行がある）は InputError。"""
    rows = jiko.read() if rows is None else rows
    rows = jiko.of_theme(rows, theme)
    teigi["jiko"] = None
    if not rows:
        return teigi
    by = {r["id"]: r for r in rows}
    errs = [f"論点の行 {k}（{P}）が、事項の表に無いか、name が違う"
            for P, k, _, _ in teigi["topics"] if k not in by or by[k]["name"] != P]
    if teigi["junbi"]:
        errs.append("準備中の行がある（事項の表があるテーマでは、記録の無い事項を事項の表から出す）")
    if errs:
        raise inputs.InputError(f"teigi/note-{theme}.tsv：{len(errs)} 件\n" + "\n".join(f"  - {e}" for e in errs))
    nagai = {k: (sh, se) for _, k, sh, se in teigi["topics"]}
    trows = ronten.themes(inp, theme)
    qs = {r["value"] for r in trows if r["kind"] in ("問い", "質疑")}
    names = {r["name"] for r in rows}
    aru = {r["point"] for r in ronten.kotogara(inp, names)} | (ronten.taio_points(inp, qs) & names)
    teigi["shudai"] = shudai_of(theme, rows, shudai)    # 生成AIの2回の読み取りの行（SCHEMA.md 7.10）
    aru |= {r["point"] for r in teigi["shudai"]}
    teigi["jiko"] = [dict(r, aru=r["name"] in aru) for r in rows]
    teigi["topics"] = [(r["name"], r["id"]) + nagai.get(r["id"], (r["name"], r["name"])) for r in rows if r["name"] in aru]
    return teigi


def jiko_matome(inp, teigi):
    """事項の表の行を、計画の章立ての要素ごとにまとめる（SCHEMA.md 7.9、docs/design.md 4節）。
    → (計画の名前（章立ての番号 0 の要素の name）, [(要素の行か None, 事項の行の並び)])。
    要素は章立ての順（n の順）。taikei が nashi の行は、最後に None のまとまりにする。
    テーマの行の taikei が全部 nashi のとき（章立てが無いテーマ。kokyo と chiiki）は、計画の名前を None にし、
    全部の行を None のまとまりにする（2026-11-28）。
    章立てが2つ以上の体系にまたがるときは InputError（計画の名前を1つに決められないため）。"""
    tk = ronten.taikei(inp)
    rows = teigi["jiko"]
    taikei = {tk[r["taikei"]]["taikei"] for r in rows if r["taikei"] != "nashi"}
    if not taikei:
        return None, [(None, rows)]
    if len(taikei) != 1 or f"tk:{next(iter(taikei))}/0" not in tk:
        raise inputs.InputError(f"事項の表の {rows[0]['theme']} の行の章立てが、1つの体系でないか、番号 0 の要素が無い（{sorted(taikei)}）")
    keikaku = tk[f"tk:{next(iter(taikei))}/0"]["name"]
    youso = sorted({r["taikei"] for r in rows if r["taikei"] != "nashi"}, key=lambda k: int(tk[k]["n"]))
    out = [(tk[k], [r for r in rows if r["taikei"] == k]) for k in youso]
    nashi = [r for r in rows if r["taikei"] == "nashi"]
    if nashi:
        out.append((None, nashi))
    return keikaku, out


def nashi_wake(rows, matome_saki=False):
    """章立てに入らない事項の行 → [(まとまりの名前, 行の並び)]（SCHEMA.md 7.9、docs/design.md 4節。2026-11-28）。
    章立てがあるテーマ（matome_saki が偽）は、matome が空の行を先に（名前は空）、そのあとに、matome のある行を、まとまり
    ごとに、表で最初に出る順に並べる。matome が空の行が無くても、見出しのために先頭を残す。
    章立てが無いテーマ（matome_saki が真）は、まとまりを先に並べ、matome が空の行をそのあとに置く（行が無ければ置かない）。
    どちらも、matome が jiko.HOKA の行は、最後に置く。"""
    mt = jiko.matome_jun(rows)
    hoka = mt.pop(jiko.HOKA, None)
    kara = ("", [r for r in rows if not r.get("matome")])
    if matome_saki:
        out = list(mt.items()) + ([kara] if kara[1] else [])
    else:
        out = [kara] + list(mt.items())
    if hoka:
        out.append((jiko.HOKA, hoka))
    return out


def _words(cell):
    return [w.strip() for w in re.sub(r"（[^）]*）", "", cell).split("、") if w.strip()]


def read_kotoba(path=DESIGN_PATH):
    """docs/design.md 2節の言葉の表 → (使わない語, 確認する所) の並びと、使う語の集まり。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    try:
        s = lines.index(DESIGN_SETSU)
    except ValueError:
        raise inputs.InputError(f"{path}：節の見出し（{DESIGN_SETSU}）が無い")
    e = next((j for j in range(s + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    lines = lines[s:e]
    try:
        i = lines.index("| 使わない | 使う | 確認する所 |")
    except ValueError:
        raise inputs.InputError(f"{path}：言葉の表の見出しの行が無い")
    ng, ok = [], set()
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3 or cells[2] not in ("文", "リンクの名前"):
            raise inputs.InputError(f"{path}：言葉の表の行の形が違う（{line}）")
        ng += [(w, cells[2]) for w in _words(cells[0])]
        ok |= set(_words(cells[1]))
    if not ng:
        raise inputs.InputError(f"{path}：言葉の表に行が無い")
    # 表の読み方の項目のうち、「次の言葉の一部として出る場合も、残っていると見ない：…」の言葉も、同じ扱いにする
    for line in lines[:i]:
        if line.startswith(NOKOSU):
            ok |= {w.strip() for w in line[len(NOKOSU):].rstrip("。").split("、") if w.strip()}
    return ng, ok


class _Text(HTMLParser):
    """画面に出る文（タグを除いた字）と、リンクの文字を集める。style と script の中は除く。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self._skip, self._a = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip += 1
        elif tag == "a":
            self._a = []

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip -= 1
        elif tag == "a" and self._a is not None:
            self.links.append("".join(self._a))
            self._a = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._a is not None:
            self._a.append(data)


def screen_text(page):
    p = _Text()
    p.feed(page)
    return p.parts, p.links


def drop_marked(s):
    return re.sub(A + "[^" + B + "]*" + B, "\n", s)


def kotoba_problems(page, ng, ok):
    """印の付いた文（資料からの文）を除いた画面の文に、使わない語が残っていれば、語と前後の字を返す。"""
    parts, links = screen_text(page)
    targets = {"文": drop_marked("\n".join(parts)), "リンクの名前": drop_marked("\n".join(links))}
    out = []
    for w, where in ng:
        text = targets[where]
        covers = [(m.start(), m.end()) for o in ok if w in o and o != w for m in re.finditer(re.escape(o), text)]
        for m in re.finditer(re.escape(w), text):
            if any(a <= m.start() and m.end() <= b for a, b in covers):
                continue
            ctx = text[max(0, m.start() - 15):m.end() + 15].replace("\n", "／")
            out.append(("(c) 使わない言葉", f"「{w}」（{where}）：…{ctx}…"))
    return out


# ---- 記録を集める ----

def collect(inp, teigi, theme):
    """記録を集め、(a)(b) の検査を行う。返り値は (model, problems, quote_result)。
    事項の表があるテーマは、質問と事項の対応の表（taio/shudai.tsv）の行（jiko_ni_suru が teigi["shudai"] に入れたもの）も集める。"""
    trows = ronten.themes(inp, theme)
    qsrc = {r["value"]: r["source"] for r in trows if r["kind"] in ("問い", "質疑")}
    # 論点は、テーマの定義の事柄にあるか、そのテーマの質問・質疑との確定済みの対応の記録があるもの（SCHEMA.md §8。
    # 確定済みの記録があるものを出さないままにしない。2026-11-27 の依頼者の決定）
    points = {r["value"] for r in trows if r["kind"] == "事柄"} | ronten.taio_points(inp, set(qsrc))
    problems = []
    yomi = teigi.get("shudai") or [] if teigi.get("jiko") else []
    points |= {r["point"] for r in yomi}
    for q in dict.fromkeys(r["question"] for r in yomi):
        if q not in qsrc:
            qsrc[q] = ippan_src(inp, q)       # テーマの定義に無い質問の、議員の名前と題名（題は dai_of で選ぶ）
    for P, *_ in teigi["topics"]:
        if P not in points:
            problems.append(("定義", f"論点「{P}」が、hino-ronten の題材 {theme} の事柄に無く、"
                                     "その題材の質問・質疑との確定済みの対応の記録も無い"))
    names = [t[0] for t in teigi["topics"]]
    ko = ronten.kotogara(inp, set(names))
    katei = ronten.katei(inp, theme)
    _, more = ronten.katei_dasanai(inp, theme)      # 出さない過程の記録の行が、理由の条件に当たるか（SCHEMA.md §1）
    problems += [("(b) 出典の無い記述", m) for m in more]
    ta = ronten.taio(inp, set(names), set(qsrc))

    # (a) 引用と段落
    qrows = [dict(where=f"事柄の記録 {r['point']} / {r['source']}", source=r["source"], quote=r["quote"])
             for r in ko]
    qrows += [dict(where=f"過程の記録 {theme} step {r['step']}", source=r["sources"].split(",")[0],
                   quote=r["quote"]) for r in katei]
    res = shogo.check_quotes(inp, qrows)
    pres = shogo.check_paras(inp, [dict(where=f"問いと事項の対応 {r['question']} / {r['point']}", hani=r["hani"])
                                   for r in ta])
    pres2 = shogo.check_paras(inp, [dict(where=f"質問と事項の対応の表 {r['question']} / {r['jiko']}", hani=r["hani"])
                                    for r in yomi])
    pres.total += pres2.total
    pres.matched += pres2.matched
    pres.mismatched += pres2.mismatched
    for m in res.mismatched + pres.mismatched:
        problems.append(("(a) 引用がもとの資料に無い", f"{m['where']}：{m['reason']}（{m['source']}）"
                         + (f"「{m['quote']}」" if m["quote"] else "")))

    # (b) 出典
    def named(key):
        try:
            return keys.source_name(inp, key), keys.source_url(inp, key)
        except keys.KeyFormError:
            return "", ""

    for r in ko:
        n, u = named(r["source"]) if r["source"] else ("", "")
        if not (n and u):
            problems.append(("(b) 出典の無い記述", f"事柄の記録 {r['point']}：資料「{r['source']}」の名前か url が作れない"))
    for r in katei:
        srcs = [s for s in r["sources"].split(",") if s]
        if not srcs or any(not named(s)[0] for s in srcs[:2]):
            problems.append(("(b) 出典の無い記述", f"過程の記録 {theme} step {r['step']}：資料が無いか、名前が作れない（{r['sources']}）"))
    for r in ta + yomi:
        if not r["hani"] or not qhead_parts(qsrc.get(r["question"], ""))[1]:
            problems.append(("(b) 出典の無い記述", f"問いと事項の対応 {r['question']} / {r['point']}：範囲か問いの題が無い"))
    # 目的と手段（SCHEMA.md 7.9）：入力のつながりの記録のうち、両端が事項の表にある行。引用と出典を、ほかと同じく検査する
    moku = jiko.mokuteki_gyo(inp, jiko.read()) if teigi.get("jiko") else []
    mres = shogo.check_quotes(inp, [dict(where=f"つながりの記録 {r['upper']} → {r['lower']} / {r['source']}",
                                         source=r["source"], quote=r["quote"]) for r in moku])
    for m in mres.mismatched:
        problems.append(("(a) 引用がもとの資料に無い", f"{m['where']}：{m['reason']}（{m['source']}）「{m['quote']}」"))
    for r in moku:
        n, u = named(r["source"]) if r["source"] else ("", "")
        if not (n and u):
            problems.append(("(b) 出典の無い記述", f"つながりの記録 {r['upper']} → {r['lower']}：資料「{r['source']}」の名前か url が作れない"))
    # 注（SCHEMA.md §5）：付ける記述があるか、注のもとの資料があるか、「」の字が資料にあるか
    for c in teigi.get("chu", []):
        where = f"注 {c['source']}「{c['part']}」"
        if not (c["source"] and c["part"] and c["moto"] and c["text"]):
            problems.append(("定義", f"{where}：key・name・short・setsumei に空がある"))
            continue
        if not any(r["source"].split("/")[0] == c["source"].split("/")[0] and c["part"] in r["quote"] for r in ko):
            problems.append(("定義", f"{where}：注を付ける記述が見つからない"))
        n, u = named(c["moto"])
        if not (n and u):
            problems.append(("(b) 出典の無い記述", f"{where}：注のもとの資料「{c['moto']}」の名前か url が作れない"))
        frs = re.findall(r"「([^」]+)」", c["text"])
        cres = shogo.check_quotes(inp, [dict(where=where, source=c["moto"], quote=f) for f in frs])
        for m in cres.mismatched:
            problems.append(("(a) 引用がもとの資料に無い", f"{m['where']}：{m['reason']}（{m['source']}）「{m['quote']}」"))
    return dict(ko=ko, katei=katei, ta=ta, qsrc=qsrc, mokuteki=moku, yomi=yomi), problems, (res, pres)


# ---- ページ ----

def qhead_parts(src):
    m = re.search(r"\d+番 (\S+) (.*)$", src)
    who = m.group(1) + "議員" if m else ""
    dai = m.group(2) if m else src
    dai = re.sub(r"^問\d+", "", dai)
    dai = re.sub(r"。?テーマにかかわる部分：.*$", "", dai)
    return who, dai


def qdate(q):
    return keys.sid_date(keys.sid_of(q))


def qhead(q, who, dai):
    kind = "議案への質疑" if q.startswith("sq:") else "一般質問"
    return f"{keys.ymd(qdate(q))}　{kind}（{S(who)}）{S_kagi(dai)}"


def yomi_go(D, yomi):
    """段落の yomi（「一致」か「1回だけ」）→ 言葉（docs/design.md 3節）。MCP の応答（tools/build_mcp.py）も使う。"""
    if yomi == ym.ICCHI:
        return D.kotoba("質問と事項の対応の表 yomi が「一致」")
    if yomi == ym.IKKAI:
        return D.kotoba("質問と事項の対応の表 yomi が「1回だけ」")
    raise ValueError(f"yomi が違う（{yomi}）")


def kakunin_go(D, q):
    """質問（Page.ronten の qs の1つ）→ 人が確認した質問か、生成AIが2回読んだ質問（未確認）かの言葉。
    MCP の応答（tools/build_mcp.py）も使う。"""
    D.dasanai("質問と事項の対応の表 chu")
    return D.kotoba("質問と事項の対応の表 question") if q["mikakunin"] else D.bun("shitsumon-kakutei")


class Page:
    def __init__(self, inp, teigi, model, D=None):
        if D is None:
            import build_suji  # docs/design.md 3節の言葉（build_suji が、このファイルを読み込むので、ここで読む）
            D = build_suji.read_design()
        self.inp, self.t, self.m, self.D = inp, teigi, model, D
        self.pat = re.compile("|".join(re.escape(w) for w in teigi["words"])) if teigi["words"] else None

    def srcname(self, key):
        return keys.source_name(self.inp, key.split("「")[0])

    def url(self, x):
        p = None
        if x["source"].startswith("sp:"):
            p = shogo.para_of_quote(self.inp.statement_text(keys.sid_of(x["source"])), x["quote"])
        return keys.source_url(self.inp, x["source"], p)

    def link(self, x):
        return f"<a href='{E(self.url(x))}' target='_blank'>{S(self.srcname(x['source']))}</a>"

    def atai_shu(self, x):
        """記述の値 → ("kingaku", 単位を付けた字) か ("suchi", 字) か None。MCP の応答（tools/build_mcp.py）も使う。"""
        v = x["value"]
        if not v:
            return None
        if re.fullmatch(r"[\d,]+", v):
            unit = next((u for head, u in self.t["units"] if x["source"].startswith(head)), "")
            if unit:
                return ("kingaku", v + unit)
        if re.fullmatch(r"[\d,\.]+", v):
            return ("suchi", v)
        return None

    def atai(self, x):
        a = self.atai_shu(x)
        if a is None:
            return ""
        if a[0] == "kingaku":
            return "金額：" + S(a[1])
        return "数値：" + S(a[1]) + "（資料に単位の記述なし）"

    @staticmethod
    def doko(x):
        return "議会での答弁" if x["source"].startswith("sp:") else "町の資料"

    def katei_rows(self):
        def kikan(x):
            f, t = x["from"], x["to"]
            return keys.ymd(f) + ("〜" + keys.ymd(t) if t and t != f else "") if f else ""
        return "".join(f"<tr><td class='nw'>{kikan(x)}</td><td>{E(x['name'])}</td>"
                       f"<td>{'、'.join(S(self.srcname(s)) for s in x['sources'].split(',')[:2])}</td></tr>"
                       for x in sorted(self.m["katei"], key=lambda x: x.get("from") or "", reverse=True))

    def chu_list(self, sid_or_source, text):
        """その資料の、その字を含む文に付ける「作成者の注」の並び。注ごとに、文（text）、注のもとの資料の ID（moto）、
        外部の公的な資料なら確認した日（kakunin。ほかは空）。MCP の応答（tools/build_mcp.py）も使う。"""
        out = []
        for c in self.t.get("chu", []):
            if c["source"].split("/")[0] == sid_or_source.split("/")[0] and c["part"] in text:
                k = ""
                if c["moto"].startswith("ext:"):
                    k = next(r["kakunin"] for r in self.inp.gaibu() if c["moto"] == f"ext:{r['id']}/{r['page']}")
                out.append(dict(text=c["text"], moto=c["moto"], kakunin=k))
        return out

    def chu(self, sid_or_source, text):
        """その資料の、その字を含む文に付ける「作成者の注」。無ければ空。"""
        out = []
        for c in self.chu_list(sid_or_source, text):
            link = f"<a href='{E(keys.source_url(self.inp, c['moto']))}' target='_blank'>{S(keys.source_name(self.inp, c['moto']))}</a>"
            if c["kakunin"]:
                link += f"　{keys.ymd(c['kakunin'])}に確認"
            out.append(f"<div class='chu'>作成者の注：{E(c['text'])}（もとの資料：{link}）</div>")
        return "".join(out)

    def ronten(self, P):
        """論点 P の記述と質問を集める（試作のページと MCP の応答の、共通の集め方）。
        → dict(ko：記述（新しい順）, docs：町の資料の記述（新しい順）, tome：今後検討・決定するとされていること,
               jisseki：実績の記述があるか, qs：質問（日付の新しい順）。質問ごとに question、date、sitsugi（議案への質疑か）、
               who、dai、paras（(sid, 段落の番号, 段落の文) の並び）,
               mokuteki：目的と手段の相手ごとに、gawa（相手の側。"upper" は目的、"lower" は手段）、name（相手の名前）、
               slug（相手の論点の ID。論点のページと issue が無い相手は空）、rows（つながりの記録の行。資料の日付の新しい順）)"""
        ko = sorted([x for x in self.m["ko"] if x["point"] == P], key=lambda x: x["source_date"], reverse=True)
        docs = sorted([x for x in ko if not x["source"].startswith("sp:")], key=lambda x: x["source_date"], reverse=True)
        tome = [x for x in ko if self.pat and self.pat.search(x["quote"])]
        ta = [r for r in self.m["ta"] if r["point"] == P]
        qs = []
        for r in ta:
            q = r["question"]
            who = qhead_parts(self.m["qsrc"].get(q, ""))[0]
            paras = [(sid, i, inputs.paragraphs(self.inp.statement_text(sid))[i - 1]) for sid, i in keys.paras_of(r["hani"])]
            dai = self.dai(q, {(sid, i) for sid, i, _ in paras})
            qs.append(dict(question=q, date=qdate(q), sitsugi=q.startswith("sq:"), who=who, dai=dai, paras=paras,
                           mikakunin=False, yomi={}))
        # 生成AIの2回の読み取りの行（SCHEMA.md 7.10）。質問ごとに段落をまとめ、段落ごとに一致か1回だけかを持つ
        yq = {}
        for r in self.m.get("yomi", []):
            if r["point"] == P:
                for p in keys.paras_of(r["hani"]):
                    d = yq.setdefault(r["question"], {})
                    d[p] = ym.yomi_awase(d.get(p), r["yomi"])     # 2つのテーマの読み取りの行（SCHEMA.md 7.10）
        for q, fl in yq.items():
            who = qhead_parts(self.m["qsrc"].get(q, ""))[0]
            paras = [(sid, i, inputs.paragraphs(self.inp.statement_text(sid))[i - 1]) for sid, i in sorted(fl)]
            dai = self.dai(q, set(fl))
            qs.append(dict(question=q, date=qdate(q), sitsugi=q.startswith("sq:"), who=who, dai=dai, paras=paras,
                           mikakunin=True, yomi=fl))
        qs.sort(key=lambda x: x["date"], reverse=True)
        slugs = {p: k for p, k, _, _ in self.t["topics"]}
        aite = {}
        for r in self.m.get("mokuteki", []):
            for mine, other in (("upper", "lower"), ("lower", "upper")):
                if r[mine] == P:
                    aite.setdefault((other, r[other]), []).append(r)
        moku = [dict(gawa=g, name=n, slug=slugs.get(n, ""),
                     rows=sorted(rs, key=lambda r: (r["source_date"], r["source"]), reverse=True))
                for (g, n), rs in aite.items()]
        return dict(ko=ko, docs=docs, tome=tome, jisseki=any(x["kind"] == "実績" for x in ko), qs=qs, mokuteki=moku)

    def dai(self, q, paras):
        """質問の題（dai_of）。paras は、出すものに付いた段落（発言の sid と段落の番号の組）の集まり。"""
        return dai_of(self.inp, q, self.m["qsrc"], paras, self.D.bun("bunya-dai-nashi"))

    def topic(self, P, slug, short, setsumei):
        inp, T, qsrc = self.inp, self.t, self.m["qsrc"]
        R = self.ronten(P)
        ko, docs = R["ko"], R["docs"]
        sec1 = "".join(f"<div class='now'><div>「{S(x['quote'])}」</div><div class='m'>{keys.ymd(x['source_date'])}の資料　"
                       f"{self.link(x)}{'　' + self.atai(x) if self.atai(x) else ''}</div></div>" for x in docs) \
            or "<p class='m'>町の資料の記述は、まだ整理できていません。</p>"
        rows2 = "".join(f"<tr><td class='nw'>{keys.ymd(x['source_date'])}</td><td class='nw'>{self.doko(x)}</td>"
                        f"<td>「{S(x['quote'])}」{'<br><span class=m>' + self.atai(x) + '</span>' if self.atai(x) else ''}{self.chu(x['source'], x['quote'])}</td>"
                        f"<td>{self.link(x)}</td></tr>" for x in ko)
        tome = R["tome"]
        rows3 = "".join(f"<tr><td class='nw'>{keys.ymd(x['source_date'])}</td><td>「{S(x['quote'])}」</td>"
                        f"<td>{self.link(x)}</td></tr>" for x in tome)
        ta = R["qs"]
        D = self.D
        blocks = []
        for r in ta:
            q = r["question"]
            ps = r["paras"]
            body, cur = [], None
            for sid, i, para in ps:
                if sid != cur:
                    cur = sid
                    body.append(f"<div class='spk'>{S(inp.speaker(sid))}</div>")
                yl = f"<span class='m'>（{E(self.yomi_go(r['yomi'][(sid, i)]))}）</span>" if r["mikakunin"] else ""
                body.append(f"<div class='para'>{S(para)}　<a href='{E(keys.search_url(sid, i))}' target='_blank'>会議録</a>{yl}{self.chu('sp:' + sid, para)}</div>")
            blocks.append(f"<div class='qa'><h3>{qhead(q, r['who'], r['dai'])}</h3><p class='m'>{E(self.kakunin_go(r))}</p>"
                          f"<details><summary>{E(short)}に関する部分を表示（{len(ps)}か所）</summary>"
                          f"{''.join(body)}</details><p class='m'><a href='{E(keys.source_url(inp, q))}' target='_blank'>"
                          f"会議録でこの質問の全体を見る</a></p></div>")
        sib = "／".join(f"<a href='#{s}'>{E(p)}</a>" for p, s, _, _ in T["topics"] if s != slug)
        jis = ""        # 実績が無いことの文は出さない（事柄の記録の kind に「実績」が無く、いつも出てしまうため。2026-11-27）
        sec3 = (f"<h2>今後検討・決定するとされていること</h2><table><tr><th>時期</th><th>内容</th><th>もとの資料</th></tr>{rows3}</table>"
                "<p class='m'>上の表のうち、「まだ」「今後」などの語を含む記述を抜き出しています。その後の状況は、上の表で、より新しい時期の記述を確認してください。</p>") \
            if tome else ""
        th = E(T["theme"])
        sec_m = self.mokuteki_html(R["mokuteki"])
        yset = f"<p class='m'>{E(D.bun('yomi-setsumei', short=short))}</p>" if any(x["mikakunin"] for x in ta) else ""
        keisai = (E(D.bun("keisai-yomi", short=short)) if any(x["mikakunin"] for x in ta)
                  else f"掲載しているのは、内容を確認できた質問です。ほかの質問でも、{E(short)}が取り上げられている場合があります。")
        h = f"""<section id='{slug}' class='page'>
<p class='lead'><a href='#top'>{SITE}</a> ＞ <a href='#top'>{th}</a> ＞ {E(P)}</p>
<h1>{E(P)}</h1>
<p class='lead'>「{th}」のうち、{E(setsumei)}について、町の資料と議会の会議録の記述を集めたページです。意見や評価は加えていません。各項目のリンクから、もとの資料を確認できます。</p>
<div class='nav'><b>同じテーマのほかのページ</b>：{sib}　<a href='#top'>テーマのページへ戻る</a></div>
<h2>町の資料の記述（新しい順）</h2>{sec1}
<h2>これまでの説明と答弁（新しい順）</h2>
<table><tr><th>時期</th><th>区分</th><th>内容</th><th>もとの資料</th></tr>{rows2}</table>{jis}
{sec3}{sec_m}
<h2>議会での質問と答弁（{len(ta)}件）</h2>
<p class='m'>一つの質問では、複数の話題が取り上げられます。ここでは、{E(short)}に関する部分だけを抜き出しています。質問の全体は、会議録で確認できます。</p>{yset}{''.join(blocks)}
<p class='m'>{keisai}</p>
</section>"""
        return h, len(ko), len(ta), [(r["question"], {(sid, i) for sid, i, _ in r["paras"]}) for r in ta]

    def yomi_go(self, yomi):
        return yomi_go(self.D, yomi)

    def kakunin_go(self, q):
        return kakunin_go(self.D, q)

    def mokuteki_html(self, moku):
        """目的と手段（docs/design.md 4節）。相手が無ければ空。言葉は docs/design.md 3節から引く。"""
        if not moku:
            return ""
        D = self.D
        rows = []
        for a in moku:
            yaku = D.kotoba("つながりの記録 upper") if a["gawa"] == "upper" else D.kotoba("つながりの記録 lower")
            name = f"<a href='#{a['slug']}'>{E(a['name'])}</a>" if a["slug"] else E(a["name"])
            for r in a["rows"]:
                rows.append(f"<tr><td>{E(yaku)}：{name}</td><td>「{S(r['quote'])}」</td>"
                            f"<td>{self.link(r)}</td></tr>")
        return (f"<h2>{E(D.kotoba('つながりの記録 link が「目的と手段」'))}</h2>"
                f"<p class='m'>{E(D.bun('mokuteki-setsumei'))}</p><table><tr><th>{E(D.bun('mokuteki-aite'))}</th><th>{E(D.kotoba('つながりの記録 quote'))}</th>"
                f"<th>{E(D.kotoba('つながりの記録 source'))}</th></tr>{''.join(rows)}</table>")

    def ichiran_html(self, rows):
        """論点の一覧の表の行（HTML）。事項の表があるテーマは、計画の章立ての要素ごとにまとめ、種類を出す。"""
        T, D = self.t, self.D
        if not T.get("jiko"):
            return "".join(rows[s] for _, s, _, _ in T["topics"]), ""
        keikaku, matome = jiko_matome(self.inp, T)
        out = []
        D.dasanai("事項の表 matome")
        for youso, rs0 in matome:
            if keikaku is not None:
                mi = S(youso["name"]) if youso else E(D.bun("ronten-nashi", keikaku=keikaku))
                out.append(f"<tr><th colspan='4'>{mi}</th></tr>")
            for mt, rs in ([("", rs0)] if youso else nashi_wake(rs0, keikaku is None)):
                if mt:
                    out.append(f"<tr><th colspan='4'>{E(mt)}</th></tr>"
                               f"<tr><td colspan='4' class='m'>{E(D.bun('ronten-matome-setsumei'))}</td></tr>")
                elif keikaku is None:
                    out.append(f"<tr><th colspan='4'>{E(D.bun('ronten-matome-nashi'))}</th></tr>")
                for r in rs:
                    shu = E({"kadai": D.kotoba("事項の表 shurui が「kadai」"), "torikumi": D.kotoba("事項の表 shurui が「torikumi」"),
                             "atai": D.kotoba("事項の表 shurui が「atai」")}[r["shurui"]])
                    if r["aru"]:
                        out.append(rows[r["id"]].replace("</td>", f"</td><td>{shu}</td>", 1))
                    else:
                        out.append(f"<tr><td>{E(r['name'])}</td><td>{shu}</td><td colspan='2'>{E(D.bun('ronten-mada'))}</td></tr>")
        if keikaku is None:
            return "".join(out), f"<p class='m'>{E(D.bun('ronten-matome-jiko-setsumei'))}</p>"
        return "".join(out), f"<p class='m'>{E(D.bun('ronten-jiko-setsumei', keikaku=keikaku))}</p>"

    def render(self, today):
        T, qsrc = self.t, self.m["qsrc"]
        th = E(T["theme"])
        pages, rows, qmap, qsids, counts = [], {}, {}, {}, []
        for P, slug, short, setsumei in T["topics"]:
            h, nk, nt, qs = self.topic(P, slug, short, setsumei)
            pages.append(h)
            counts.append((P, nk, nt))
            rows[slug] = f"<tr><td><a href='#{slug}'>{E(P)}</a></td><td>{nk}件</td><td>{nt}件</td></tr>"
            for q, sids in qs:
                qmap.setdefault(q, []).append((P, slug))
                qsids.setdefault(q, set()).update(sids)
        # 題は、その質問が付いた論点の全部の段落で選ぶ（docs/design.md 4節。2026-11-28）
        qrows = "".join(f"<tr><td>{qhead(q, qhead_parts(qsrc.get(q, ''))[0], self.dai(q, qsids[q]))}</td><td>{'、'.join(f'<a href=#{s}>{E(p)}</a>' for p, s in ps)}</td>"
                        f"<td><a href='{E(keys.source_url(self.inp, q))}' target='_blank'>会議録</a></td></tr>"
                        for q, ps in sorted(qmap.items(), key=lambda kv: qdate(kv[0]), reverse=True))
        ichiran, ichiran_setsumei = self.ichiran_html(rows)
        shu_th = f"<th>{E(self.D.kotoba('事項の表 shurui'))}</th>" if T.get("jiko") else ""
        top = f"""<section id='top' class='page'>
<p class='lead'>{SITE} ＞ {th}</p>
<h1>{th}</h1>
<p class='lead'>{E(T['setsumei'])}について、町の資料と議会の会議録の記述を、論点ごとに整理しています。意見や評価は加えていません。</p>
<h2>論点ごとのページ</h2>{ichiran_setsumei}
<table><tr><th>論点</th>{shu_th}<th>町の資料・答弁の記述</th><th>議会での質問</th></tr>{ichiran}</table>
{"<p class='m'>準備中の論点：" + E('／'.join(T['junbi'])) + "　ほか</p>" if T['junbi'] else ""}
<h2>これまでの経過（新しい順）</h2>
<table><tr><th>時期</th><th>内容</th><th>もとの資料</th></tr>{self.katei_rows()}</table>
<h2>議会での質問から見る（{len(qmap)}件）</h2>
<p class='m'>一つの質問が、複数の論点にまたがることがあります。質問ごとに、関係する論点のページを示します。</p>
<table><tr><th>質問</th><th>関係する論点</th><th>全体</th></tr>{qrows}</table>
<p class='m'>{E(self.D.bun("keisai-yomi-theme")) if self.m.get("yomi") else "掲載しているのは、内容を確認できた質問です。このテーマに関する質問は、ほかにもあります。"}</p>
</section>"""
        page = f"""<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'><title>{th}｜{SITE}</title><style>
body{{font-family:sans-serif;max-width:920px;margin:1em auto;padding:0 1em;line-height:1.7;color:#222}}
h1{{font-size:1.3em;margin-bottom:.2em}} h2{{font-size:1.05em;border-top:2px solid #555;padding-top:.5em;margin-top:1.8em}} h3{{font-size:1em;margin:.2em 0}}
.lead,.m{{font-size:.88em;color:#555}} .now{{border-left:4px solid #2a6fb0;padding:.3em .7em;margin:.6em 0;background:#f4f8fc}}
table{{border-collapse:collapse;width:100%;font-size:.9em}} td,th{{border:1px solid #bbb;padding:.35em .5em;vertical-align:top;text-align:left}} th{{background:#eee}} .nw{{white-space:nowrap}}
.qa{{border:1px solid #bbb;border-radius:4px;padding:.5em .8em;margin:.7em 0}} .spk{{font-weight:bold;font-size:.9em;margin-top:.6em}} .para{{font-size:.92em;margin:.3em 0;padding-left:.6em;border-left:3px solid #ccc}}
.chu{{font-size:.88em;margin:.3em 0;padding:.3em .6em;border:1px dashed #888;background:#fffbe8}} .nav{{font-size:.85em;border:1px solid #ccc;padding:.4em .8em;margin:.6em 0}} .note{{font-size:.85em;background:#f6f6f6;border:1px solid #ccc;padding:.5em .8em;margin-top:2em}}
.page{{display:none}} .page.on{{display:block}}
</style></head><body>
{top}{''.join(pages)}
<div class='note'><b>このページについて</b><br>町と町議会が公開している資料（会議録、計画、当初予算の概要、広報ひの など）をもとに作成しています。掲載している文は資料からの引用で、要約や言い換えは行っていません。「作成者の注」とある所だけは、引用した文だけでは数の意味を読み違えるおそれがあるため、作成者が補った説明です。正確な内容は、もとの資料で確認してください。個人による試作であり、日野町および日野町議会の公式のものではありません。（{today.year}年{today.month}月{today.day}日作成）</div>
<script>
function show(){{var id=(location.hash||'#top').slice(1);var ps=document.querySelectorAll('.page');var hit=false;ps.forEach(function(p){{var on=p.id===id;p.classList.toggle('on',on);if(on)hit=true;}});if(!hit)document.getElementById('top').classList.add('on');window.scrollTo(0,0);}}
window.addEventListener('hashchange',show);show();
</script></body></html>"""
        return page, counts, len(qmap)


def build(inp, teigi, theme, kotoba, today):
    """検査を通ればページ（印を消した HTML）と件数を返す。当たれば Stop。"""
    model, problems, (res, pres) = collect(inp, teigi, theme)
    if problems:
        raise Stop(problems)
    page, counts, nq = Page(inp, teigi, model).render(today)
    problems = kotoba_problems(page, *kotoba)
    if problems:
        raise Stop(problems)
    return page.replace(A, "").replace(B, ""), dict(counts=counts, questions=nq, quotes=res, paras=pres)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not re.fullmatch(r"[a-z0-9-]+", argv[0]):
        print("使い方：python3 -B tools/build_note.py <テーマ>", file=sys.stderr)
        return 2
    theme = argv[0]
    try:
        inp = inputs.Inputs()                                   # (d) lock と入力
        teigi = read_teigi(os.path.join(inputs.ROOT, "teigi", f"note-{theme}.tsv"), theme)
        jiko_ni_suru(inp, teigi, theme)
        page, info = build(inp, teigi, theme, read_kotoba(), datetime.date.today())
    except inputs.InputError as e:
        print(f"止めた：(d) lock と入力、または項目の表\n{e}", file=sys.stderr)
        return 1
    except Stop as e:
        print(f"止めた：{len(e.problems)} 件。ページは作っていない。", file=sys.stderr)
        for kind, msg in e.problems:
            print(f"  - {kind}：{msg}", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{theme}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    q, p = info["quotes"], info["paras"]
    print(f"{os.path.relpath(out, inputs.ROOT)}（{os.path.getsize(out)} バイト）")
    print(f"引用の照合：対象 {q.total}、合った {q.matched}、合わなかった {len(q.mismatched)}")
    print(f"段落の確認：対象 {p.total}、合った {p.matched}、合わなかった {len(p.mismatched)}")
    for P, nk, nt in info["counts"]:
        print(f"  {P}：記述 {nk} 件、議会での質問 {nt} 件")
    print(f"議会での質問から見る：{info['questions']} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
