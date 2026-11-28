"""テーマ1つを1ページにする（SCHEMA.md §7.7、docs/design.md 3節・4節）。

実行：python3 -B tools/build_theme.py <テーマの ID>   （例 hoiku → build/theme/hoiku.html）
テーマの名前、施設、資料は、hino-ronten のテーマの定義（ref/themes.tsv）から引く。資料のうち計画は、kind「系列」の
value を系列の表（ref/lineage.tsv）の series で引いた plan の資料（pt:<plan>/…）とする。
経過は過程の記録（records/katei.tsv）、施設ごとの欄は施設の記録（records/shisetsu.tsv）の、確定済みの行から作る。
施設ごとの欄には、テーマの資料の表（テーマの表で施設の表として指定した表を除く）の、その施設の行か列の欄も、
記録の表の下に出す。その欄は、施設の表には出さない（docs/design.md 4節。2026-11-25 の依頼者の了承）。
説明の文と施設の表は、テーマの表（teigi/theme.tsv）から、施設の表の欄の数値は数値と内容の表から、資料どうしの関係は
資料どうしの関係の表から引く。経過の行の sources の資料が、hyogen が「一部改正」の関係の kara の資料なら、その行の下に、
e の資料と、2つの資料の数値の組み合わせ（tools/suji.py の kaisei_tsui）を出す（docs/design.md 4節）。数値を計算しない。外から何も読み込まない1つの HTML にする。
画面に出す言葉は、docs/design.md 3節の2つの表から読む（tools/build_suji.py の read_design と同じ読み方）。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all。テーマの表と資料どうしの関係の表を含む）で問題がある
  (b) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文と、hino-ronten の記録の
      value・target・quote、過程の記録の name・quote、施設の参照表の name・aliases は除く。施設の記録の aspect と kind は対象）
  (c) テーマの定義に、そのテーマの kind「名前」の行が1行でない。テーマの施設が施設の参照表に無い
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems）
  (f) 過程の記録と施設の記録の quote が、source の資料の本文に無い（SCHEMA.md §3）。会議録の発言者の役職から、
      町の答弁か議員の発言かを決められない（役職が空か、議長を含む）。資料の名前を作れない。過程の記録の from・to の形が違う
  (g) 施設の表に、施設の割り当てが未確認の行（tools/suji.py の shisetsu_mikakunin）がある。施設の表の施設が、
      テーマの施設に無い。施設ごとの欄に出す資料の表の行か列に、施設の割り当てが未確認の行がある
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
    """項目の表、数値と内容の表、資料の一覧の表、資料の中の場所の表の4つに、資料どうしの関係の表とテーマの表を加えて読む。
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
    """資料の ID → 画面に出す資料の名前と url。作れない資料は problems にためる。"""

    def __init__(self, D, inp, by_bunsho):
        self.D, self.inp, self.by = D, inp, by_bunsho
        self.problems = []

    def stop(self, msg):
        self.problems.append(("(f) 資料の名前", msg))

    def koho(self, hiduke, dai, key):
        m = re.fullmatch(r"([0-9]{4})-([0-9]{2})(?:-[0-9]{2})?", hiduke or "")
        if not m:
            self.stop(f"広報（koho）の号の年月が無い（{key}）")
            return S(dai)
        return self.D.bun("koho", nen=int(m[1]), tsuki=int(m[2]), dai=S(dai))

    def nendo_dake(self, bkey):
        """資料の ID が、資料の一覧の表に無い doc の ID で、入力の台帳（sources.tsv）の date が空、fiscal_year がある資料なら、
        fiscal_year の字。ほかは空（docs/design.md 3節。2026-11-27）。広報（koho）は除く（号の年月で出すため）。"""
        if not bkey or bkey in self.by:
            return ""
        m = sj.RE_BUNSHO_DOC.fullmatch(bkey)
        row = (self.inp.docs().get(m[1]) or {}) if m else {}
        if row.get("date") or row.get("category") == sj.KOHO:
            return ""
        fy = row.get("fiscal_year", "")
        return fy if re.fullmatch(r"[0-9]{4}", fy or "") else ""

    def hiduke_nashi(self, bkey):
        """資料の ID が資料の一覧の表にあり、hiduke が空か。"""
        b = self.by.get(bkey or "")
        return b is not None and not sj.RE_HIDUKE.fullmatch(b["hiduke"] or "")

    def kiroku_jun(self, r):
        """施設の記録の並べ方：資料の一覧の表の hiduke が空の資料を最後に置き、ほかは source_date の順。"""
        return (self.hiduke_nashi(sj.bunsho_of(r["source"])), r["source_date"], r["source"], r["aspect"])

    def bunsho(self, bkey):
        """資料の ID → 資料の名前（HTML）。資料の一覧の表にあれば namae と括弧（han と hiduke）。広報（koho）は koho の文。"""
        b = self.by.get(bkey)
        if b:
            if b["shurui"] == sj.KOHO:
                return self.koho(b["hiduke"], b["namae"], bkey)
            return bh.namae_ji(self.D, b)
        m = sj.RE_BUNSHO_DOC.fullmatch(bkey)
        if m:
            row = self.inp.docs().get(m[1])
            if row is None or not row.get("title"):
                self.stop(f"hino-town-docs の資料が入力に無い（{bkey}）")
                return S(bkey)
            if row.get("category") == sj.KOHO:
                return self.koho(row.get("date", ""), row["title"], bkey)
            nendo = self.nendo_dake(bkey)
            if nendo:
                return f"{S(row['title'])}（{E(self.D.bun('nendo', nendo=int(nendo)))}）"
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
        """資料の ID（ページか発言）→ (資料の名前とページの HTML, url)。"""
        try:
            kind, g = keys.parse(key)
        except keys.KeyFormError:
            self.stop(f"資料の ID の形が違う（{key}）")
            return S(key), ""
        if kind == "sp":
            kubun = self.kubun(g[0])
            hi = inputs.hatsugen_hi(g[0])     # sid が日付で始まらない発言は、会議録の索引の日（2026-11-28）
            name = self.D.bun("kaigiroku-kubun", hi=bs.hi_str(self.D, hi) if hi else "", kubun=E(kubun or ""))
            text = self.inp.statement_text(g[0])
            p = shogo.para_of_quote(text, quote) if text and quote else None
            return name, keys.source_url(self.inp, key, p)
        if kind in ("doc", "pt"):
            return (f"{self.bunsho(sj.bunsho_of(key))}　{E(self.D.bun('page', n=sj.page_no(key)))}",
                    keys.source_url(self.inp, key))
        self.stop(f"資料の名前を作れない ID（{key}）")
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
        """資料の ID が、テーマの資料か。kind「資料」の doc の ID か、系列の計画（pt:<plan>/… か plan:<plan>）。"""
        if bkey in self.docs:
            return True
        m = sj.RE_BUNSHO_PT.fullmatch(bkey) or keys.RE_PLAN.fullmatch(bkey)
        return bool(m) and m[1] in self.plans


