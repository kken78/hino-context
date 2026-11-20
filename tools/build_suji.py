"""数値の表から、定義1つのページを作る（SCHEMA.md §6・§7）。

実行：python3 -B tools/build_suji.py <定義の id>   （例 taiki → build/suji/taiki.html）
中身は teigi/suji.tsv・atai.tsv・bunsho.tsv・bubun.tsv と、lock の版の入力だけから作る。hino-ronten の記録は使わない。
列は、tools/suji.py の jiten_kankei が返す時点の関係で分ける。単語で数値の意味や種類を決めない。数値を計算しない。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all。inyo の照合、文書の部分の検査を含む）で問題がある
  (b) 画面に出る文に、SKILL.md §2 の「使わない」言葉が残っている（資料からの文は除く。tools/build_note.py の印と検査）
  (c) 定義の id が定義の表に無い
  (d) lock と入力が合わない
"""
import datetime
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import shogo  # noqa: E402
import suji as sj  # noqa: E402

OUT_DIR = os.path.join(inputs.ROOT, "build", "suji")
A, B = bn.A, bn.B
E, S = bn.E, bn.S
Stop = bn.Stop

# 時点の関係を出していない理由（suji.jiten_kankei が None を返す場合。SCHEMA.md §7.3）。並べる順
RIYU_NENDO = "対象の年度が無い"
RIYU_HIDUKE = "資料に日付が無い"
RIYU_SHIRYO = "資料が無い"
RIYU = (RIYU_NENDO, RIYU_HIDUKE, RIYU_SHIRYO)
# 列の順（SCHEMA.md §7.3 の3つの関係）
KANKEI = (sj.KANKEI_ATO, sj.KANKEI_TOCHU, sj.KANKEI_MAE)       # 列の順
# 時点の関係の印 → 画面の言葉。画面の言葉は、データの構造（tools/suji.py・SCHEMA.md）に書かず、画面の側で持つ
KOTOBA = {sj.KANKEI_ATO: "資料の日付より後の時点について書いた数値",
          sj.KANKEI_MAE: "資料の日付より前か同じ時点について書いた数値",
          sj.KANKEI_TOCHU: "年度の途中に出た資料の数値"}
# 「資料の間で、数値が一致していません」を出すときに比較する行の、資料の字での種類（空か「実績」）
HIKAKU_SHURUI = ("", "実績")


# ---- 表を読む ----

def read_tables(teigi_dir=None):
    """4つの表を読む。→ (表の辞書, 読むときの問題の並び)。表のファイルが無ければ、問題として返す。"""
    d = teigi_dir or sj.TEIGI_DIR
    out, problems = {}, []
    for key, fname, reader, name in (("suji", "suji.tsv", sj.read_suji, sj.SUJI_NAME),
                                     ("atai", "atai.tsv", sj.read_atai, sj.ATAI_NAME),
                                     ("bunsho", "bunsho.tsv", sj.read_bunsho, sj.BUNSHO_NAME),
                                     ("bubun", "bubun.tsv", sj.read_bubun, sj.BUBUN_NAME)):
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            problems.append(sj.Mondai(name, 0, "表が無い"))
            out[key] = []
            continue
        rows, p = reader(sj._read_file(path))
        out[key] = rows
        problems += p
    return out, problems


def mondai_str(m):
    return f"{m.hyo} の {m.gyo} 行目：{m.naiyo}"


# ---- 行ごとの中身 ----

def riyu_of(r, by):
    """時点の関係を出していない行の理由。jiten_kankei と同じ順で見る。"""
    if not r["nendo"].strip():
        return RIYU_NENDO
    if not r["shiryo"].strip():
        return RIYU_SHIRYO
    return RIYU_HIDUKE


