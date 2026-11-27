"""資料の中の場所の表の、表1つを1ページにする（SCHEMA.md §7.2・§7.3、docs/design.md 3節・4節）。

実行：python3 -B tools/build_hyo.py <資料の ID> <表の番号>
  （例 pt:youho/honpen 4 → build/hyo/pt_youho_honpen_4.html。ファイル名は、資料の ID の「:」と「/」を「_」にし、
  表の番号を付けたもの）
中身は teigi/ の4つの表と、lock の版の入力だけから作る。数値を計算しない。
行は、資料の中の場所の表で、表を親にする行。並べる順は、もとの資料から取り出した文字（text_raw）の表の範囲での、行の位置の順。
列は、表を親にする列。並べる順は jun の順。
欄の数値は、もとの資料から取り出した文字（text_raw）の表の範囲の、行の name に続く数値から、列の jun の順で取る（SCHEMA.md §7.3）。
数値と内容の表に、その欄を指す行があれば、取った数値と atai が一致することを確認する。
親の表か行の torikata が「読んだ」の表は、もとの資料から取り出した文字から数えられないので、数値と内容の表に行がある欄だけを出せる。
表の torikata が「読んだ」の表は、もとの資料から取り出した文字の表の範囲を使わない（表の題が行のあとに出るなど、範囲が決まらないため）。
行は、資料の中の場所の表の番号の順に並べる。
torikata が「読んだ」で、chu に確認の記録が無い表・行・列・見出しには、数値のページと同じ未確認の印を付け、表の下に定型文を出す
（判定は tools/suji.py の mikakunin）。
画面に出す言葉は、docs/design.md 3節の2つの表から読む（tools/build_suji.py の read_design と同じ読み方）。

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all）で問題がある
  (b) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文は除く）
  (c) 資料の ID と表の番号が、資料の一覧の表と資料の中の場所の表に無い。表に行か列が無い
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems。
      1つ目の表の「同じ項目の数値がある、ほかの資料」の画面の言葉と、2つ目の表の midashi-onaji の文が違う場合を含む）
  (f) 表の範囲が決まらない。行の name と数値の行が1行に決まらない。行の数値の数が、列の jun に足りない
  (g) 数値と内容の表の数値と、もとの資料から取り出した文字から取った数値が一致しない
  (h) torikata が「読んだ」の表で、数値と内容の表に行が無い欄がある（もとの資料から取り出した文字から取れない）
"""
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import shogo  # noqa: E402
import suji as sj  # noqa: E402

OUT_DIR = os.path.join(inputs.ROOT, "build", "hyo")
SRC_PATH = os.path.abspath(__file__)
A, B = bn.A, bn.B
E, S = bn.E, bn.S
Stop = bn.Stop
RE_BANGO = re.compile(r"[1-9][0-9]*")


def out_name(bkey, n):
    """資料の ID と表の番号 → 出力のファイル名。"""
    return re.sub(r"[:/]", "_", bkey) + f"_{n}.html"


def design_problems(D, src=None):
    """docs/design.md 3節の表と、このツールが合うか。→ 問題の並び。"""
    out = bs.design_problems(D, src, path=SRC_PATH)
    k = "同じ項目の数値がある、ほかの資料"
    if k in D.h1 and "midashi-onaji" in D.h2 and D.h1[k][0] != D.h2["midashi-onaji"]:
        out.append(f"1つ目の表の「{k}」の画面の言葉と、2つ目の表の midashi-onaji の文が違う")
    return out


# ---- 表の行と列、欄の数値 ----