def shitei_hyo(trow):
    """テーマの表の「施設の表」の行 → (資料の ID, 表の番号)。行が無ければ None。"""
    return (sj.bunsho_of(trow["tokoro"]), trow["hyo"]) if trow else None


def kijutsu_no_hyo(part, by, th, shitei):
    """資料の中の場所の行 part が、施設ごとの欄に出す資料の表の行か列か。→ 親の表の行か None。

    行か列で、shisetsu があり、親の表がテーマの資料の表で、施設の表として指定した表（shitei）ではないもの。
    by は (資料の ID, 番号) → 資料の中の場所の行。"""
    if part.get("shu") not in (sj.GYO, sj.RETSU) or not part.get("shisetsu", "").strip():
        return None
    if not th.has(part["bunsho"]) or (part["bunsho"], part["oya"]) == shitei:
        return None
    hyo = by.get((part["bunsho"], part["oya"]))
    return hyo if hyo is not None and hyo["shu"] == sj.HYO else None


def kijutsu_no_midashi(part, th):
    """資料の中の場所の行 part が、テーマの資料の見出しで、shisetsu があるもの（再編整備計画 34ページの、施設の名前を
    見出しにした段落。SCHEMA.md 7.2）か。その見出しを指す数値は、テーマの表の「施設の表」の欄に出さない（docs/design.md 4節）。"""
    return (part.get("shu") == sj.MIDASHI and bool(part.get("shisetsu", "").strip())
            and th.has(part["bunsho"]))


