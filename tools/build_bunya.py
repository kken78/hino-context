"""質問の題と分野の対応の表から、総合計画の分野ごとの試作のページを作る（SCHEMA.md 7.11、docs/design.md 4節）。

実行：python3 -B tools/build_bunya.py   （build/bunya/index.html）
中身は、MCP の応答（tools/build_mcp.py の field）と同じデータ（taio/bunya.tsv、teigi/bunya-wadai.tsv、入力の台帳（hino-council-search data/ippan.tsv）と
総合計画、論点の試作のページと同じ集め方の論点）から作る。画面に出す言葉は、docs/design.md 3節の2つの表から読む。
このファイルには、画面の言葉を書かない。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/bunya.py の check と check_wadai）と、台帳の題の start の発言と段落の確認
  (b) 論点の試作のページと同じ検査（tools/build_note.py の collect）
  (c) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文は除く）
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems）
  (k) 施策検証結果報告書の記述の表が、読み取りの結果から作り直した行と同じでない（tools/kensho.py の check）
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import build_theme as bt  # noqa: E402
import bunya as bu  # noqa: E402
import kensho as ks  # noqa: E402
import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402

OUT = os.path.join(inputs.ROOT, "build", "bunya", "index.html")
SRC_PATH = os.path.abspath(__file__)
E, S, Stop = bn.E, bn.S, bn.Stop


def yomu(inp):
    """→ (tools/bunya.py の matome に計画 kk を足したもの, 問題の並び)。問題があれば、まとめは None。"""
    kk = bu.keikaku(inp)
    brows, wrows = bu.read(), bu.read_wadai()
    more = bu.check_wadai(wrows)
    if not more:
        more = bu.check(brows, bu.dai_list(inp), set(bu.bunya_jun(kk)), wrows) + bu.start_problems(inp)
    if more:
        return None, more
    m = bu.matome(inp, brows, wrows, kk)
    m["kk"] = kk
    return m, []


def yomi_go(D, r):
    """表の1行 → 読みの言葉。分野の行は、そのあとに中心の分野かの言葉を続ける（docs/design.md 3節）。"""
    y = {bu.ICCHI: D.kotoba("質問の題と分野の対応の表 yomi が「一致」"),
         bu.IKKAI: D.kotoba("質問の題と分野の対応の表 yomi が「1回だけ」")}[r["yomi"]]
    if not r["bunya"]:
        return y
    c = {bu.ICCHI: D.kotoba("質問の題と分野の対応の表 chushin が「一致」"),
         bu.IKKAI: D.kotoba("質問の題と分野の対応の表 chushin が「1回だけ」"),
         "": D.kotoba("質問の題と分野の対応の表 chushin が空")}[r["chushin"]]
    return f"{y}　{c}"


def ronten_ichiran(m, fid, notes, ronten):
    """分野の論点を基本施策ごとに並べたもの（docs/design.md 4節の field の8。2026-11-28）。MCP の応答（field）と試作のページが使う。
    notes は、テーマ → (論点の表, build_note.Page)（分野のテーマを含む）。ronten は、題 → 論点の (名前, ID, テーマ) の並び。
    → (読んだ分野か, 節の並び)。読んだ分野（事項の表に、その分野のテーマの行がある分野）の節は (種類, 見出し, 行の並び) で、
    種類は "kihon"（見出しは基本施策の (番号, 名前)。行の並びの最初は、基本施策そのものの行（無ければ None）。続いて、
    その基本施策に入る論点の行を、まとまり（matome）が空の行、まとまりごとの行の順に (まとまり, 行) で並べる）、
    "nashi"（基本施策に入れていない論点。(まとまり, 行) の並び。まとまりを先に、空のものをあとに）、
    "theme"（テーマの読み取りで作った事項で、この分野のテーマも付いたもの。行の並び）、"hoka"（ほかの分野にかかわる話題。行の並び）。
    読んでいない分野の節は ("yomanai", テーマの ID, [(名前, ID)])。題の一覧の題に付いた論点の名前と ID の組は、テーマの順。"""
    th = jiko.bunya_theme(fid)
    if th not in notes:
        out = {}
        for k in m["by"].get(fid, []):
            for P, slug, t in ronten.get(k, []):
                if not jiko.is_bunya(t) and slug not in [s for _, s in out.get(t, [])]:
                    out.setdefault(t, []).append((P, slug))
        jun = {t: {slug: i for i, (_, slug, _, _) in enumerate(notes[t][0]["topics"])} for t in out}
        return False, [("yomanai", t, sorted(out[t], key=lambda x: jun[t].get(x[1], 0))) for t in notes if t in out]
    T = notes[th][0]
    rows = T["jiko"]
    own = [r for r in rows if all(jiko.is_bunya(t) for t in jiko.themes_of(r))]
    hoka = [r for r in own if r["matome"] == jiko.HOKA]
    own = [r for r in own if r["matome"] != jiko.HOKA]
    x = m["bunya"][fid]
    out = []
    for no, name in x["shisaku"]:
        k = fid + no
        jishin = next((r for r in own if r["id"] in T["kihon"] and jiko.kihon_of(r) == [k]), None)
        rs = [r for r in own if k in jiko.kihon_of(r) and r is not jishin]
        out.append(("kihon", (no, name), [jishin] + bn.nashi_wake(rs)))
    mine = {fid + no for no, _ in x["shisaku"]}
    nashi = [r for r in own if not mine & set(jiko.kihon_of(r))]
    if nashi:
        out.append(("nashi", None, bn.nashi_wake(nashi, True)))
    th_rows = [r for r in rows if not all(jiko.is_bunya(t) for t in jiko.themes_of(r))]
    if th_rows:
        out.append(("theme", None, th_rows))
    if hoka:
        out.append(("hoka", jiko.HOKA, hoka))
    return True, out


def kihon_midashi_id(th, jishin, no):
    """基本施策の見出しの ID（まとまりの ID の頭。SCHEMA.md 7.9）。基本施策そのものの行の ID。行が無ければ、テーマの ID と番号。"""
    return jishin["id"] if jishin else f"{th}-k{no.strip('()')}"


def midashi_gun(inp, notes, m):
    """論点を並べる所（MCP の theme と field の応答、試作のページ）の、いちばん下の見出しごとの論点の並び（docs/design.md 4節。2026-11-28）。
    notes は、テーマ → (論点の表, Page か None)（分野のテーマを含む）。m は、分野の番号 → 分野（tools/bunya.py の keikaku の分野）を
    m["bunya"] に持つもの。→ dict(theme, ue, mt, id, rows) の並び。ue は上の見出し（("youso", 章立ての要素の行)、
    ("nashi", 計画の名前)、("theme",)、("kihon", (番号, 名前))、("kihon-nashi",)、("theme-ronten",)、("hoka",)）、mt はまとまりの
    名前（まとまりでない見出しは空）、id はまとまりの ID（まとまりでない見出しは None）、rows は事項の行の並び（並べる順）。
    行の無い見出しは入れない。"""
    out = []

    def add(th, ue, mt, mid, rows):
        if rows:
            out.append(dict(theme=th, ue=ue, mt=mt, id=jiko.matome_id(mid, mt) if mt else None, rows=rows))
    for th, (T, _) in notes.items():
        if not T.get("jiko"):
            continue
        if not jiko.is_bunya(th):
            keikaku, gs = bn.jiko_matome(inp, T)
            for youso, rs0 in gs:
                if youso:
                    add(th, ("youso", youso), "", None, rs0)
                    continue
                for mt, rs in bn.nashi_wake(rs0, keikaku is None):
                    add(th, ("theme",) if keikaku is None else ("nashi", keikaku), mt, th, rs)
            continue
        yonda, secs = ronten_ichiran(m, T["bunya"], notes, {})
        for kind, mi, rs in secs:
            if kind == "kihon":
                jishin, subs = rs[0], rs[1:]
                mid = kihon_midashi_id(th, jishin, mi[0])
                for mt, xs in subs:
                    add(th, ("kihon", mi), mt, mid, ([jishin] if jishin and not mt else []) + xs)
                if jishin and not any(not mt for mt, _ in subs):
                    add(th, ("kihon", mi), "", mid, [jishin])
            elif kind == "nashi":
                for mt, xs in rs:
                    add(th, ("kihon-nashi",), mt, th, xs)
            elif kind == "theme":
                add(th, ("theme-ronten",), "", th, rs)
            else:
                add(th, ("hoka",), jiko.HOKA, th, rs)
    return out


def page_id(m, fid):
    """分野の番号か話題の ID → ページの中の場所の ID（英字と数字）。"""
    if fid in m["bunya"]:
        return "b" + str(list(m["bunya"]).index(fid) + 1)
    return fid


def ronten_link(P, slug, th):
    """論点の名前。テーマの論点は、論点の試作のページ（build/note/<テーマ>.html）へのリンクにする。総合計画の分野の論点は、
    論点の試作のページを作っていないので、名前だけを出す（2026-11-28）。"""
    if jiko.is_bunya(th):
        return E(P)
    return f"<a href='../note/{E(th)}.html#{E(slug)}'>{E(P)}</a>"


def ronten_html(D, m, fid, notes, ronten):
    """分野のページの論点（MCP の field の応答と同じ中身。ID は出さない。docs/design.md 4節の field の8）。"""
    kei = S(m["kk"]["name"])
    D.dasanai("事項の表 kihon")
    yonda, secs = ronten_ichiran(m, fid, notes, ronten)
    out = [f"<h2>{E(D.bun('mcp-midashi-ronten'))}</h2>"]
    jiko_th = {}
    for th, (T, _) in notes.items():
        for _, slug, _, _ in T["topics"]:
            jiko_th.setdefault(slug, th)

    def li(r, ato=""):
        name = ronten_link(r["name"], r["id"], jiko_th.get(r["id"], "")) if r["aru"] else E(r["name"])
        mada = "" if r["aru"] else f"（{E(D.bun('ronten-mada'))}）"
        kazu = ""
        if r["aru"]:
            k = bn.ronten_kazu(D, notes[jiko_th[r["id"]]][1].ronten(r["name"])["qs"])
            kazu = f"　<span class='m'>{E(k)}</span>" if k else ""
        return f"<li>{name}{mada}{ato}{kazu}</li>"

    def matome_p(th, mt):
        bun, url = bn.matome_bun(D, m["inp"], notes[th][0]["matome"].get(mt))
        link = f"　<a href='{E(url)}' target='_blank'>{E(D.bun('matome-moto-link'))}</a>" if url else ""
        return f"<p class='m'>{bun}{link}</p>"
    th = jiko.bunya_theme(fid)
    if not yonda:
        out.append(f"<p class='m'>{E(D.bun('mcp-ronten-bunya-yomanai'))}</p>")
        for _, t, ps in secs:
            out.append(f"<h3>{S(bt.Theme(m['inp'], t).namae[0])}</h3><ul>"
                       + "".join(f"<li>{ronten_link(P, slug, t)}</li>" for P, slug in ps) + "</ul>")
        return "".join(out)
    out.append(f"<p class='m'>{D.bun('mcp-ronten-setsumei-bunya', keikaku=kei)}</p><p class='m'>{E(D.bun('ronten-kazu-setsumei'))}</p>")
    for kind, mi, rs in secs:
        if kind == "kihon":
            jishin, subs = rs[0], rs[1:]
            out.append(f"<h3>{S(mi[0] + mi[1])}</h3><ul>")
            if jishin:
                out.append(li(jishin, f"　<span class='m'>{E(D.bun('ronten-kihon-jishin'))}</span>" if jishin["aru"] else ""))
            out += [li(r) for mt, xs in subs if not mt for r in xs]
            out.append("</ul>")
            for mt, xs in subs:
                if mt and xs:
                    out.append(f"<h4>{E(mt)}</h4>{matome_p(th, mt)}<ul>"
                               + "".join(li(r) for r in xs) + "</ul>")
        elif kind == "nashi":
            out.append(f"<h3>{E(D.bun('ronten-kihon-nashi', keikaku=kei))}</h3>")
            for mt, xs in rs:
                if mt:
                    out.append(f"<h4>{E(mt)}</h4>{matome_p(th, mt)}")
                elif len(rs) > 1:
                    out.append(f"<h4>{E(D.bun('ronten-matome-nashi'))}</h4>")
                out.append("<ul>" + "".join(li(r) for r in xs) + "</ul>")
        elif kind == "theme":
            out.append(f"<h3>{E(D.bun('ronten-theme-ronten'))}</h3><p class='m'>{E(D.bun('ronten-theme-ronten-setsumei'))}</p><ul>"
                       + "".join(li(r, "　" + D.bun("ronten-theme-mei", theme=S(theme_namae(m, r)))) for r in rs) + "</ul>")
        else:
            out.append(f"<h3>{E(mi)}</h3>{matome_p(th, mi)}<ul>"
                       + "".join(li(r) for r in rs) + "</ul>")
    return "".join(out)


def theme_namae(m, r):
    """事項の行の theme の列の、分野でない最初のテーマの名前（テーマの定義の字）。"""
    t = next(t for t in jiko.themes_of(r) if not jiko.is_bunya(t))
    return bt.Theme(m["inp"], t).namae[0]


def render(D, m, ronten, today, notes=None):
    """ページの HTML（資料からの文の印を付けたまま）。ronten は題 → 論点の (名前, ID, テーマ) の並び。
    notes は、テーマ → (論点の表, build_note.Page)（分野のテーマを含む）。"""
    notes = notes or {}
    kk = m["kk"]
    kei = S(kk["name"])

    def namae(fid):
        x = m["bunya"].get(fid)
        return S(x["no"] + x["name"]) if x else E(next(n for i, n in m["wadai"] if i == fid))

    def link(fid):
        return f"<a href='#{page_id(m, fid)}'>{namae(fid)}</a>"

    D.dasanai("質問の題と分野の対応の表 bunya")
    D.dasanai("分野に無い話題の名前の表 matome")
    D.dasanai("分野に無い話題の名前の表 id")
    D.dasanai("質問の題と分野の対応の表 from、n")
    D.dasanai("質問の題と分野の対応の表 chu")
    kazu = lambda f: E(D.bun("bunya-kazu", n=len(m["by"].get(f, []))))  # noqa: E731
    ds = sorted(r["date"] for r in m["dai"].values())
    hani = D.bun("bunya-hani", a=E(bs.hi_str(D, ds[0])), z=E(bs.hi_str(D, ds[-1])), keikaku=kei)
    top = [f"<h1>{D.bun('mcp-midashi-bunya', keikaku=kei)}</h1>", f"<p class='m'>{E(D.bun('mcp-atama'))}</p>",
           f"<p class='lead'>{D.bun('bunya-setsumei', keikaku=kei)}</p>", f"<p class='m'>{hani}</p>",
           f"<p class='m'>{D.bun('bunya-ichiran-setsumei', keikaku=kei)}</p>"]
    for h in kk["hashira"]:
        top.append(f"<h2>{S(h['no'] + ' ' + h['name'])}</h2><ul>"
                   + "".join(f"<li>{link(x['no'])}　{kazu(x['no'])}</li>" for x in h["bunya"]) + "</ul>")
    top.append(f"<h2>{E(D.kotoba('質問の題と分野の対応の表 wadai'))}</h2><p class='m'>{E(D.bun('bunya-wadai-setsumei'))}</p><ul>"
               + "".join(f"<li>{link(i)}　{kazu(i)}</li>" for i, _ in m["wadai"]) + "</ul>")
    secs = [f"<section id='top' class='page'>{''.join(top)}</section>"]
    modoru = f"<p class='m'><a href='#top'>{E(D.bun('bunya-modoru'))}</a></p>"
    for fid in list(m["bunya"]) + [i for i, _ in m["wadai"]]:
        body = [modoru, f"<h1>{namae(fid)}</h1>", f"<p class='lead'>{D.bun('bunya-setsumei', keikaku=kei)}</p>"]
        x = m["bunya"].get(fid)
        if x:
            h = x["hashira"]
            t = x["tokoro"]
            pp = bu_page(t) if len(t) == 1 else D.bun("kikan", a=bu_page(t[:1]), z=bu_page(t[-1:]))
            body.append(f"<p class='m'>{S(h['no'] + ' ' + h['name'])}　{S(x['seisaku'][0] + ' ' + x['seisaku'][1])}</p>")
            body.append(f"<h2>{S(x['midashi'])}</h2><ul>" + "".join(f"<li>{S(no + name)}</li>" for no, name in x["shisaku"])
                        + "</ul>")
            body.append(f"<p class='m'>{E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}："
                        f"<a href='{E(keys.source_url(m['inp'], t[0]))}' target='_blank'>{kei}　{E(D.bun('page', n=pp))}</a></p>")
            body.append(ronten_html(D, m, fid, notes, ronten))
            body.append(kensho_html(D, m, fid))
        else:
            body.append(f"<p class='m'>{E(D.bun('bunya-wadai-setsumei'))}</p>")
        dai = m["by"].get(fid, [])
        body.append(f"<h2>{E(D.bun('bunya-midashi-dai', n=len(dai)))}</h2><p class='m'>{E(D.bun('bunya-dai-setsumei'))}</p><ul>")
        for k in dai:
            r, rows = m["dai"][k], m["of"][k]
            mine = next(y for y in rows if (y["bunya"] or m["m2id"][y["wadai"]]) == fid)
            ttl = S("「" + r["title"] + "」") if r["title"].strip() else E(D.bun("bunya-dai-nashi"))
            li = [f"<b>{E(keys.ymd(r['date']))}</b>　{ttl}", f"<span class='m'>{E(yomi_go(D, mine))}</span>"]
            hoka = [y for y in rows if y is not mine]
            if hoka:
                li.append(D.bun("bunya-hoka", hoka="、".join(link(y["bunya"] or m["m2id"][y["wadai"]]) for y in hoka)))
            ron = ronten.get(k)
            if ron:
                li.append(D.bun("bunya-ronten", ronten="、".join(ronten_link(P, s, th) for P, s, th in ron)))
            sid, p = bu.start_of(r)
            li.append(f"<a href='{E(keys.search_url(sid, p))}' target='_blank'>{E(D.bun('bunya-link'))}</a>")
            body.append("<li>" + "<br>".join(li) + "</li>")
        body.append("</ul>")
        secs.append(f"<section id='{page_id(m, fid)}' class='page'>{''.join(body)}</section>")
    owari = D.bun("owari-bunya", keikaku=kei) + E(D.bun("sakusei-bi", hi=keys.ymd(today.isoformat())))
    return f"""<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'><title>{D.bun('mcp-midashi-bunya', keikaku=kei)}</title><style>