class Hyo:
    """表1つの、行・列・欄の数値。problems に、止める理由（区分, 内容）をためる。"""

    def __init__(self, inp, tables, bkey, n):
        self.problems = []
        bub = [r for r in tables["bubun"] if r["bunsho"] == bkey]
        self.by_n = {r["n"]: r for r in bub}
        self.hyo = self.by_n.get(n)
        self.bunsho = next((r for r in tables["bunsho"] if r["bunsho"] == bkey), None)
        if self.bunsho is None:
            self.stop("(c) 資料と表", f"{bkey} が {sj.BUNSHO_NAME} に無い")
        if self.hyo is None or self.hyo["shu"] != sj.HYO:
            self.stop("(c) 資料と表", f"{bkey} の {n} が、{sj.BUBUN_NAME} の表でない")
            return
        self.gyo = [r for r in bub if r["oya"] == n and r["shu"] == sj.GYO]
        self.retsu = sorted((r for r in bub if r["oya"] == n and r["shu"] == sj.RETSU), key=lambda r: int(r["jun"]))
        if not self.gyo or not self.retsu:
            self.stop("(c) 資料と表", f"{bkey} の表 {n} に、行か列が無い（行 {len(self.gyo)}、列 {len(self.retsu)}）")
            return
        # 数値と内容の表で、この表の欄を指す行
        gn, rn = {g["n"] for g in self.gyo}, {c["n"] for c in self.retsu}
        self.atai = {}
        for r in tables["atai"]:
            if sj.bunsho_of(r["shiryo"]) == bkey and r["bubun"] in gn and r["retsu"] in rn:
                self.atai.setdefault((r["bubun"], r["retsu"]), []).append(r)
        lines = None
        if self.hyo["torikata"] != sj.YONDA:
            lines, why = sj.table_range(inp, tables["bubun"], self.hyo)
            if lines is None:
                self.stop("(f) 表の範囲", why)
                return
        self.cell, ichi = {}, {}
        self.n_moji = 0            # もとの資料から取り出した文字から取った欄の数
        for g in self.gyo:
            yonda = sj.YONDA in (self.hyo["torikata"], g["torikata"])
            ichi[g["n"]] = self.read_row(lines, g) if yonda else self.count_row(lines, g)
        if self.problems:
            return
        self.gyo.sort(key=lambda g: (ichi[g["n"]], int(g["n"])))

    def stop(self, kind, msg):
        self.problems.append((kind, msg))

    def count_row(self, lines, g):
        """torikata が「機械」の行：もとの資料から取り出した文字の行から、列の jun の順で数値を取る。→ 行の位置。"""
        hits = [i for i, ln in enumerate(lines) if sj.row_numbers(ln, g["name"]) is not None]
        if len(hits) != 1:
            self.stop("(f) 行", f"{sj.BUBUN_NAME} の {g['_gyo']} 行目：行の name と数値の行が、表の範囲に {len(hits)} 行ある"
                               f"（1行のはず：{g['name']}）")
            return None
        nums = sj.row_numbers(lines[hits[0]], g["name"])
        for c in self.retsu:
            j = int(c["jun"])
            if j > len(nums):
                self.stop("(f) 行", f"{sj.BUBUN_NAME} の {g['_gyo']} 行目：行の数値は {len(nums)} 個で、"
                                   f"列の jun（{j}）の数値が無い")
                continue
            v = nums[j - 1]
            for r in self.atai.get((g["n"], c["n"]), []):
                if shogo.norm(r["atai"]) != shogo.norm(v):
                    self.stop("(g) 数値の一致", f"{sj.ATAI_NAME} の {r['_gyo']} 行目：atai（{r['atai']}）が、"
                                            f"もとの資料から取り出した文字の行の {j} つ目（{v}）と違う")
            self.cell[(g["n"], c["n"])] = v
            self.n_moji += 1
        return hits[0]

    def read_row(self, lines, g):
        """torikata が「読んだ」の表か行：数値と内容の表の行だけを使う。→ 行の位置。

        lines が None（表の torikata が「読んだ」）なら、資料の中の場所の表の番号を、行の位置とする。
        """
        q = shogo.norm(g["name"])
        at = [int(g["n"])] if lines is None else [i for i, ln in enumerate(lines) if q and shogo.norm(ln).startswith(q)]
        if not at:
            self.stop("(f) 行", f"{sj.BUBUN_NAME} の {g['_gyo']} 行目：行の name が、表の範囲に無い（{g['name']}）")
        for c in self.retsu:
            rs = self.atai.get((g["n"], c["n"]), [])
            vals = {shogo.norm(r["atai"]) for r in rs}
            if not rs:
                self.stop("(h) 数値と内容の表に行が無い欄",
                          f"torikata が「読んだ」の表なので、もとの資料から取り出した文字から取れない（行 {g['name']}、列 {c['name']}）")
            elif len(vals) > 1:
                self.stop("(g) 数値の一致", f"同じ欄を指す数値と内容の表の行の atai が違う（行 {g['name']}、列 {c['name']}）")
            else:
                self.cell[(g["n"], c["n"])] = rs[0]["atai"]
        return at[0] if at else None

    def midashi(self):
        """表の親をたどった見出しの行の並び（上から）。"""
        out, oya = [], self.hyo["oya"]
        while oya:
            x = self.by_n[oya]
            out.insert(0, x)
            oya = x["oya"]
        return out