def kikan(D, r):
    """過程の記録の from・to → 画面に出す時期（docs/design.md 3節）。"""
    a = bs.hi_str(D, r["from"])
    if not r["to"]:
        return D.bun("kikan-tochu", a=a)
    if r["to"] == r["from"]:
        return a
    return D.bun("kikan", a=a, z=bs.hi_str(D, r["to"]))


def jun_shisetsu(hyo, th, ref):
    """施設ごとの欄の順：施設の表（hyo。無ければ None）の行の順に、表にある施設を先に置き、残りは施設の参照表の順。"""
    out = []
    if hyo is not None:
        out += [k for ks in hyo.keys for k in ks]
    out += [k for k in ref if k in th.shisetsu]
    return [k for k in dict.fromkeys(out) if k in th.shisetsu]


# ---- 一部改正の前後（docs/design.md 4節のテーマのページの3） ----

class Kaisei:
    """資料どうしの関係の表で hyogen が「一部改正」の行ごとの、数値の組み合わせ（tools/suji.py の kaisei_tsui）。
    kara（改正後の資料の ID）→ (e の資料の ID, KaiseiTsui) の並び。shinai は、組み合わせなかった行の数の合計。"""

    def __init__(self, tables):
        by = {(r["bunsho"], r["n"]): r for r in tables["bubun"]}
        jun = {r["id"]: i for i, r in enumerate(tables["suji"])}
        self.bubun_by = by
        self.teigi = {r["id"]: r for r in tables["suji"]}
        self.by_kara = {}
        for kara, es in sj.kaisei_kankei(tables["kankei"]).items():
            self.by_kara[kara] = [(e, sj.kaisei_tsui(kara, e, tables["atai"], by, jun)) for e in es]
        self.shinai = sum(len(x.shinai) for v in self.by_kara.values() for _, x in v)
        self.hoka = sum(len(x.hoka) for v in self.by_kara.values() for _, x in v)

    def of(self, srcs):
        """過程の記録の sources の並び → その行に出す (e の資料の ID, KaiseiTsui) の並び。"""
        out = []
        for s in srcs:
            for x in self.by_kara.get(sj.bunsho_of(s) or "", []):
                if x not in out:
                    out.append(x)
        return out

    def suji_ids(self):
        """組み合わせの項目に出る項目の id の集まり。"""
        out = set()
        for v in self.by_kara.values():
            for _, x in v:
                out |= {a["suji"] for a, _, _ in x.chigau}
                out |= {r["suji"] for r, _ in x.kuwawaru + x.nai}
        return out

    def items(self, D, x, teigi_namae):
        """KaiseiTsui → 項目の文（HTML の断片）の並び。teigi_namae は項目の表の行 → 名前の HTML。
        組み合わせた2行の atai が違うもの、kara の資料にだけある数値、e の資料にだけある数値の順。"""
        D.kotoba("資料どうしの関係の表 kara、e の資料の、同じ項目の、改正前と改正後の組み合わせで、atai が違うもの")   # 見出しは呼ぶ側で出す
        D.dasanai("数値と内容の表 atai（一部改正の kara の資料にだけある数値）")            # 文は kaisei-kuwawaru
        D.dasanai("数値と内容の表 atai（一部改正の e の資料にだけある数値）")                # 文は kaisei-nai
        mae_w = E(D.kotoba("数値と内容の表 atai（一部改正の組み合わせの、e の資料の側）"))
        ato_w = E(D.kotoba("数値と内容の表 atai（一部改正の組み合わせの、kara の資料の側）"))

        def page(r):
            return E(D.bun("page", n=sj.page_no(r["shiryo"])))

        def gyo(r):
            part = self.bubun_by.get((sj.bunsho_of(r["shiryo"]), r["bubun"]))
            return bh.midashi_ji(D, part) if part else ""

        def name(r, jo):
            nm = teigi_namae(self.teigi[r["suji"]])
            return nm + (f"　{gyo(r)}" if jo == 2 and gyo(r) else "")

        out = []
        for a, b, jo in x.chigau:
            out.append(D.bun("kaisei-tsui", name=name(b, jo),
                             mae=D.bun("kaisei-atai", kaisei=mae_w, atai=S(a["atai"]), page=page(a)),
                             ato=D.bun("kaisei-atai", kaisei=ato_w, atai=S(b["atai"]), page=page(b))))
        for r, jo in x.kuwawaru:
            t = self.teigi[r["suji"]]
            out.append(D.bun("kaisei-kuwawaru", name=teigi_namae(t), jiki=S(r["jiten"]) if jo == 1 else gyo(r),
                             nakami=E(bs.atai_go(D, t)), page=page(r)))
        for r, jo in x.nai:
            t = self.teigi[r["suji"]]
            out.append(D.bun("kaisei-nai", name=teigi_namae(t), jiki=S(r["jiten"]) if jo == 1 else gyo(r),
                             nakami=E(bs.atai_go(D, t)), page=page(r)))
        return out


