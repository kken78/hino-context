"""テーマ1つを1ページにする（SCHEMA.md §7.7、docs/design.md 3節・4節）。

実行：python3 -B tools/build_theme.py <テーマの鍵>   （例 hoiku → build/theme/hoiku.html）
テーマの名前、施設、資料は、hino-ronten のテーマの定義（ref/themes.tsv）から引く。資料のうち計画は、kind「系列」の
value を系列の表（ref/lineage.tsv）の series で引いた plan の文書（pt:<plan>/…）とする。
経過は過程の記録（records/katei.tsv）、施設ごとの欄は施設の記録（records/shisetsu.tsv）の、確定済みの行から作る。
説明の文と施設の表は、テーマの表（teigi/theme.tsv）から、施設の表の欄の数値は数値の表から、資料どうしの関係は
文書どうしの関係の表から引く。数値を計算しない。外から何も読み込まない1つの HTML にする。
画面に出す言葉は、docs/design.md 3節の2つの表から読む（tools/build_suji.py の read_design と同じ読み方）。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all。テーマの表と文書どうしの関係の表を含む）で問題がある
  (b) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文と、hino-ronten の記録の
      value・target・quote、過程の記録の name・quote、施設の参照表の name・aliases は除く。施設の記録の aspect と kind は対象）
  (c) テーマの定義に、そのテーマの kind「名前」の行が1行でない。テーマの施設が施設の参照表に無い
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems）
  (f) 過程の記録と施設の記録の quote が、source の資料の本文に無い（SCHEMA.md §3）。会議録の発言者の役職から、
      町の答弁か議員の発言かを決められない（役職が空か、議長を含む）。資料の名前を作れない。過程の記録の from・to の形が違う
  (g) 施設の表に、施設の割り当てが未確認の行（tools/suji.py の shisetsu_mikakunin）がある。施設の表の施設が、
      テーマの施設に無い
"""
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_hyo as bh  # noqa: E402
import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import ronten  # noqa: E402
import shogo  # noqa: E402
import suji as sj  # noqa: E402

OUT_DIR = os.path.join(inputs.ROOT, "build", "theme")
SRC_PATH = os.path.abspath(__file__)
A, B = bn.A, bn.B
E, S = bn.E, bn.S
Stop = bn.Stop
RE_THEME = re.compile(r"[a-z0-9-]+")

# hino-ronten のテーマの定義の kind（SCHEMA.md §7.7）
KIND_SHISETSU, KIND_SHIRYO, KIND_KEIRETSU = "施設", "資料", "系列"
# 施設の記録の aspect のうち、施設の表の欄に出すもの（docs/design.md 3節）
UNEI = "運営"
# 会議録の発言者の役職の区分（hino-council-search の区分と同じ）。「数字＋番」は議員、議長を含む役職は議長
RE_GIIN = re.compile(r"[0-9０-９]+番")
GICHO = "議長"


def design_problems(D, src=None):
    """docs/design.md 3節の表と、このツールが合うか。→ 問題の並び。"""
    return bs.design_problems(D, src, path=SRC_PATH)


def read_tables(teigi_dir=None):
    """数値・定義・文書・文書の部分の4つの表に、文書どうしの関係の表とテーマの表を加えて読む。
    テーマの表が無ければ、行が無いものとする（説明の文と施設の表の無いテーマとして作る）。"""
    d = teigi_dir or sj.TEIGI_DIR
    tables, problems = bs.read_tables(d)
    for key, fname, reader, name, hissu in (("kankei", "bunsho-kankei.tsv", sj.read_bunsho_kankei,
                                             sj.BUNSHO_KANKEI_NAME, True),
                                            ("theme", "theme.tsv", sj.read_theme, sj.THEME_NAME, False)):
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            if hissu:
                problems.append(sj.Mondai(name, 0, "表が無い"))
            tables[key] = []
            continue
        rows, p = reader(sj._read_file(path))
        tables[key] = rows
        problems += p
    return tables, problems


# ---- 資料の名前 ----