def toki_of(r, teigi):
    """表の行の時点 → (並べる順の鍵, 表に出す字)。時点の関係を出す行（nendo がある行）に使う。"""
    m = sj.RE_NENGETSU.fullmatch(r["jiten"].strip())
    if m:
        y, mo = sj.GENGO[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2))), int(m.group(3))
        return (y, mo, 0), f"{y}年{mo}月"
    nendo = int(r["nendo"])
    t = teigi.get("nendo_tsuki", "")
    if t in sj.NENDO_TSUKI:
        t = int(t)
        y = nendo if t >= 4 else nendo + 1
        return (y, t, 0), f"{y}年{t}月"
    return (nendo, 4, 1), f"{nendo}年度"


def hiduke_of(shiryo, by):
    """資料の日付 → (並べる順の鍵, 表に出す字)。発言は発言の日、ほかは文書の表の hiduke。無ければ None。"""
    try:
        kind, g = keys.parse(shiryo)
    except keys.KeyFormError:
        return None
    if kind == "sp":
        h = keys.sid_date(g[0])
    else:
        h = (by.get(sj.bunsho_of(shiryo)) or {}).get("hiduke", "")
        if not sj.RE_HIDUKE.fullmatch(h or ""):
            return None
    if not h:
        return None
    return tuple(int(x) for x in h.split("-")) + (0,) * (3 - len(h.split("-"))), keys.ymd(h)


def para_range(bubun):
    """段落の鍵 → (始め, 終わり)。"""
    _, g = keys.parse(bubun)
    return int(g[1]), int(g[2] or g[1])


def ichi_of(r, index):
    """資料の中の位置（文書の部分の表から、親をたどる）。→ (HTML, 未確認の部分があるか)。指していなければ ("", False)。"""
    if not r["bubun"]:
        return "", False
    if r["shiryo"].startswith("sp:"):
        a, z = para_range(r["bubun"])
        return (f"発言の段落{a}" if a == z else f"発言の段落{a}〜{z}"), False
    b = sj.bunsho_of(r["shiryo"])
    chain, n = [], r["bubun"]
    while n:
        x = index[(b, n)]
        chain.append(x)
        n = x["oya"]
    chain.reverse()
    if r["retsu"]:
        chain.append(index[(b, r["retsu"])])
    mikakunin = any(x["torikata"] == sj.YONDA for x in chain)
    head = {sj.HYO: "表", sj.GYO: "行", sj.RETSU: "列"}
    parts = [f"{head.get(x['shu'], '')}「{S(x['name'])}」" + ("（未確認）" if x["torikata"] == sj.YONDA else "")
             for x in chain]
    return " ＞ ".join(parts), mikakunin


class Entry:
    """数値の表の1行と、ページに出す中身。"""

    def __init__(self, r, teigi, inp, by, index):
        self.r, self.gyo, self.id = r, r["_gyo"], f"g{r['_gyo']}"
        self.kankei = sj.jiten_kankei(r, teigi, by)
        self.riyu = None if self.kankei else riyu_of(r, by)
        self.toki = toki_of(r, teigi) if self.kankei else None
        self.label = self.toki[1] if self.toki else r["jiten"]
        sh = r["shiryo"].strip()
        self.sp = sh.startswith("sp:")
        self.hiduke = hiduke_of(sh, by) if sh else None
        self.namae = self.page = self.url = self.konkyo = ""
        self.ichi, self.mikakunin = ichi_of(r, index) if sh else ("", False)
        if not sh:
            return
        kind, g = keys.parse(sh)
        if self.sp:
            d = keys.sid_date(g[0])
            sp_name = inp.speaker(g[0])
            self.namae = f"会議録 {keys.ymd(d)} {S(sp_name)}" if d and sp_name else ""
        else:
            row = by.get(sj.bunsho_of(sh))
            if row and row["namae"]:
                self.namae = S(row["namae"])
            else:
                n = keys.source_name(inp, sh)
                self.namae = S(n) if n else ""
            if kind in ("pt", "doc"):
                self.page = f"{g[-1]}ページ"
            if row and row["konkyo"]:
                self.konkyo = f"「{S(row['konkyo'])}」（{sj.page_no(row['konkyo_tokoro'])}ページ）"
        para = para_range(r["bubun"])[0] if self.sp and r["bubun"] else None
        self.url = keys.source_url(inp, sh, para)

    @property
    def atai(self):
        """数値の字（資料の字。印で囲む）。数値が無い行は状態の字。"""
        return S(self.r["atai"]) if self.r["atai"] else E(self.r["jotai"])

    def chip(self):
        ji = f"<span class=ji>資料の字：{S(self.r['shurui'])}</span>" if self.r["shurui"] else ""
        if self.r["shiryo"].strip():
            hi = self.hiduke[1] if self.hiduke else "資料に日付の記述がありません"
            moto = f"<span class=moto>{self.namae}（{hi}）</span>"
        else:
            moto = f"<span class=moto>{E(self.r['jotai'])}</span>" if self.r["atai"] else ""
        kubun = f"<span class=moto>{E(self.r['kubun'])}</span>" if self.r["kubun"] and not self.toki else ""
        return f"<div class=chip><a href='#{self.id}'><b>{self.atai}</b></a>{ji}{moto}{kubun}</div>"


