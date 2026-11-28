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
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import bunya as bu  # noqa: E402
import inputs  # noqa: E402
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


def page_id(m, fid):
    """分野の番号か話題の ID → ページの中の場所の ID（英字と数字）。"""
    if fid in m["bunya"]:
        return "b" + str(list(m["bunya"]).index(fid) + 1)
    return fid


def render(D, m, ronten, today):
    """ページの HTML（資料からの文の印を付けたまま）。ronten は題 → 論点の (名前, ID, テーマ) の並び。"""
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
    top = [f"<h1>{D.bun('mcp-midashi-bunya', keikaku=kei)}</h1>", f"<p class='m'>{E(D.bun('mcp-atama'))}</p>",
           f"<p class='lead'>{D.bun('bunya-setsumei', keikaku=kei)}</p>",
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
                li.append(D.bun("bunya-ronten", ronten="、".join(
                    f"<a href='../note/{E(th)}.html#{E(s)}'>{E(P)}</a>" for P, s, th in ron)))
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


def bu_page(t):
    """基本施策のページの pt の ID の並びの最初 → ページの番号。"""
    return int(t[0].rsplit("/", 1)[1])


def build(inp, D, kotoba, today, notes=None):
    """検査を通れば、ページ（印を消した HTML）と件数を返す。当たれば Stop。notes は tools/build_mcp.py の read_notes で
    読んだもの（None なら読む）。"""
    import build_mcp
    import build_suji as bs
    problems = [("(e) デザインシステムとの対応", x) for x in bs.design_problems(D, path=SRC_PATH)]
    m, more = yomu(inp)
    problems += [("(a) 分野", x) for x in more]
    notes = build_mcp.read_notes(inp) if notes is None else notes
    pages = {}
    for theme, T in notes.items():
        model, more, _ = bn.collect(inp, T, theme)
        problems += more
        pages[theme] = (T, bn.Page(inp, T, model, D))
    if problems:
        raise Stop(list(dict.fromkeys(problems)))
    m["inp"] = inp
    ronten = bu.ronten_of_dai(inp, pages)
    page = render(D, m, ronten, today)
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop(problems)
    return page.replace(bn.A, "").replace(bn.B, ""), dict(dai=len(m["dai"]), ronten=len(ronten))


def main(argv=None):
    import build_suji as bs
    try:
        inp = inputs.Inputs()
        page, info = build(inp, bs.read_design(), bn.read_kotoba(), datetime.date.today())
    except (inputs.InputError, bu.BunyaError, OSError) as e:
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