class Namae:
    """資料の鍵 → 画面に出す資料の名前と url。作れない資料は problems にためる。"""

    def __init__(self, D, inp, by_bunsho):
        self.D, self.inp, self.by = D, inp, by_bunsho
        self.problems = []

    def stop(self, msg):
        self.problems.append(("(f) 資料の名前", msg))

    def koho(self, hiduke, dai, key):
        m = re.fullmatch(r"([0-9]{4})-([0-9]{2})(?:-[0-9]{2})?", hiduke or "")
        if not m:
            self.stop(f"広報ひのの号の年月が無い（{key}）")
            return S(dai)
        return self.D.bun("koho", nen=int(m[1]), tsuki=int(m[2]), dai=S(dai))

    def bunsho(self, bkey):
        """文書の鍵 → 資料の名前（HTML）。文書の表にあれば namae と括弧（han と hiduke）。広報ひのは koho の文。"""
        b = self.by.get(bkey)
        if b:
            if b["shurui"] == sj.KOHO:
                return self.koho(b["hiduke"], b["namae"], bkey)
            return f"{S(b['namae'])}（{bh.kakko_ji(self.D, b)}）"
        m = sj.RE_BUNSHO_DOC.fullmatch(bkey)
        if m:
            row = self.inp.docs().get(m[1])
            if row is None or not row.get("title"):
                self.stop(f"hino-town-docs の資料が入力に無い（{bkey}）")
                return S(bkey)
            if row.get("category") == sj.KOHO:
                return self.koho(row.get("date", ""), row["title"], bkey)
            return S(row["title"])
        m = sj.RE_BUNSHO_PT.fullmatch(bkey) or keys.RE_PLAN.fullmatch(bkey)
        name = (((self.inp.plan(m[1]) or {}).get("meta") or {}).get("name", "")) if m else ""
        if not name:
            self.stop(f"計画の名前が作れない（{bkey}）")
            return S(bkey)
        return S(name)

    def kubun(self, sid):
        """会議録の発言 → 区分の字（町の答弁か、議員の発言か）。発言者の役職から決める。決められなければ None。"""
        role = self.inp.role(sid)
        if role is None or not role.strip() or GICHO in role:
            self.stop(f"会議録の発言者の役職から、区分を決められない（sp:{sid}、役職「{role or ''}」）")
            return None
        if RE_GIIN.fullmatch(role.strip()):
            w = self.D.kotoba("会議録の発言者の役職が「数字＋番」")
        else:
            w = self.D.kotoba("会議録の発言者の役職が、議長でも「数字＋番」でもない")
        return bs.RE_KAGIKAKKO.search(w).group(1)

    def shiryo(self, key, quote=""):
        """資料の鍵（ページか発言）→ (資料の名前とページの HTML, url)。"""
        try:
            kind, g = keys.parse(key)
        except keys.KeyFormError:
            self.stop(f"資料の鍵の形が違う（{key}）")
            return S(key), ""
        if kind == "sp":
            kubun = self.kubun(g[0])
            hi = keys.sid_date(g[0])
            name = self.D.bun("kaigiroku-kubun", hi=bs.hi_str(self.D, hi) if hi else "", kubun=E(kubun or ""))
            text = self.inp.statement_text(g[0])
            p = shogo.para_of_quote(text, quote) if text and quote else None
            return name, keys.source_url(self.inp, key, p)
        if kind in ("doc", "pt"):
            return (f"{self.bunsho(sj.bunsho_of(key))}　{E(self.D.bun('page', n=sj.page_no(key)))}",
                    keys.source_url(self.inp, key))
        self.stop(f"資料の名前を作れない鍵（{key}）")
        return S(key), ""

    def link(self, key, quote=""):
        name, url = self.shiryo(key, quote)
        return f"<a href='{E(url)}'>{name}</a>" if url else name


# ---- テーマの範囲 ----

