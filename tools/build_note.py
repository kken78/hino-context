"""論点ノートの試作のページを作る。

実行：python3 -B tools/build_note.py <テーマ>   （例 hoiku → build/note/hoiku.html）
テーマの名前・論点・準備中の論点などは teigi/note-<テーマ>.tsv（試作のための仮の表。SCHEMA.md §5）から読む。
記述は hino-ronten の確定した記録（SCHEMA.md §1）から取る。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 引用が原典に無い行（段落の鍵が発言の段落を指していない行を含む）
  (b) 出典の無い記述
  (c) 画面に出る文に、SKILL.md §2 の「使わない」言葉が残っている（資料からの引用の中は除く）
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
import keys  # noqa: E402
import ronten  # noqa: E402
import shogo  # noqa: E402

TEIGI_COLUMNS = ["kind", "key", "name", "short", "setsumei"]
TEIGI_KINDS = ("テーマ", "論点", "準備中", "抜き出しの語", "単位", "注")
SKILL_PATH = os.path.join(inputs.ROOT, "SKILL.md")
OUT_DIR = os.path.join(inputs.ROOT, "build", "note")
SITE = "日野町 論点ノート（非公式・試作）"

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


# ---- 定義の表と言葉の表 ----

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


def _words(cell):
    return [w.strip() for w in re.sub(r"（[^）]*）", "", cell).split("、") if w.strip()]


def read_kotoba(path=SKILL_PATH):
    """SKILL.md §2 の言葉の表 → (使わない語, 確かめる所) の並びと、使う語の集まり。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    try:
        i = lines.index("| 使わない | 使う | 確かめる所 |")
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
    """記録を集め、(a)(b) の検査を行う。返り値は (model, problems, quote_result)。"""
    trows = ronten.themes(inp, theme)
    points = {r["value"] for r in trows if r["kind"] == "事柄"}
    problems = []
    for P, *_ in teigi["topics"]:
        if P not in points:
            problems.append(("定義", f"論点「{P}」が hino-ronten の題材 {theme} の事柄に無い"))
    qsrc = {r["value"]: r["source"] for r in trows if r["kind"] in ("問い", "質疑")}
    names = [t[0] for t in teigi["topics"]]
    ko = ronten.kotogara(inp, set(names))
    katei = ronten.katei(inp, theme)
    ta = ronten.taio(inp, set(names), set(qsrc))

    # (a) 引用と段落
    qrows = [dict(where=f"事柄の記録 {r['point']} / {r['source']}", source=r["source"], quote=r["quote"])
             for r in ko]
    qrows += [dict(where=f"過程の記録 {theme} step {r['step']}", source=r["sources"].split(",")[0],
                   quote=r["quote"]) for r in katei]
    res = shogo.check_quotes(inp, qrows)
    pres = shogo.check_paras(inp, [dict(where=f"問いと事項の対応 {r['question']} / {r['point']}", hani=r["hani"])
                                   for r in ta])
    for m in res.mismatched + pres.mismatched:
        problems.append(("(a) 引用が原典に無い", f"{m['where']}：{m['reason']}（{m['source']}）"
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
    for r in ta:
        if not r["hani"] or not qhead_parts(qsrc.get(r["question"], ""))[1]:
            problems.append(("(b) 出典の無い記述", f"問いと事項の対応 {r['question']} / {r['point']}：範囲か問いの題が無い"))
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
            problems.append(("(a) 引用が原典に無い", f"{m['where']}：{m['reason']}（{m['source']}）「{m['quote']}」"))
    return dict(ko=ko, katei=katei, ta=ta, qsrc=qsrc), problems, (res, pres)


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


def qhead(q, qsrc):
    who, dai = qhead_parts(qsrc.get(q, ""))
    kind = "議案への質疑" if q.startswith("sq:") else "一般質問"
    return f"{keys.ymd(qdate(q))}　{kind}（{S(who)}）{S_kagi(dai)}"


class Page:
    def __init__(self, inp, teigi, model):
        self.inp, self.t, self.m = inp, teigi, model
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

    def atai(self, x):
        v = x["value"]
        if not v:
            return ""
        if re.fullmatch(r"[\d,]+", v):
            unit = next((u for head, u in self.t["units"] if x["source"].startswith(head)), "")
            if unit:
                return "金額：" + S(v + unit)
        if re.fullmatch(r"[\d,\.]+", v):
            return "数値：" + S(v) + "（資料に単位の記述なし）"
        return ""

    @staticmethod
    def doko(x):
        return "議会での答弁" if x["source"].startswith("sp:") else "町の資料"

    def katei_rows(self):
        def kikan(x):
            f, t = x["from"], x["to"]
            return keys.ymd(f) + ("〜" + keys.ymd(t) if t and t != f else "") if f else ""
        return "".join(f"<tr><td class='nw'>{kikan(x)}</td><td>{E(x['name'])}</td>"
                       f"<td>{'、'.join(S(self.srcname(s)) for s in x['sources'].split(',')[:2])}</td></tr>"
                       for x in self.m["katei"])

    def chu(self, sid_or_source, text):
        """その資料の、その字を含む文に付ける「作成者の注」。無ければ空。"""
        out = []
        for c in self.t.get("chu", []):
            if c["source"].split("/")[0] == sid_or_source.split("/")[0] and c["part"] in text:
                link = f"<a href='{E(keys.source_url(self.inp, c['moto']))}' target='_blank'>{S(keys.source_name(self.inp, c['moto']))}</a>"
                if c["moto"].startswith("ext:"):
                    k = next(r["kakunin"] for r in self.inp.gaibu() if c["moto"] == f"ext:{r['id']}/{r['page']}")
                    link += f"　{keys.ymd(k)}に確認"
                out.append(f"<div class='chu'>作成者の注：{E(c['text'])}（もとの資料：{link}）</div>")
        return "".join(out)

    def topic(self, P, slug, short, setsumei):
        inp, T, qsrc = self.inp, self.t, self.m["qsrc"]
        ko = sorted([x for x in self.m["ko"] if x["point"] == P], key=lambda x: x["source_date"])
        docs = sorted([x for x in ko if not x["source"].startswith("sp:")], key=lambda x: x["source_date"], reverse=True)
        sec1 = "".join(f"<div class='now'><div>「{S(x['quote'])}」</div><div class='m'>{keys.ymd(x['source_date'])}の資料　"
                       f"{self.link(x)}{'　' + self.atai(x) if self.atai(x) else ''}</div></div>" for x in docs) \
            or "<p class='m'>町の資料の記述は、まだ整理できていません。</p>"
        rows2 = "".join(f"<tr><td class='nw'>{keys.ymd(x['source_date'])}</td><td class='nw'>{self.doko(x)}</td>"
                        f"<td>「{S(x['quote'])}」{'<br><span class=m>' + self.atai(x) + '</span>' if self.atai(x) else ''}{self.chu(x['source'], x['quote'])}</td>"
                        f"<td>{self.link(x)}</td></tr>" for x in ko)
        tome = [x for x in ko if self.pat and self.pat.search(x["quote"])]
        rows3 = "".join(f"<tr><td class='nw'>{keys.ymd(x['source_date'])}</td><td>「{S(x['quote'])}」</td>"
                        f"<td>{self.link(x)}</td></tr>" for x in tome)
        ta = sorted([r for r in self.m["ta"] if r["point"] == P], key=lambda r: qdate(r["question"]))
        blocks = []
        for r in ta:
            q = r["question"]
            ps = keys.paras_of(r["hani"])
            body, cur = [], None
            for sid, i in ps:
                if sid != cur:
                    cur = sid
                    body.append(f"<div class='spk'>{S(inp.speaker(sid))}</div>")
                para = inputs.paragraphs(inp.statement_text(sid))[i - 1]
                body.append(f"<div class='para'>{S(para)}　<a href='{E(keys.search_url(sid, i))}' target='_blank'>会議録</a>{self.chu('sp:' + sid, para)}</div>")
            blocks.append(f"<div class='qa'><h3>{qhead(q, qsrc)}</h3><details><summary>{E(short)}に関する部分を表示（{len(ps)}か所）</summary>"
                          f"{''.join(body)}</details><p class='m'><a href='{E(keys.source_url(inp, q))}' target='_blank'>"
                          f"会議録でこの質問の全体を見る</a></p></div>")
        sib = "／".join(f"<a href='#{s}'>{E(p)}</a>" for p, s, _, _ in T["topics"] if s != slug)
        jis = "" if any(x["kind"] == "実績" for x in ko) else \
            "<p class='m'>実績（契約額、決算額、完成後の数値など）が分かる資料は、このページのもとにした資料の中にはありません。</p>"
        sec3 = (f"<h2>今後検討・決定するとされていること</h2><table><tr><th>時期</th><th>内容</th><th>もとの資料</th></tr>{rows3}</table>"
                "<p class='m'>上の表のうち、「まだ」「今後」などの語を含む記述を抜き出しています。その後の状況は、上の表の新しい時期の記述で確認してください。</p>") \
            if tome else ""
        th = E(T["theme"])
        h = f"""<section id='{slug}' class='page'>
<p class='lead'><a href='#top'>{SITE}</a> ＞ <a href='#top'>{th}</a> ＞ {E(P)}</p>
<h1>{E(P)}</h1>
<p class='lead'>「{th}」のうち、{E(setsumei)}について、町の資料と議会の会議録の記述を集めたページです。意見や評価は加えていません。各項目のリンクから、もとの資料を確認できます。</p>
<div class='nav'><b>同じテーマのほかのページ</b>：{sib}　<a href='#top'>テーマのページへ戻る</a></div>
<h2>町の資料の記述（新しいものから）</h2>{sec1}
<h2>説明の移り変わり（時期の順）</h2>
<table><tr><th>時期</th><th>区分</th><th>内容</th><th>もとの資料</th></tr>{rows2}</table>{jis}
{sec3}
<h2>議会での質問と答弁（{len(ta)}件）</h2>
<p class='m'>一つの質問では、複数の話題が取り上げられます。ここでは、{E(short)}に関する部分だけを抜き出しています。質問の全体は、会議録で確認できます。</p>{''.join(blocks)}
<p class='m'>掲載しているのは、内容を確認できた質問です。ほかの質問でも、{E(short)}が取り上げられている場合があります。</p>
</section>"""
        return h, len(ko), len(ta), [r["question"] for r in ta]

    def render(self, today):
        T, qsrc = self.t, self.m["qsrc"]
        th = E(T["theme"])
        pages, rows, qmap, counts = [], [], {}, []
        for P, slug, short, setsumei in T["topics"]:
            h, nk, nt, qs = self.topic(P, slug, short, setsumei)
            pages.append(h)
            counts.append((P, nk, nt))
            rows.append(f"<tr><td><a href='#{slug}'>{E(P)}</a></td><td>{nk}件</td><td>{nt}件</td></tr>")
            for q in qs:
                qmap.setdefault(q, []).append((P, slug))
        qrows = "".join(f"<tr><td>{qhead(q, qsrc)}</td><td>{'、'.join(f'<a href=#{s}>{E(p)}</a>' for p, s in ps)}</td>"
                        f"<td><a href='{E(keys.source_url(self.inp, q))}' target='_blank'>会議録</a></td></tr>"
                        for q, ps in sorted(qmap.items(), key=lambda kv: qdate(kv[0])))
        top = f"""<section id='top' class='page'>
<p class='lead'>{SITE} ＞ {th}</p>
<h1>{th}</h1>
<p class='lead'>{E(T['setsumei'])}について、町の資料と議会の会議録の記述を、論点ごとに整理しています。意見や評価は加えていません。</p>
<h2>論点ごとのページ</h2>
<table><tr><th>論点</th><th>町の資料・答弁の記述</th><th>議会での質問</th></tr>{''.join(rows)}</table>
<p class='m'>準備中の論点：{E('／'.join(T['junbi']))}　ほか</p>
<h2>これまでの経過</h2>
<table><tr><th>時期</th><th>内容</th><th>もとの資料</th></tr>{self.katei_rows()}</table>
<h2>議会での質問から見る（{len(qmap)}件）</h2>
<p class='m'>一つの質問が、複数の論点にまたがることがあります。質問ごとに、関係する論点のページを示します。</p>
<table><tr><th>質問</th><th>関係する論点</th><th>全体</th></tr>{qrows}</table>
<p class='m'>掲載しているのは、内容を確認できた質問です。このテーマに関する質問は、ほかにもあります。</p>
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
        page, info = build(inp, teigi, theme, read_kotoba(), datetime.date.today())
    except inputs.InputError as e:
        print(f"止めた：(d) lock と入力、または定義の表\n{e}", file=sys.stderr)
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
    print(f"引用の照らし合わせ：対象 {q.total}、合った {q.matched}、合わなかった {len(q.mismatched)}")
    print(f"段落の確かめ：対象 {p.total}、合った {p.matched}、合わなかった {len(p.mismatched)}")
    for P, nk, nt in info["counts"]:
        print(f"  {P}：記述 {nk} 件、議会での質問 {nt} 件")
    print(f"議会での質問から見る：{info['questions']} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