# ---- ページ ----

STYLE = """body{font-family:sans-serif;line-height:1.7;max-width:60rem;margin:1.5rem auto;padding:0 1rem;color:#222}
h1{font-size:1.4rem} h2{font-size:1.15rem;border-bottom:1px solid #999;margin-top:2rem} h3{font-size:1rem;margin:1rem 0 .3rem}
table{border-collapse:collapse;width:100%} th,td{border:1px solid #bbb;padding:.4rem .6rem;vertical-align:top;text-align:left}
thead th{background:#f0f0f0} tbody th{white-space:nowrap;width:6.5rem}
.chip{margin:.15rem 0} .chip b{font-size:1.1rem} .ji{margin-left:.5rem;border:1px solid #777;padding:0 .3rem;font-size:.8rem}
.moto{margin-left:.5rem;font-size:.85rem;color:#555} .chigau{margin-top:.3rem;font-size:.85rem;border-left:3px solid #555;padding-left:.5rem}
.nai{font-size:.85rem;color:#555} .note{background:#f6f6f6;padding:.6rem .9rem;font-size:.9rem}
section{border:1px solid #ccc;padding:.6rem .9rem;margin:.6rem 0} section h3{margin:0 0 .3rem}
dl{display:grid;grid-template-columns:11rem 1fr;gap:.1rem .8rem;margin:0}
dt{color:#555;font-size:.85rem} dd{margin:0}
@media (max-width:40rem){dl{grid-template-columns:1fr}}"""