class Theme:
    """テーマの定義から引いた、テーマの名前・施設・資料。"""

    def __init__(self, inp, theme):
        rows = ronten.themes(inp, theme)
        self.namae = [r["value"] for r in rows if r["kind"] == sj.THEME_NAMAE]
        self.shisetsu = [r["value"] for r in rows if r["kind"] == KIND_SHISETSU]
        self.docs = {r["value"] for r in rows if r["kind"] == KIND_SHIRYO}
        self.plans = ronten.lineage_plans(inp, {r["value"] for r in rows if r["kind"] == KIND_KEIRETSU})

    def has(self, bkey):
        """文書の鍵が、テーマの資料か。kind「資料」の doc の鍵か、系列の計画（pt:<plan>/… か plan:<plan>）。"""
        if bkey in self.docs:
            return True
        m = sj.RE_BUNSHO_PT.fullmatch(bkey) or keys.RE_PLAN.fullmatch(bkey)
        return bool(m) and m[1] in self.plans


def anchor(fa):
    """施設の鍵 → ページ内リンクの id。"""
    return fa.replace(":", "-")


# ---- 施設の表 ----

class ShisetsuHyo:
    """テーマの表の「施設の表」の行が指す表の、行（shisetsu がある行か列）と欄。"""

    def __init__(self, D, tables, trow, ref_by_key, kiroku, theme_shisetsu):
        self.problems = []
        bub = tables["bubun"]
        self.bubun_by = {(r["bunsho"], r["n"]): r for r in bub}
        index = {k: [v] for k, v in self.bubun_by.items()}
        self.trow = trow
        self.hyo = sj.theme_hyo_bubun(trow, index)
        self.gyo = sorted(sj.theme_hyo_gyo(self.hyo, bub), key=lambda g: (g["shu"], int(g["jun"] or 0), int(g["n"])))
        self.keys = [tuple(sorted(set(sj.shisetsu_keys(g["shisetsu"])))) for g in self.gyo]
        for g, ks in zip(self.gyo, self.keys):
            if sj.shisetsu_mikakunin(g, ref_by_key):
                self.problems.append(("(g) 施設の表", f"{sj.BUBUN_NAME} の {g['_gyo']} 行目：施設の割り当てが未確認"
                                                     f"（{g['name']}）"))
            bad = [k for k in ks if k not in theme_shisetsu]
            if bad:
                self.problems.append(("(g) 施設の表", f"{sj.BUBUN_NAME} の {g['_gyo']} 行目：施設が、テーマの施設に無い"
                                                     f"（{'・'.join(bad)}）"))
        # 施設の鍵の組が同じ数値（定義ごと）
        self.suji = []            # 定義の表の行の並び（定義の表の順）
        self.atai = {}            # (定義の id, 施設の鍵の組) → 数値の表の行の並び
        kumi = set(self.keys)
        for r in tables["atai"]:
            ks = sj.atai_shisetsu(r, self.bubun_by)
            if r["jotai"] == sj.ARU and ks in kumi:
                self.atai.setdefault((r["suji"], ks), []).append(r)
        ids = {s for s, _ in self.atai}
        self.suji = [t for t in tables["suji"] if t["id"] in ids]
        # 運営：source のページが、施設の表のページと同じ行
        self.unei = {}
        for ks in kumi:
            vals = [r["value"] for r in kiroku if r["facility"] in ks and r["aspect"] == UNEI
                    and r["source"] == self.hyo["tokoro"]]
            self.unei[ks] = list(dict.fromkeys(vals))
        self.matome = any(g["matome"].strip() for g in self.gyo)


# ---- ページ ----

STYLE = """body{font-family:sans-serif;line-height:1.7;max-width:60rem;margin:1.5rem auto;padding:0 1rem;color:#222}
h1{font-size:1.3rem} h2{font-size:1.1rem;border-top:2px solid #555;padding-top:.5rem;margin-top:1.8rem} h3{font-size:1rem;margin-top:1.4rem}
table{border-collapse:collapse;margin:.4rem 0 1rem;width:100%} th,td{border:1px solid #999;padding:.3rem .6rem;text-align:left;vertical-align:top}
th{background:#eee;font-weight:normal} td.r{text-align:right} .s{color:#555;font-size:.9rem} .q{margin:.3rem 0}
.setsumei{border-left:4px solid #999;padding:.2rem 1rem;margin:.8rem 0}"""