def suji_page_aru(inp, tables, ids, kotoba, today, D):
    """項目の id の集まり → 数値のページ（tools/build_suji.py）を作れる id の集まり。"""
    out = set()
    for sid in sorted(ids):
        try:
            bs.build(inp, tables, sid, kotoba, today, design=D)
        except Stop:
            continue
        out.add(sid)
    return out


def anchor(fa):
    """施設の ID → ページ内リンクの id。"""
    return fa.replace(":", "-")


# ---- 施設の表 ----

class ShisetsuHyo:
    """テーマの表の「施設の表」の行が指す表の、行（shisetsu がある行か列）と欄。"""

    def __init__(self, D, tables, trow, ref_by_key, kiroku, theme_shisetsu, th):
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
        # 施設の ID の組が同じ数値（項目ごと）
        self.suji = []            # 項目の表の行の並び（項目の表の順）
        self.atai = {}            # (項目の id, 施設の ID の組) → 数値と内容の表の行の並び
        kumi = set(self.keys)
        shitei = shitei_hyo(trow)
        for r in tables["atai"]:
            ks = sj.atai_shisetsu(r, self.bubun_by)
            b = sj.bunsho_of(r["shiryo"]) if r["shiryo"].strip() else None
            parts = [self.bubun_by.get((b, n)) for n in (r["bubun"], r["retsu"]) if b and n]
            if any(x is not None and kijutsu_no_hyo(x, self.bubun_by, th, shitei) is not None for x in parts):
                continue        # 施設ごとの欄にだけ出す（同じ内容を2か所に出さない）
            if any(x is not None and kijutsu_no_midashi(x, th) for x in parts):
                continue        # テーマの資料の見出しを指す数値（段落の文）は、施設の表の欄に出さない
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


# ---- 施設ごとの、資料の表の欄 ----