class Page:
    def __init__(self, teigi, entries):
        self.t, self.es = teigi, entries
        self.chigau = 0

    def head(self):
        t = self.t
        an = "数値の定義は、まだ案です。" if t["kettei"] == "案" else ""
        dl = "".join(f"<dt>{k}</dt><dd>{E(t[c])}</dd>" for k, c in (
            ("数えているもの", "nani"), ("単位", "tani"), ("いつの数値として並べるか", "toki"),
            ("資料での言い方", "iikata"), ("注意", "chui")))
        return (f"<h1>{E(t['name'])}（試作）</h1>\n"
                f"<p class=note>非公式の試作です。日野町が公開している資料と会議録をもとに、数値と、もとの資料の位置を並べたものです。"
                f"良し悪しは書いていません。{an}</p>\n<h2>何を数えた数値か</h2>\n<dl>{dl}</dl>\n")

    def cell_mae(self, es):
        """前か同じ時点の列の中身。資料の字が空か「実績」の数値どうしで、字が違えば、一致していないことを書く。"""
        h = "".join(e.chip() for e in es)
        hikaku = {shogo.norm(e.r["atai"]) for e in es
                  if e.r["jotai"] == sj.ARU and e.r["shurui"].strip() in HIKAKU_SHURUI}
        if len(hikaku) > 1:
            self.chigau += 1
            h += "<div class=chigau>資料の間で、数値が一致していません</div>"
        return h

    def nen(self):
        """年ごとの数値の表（区分ごとに分ける）。"""
        kes = [e for e in self.es if e.kankei]
        cols = [k for k in KANKEI if any(e.kankei == k for e in kes)]
        kubuns = list(dict.fromkeys(e.r["kubun"] for e in kes))
        out = []
        for kb in kubuns:
            es = [e for e in kes if e.r["kubun"] == kb]
            tokis = sorted({e.toki for e in es})
            rows = []
            for key, label in tokis:
                cells = []
                for k in cols:
                    xs = [e for e in es if e.toki[1] == label and e.kankei == k]
                    cells.append(self.cell_mae(xs) if k == sj.KANKEI_MAE else "".join(e.chip() for e in xs))
                rows.append(f"<tr><th>{E(label)}</th>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            head = "".join(f"<th>{E(KOTOBA[k])}</th>" for k in cols)
            out.append((f"<h3>{E(kb)}</h3>" if kb else "")
                       + f"<table>\n<thead><tr><th>時点</th>{head}</tr></thead>\n<tbody>{''.join(rows)}</tbody>\n</table>")
        t = self.t["nendo_tsuki"]
        if t in sj.NENDO_TSUKI:
            nendo = f"年度で書かれた数値は、定義の決まりにより、その年度の{int(t)}月の数値として並べています。"
        elif any(not sj.RE_NENGETSU.fullmatch(e.r["jiten"].strip()) for e in kes):
            nendo = "年度で書かれた数値は、年度を、その年の4月から翌年の3月までの期間として扱っています。"
        else:
            nendo = ""
        setsumei = (f"<p>列は、数値の時点と、資料の日付（答弁は発言の日）の2つから、ツールで分けています。"
                    f"資料の言葉（「目標」「実績」など）では分けていません。{nendo}"
                    "資料がその数値について種類を書いている場合は、「資料の字」として添えています。"
                    "数値を選ぶと、下の「数値ごとの、もとの資料」に移ります。</p>")
        body = "\n".join(out)
        chigau = ("<p class=note>「資料の間で、数値が一致していません」は、同じ時点の"
                  f"「{KOTOBA[sj.KANKEI_MAE]}」のうち、資料の字が無いか「実績」の数値どうしで、字が違うときに出しています。</p>"
                  if self.chigau else "")
        return f"<h2>年ごとの数値</h2>\n{setsumei}\n{body}\n{chigau}\n{self.nai()}"

    def nai(self):
        """時点の関係を出していない数値を、理由ごとに並べる。"""
        es = [e for e in self.es if not e.kankei]
        if not es:
            return ""
        out = ["<h3>時点の関係を出していない数値</h3>"]
        for riyu in RIYU:
            xs = [e for e in es if e.riyu == riyu]
            if not xs:
                continue
            li = "".join(f"<li>{E(e.label)}{'（' + E(e.r['kubun']) + '）' if e.r['kubun'] else ''}：{e.chip()}"
                         + (f"<div class=nai>{E(e.r['hani'])}（{E(e.r['kakunin'])} に調べた）</div>"
                            if e.r["jotai"] != sj.ARU and e.r["hani"] else "")
                         + "</li>" for e in xs)
            out.append(f"<p>理由：{riyu}（{len(xs)}行）</p><ul>{li}</ul>")
        return "\n".join(out)

    def hiduke_jun(self):
        """どの行も時点の関係を出さない定義：資料の日付の順（古い順）に並べた表。日付の無い行は終わりに置く。"""
        es = sorted(self.es, key=lambda e: (e.hiduke is None, e.hiduke[0] if e.hiduke else (), e.gyo))
        rows = "".join(
            f"<tr><td>{e.hiduke[1] if e.hiduke else '資料に日付の記述がありません'}</td>"
            f"<td><a href='#{e.id}'><b>{e.atai}</b></a></td>"
            f"<td>{S(e.r['shurui']) if e.r['shurui'] else ''}</td>"
            f"<td>{e.namae}{'　' + e.page if e.page else ''}</td></tr>" for e in es)
        riyu = Counter(e.riyu for e in self.es)
        r = "、".join(f"{x}（{riyu[x]}行）" for x in RIYU if riyu[x])
        return (f"<h2>資料の日付の順に並べた数値</h2>\n"
                f"<p>どの数値にも、時点の関係を出していません（理由：{r}）。そのため、資料の日付（答弁は発言の日）の古い順に並べています。"
                "並べ方は、まだ決まっていません。数値を選ぶと、下の「数値ごとの、もとの資料」に移ります。</p>\n"
                f"<table>\n<thead><tr><th>資料の日付</th><th>数値</th><th>資料の字での種類</th><th>もとの資料</th></tr></thead>\n"
                f"<tbody>{rows}</tbody>\n</table>")

    def detail(self, e):
        r = e.r
        items = [("いつの数値か", E(r["jiten"]))]
        if r["kubun"]:
            items.append(("内訳", E(r["kubun"])))
        if r["shiryo"].strip():
            items += [("区分", "議会での答弁" if e.sp else "町の資料"),
                      ("もとの資料", e.namae + (f"　{e.page}" if e.page else "")),
                      ("資料の日付", e.hiduke[1] if e.hiduke else "資料に日付の記述がありません"),
                      ("資料の中の位置", e.ichi or ("まだ指していません（ページまで）" if e.page else "まだ指していません")),
                      ("資料の文", f"「{S(r['inyo'])}」" if r["inyo"] else "引用はありません")]
        items.append(("資料の字での種類", S(r["shurui"]) if r["shurui"] else "資料に、種類を示す字はありません"))
        items.append(("時点の関係", E(KOTOBA[e.kankei]) if e.kankei else f"出していません（{e.riyu}）"))
        if e.konkyo:
            items.append(("資料の根拠（資料の文）", e.konkyo))
        if r["chu"]:
            items.append(("確認の状態", E(r["chu"])))
        if r["jotai"] != sj.ARU:
            items.append(("状態", E(r["jotai"])))
            if r["hani"]:
                items.append(("調べた範囲", E(r["hani"])))
            if r["kakunin"]:
                items.append(("調べた日", keys.ymd(r["kakunin"])))
        dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in items)
        if r["shiryo"].strip():
            link = (f"<p><a href='{E(e.url)}'>もとの資料を確認できます</a></p>" if e.url
                    else "<p>もとの資料へのリンクは、まだありません</p>")
        else:
            link = ""
        kb = f"{E(r['kubun'])}　" if r["kubun"] else ""
        return f"<section id='{e.id}'><h3>{kb}{E(e.label)}：{e.atai}</h3><dl>{dl}</dl>{link}</section>"

    def dashite_inai(self):
        """このページで、まだ出していないもの。その定義の行に当てはまるものだけ。"""
        li = []
        if any(e.sp for e in self.es):
            li.append("答弁が、何を問われての答えか（質問した議員と題）。")
        nashi = list(dict.fromkeys(e.namae for e in self.es if e.r["shiryo"].strip() and not e.sp and not e.r["bubun"]))
        if nashi:
            li.append("次の資料の数値の、資料の中の位置（表の行と列など）：" + "、".join(nashi) + "。")
        docs = {sj.bunsho_of(e.r["shiryo"]) or e.r["shiryo"] for e in self.es if e.r["shiryo"].strip()}
        if len(docs) > 1:
            li.append("資料どうしの関係（計画の版、ほかのページを指す記述）。")
        if not li:
            return ""
        return "<h2>このページで、まだ出していないもの</h2>\n<ul>" + "".join(f"<li>{x}</li>" for x in li) + "</ul>"

    def render(self, today):
        if any(e.kankei for e in self.es):
            main = self.nen()
        else:
            main = self.hiduke_jun()
        mikakunin = ("<p class=note>資料の中の位置に「（未確認）」とある部分は、生成AIが資料を読んで決めた位置で、まだ確認していません。</p>"
                     if any(e.mikakunin for e in self.es) else "")
        details = "".join(self.detail(e) for e in self.es)
        note = ("<p class=note><b>このページについて</b><br>町と町議会が公開している資料（会議録、計画、町の資料）をもとに作成しています。"
                "「資料の文」は資料からの引用で、要約や言い換えは行っていません。「何を数えた数値か」と「確認の状態」は、作成者が書いた文です。"
                "数値の足し算や割合の計算は行っていません。正確な内容は、もとの資料で確認してください。"
                "個人による試作であり、日野町および日野町議会の公式のものではありません。"
                f"（{today.year}年{today.month}月{today.day}日作成）</p>")
        return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(self.t['name'])}（試作）</title>