# ---- ページ ----

STYLE = """body{font-family:sans-serif;line-height:1.7;max-width:52rem;margin:1.5rem auto;padding:0 1rem;color:#222}
h1{font-size:1.3rem;margin-bottom:.2rem} h2{font-size:1.05rem;border-top:2px solid #555;padding-top:.5rem;margin-top:1.8rem}
table{border-collapse:collapse;margin:.6rem 0} th,td{border:1px solid #999;padding:.3rem .7rem;text-align:right}
th{background:#eee} th.g{text-align:left;white-space:nowrap} th.m{text-align:center}
.s{color:#555;font-size:.9rem} .q{margin:.3rem 0 .3rem 1rem}"""


def hiduke_ji(D, h):
    """資料の一覧の表の hiduke → 画面に出す日付。空なら、日付の記述が無いことを出す。"""
    return bs.hi_str(D, h) if sj.RE_HIDUKE.fullmatch(h or "") else D.kotoba("資料の一覧の表 hiduke が空")


def midashi_ji(D, r):
    """資料の中の場所の行 → 画面に出す見出し。torikata が「読んだ」で、chu に確認の記録が無い部分には、未確認の印を付ける。"""
    if sj.mikakunin(r):
        return S(r["name"]) + E(D.kotoba("資料の中の場所の表 torikata が「読んだ」で、chu に確認の記録が無い"))
    return S(r["name"])


def thead(D, retsu):
    """列の見出し。matome がある列は、見出しの上の行に、同じ matome が続く列をまとめて出す。"""
    D.dasanai("資料の中の場所の表 matome")
    if not any(c["matome"] for c in retsu):
        return "<tr><th class=g></th>" + "".join(f"<th>{midashi_ji(D, c)}</th>" for c in retsu) + "</tr>"
    ue, i = [], 0
    while i < len(retsu):
        m = retsu[i]["matome"]
        if not m:
            ue.append(f"<th rowspan=2>{midashi_ji(D, retsu[i])}</th>")
            i += 1
            continue
        k = i
        while k < len(retsu) and retsu[k]["matome"] == m:
            k += 1
        ue.append(f"<th class=m colspan={k - i}>{S(m)}</th>")
        i = k
    shita = "".join(f"<th>{midashi_ji(D, c)}</th>" for c in retsu if c["matome"])
    return f"<tr><th class=g rowspan=2></th>{''.join(ue)}</tr>\n<tr>{shita}</tr>"


def hoka_bunsho(tables, h, bkey):
    """この表の欄を指す項目について、数値と内容の表に行がある、ほかの資料。→ 資料の ID → ページの番号の集まり。"""
    sids = {r["suji"] for rs in h.atai.values() for r in rs}
    by = {r["bunsho"] for r in tables["bunsho"]}
    out = {}
    for r in tables["atai"]:
        k = sj.bunsho_of(r["shiryo"]) if r["shiryo"] else None
        if r["suji"] in sids and k and k != bkey and k in by:
            p = sj.page_no(r["shiryo"])
            out.setdefault(k, set()).update([p] if p else [])
    return out


def kakko_ji(D, b):
    """資料の一覧の表の行 → 資料の名前のあとの括弧の中。han があれば han と hiduke、無ければ hiduke だけ（docs/design.md 3節）。"""
    D.dasanai("資料の一覧の表 han")
    hi = hiduke_ji(D, b["hiduke"])
    return f"{S(b['han'])}、{E(hi)}" if b["han"] else E(hi)