body{{font-family:sans-serif;max-width:920px;margin:1em auto;padding:0 1em;line-height:1.7;color:#222}}
h1{{font-size:1.3em}} h2{{font-size:1.05em;border-top:2px solid #555;padding-top:.5em;margin-top:1.6em}}
.lead,.m{{font-size:.88em;color:#555}} li{{margin:.4em 0}} .note{{font-size:.85em;background:#f6f6f6;border:1px solid #ccc;padding:.5em .8em;margin-top:2em}}
.page{{display:none}} .page.on{{display:block}}
</style></head><body>
{''.join(secs)}
<div class='note'>{owari}</div>
<script>
function show(){{var id=(location.hash||'#top').slice(1);var ps=document.querySelectorAll('.page');var hit=false;ps.forEach(function(p){{var on=p.id===id;p.classList.toggle('on',on);if(on)hit=true;}});if(!hit)document.getElementById('top').classList.add('on');window.scrollTo(0,0);}}
window.addEventListener('hashchange',show);show();
</script></body></html>"""


def kensho_html(D, m, fid):
    """分野のページの町の検証（docs/design.md 4節の field の7。MCP の応答と同じ中身。ID は出さない）。"""
    K, x, nm = m["ks"], m["bunya"][fid], m["namae"]
    D.dasanai("施策検証の取り組みと分野の対応の表 saisho")
    D.dasanai("施策検証の取り組みと分野の対応の表 bunya、shisaku")
    D.dasanai("施策検証シートの表 no、name、kihon_no、kihon")
    D.dasanai("施策検証シートの表 tantou")
    D.dasanai("施策検証シートの表 houkou")
    D.dasanai("施策検証シートの表 tasseido、kekka")
    D.dasanai("施策検証の欄の表 midashi")
    D.dasanai("施策検証シートの検収の台帳 reviewer")
    yomi = {ks.ICCHI: D.kotoba("施策検証の取り組みと分野の対応の表 yomi が「一致」"),
            ks.IKKAI: D.kotoba("施策検証の取り組みと分野の対応の表 yomi が「1回だけ」")}
    sh = dict(x["shisaku"])

    def shisaku(k):
        return "、".join(D.bun("kensho-shisaku-yomi", shisaku=S(r["shisaku"] + sh[r["shisaku"]]), yomi=E(yomi[r["yomi"]]))
                        for r in K["bunya"][k] if r["bunya"] == fid)

    def namae(k):
        t = K["tori"][k]
        return D.bun("kensho-torikumi", no=S(t["no"]), name=S(t["name"]))

    def link(name, url):
        return f"<a href='{E(url)}' target='_blank'>{name}</a>" if url else name

    def pages(t):
        p = int(t["page"])
        return E(D.bun("page", n=D.bun("kikan", a=p, z=p + 1)))

    def ran(t, r):
        return D.bun("hyo-kijutsu-ran", midashi=S(ks.kohos(K["ran"][r])[0]), atai=S(t[r])) + f"（{pages(t)}）"
    naka = [k for k in K["tori"] if K["naka"].get(k) == fid]
    hoka = [k for k in K["tori"] if K["naka"].get(k) != fid and any(r["bunya"] == fid for r in K["bunya"].get(k, []))]
    o = [f"<h2>{E(D.bun('kensho-midashi'))}</h2>", f"<p class='m'>{E(D.bun('kensho-setsumei'))}</p>",
         f"<p class='m'>{E(D.bun('kensho-mikakunin'))}</p>", f"<p class='m'>{E(D.bun('kensho-nendo'))}</p>"]
    if any(not K["hito"].get(k) for k in naka + hoka):
        o.append(f"<p class='m'>{E(D.bun('kensho-hito'))}</p>")
    aru = {r["shisaku"] for rs in K["bunya"].values() for r in rs if r["bunya"] == fid}
    nai = [f"<li>{D.bun('kensho-nai', shisaku=S(no + name))}</li>" for no, name in x["shisaku"] if no not in aru]
    if nai:
        o.append("<ul>" + "".join(nai) + "</ul>")
    for k in naka:
        t, sr = K["tori"][k], K["sr"][k]
        li = [f"<li>{D.bun('kensho-tantou', tantou=S(t['tantou']))}"]
        hon = []
        if not ks.onaji(t["tantou"], sr["dept"]):
            hon.append(D.bun("kensho-tantou-honpen", tantou=S(sr["dept"])))
        li.append("<br>".join([""] + [f"<span class='m'>{h}</span>" for h in hon]) + "</li>" if hon else "</li>")
        li.append(f"<li>{D.bun('kensho-ichi', kihon_no=S(t['kihon_no']), kihon=S(t['kihon']), houkou=S(t['houkou']))}")
        if not ks.onaji(t["houkou"], sr["houkou"]):
            li.append(f"<br><span class='m'>{D.bun('kensho-houkou-honpen', houkou=S(sr['houkou']))}</span>")
            hon.append("")
        if hon:
            hn, hu = nm.shiryo(sr["honpen"])
            li.append(f"<br><span class='m'>{D.bun('kensho-honpen', shiryo=link(hn, hu))}</span>")
        li.append("</li>")
        sn = f"{nm.bunsho(ks.SHIRYO)}　{pages(t)}"
        o.append(f"<h3>{namae(k)}</h3><ul>" + "".join(li)
                 + f"<li>{D.bun('kensho-shisaku', shisaku=shisaku(k))}</li>"
                 f"<li>{ran(t, 'kekka')}</li><li>{ran(t, 'tasseido')}</li>"
                 f"<li>{E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}："
                 f"{link(sn, keys.source_url(m['inp'], ks.SHIRYO + '/' + t['page']))}</li></ul>")
    if hoka:
        o.append(f"<h3>{E(D.bun('kensho-hoka'))}</h3><ul>"
                 + "".join(f"<li>{namae(k)}　{D.bun('kensho-shisaku', shisaku=shisaku(k))}</li>" for k in hoka) + "</ul>")
    return "".join(o)


def bu_page(t):
    """基本施策のページの pt の ID の並びの最初 → ページの番号。"""
    return int(t[0].rsplit("/", 1)[1])


def build(inp, D, kotoba, today, notes=None, bunya_notes=None):
    """検査を通れば、ページ（印を消した HTML）と件数を返す。当たれば Stop。notes は tools/build_mcp.py の read_notes で
    読んだもの（None なら読む）。"""
    import build_mcp
    import build_suji as bs
    problems = [("(e) デザインシステムとの対応", x) for x in bs.design_problems(D, path=SRC_PATH)]
    m, more = yomu(inp)
    problems += [("(a) 分野", x) for x in more]
    notes = build_mcp.read_notes(inp) if notes is None else notes
    bunya_notes = build_mcp.read_bunya_notes(inp) if bunya_notes is None else bunya_notes
    pages = {}
    for theme, T in list(notes.items()) + list(bunya_notes.items()):
        model, more, _ = bn.collect(inp, T, theme)
        problems += more
        pages[theme] = (T, bn.Page(inp, T, model, D))
    m["ks"], more = ks.matome(inp)
    problems += [("(k) 施策検証", x) for x in more]
    if problems:
        raise Stop(list(dict.fromkeys(problems)))
    m["inp"] = inp
    tables, more = bt.read_tables()
    if more:
        raise Stop([("(k) 施策検証", bs.mondai_str(x)) for x in more])
    m["namae"] = bt.Namae(D, inp, {r["bunsho"]: r for r in tables["bunsho"]})
    ronten = bu.ronten_of_dai(inp, pages)
    page = render(D, m, ronten, today, pages)
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop(problems)
    return page.replace(bn.A, "").replace(bn.B, ""), dict(dai=len(m["dai"]), ronten=len(ronten))


def main(argv=None):
    import build_suji as bs
    try:
        inp = inputs.Inputs()
        page, info = build(inp, bs.read_design(), bn.read_kotoba(), datetime.date.today())
    except (inputs.InputError, bu.BunyaError, ks.KenshoError, OSError) as e:
        print(f"止めた：(d) lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    except Stop as e:
        print(f"止めた：{len(e.problems)} 件。ページは作っていない。", file=sys.stderr)
        for kind, msg in e.problems:
            print(f"  - {kind}：{msg}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{os.path.relpath(OUT, inputs.ROOT)}（{os.path.getsize(OUT)} バイト）")
    print(f"題 {info['dai']}、論点を添えた題 {info['ronten']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