class HyoKijutsu:
    """施設の ID → 資料の表の行か列（kijutsu_no_hyo）と、その欄の並び。"""

    def __init__(self, tables, th, trow, ref_by_key):
        self.problems = []
        bub = tables["bubun"]
        by = {(r["bunsho"], r["n"]): r for r in bub}
        hiduke = {r["bunsho"]: r["hiduke"] for r in tables["bunsho"]}
        shitei = shitei_hyo(trow)
        self.gyo = {}                                   # 施設の ID → (部分, 表, 欄の並び) の並び
        for p in bub:
            hyo = kijutsu_no_hyo(p, by, th, shitei)
            if hyo is None:
                continue
            if sj.shisetsu_mikakunin(p, ref_by_key):
                self.problems.append(("(g) 施設の割り当て", f"{sj.BUBUN_NAME} の {p['_gyo']} 行目：施設の割り当てが"
                                                        f"未確認（{p['name']}）"))
            aite_shu = sj.RETSU if p["shu"] == sj.GYO else sj.GYO
            aite = sorted((x for x in bub if x["bunsho"] == p["bunsho"] and x["oya"] == p["oya"]
                           and x["shu"] == aite_shu),
                          key=lambda x: (int(x["jun"] or 0), int(x["n"])))
            ran = []
            for x in aite:
                g, c = (p["n"], x["n"]) if p["shu"] == sj.GYO else (x["n"], p["n"])
                ran += [(x, r) for r in tables["atai"]
                        if r["jotai"] == sj.ARU and r["bubun"] == g and r["retsu"] == c
                        and sj.bunsho_of(r["shiryo"]) == p["bunsho"]]
            for k in dict.fromkeys(sj.shisetsu_keys(p["shisetsu"])):
                self.gyo.setdefault(k, []).append((p, hyo, ran))
        for k in self.gyo:
            self.gyo[k].sort(key=lambda t: (hiduke.get(t[0]["bunsho"]) or "9999", t[0]["bunsho"], int(t[1]["n"]),
                                            int(t[0]["n"])))

    def kazu(self):
        return sum(len(v) for v in self.gyo.values())


# ---- ページ ----

STYLE = """body{font-family:sans-serif;line-height:1.7;max-width:60rem;margin:1.5rem auto;padding:0 1rem;color:#222}
h1{font-size:1.3rem} h2{font-size:1.1rem;border-top:2px solid #555;padding-top:.5rem;margin-top:1.8rem} h3{font-size:1rem;margin-top:1.4rem}
table{border-collapse:collapse;margin:.4rem 0 1rem;width:100%} th,td{border:1px solid #999;padding:.3rem .6rem;text-align:left;vertical-align:top}
th{background:#eee;font-weight:normal} td.r{text-align:right} .s{color:#555;font-size:.9rem} .q{margin:.3rem 0}
.setsumei{border-left:4px solid #999;padding:.2rem 1rem;margin:.8rem 0}"""