<style>
{STYLE}
</style></head><body>
{self.head()}
{main}
<h2>数値ごとの、もとの資料</h2>
{mikakunin}{details}
{self.dashite_inai()}
{note}
</body></html>
"""


def build(inp, tables, sid, kotoba, today, read_problems=()):
    """検査を通ればページ（印を消した HTML）と件数を返す。当たれば Stop。

    tables は {"suji", "atai", "bunsho", "bubun"} → 行の並び（tools/suji.py の read_* で読んだ物）。
    """
    problems = [("(a) 表の検査", mondai_str(m)) for m in read_problems]
    mondai, _, _ = sj.check_all(inp, tables["suji"], tables["atai"], tables["bunsho"], tables["bubun"])
    problems += [("(a) 表の検査", mondai_str(m)) for m in mondai]
    teigi = next((r for r in tables["suji"] if r["id"] == sid), None)
    if teigi is None:
        problems.append(("(c) 定義の id", f"{sid} が {sj.SUJI_NAME} に無い"))
    if problems:
        raise Stop(problems)
    by = {r["bunsho"]: r for r in tables["bunsho"]}
    index = {(r["bunsho"], r["n"]): r for r in tables["bubun"]}
    entries = [Entry(r, teigi, inp, by, index) for r in tables["atai"] if r["suji"] == sid]
    for e in entries:
        if e.r["shiryo"].strip() and not e.namae:
            problems.append(("(a) 表の検査", f"{sj.ATAI_NAME} の {e.gyo} 行目：もとの資料の名前が作れない（{e.r['shiryo']}）"))
    if problems:
        raise Stop(problems)
    p = Page(teigi, entries)
    page = p.render(today)
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop([("(b) 使わない言葉", m) for _, m in problems])
    page = page.replace(A, "").replace(B, "")
    return page, dict(gyo=len(entries), kankei=Counter(e.kankei for e in entries), chigau=p.chigau,
                      ji=len(page))


def main(argv=None, teigi_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not re.fullmatch(r"[a-z0-9-]+", argv[0]):
        print("使い方：python3 -B tools/build_suji.py <定義の id>", file=sys.stderr)
        return 2
    sid = argv[0]
    try:
        inp = inputs.Inputs()                                   # (d) lock と入力
        tables, read_problems = read_tables(teigi_dir)
        page, info = build(inp, tables, sid, bn.read_kotoba(), datetime.date.today(), read_problems)
    except (inputs.InputError, OSError, UnicodeDecodeError) as e:
        print(f"止めた：(d) lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    except Stop as e:
        print(f"止めた：{len(e.problems)} 件。ページは作っていない。", file=sys.stderr)
        for kind, msg in e.problems:
            print(f"  - {kind}：{msg}", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{sid}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    k = info["kankei"]
    print(f"{os.path.relpath(out, inputs.ROOT)}（{os.path.getsize(out)} バイト、{info['ji']} 字）")
    print(f"数値の行：{info['gyo']}（後の時点 {k[sj.KANKEI_ATO]}、年度の途中 {k[sj.KANKEI_TOCHU]}、"
          f"前か同じ時点 {k[sj.KANKEI_MAE]}、時点の関係を出していない {k[None]}）")
    print(f"資料の間で数値が一致していない時点：{info['chigau']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