def render(D, inp, tables, h, bkey, today):
    b, hyo = h.bunsho, h.hyo
    kakko = kakko_ji(D, b)
    page = D.bun("page", n=sj.page_no(hyo["tokoro"]))
    o = [f"<p class=s>{E(D.bun('atama-hyo'))}</p>",
         f"<h1>{midashi_ji(D, hyo)}</h1>",
         f"<p>{S(b['namae'])}（{kakko}）　{E(page)}</p>"]
    mi = h.midashi()
    if mi:
        o.append("<p class=s>" + "　".join(midashi_ji(D, x) for x in mi) + "</p>")
    rows = []
    for g in h.gyo:
        tds = "".join(f"<td>{S(h.cell[(g['n'], c['n'])])}</td>" for c in h.retsu)
        rows.append(f"<tr><th class=g>{midashi_ji(D, g)}</th>{tds}</tr>")
    o.append(f"<table>\n<thead>{thead(D, h.retsu)}</thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>")
    if any(sj.mikakunin(x) for x in [hyo] + mi + h.gyo + h.retsu):
        o.append(f"<p class=s>{E(D.bun('mikakunin-hyo'))}</p>")
    url = keys.source_url(inp, hyo["tokoro"])
    o.append(f"<p><a href='{E(url)}'>{E(D.bun('link'))}</a></p>" if url else f"<p>{E(D.bun('link-nashi'))}</p>")
    if b["konkyo"]:
        kp = D.bun("page", n=sj.page_no(b["konkyo_tokoro"]))
        o.append(f"<h2>{E(D.kotoba('資料の一覧の表 konkyo'))}</h2><p class=q>「{S(b['konkyo'])}」（{E(kp)}）</p>")
    hoka = hoka_bunsho(tables, h, bkey)
    if hoka:
        by = {r["bunsho"]: r for r in tables["bunsho"]}
        D.kotoba("同じ項目の数値がある、ほかの資料")        # 見出しの文は midashi-onaji（design_problems で同じことを確認する）
        li = []
        for k in sorted(hoka, key=lambda k: (by[k]["hiduke"] or "9999", k)):
            pp = "、".join(str(p) for p in sorted(hoka[k]))
            li.append(f"<li>{S(by[k]['namae'])}（{kakko_ji(D, by[k])}）"
                      + (f"　{E(D.bun('page', n=pp))}" if pp else "") + "</li>")
        nashi = any(not sj.RE_HIDUKE.fullmatch(by[k]["hiduke"] or "") for k in hoka)
        hb = f"<p class=s>{E(bs.hiduke_bun(D, False, True))}</p>\n" if nashi else ""
        o.append(f"<h2>{E(D.bun('midashi-onaji'))}</h2>\n{hb}<ul>\n" + "\n".join(li) + "\n</ul>")
    o.append(f"<h2>{E(D.bun('midashi-owari'))}</h2><p class=s>{E(D.bun('owari-hyo'))}"
             f"{E(D.bun('sakusei-bi', hi=bs.hi_str(D, today.isoformat())))}</p>")
    body = "\n".join(o)
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{D.bun('dai', name=S(hyo['name']))}</title>
<style>
{STYLE}
</style></head><body>
{body}
</body></html>
"""


def build(inp, tables, bkey, n, kotoba, today, read_problems=(), design=None):
    """検査を通ればページ（印を消した HTML）と件数を返す。当たれば Stop。

    tables は {"suji", "atai", "bunsho", "bubun"} → 行の並び（tools/build_suji.py の read_tables で読んだもの）。
    """
    D = design or bs.read_design()
    problems = [("(e) デザインシステムとの対応", m) for m in design_problems(D)]
    if problems:
        raise Stop(problems)
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in read_problems]
    mondai, _, _ = sj.check_all(inp, tables["suji"], tables["atai"], tables["bunsho"], tables["bubun"])
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in mondai]
    if problems:
        raise Stop(problems)
    h = Hyo(inp, tables, bkey, n)
    if h.problems:
        raise Stop(h.problems)
    page = render(D, inp, tables, h, bkey, today)
    problems = bn.kotoba_problems(page, *kotoba)
    if problems:
        raise Stop([("(b) 使わない言葉", m) for _, m in problems])
    page = page.replace(A, "").replace(B, "")
    return page, dict(gyo=len(h.gyo), retsu=len(h.retsu), ran=len(h.cell), moji=h.n_moji,
                      atai=sum(1 for k in h.cell if k in h.atai), ji=len(page))


def main(argv=None, teigi_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or not RE_BANGO.fullmatch(argv[1]):
        print("使い方：python3 -B tools/build_hyo.py <資料の ID> <表の番号>", file=sys.stderr)
        return 2
    bkey, n = argv
    try:
        inp = inputs.Inputs()                                   # (d) lock と入力
        tables, read_problems = bs.read_tables(teigi_dir)
        page, info = build(inp, tables, bkey, n, bn.read_kotoba(), datetime.date.today(), read_problems,
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
    out = os.path.join(OUT_DIR, out_name(bkey, n))
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{os.path.relpath(out, inputs.ROOT)}（{os.path.getsize(out)} バイト、{info['ji']} 文字）")
    print(f"行 {info['gyo']}、列 {info['retsu']}、欄 {info['ran']}（もとの資料から取り出した文字から取った欄 {info['moji']}、"
          f"うち数値と内容の表に行がある欄 {info['atai']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