class Page:
    def __init__(self, D, inp, tables, theme, th, ref_by_key, kiroku, katei, namae, hyo, hk):
        self.D, self.inp, self.t, self.theme, self.th = D, inp, tables, theme, th
        self.ref, self.kiroku, self.katei, self.n, self.hyo = ref_by_key, kiroku, katei, namae, hyo
        self.hk = hk
        self.kaisei, self.suji_pages = None, set()

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
            rows.append(f"<tr><td>{E(kikan(D, r))}</td><td>{S(r['name'])}</td><td>「{S(r['quote'])}」</td>"
                        f"<td>{links}</td></tr>")
            rows += self.kaisei_gyo(srcs)
        return (f"<h2>{E(D.bun('midashi-keika'))}</h2>\n<p class=s>{E(D.bun('keika-setsumei'))}</p>\n"
                f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")

    def kaisei_gyo(self, srcs):
        """経過の行の下に足す行（一部改正の e の資料と、数値の組み合わせ。docs/design.md 4節）。ID は出さない。"""
        D, out = self.D, []
        if self.kaisei is None:
            return out

        def namae(t):
            if t["id"] in self.suji_pages:
                return f"<a href='../suji/{E(t['id'])}.html'>{E(t['name'])}</a>"
            return E(t["name"])
        for e, x in self.kaisei.of(srcs):
            url = keys.source_url(self.inp, f"{e}/1") if sj.RE_BUNSHO_PT.fullmatch(e) or sj.RE_BUNSHO_DOC.fullmatch(e) \
                else ""
            nm = self.n.bunsho(e)
            nm = f"<a href='{E(url)}'>{nm}</a>" if url else nm
            cell = [f"<p>{E(D.kotoba('資料どうしの関係の表 hyogen が「一部改正」の行の e'))}：{nm}</p>"]
            items = self.kaisei.items(D, x, namae)
            if items:
                cell.append(f"<p>{E(D.kotoba('資料どうしの関係の表 kara、e の資料の、同じ項目の、改正前と改正後の組み合わせで、atai が違うもの'))}"
                            f"<span class=s>{E(D.bun('kaisei-hani'))}</span></p>")
                cell.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            out.append(f"<tr><td></td><td colspan=3>{''.join(cell)}</td></tr>")
        return out

    def shisetsu_hyo(self):
        D, h = self.D, self.hyo
        if h is None:
            return ""
        D.dasanai("資料の中の場所の表 shisetsu")
        D.dasanai("資料の中の場所の表 matome")
        D.dasanai("項目の表 name")
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
                    jiten = r["jiten"] if r["nendo"] else ""   # nendo が空の数値は、時期の括弧を出さない（docs/design.md 4節）
                    moto.setdefault((sj.bunsho_of(r["shiryo"]) or r["shiryo"], jiten), set()).add(
                        sj.page_no(r["shiryo"]))
            for (b, jiten), pages in moto.items():
                pp = "、".join(str(p) for p in sorted(p for p in pages if p))
                shiryo = self.n.bunsho(b) + (f"　{E(D.bun('page', n=pp))}" if pp else "")
                if jiten:
                    setsumei.append(D.bun("theme-suji", name=E(t["name"]), shiryo=shiryo, jiten=S(jiten)))
                else:
                    setsumei.append(D.bun("theme-suji-jiki-nashi", name=E(t["name"]), shiryo=shiryo))
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
        D.dasanai("資料どうしの関係の表 hyogen")
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
        head = (f"<th>{E(D.kotoba('資料どうしの関係の表 kara、e'))}</th>"
                f"<th>{E(D.kotoba('資料どうしの関係の表 inyo'))}</th>")
        hb = bs.hiduke_bun(D, False, any(self.n.hiduke_nashi(k) for k in docs))
        return (f"<h2>{E(D.bun('midashi-shiryo'))}</h2>\n<p class=s>{E(D.bun('shiryo-setsumei'))}{E(hb)}</p>\n"
                f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")

    def jun_shisetsu(self):
        return jun_shisetsu(self.hyo, self.th, self.ref)

    def kijutsu(self):
        D = self.D
        head = (f"<th>{E(D.kotoba('施設の記録 source'))}</th><th>{E(D.kotoba('施設の記録 aspect'))}</th>"
                f"<th>{E(D.kotoba('施設の記録 kind'))}</th><th>{E(D.kotoba('施設の記録 value、target'))}</th>"
                f"<th>{E(D.kotoba('施設の記録 quote'))}</th>")
        maeno = D.kotoba("施設の参照表 aliases")
        srcs = [sj.bunsho_of(r["source"]) for r in self.kiroku if r["facility"] in self.th.shisetsu]
        hb = bs.hiduke_bun(D, any(self.n.nendo_dake(b) for b in srcs), any(self.n.hiduke_nashi(b) for b in srcs))
        o = [f"<h2>{E(D.bun('midashi-kijutsu'))}</h2>",
             f"<p class=s>{E(D.bun('kijutsu-setsumei'))}{E(hb)}{E(D.bun('kubun-setsumei'))}</p>"]
        for k in self.jun_shisetsu():
            ref = self.ref[k]
            o.append(f"<h3 id='{E(anchor(k))}'>{S(ref['name'])}</h3>")
            al = [a.strip() for a in ref["aliases"].split(";") if a.strip()]
            if al:
                o.append(f"<p class=s>{E(maeno)}：{S('、'.join(al))}</p>")
            rs = sorted((r for r in self.kiroku if r["facility"] == k), key=self.n.kiroku_jun)
            if rs:
                rows = []
                for r in rs:
                    v = S(r["value"]) + (f"（{S(r['target'])}）" if r["target"] else "")
                    rows.append(f"<tr><td>{self.n.link(r['source'], r['quote'])}</td><td>{E(r['aspect'])}</td>"
                                f"<td>{E(r['kind'])}</td><td>{v}</td><td>「{S(r['quote'])}」</td></tr>")
                o.append(f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows)
                         + "\n</tbody>\n</table>")
            o.append(self.hyo_kijutsu(k))
        return "\n".join(x for x in o if x)

    def hyo_kijutsu(self, k):
        """施設 k の、資料の表の行か列の欄（docs/design.md 4節の6）。行が無ければ、見出しも出さない。"""
        D = self.D
        gyo = self.hk.gyo.get(k) if self.hk else None
        if not gyo:
            return ""
        head = (f"<th>{E(D.kotoba('資料の一覧の表 namae、han、hiduke'))}</th>"
                f"<th>{E(D.kotoba('資料の中の場所の表 name（shu が「表」）'))}</th>"
                f"<th>{E(D.kotoba('資料の中の場所の表 name（shu が「行」か「列」）'))}</th>"
                f"<th>{E(D.kotoba('数値と内容の表 atai、retsu'))}</th>")
        rows, mi = [], False
        for p, hyo, ran in gyo:
            cells = "<br>".join(D.bun("hyo-kijutsu-ran", midashi=bh.midashi_ji(D, x), atai=S(r["atai"]))
                                for x, r in ran)
            mi = mi or any(sj.mikakunin(x) for x in [p, hyo] + [x for x, _ in ran])
            rows.append(f"<tr><td>{self.n.link(hyo['tokoro'])}</td><td>{bh.midashi_ji(D, hyo)}</td>"
                        f"<td>{bh.midashi_ji(D, p)}</td><td>{cells}</td></tr>")
        o = [f"<h4>{E(D.kotoba('資料の中の場所の表 shisetsu、oya'))}</h4>",
             f"<p class=s>{E(D.bun('hyo-kijutsu-setsumei'))}"
             f"{E(bs.hiduke_bun(D, False, any(self.n.hiduke_nashi(p['bunsho']) for p, _, _ in gyo)))}</p>",
             f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"]
        if mi:
            o.append(f"<p class=s>{E(D.bun('mikakunin-hyo'))}</p>")
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
        hyo = ShisetsuHyo(D, tables, trows[0], ref, kiroku, set(th.shisetsu), th)
        problems += hyo.problems
    hk = HyoKijutsu(tables, th, trows[0] if trows else None, ref)
    problems += hk.problems
    if problems:
        raise Stop(problems)
    by = {r["bunsho"]: r for r in tables["bunsho"]}
    namae = Namae(D, inp, by)
    pg = Page(D, inp, tables, theme, th, ref, kiroku, katei, namae, hyo, hk)
    pg.kaisei = Kaisei(tables)
    pg.suji_pages = suji_page_aru(inp, tables, pg.kaisei.suji_ids(), kotoba, today, D)
    page = pg.render(today)
    if namae.problems:
        raise Stop(list(dict.fromkeys(namae.problems)))
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop([("(b) 使わない言葉", m) for _, m in problems])
    page = page.replace(A, "").replace(B, "")
    return page, dict(katei=len(katei), kiroku=len(kiroku), shisetsu=len(th.shisetsu),
                      hyo=len(hyo.gyo) if hyo else 0, inyo=res.matched, ji=len(page), hyo_kijutsu=hk.kazu(),
                      setsumei=sum(1 for r in tables["theme"] if r["theme"] == theme and r["shu"] == sj.SETSUMEI_BUN),
                      kaisei_shinai=pg.kaisei.shinai, kaisei_hoka=pg.kaisei.hoka)


def main(argv=None, teigi_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not RE_THEME.fullmatch(argv[0]):
        print("使い方：python3 -B tools/build_theme.py <テーマの ID>", file=sys.stderr)
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
          f"施設 {info['shisetsu']}（記録 {info['kiroku']} 行）、照合した引用 {info['inyo']}、"
          f"施設ごとの欄に出した資料の表の行 {info['hyo_kijutsu']}")
    print(f"一部改正の前後の数値で、組み合わせなかった行 {info['kaisei_shinai']}"
          f"（ほかのページの行が組み合わされているので出さない行 {info['kaisei_hoka']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