class Page:
    def __init__(self, D, inp, tables, theme, th, ref_by_key, kiroku, katei, namae, hyo):
        self.D, self.inp, self.t, self.theme, self.th = D, inp, tables, theme, th
        self.ref, self.kiroku, self.katei, self.n, self.hyo = ref_by_key, kiroku, katei, namae, hyo

    def setsumei(self):
        """テーマの表の「説明の文」の行の部分。行が無ければ、見出しも出さない。"""
        D = self.D
        rows = sorted((r for r in self.t["theme"] if r["theme"] == self.theme and r["shu"] == sj.SETSUMEI_BUN),
                      key=lambda r: int(r["jun"]))
        if not rows:
            return ""
        o = [f"<h2>{E(D.kotoba('テーマの表 shu が「説明の文」'))}</h2>"]
        i = 0
        while i < len(rows):
            b = sj.bunsho_of(rows[i]["tokoro"])
            k = i
            while k < len(rows) and sj.bunsho_of(rows[k]["tokoro"]) == b:
                k += 1
            url = keys.source_url(self.inp, rows[i]["tokoro"])
            name = self.n.bunsho(b)
            namae = f"<a href='{E(url)}'>{name}</a>" if url else name
            o.append(f"<p>{namae}</p><div class=setsumei>"
                     + "".join(f"<p class=q>「{S(r['inyo'])}」（{E(D.bun('page', n=sj.page_no(r['tokoro'])))}）</p>"
                               for r in rows[i:k]) + "</div>")
            i = k
        return "\n".join(o)

    def kikan(self, r):
        D = self.D
        a = bs.hi_str(D, r["from"])
        if not r["to"]:
            return D.bun("kikan-tochu", a=a)
        if r["to"] == r["from"]:
            return a
        return D.bun("kikan", a=a, z=bs.hi_str(D, r["to"]))

    def keika(self):
        D = self.D
        if not self.katei:
            return ""
        head = (f"<th>{E(D.kotoba('過程の記録 from、to'))}</th><th>{E(D.kotoba('過程の記録 name'))}</th>"
                f"<th>{E(D.kotoba('過程の記録 quote'))}</th><th>{E(D.kotoba('過程の記録 sources'))}</th>")
        rows = []
        for r in self.katei:
            srcs = list(dict.fromkeys(s.strip() for s in r["sources"].split(",") if s.strip()))
            links = "、".join(self.n.link(s, r["quote"]) for s in srcs)
            rows.append(f"<tr><td>{E(self.kikan(r))}</td><td>{S(r['name'])}</td><td>「{S(r['quote'])}」</td>"
                        f"<td>{links}</td></tr>")
        return (f"<h2>{E(D.bun('midashi-keika'))}</h2>\n<p class=s>{E(D.bun('keika-setsumei'))}</p>\n"
                f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")

    def shisetsu_hyo(self):
        D, h = self.D, self.hyo
        if h is None:
            return ""
        D.dasanai("文書の部分の表 shisetsu")
        D.dasanai("文書の部分の表 matome")
        D.dasanai("定義の表 name")
        D.dasanai("施設の参照表 name")
        tr = h.trow
        o = [f"<h2>{E(D.kotoba('テーマの表 shu が「施設の表」'))}</h2>"]
        setsumei = [D.bun("theme-hyo", shiryo=self.n.bunsho(sj.bunsho_of(tr["tokoro"])),
                          page=E(D.bun("page", n=sj.page_no(tr["tokoro"]))), hyo=bh.midashi_ji(D, h.hyo))]
        for t in h.suji:
            moto = {}
            for (sid, _), rs in h.atai.items():
                if sid != t["id"]:
                    continue
                for r in rs:
                    moto.setdefault((sj.bunsho_of(r["shiryo"]) or r["shiryo"], r["jiten"]), set()).add(
                        sj.page_no(r["shiryo"]))
            for (b, jiten), pages in moto.items():
                pp = "、".join(str(p) for p in sorted(p for p in pages if p))
                shiryo = self.n.bunsho(b) + (f"　{E(D.bun('page', n=pp))}" if pp else "")
                setsumei.append(D.bun("theme-suji", name=E(t["name"]), shiryo=shiryo, jiten=S(jiten)))
        unei = E(D.kotoba("施設の記録 aspect が「運営」"))
        if any(h.unei.values()):
            setsumei.append(D.bun("theme-unei", unei=unei))
        o.append("<p class=s>" + "<br>".join(setsumei) + "</p>")
        heads = ["<th></th>"] + (["<th></th>"] if h.matome else []) + [f"<th>{unei}</th>"]
        for t in h.suji:
            nm = D.bun("retsu-tani", name=E(t["name"]), tani=E(t["tani"])) if t["tani"] else E(t["name"])
            heads.append(f"<th>{nm}</th>")
        rows = []
        for g, ks in zip(h.gyo, h.keys):
            name = bh.midashi_ji(D, g)
            if len(ks) == 1:
                name = f"<a href='#{E(anchor(ks[0]))}'>{name}</a>"
            else:
                name += ("<br><span class=s>" + "、".join(f"<a href='#{E(anchor(k))}'>{S(self.ref[k]['name'])}</a>"
                                                          for k in ks) + "</span>")
            tds = [f"<th>{name}</th>"]
            if h.matome:
                tds.append(f"<td>{S(g['matome'])}</td>")
            tds.append(f"<td>{'、'.join(S(v) for v in h.unei[ks])}</td>")
            for t in h.suji:
                tds.append("<td class=r>" + "、".join(S(r["atai"]) for r in h.atai.get((t["id"], ks), [])) + "</td>")
            rows.append("<tr>" + "".join(tds) + "</tr>")
        o.append(f"<table>\n<thead><tr>{''.join(heads)}</tr></thead>\n<tbody>\n" + "\n".join(rows)
                 + "\n</tbody>\n</table>")
        url = keys.source_url(self.inp, tr["tokoro"])
        if url:
            o.append(f"<p><a href='{E(url)}'>{E(D.bun('link'))}</a></p>")
        used = {k for ks in h.keys for k in ks}
        nai = [k for k in self.th.shisetsu if k not in used]
        if nai:
            o.append("<p>" + D.bun("hyo-ni-nai", shisetsu="、".join(
                f"<a href='#{E(anchor(k))}'>{S(self.ref[k]['name'])}</a>" for k in self.jun_shisetsu() if k in nai))
                + "</p>")
        return "\n".join(o)

    def shiryo(self):
        D = self.D
        kk = [r for r in self.t["kankei"] if self.th.has(r["kara"]) or self.th.has(r["e"])]
        if not kk:
            return ""
        by = {r["bunsho"]: r for r in self.t["bunsho"]}
        docs = sorted({r["kara"] for r in kk} | {r["e"] for r in kk},
                      key=lambda k: ((by.get(k) or {}).get("hiduke") or "9999", k))
        D.dasanai("文書どうしの関係の表 hyogen")
        rows = []
        for k in docs:
            groups = {}
            for r in kk:
                if r["kara"] == k:
                    groups.setdefault((r["inyo"], r["hyogen"]), []).append(r)
            cells = []
            for (inyo, hyogen), rs in groups.items():
                aite = "、".join(dict.fromkeys(self.n.bunsho(r["e"]) for r in rs))
                page = E(D.bun("page", n=sj.page_no(rs[0]["tokoro"])))
                cells.append(f"<p class=q>「{S(inyo)}」（{page}）<br><span class=s>"
                             f"{D.bun('aite', hyogen=S(hyogen), aite=aite)}</span></p>")
            cell = "".join(cells) or f"<span class=s>{E(D.bun('shiryo-nashi'))}</span>"
            rows.append(f"<tr><td>{self.n.bunsho(k)}</td><td>{cell}</td></tr>")
        head = (f"<th>{E(D.kotoba('文書どうしの関係の表 kara、e'))}</th>"
                f"<th>{E(D.kotoba('文書どうしの関係の表 inyo'))}</th>")
        return (f"<h2>{E(D.bun('midashi-shiryo'))}</h2>\n<p class=s>{E(D.bun('shiryo-setsumei'))}</p>\n"
                f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")

    def jun_shisetsu(self):
        """施設ごとの欄の順：施設の表の行の順に、表にある施設を先に置き、残りは施設の参照表の順。"""
        out = []
        if self.hyo is not None:
            out += [k for ks in self.hyo.keys for k in ks]
        out += [k for k in self.ref if k in self.th.shisetsu]
        return [k for k in dict.fromkeys(out) if k in self.th.shisetsu]

    def kijutsu(self):
        D = self.D
        head = (f"<th>{E(D.kotoba('施設の記録 source'))}</th><th>{E(D.kotoba('施設の記録 aspect'))}</th>"
                f"<th>{E(D.kotoba('施設の記録 kind'))}</th><th>{E(D.kotoba('施設の記録 value、target'))}</th>"
                f"<th>{E(D.kotoba('施設の記録 quote'))}</th>")
        maeno = D.kotoba("施設の参照表 aliases")
        o = [f"<h2>{E(D.bun('midashi-kijutsu'))}</h2>",
             f"<p class=s>{E(D.bun('kijutsu-setsumei'))}{E(D.bun('kubun-setsumei'))}</p>"]
        for k in self.jun_shisetsu():
            ref = self.ref[k]
            o.append(f"<h3 id='{E(anchor(k))}'>{S(ref['name'])}</h3>")
            al = [a.strip() for a in ref["aliases"].split(";") if a.strip()]
            if al:
                o.append(f"<p class=s>{E(maeno)}：{S('、'.join(al))}</p>")
            rs = sorted((r for r in self.kiroku if r["facility"] == k),
                        key=lambda r: (r["source_date"], r["source"], r["aspect"]))
            if not rs:
                continue
            rows = []
            for r in rs:
                v = S(r["value"]) + (f"（{S(r['target'])}）" if r["target"] else "")
                rows.append(f"<tr><td>{self.n.link(r['source'], r['quote'])}</td><td>{E(r['aspect'])}</td>"
                            f"<td>{E(r['kind'])}</td><td>{v}</td><td>「{S(r['quote'])}」</td></tr>")
            o.append(f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")
        return "\n".join(o)

    def render(self, today):
        D = self.D
        D.dasanai("テーマの定義 kind が「名前」")
        name = self.th.namae[0]
        parts = [f"<p class=s>{E(D.bun('atama-theme'))}</p>", f"<h1>{S(name)}</h1>",
                 self.setsumei(), self.keika(), self.shisetsu_hyo(), self.shiryo(), self.kijutsu(),
                 f"<h2>{E(D.bun('midashi-owari'))}</h2><p class=s>{E(D.bun('owari-theme'))}"
                 f"{E(D.bun('sakusei-bi', hi=bs.hi_str(D, today.isoformat())))}</p>"]
        body = "\n".join(p for p in parts if p)
        return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{D.bun('dai', name=S(name))}</title>
<style>
{STYLE}
</style></head><body>
{body}
</body></html>
"""


def quote_problems(inp, theme, katei, kiroku):
    """過程の記録（sources の1つ目）と施設の記録の quote を、source の資料の本文と照合する（SCHEMA.md §3）。"""
    rows = [dict(where=f"過程の記録 {theme} step {r['step']}", source=r["sources"].split(",")[0].strip(),
                 quote=r["quote"]) for r in katei]
    rows += [dict(where=f"施設の記録 {r['facility']} / {r['source']} / {r['aspect']}", source=r["source"],
                  quote=r["quote"]) for r in kiroku]
    res = shogo.check_quotes(inp, rows)
    return [("(f) 引用の照合", f"{m['where']}：{m['reason']}（{m['source']}）") for m in res.mismatched], res


def build(inp, tables, theme, kotoba, today, read_problems=(), design=None):
    """検査を通ればページ（印を消した HTML）と件数を返す。当たれば Stop。

    tables は {"suji", "atai", "bunsho", "bubun", "kankei", "theme"} → 行の並び（read_tables で読んだもの）。
    """
    D = design or bs.read_design()
    problems = [("(e) デザインシステムとの対応", m) for m in design_problems(D)]
    if problems:
        raise Stop(problems)
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in read_problems]
    mondai, _, _ = sj.check_all(inp, tables["suji"], tables["atai"], tables["bunsho"], tables["bubun"],
                                tables["kankei"], tables["theme"])
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in mondai]
    if problems:
        raise Stop(problems)
    th = Theme(inp, theme)
    ref = {r["key"]: r for r in inp.shisetsu()}
    if len(th.namae) != 1:
        problems.append(("(c) テーマ", f"テーマの定義に、{theme} の kind「{sj.THEME_NAMAE}」の行が {len(th.namae)} 行ある"
                                     "（1行のはず）"))
    bad = [k for k in th.shisetsu if k not in ref]
    if bad:
        problems.append(("(c) テーマ", f"テーマの施設が、施設の参照表に無い（{'・'.join(bad)}）"))
    if problems:
        raise Stop(problems)
    kiroku = [r for r in inp.shisetsu_kiroku() if r["facility"] in th.shisetsu]
    katei = sorted(ronten.katei(inp, theme), key=lambda r: (r["from"][:7], int(r["step"])))
    for r in katei:
        for c in ("from", "to"):
            if r[c] and not (sj.RE_HIDUKE.fullmatch(r[c]) and (len(r[c]) == 7 or sj.is_ymd(r[c]))):
                problems.append(("(f) 過程の記録", f"step {r['step']} の {c} の形が違う（{r[c]}）"))
        if not r["from"]:
            problems.append(("(f) 過程の記録", f"step {r['step']} の from が空"))
    more, res = quote_problems(inp, theme, katei, kiroku)
    problems += more
    hyo = None
    trows = [r for r in tables["theme"] if r["theme"] == theme and r["shu"] == sj.SHISETSU_HYO]
    if trows:
        hyo = ShisetsuHyo(D, tables, trows[0], ref, kiroku, set(th.shisetsu))
        problems += hyo.problems
    if problems:
        raise Stop(problems)
    by = {r["bunsho"]: r for r in tables["bunsho"]}
    namae = Namae(D, inp, by)
    page = Page(D, inp, tables, theme, th, ref, kiroku, katei, namae, hyo).render(today)
    if namae.problems:
        raise Stop(list(dict.fromkeys(namae.problems)))
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop([("(b) 使わない言葉", m) for _, m in problems])
    page = page.replace(A, "").replace(B, "")
    return page, dict(katei=len(katei), kiroku=len(kiroku), shisetsu=len(th.shisetsu),
                      hyo=len(hyo.gyo) if hyo else 0, inyo=res.matched, ji=len(page),
                      setsumei=sum(1 for r in tables["theme"] if r["theme"] == theme and r["shu"] == sj.SETSUMEI_BUN))


def main(argv=None, teigi_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not RE_THEME.fullmatch(argv[0]):
        print("使い方：python3 -B tools/build_theme.py <テーマの鍵>", file=sys.stderr)
        return 2
    theme = argv[0]
    try:
        inp = inputs.Inputs()                                   # (d) lock と入力
        tables, read_problems = read_tables(teigi_dir)
        page, info = build(inp, tables, theme, bn.read_kotoba(), datetime.date.today(), read_problems,
                           bs.read_design())
    except (inputs.InputError, OSError, UnicodeDecodeError) as e:
        print(f"止めた：(d) lock と入力、または表を読めない\n{e}", file=sys.stderr)
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
    print(f"{os.path.relpath(out, inputs.ROOT)}（{os.path.getsize(out)} バイト、{info['ji']} 文字）")
    print(f"説明の文 {info['setsumei']}、経過 {info['katei']} 行、施設の表 {info['hyo']} 行、"
          f"施設 {info['shisetsu']}（記録 {info['kiroku']} 行）、照合した引用 {info['inyo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
