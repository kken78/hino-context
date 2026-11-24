"""数値の表から、定義1つのページを作る（SCHEMA.md §6・§7、docs/design.md 3節・4節）。

実行：python3 -B tools/build_suji.py <定義の id>   （例 taiki → build/suji/taiki.html）
中身は teigi/suji.tsv・atai.tsv・bunsho.tsv・bubun.tsv と、lock の版の入力だけから作る。hino-ronten の記録は使わない。
列は、tools/suji.py の jiten_kankei が返す印（ato・mae・tochu）で分ける。単語で数値の意味や種類を決めない。数値を計算しない。
画面に出す言葉は、すべて docs/design.md の3節の2つの表から読む。このファイルには、画面の言葉を書かない
（HTML のタグとスタイル、記号は除く）。表の行は、左の列の字を鍵として、次の4つの呼び出しで引く。
  D.kotoba(鍵)          1つ目の表（データの構造との対応）の、画面の言葉
  D.retsu_setsumei(鍵)  1つ目の表の、出し方の列にある列の説明「」の中の字
  D.dasanai(鍵)         1つ目の表の、画面に出さないと決めた行（何も返さない）
  D.bun(鍵, 名前=字)     2つ目の表（見出しと決まった文）の文。{名前} に字を入れる

作る前の検査（1つでも当たれば、件数と該当行を示して、ページを作らずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all。inyo の照合、文書の部分の検査を含む）で問題がある
  (b) 画面に出る文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文は除く。tools/build_note.py の印と検査）
  (c) 定義の id が定義の表に無い
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（design_problems。次の6つ）
      - データの側が返す印（suji.KANKEI）に、1つ目の表の行が無い
      - 1つ目の表の左の列が、SCHEMA.md にある列（suji.py の列の並び）か印でない
      - このツールが引く鍵が表に無い。表にあって、ページを作るツール（PAGE_TOOLS）のどれも引かない行がある
      - D.bun に渡す名前と、文の中の {名前} が合わない
      - このツールの中に、表の画面の言葉と文（4字以上のもの）が書かれている（1つ目の表の左の列の字は鍵として除く）
      - 呼び出しの鍵が、字のままでない（検査できない）
"""
import ast
import datetime
import os
import re
import string
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_note as bn  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import suji as sj  # noqa: E402

OUT_DIR = os.path.join(inputs.ROOT, "build", "suji")
DESIGN_PATH = os.path.join(inputs.ROOT, "docs", "design.md")
SRC_PATH = os.path.abspath(__file__)
A, B = bn.A, bn.B
E, S = bn.E, bn.S
Stop = bn.Stop

# ---- docs/design.md 3節を読む ----

SETSU3 = "## 3. "
HEAD1 = "| データの側 | 画面の言葉 | 出し方 |"
HEAD2 = "| 鍵 | 文 |"
RE_KAGI2 = re.compile(r"[a-z]+(?:-[a-z]+)*")
RE_SETSUMEI = re.compile(r"列の説明「([^」]*)」")
RE_DASANAI = re.compile(r"（[^（）]*出さない）")           # 画面に出さないと決めた行の、画面の言葉の形
RE_KAGIKAKKO = re.compile(r"「([^」]*)」")
CALLS1 = ("kotoba", "retsu_setsumei", "dasanai")             # 1つ目の表を引く呼び出し
CALLS2 = ("bun",)                                            # 2つ目の表を引く呼び出し
NAGASA = 4                                                   # このツールの中に書かれていないことを確認する、字の長さの下限

# 1つ目の表の左の列の形（SCHEMA.md の表の名前 → 列の並び）。テーマの定義・施設の参照表・施設の記録・過程の記録は、
# hino-ronten の入力の表（SCHEMA.md §1）
KATEI_COLUMNS = ["theme", "step", "cycle", "name", "from", "to", "sources", "quote", "status", "reviewer", "date", "note"]
THEMES_COLUMNS = ["theme", "kind", "value", "source", "views", "reviewer", "date", "note"]
HYO_COLUMNS = (("定義の表", sj.SUJI_COLUMNS), ("数値の表", sj.ATAI_COLUMNS),
               ("文書の部分の表", sj.BUBUN_COLUMNS), ("文書の表", sj.BUNSHO_COLUMNS),
               ("文書どうしの関係の表", sj.BUNSHO_KANKEI_COLUMNS), ("テーマの表", sj.THEME_COLUMNS),
               ("テーマの定義", THEMES_COLUMNS), ("施設の参照表", inputs.SHISETSU_COLUMNS),
               ("施設の記録", inputs.SHISETSU_KIROKU_COLUMNS), ("過程の記録", KATEI_COLUMNS))
# 表の名前と、そのあとの列（「、」で区切って2つ以上書ける）。長い名前から当てる（「文書の部分の表」を「文書の表」より先に）
RE_HYO_RETSU = re.compile("(" + "|".join(sorted((re.escape(h) for h, _ in HYO_COLUMNS), key=len, reverse=True))
                          + r") ([a-z_]+(?:、[a-z_]+)*)")
RE_KANKEI = re.compile(r"時点の関係 (\S+)")
KANKEI_NASHI = "無し"
# 上の形に当てはまらない左の列（決めた形の一覧）→ その字が指す、表の列の組（表の名前, 列）の並び。
# 会議録の発言者の役職は、入力の会議録の索引の role で、SCHEMA.md の表の列ではないので、組を持たない
KATACHI = {"shiryo が発言": (("数値の表", "shiryo"),),
           "shiryo が計画・町の資料": (("数値の表", "shiryo"),),
           "文書の部分（bubun・retsu から親をたどった並び）": (("数値の表", "bubun"), ("数値の表", "retsu")),
           "bubun が空": (("数値の表", "bubun"),),
           "同じ定義の数値がある、ほかの文書": (("数値の表", "suji"), ("数値の表", "shiryo")),
           "会議録の発言者の役職が「数字＋番」": (),
           "会議録の発言者の役職が、議長でも「数字＋番」でもない": ()}
# docs/design.md 3節の表を引く、ページを作るツール。表の行は、このどれかが引いていればよい
PAGE_TOOLS = ("build_suji.py", "build_hyo.py", "build_theme.py")


class Design:
    """docs/design.md 3節の2つの表。h1：鍵 → (画面の言葉, 出し方)。h2：鍵 → 文。"""

    def __init__(self, h1, h2):
        self.h1, self.h2 = h1, h2

    def kotoba(self, key):
        return self.h1[key][0]

    def retsu_setsumei(self, key):
        return RE_SETSUMEI.search(self.h1[key][1]).group(1)

    def dasanai(self, key):
        """画面に出さないと決めた行。引いたことを示すだけで、何も返さない。"""
        return None

    def bun(self, key, **kw):
        return self.h2[key].format(**kw)


def _table(lines, head, ncol, path):
    try:
        i = lines.index(head)
    except ValueError:
        raise inputs.InputError(f"{path}：3節に表の見出しの行（{head}）が無い")
    out = {}
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != ncol or not all(cells[:2]):
            raise inputs.InputError(f"{path}：表の行の形が違う（{line}）")
        if cells[0] in out:
            raise inputs.InputError(f"{path}：表の左の列が重なっている（{cells[0]}）")
        out[cells[0]] = tuple(cells[1:]) if ncol > 2 else cells[1]
    if not out:
        raise inputs.InputError(f"{path}：表に行が無い（{head}）")
    return out


def read_design(path=DESIGN_PATH):
    """docs/design.md 3節の2つの表を読む。→ Design。読めなければ inputs.InputError。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    s = next((i for i, x in enumerate(lines) if x.startswith(SETSU3)), None)
    if s is None:
        raise inputs.InputError(f"{path}：3節の見出しが無い")
    e = next((j for j in range(s + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    lines = lines[s:e]
    return Design(_table(lines, HEAD1, 3, path), _table(lines, HEAD2, 2, path))


def _names(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}


def _fragments(text):
    return re.split(r"\{[^{}]*\}", text)


def hidari_problems(key):
    """1つ目の表の左の列が、SCHEMA.md にある列か印であるか。→ 問題の並び。"""
    out = []
    m = RE_KANKEI.fullmatch(key)
    if m:
        if m.group(1) not in sj.KANKEI and m.group(1) != KANKEI_NASHI:
            out.append(f"「{key}」：印が suji.KANKEI に無い")
        return out
    refs = [(h, c) for h, cs in RE_HYO_RETSU.findall(key) for c in cs.split("、")]
    if any(key.startswith(h + " ") for h, _ in HYO_COLUMNS):
        pass
    elif key in KATACHI:
        refs += list(KATACHI[key])
    else:
        out.append(f"「{key}」：決めた形（表の名前と列、時点の関係と印、決めた形の一覧）のどれでもない")
    cols = dict(HYO_COLUMNS)
    for h, c in refs:
        if c not in cols[h]:
            out.append(f"「{key}」：{c} が{h}の列に無い")
    return out


def scan_calls(src):
    """このツールの文 → (1つ目の表の鍵の集まり, 2つ目の表の鍵 → 渡す名前の集まりの並び, 字のままでない呼び出しの行)。"""
    k1, k2, bad = set(), {}, []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in CALLS1 + CALLS2):
            continue
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            bad.append(node.lineno)
            continue
        k = node.args[0].value
        if node.func.attr in CALLS1:
            k1.add(k)
        else:
            k2.setdefault(k, []).append({x.arg for x in node.keywords})
    return k1, k2, bad


def tool_sources(path):
    """PAGE_TOOLS のうち、path でないツールの文の並び。ファイルが無いツールは除く。"""
    out = []
    for name in PAGE_TOOLS:
        p = os.path.join(HERE, name)
        if os.path.abspath(p) != os.path.abspath(path) and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out.append(f.read())
    return out


def design_problems(d, src=None, path=SRC_PATH, others=None):
    """docs/design.md 3節の表と、ツール（path。src はその文）が合うか。→ 問題の並び。

    表にあって引いていない行は、ページを作るツール（PAGE_TOOLS）のどれも引いていない行だけを出す。
    others は、ほかのツールの文の並び。None なら PAGE_TOOLS のファイルを読む。
    """
    if src is None:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    if others is None:
        others = tool_sources(path)
    out = []
    for k in sj.KANKEI:
        if f"時点の関係 {k}" not in d.h1:
            out.append(f"データの側が返す印 {k} に、1つ目の表の行が無い")
    for key in d.h1:
        out += hidari_problems(key)
    k1, k2, bad = scan_calls(src)
    all1, all2 = set(k1), set(k2)
    for o in others:
        o1, o2, _ = scan_calls(o)
        all1 |= o1
        all2 |= set(o2)
    out += [f"このツールの {n} 行目：鍵が字のままでない" for n in bad]
    out += [f"このツールが引く鍵「{k}」が、1つ目の表に無い" for k in sorted(k1 - set(d.h1))]
    out += [f"1つ目の表の行「{k}」を、ページを作るツールのどれも引いていない" for k in d.h1 if k not in all1]
    out += [f"このツールが引く鍵「{k}」が、2つ目の表に無い" for k in sorted(set(k2) - set(d.h2))]
    out += [f"2つ目の表の行「{k}」を、ページを作るツールのどれも引いていない" for k in d.h2 if k not in all2]
    for k, uses in k2.items():
        if k in d.h2:
            want = _names(d.h2[k])
            out += [f"2つ目の表の行「{k}」：文の中の名前 {sorted(want)} と、渡す名前 {sorted(u)} が合わない"
                    for u in uses if u != want]
    words = []
    for k, (w, how) in d.h1.items():
        if RE_DASANAI.fullmatch(w):
            continue
        if _names(w):
            out.append(f"1つ目の表の行「{k}」：画面の言葉に {{}} がある")
        words += [w] + RE_KAGIKAKKO.findall(w) + RE_SETSUMEI.findall(how)
    for k, t in d.h2.items():
        words += _fragments(t) + RE_KAGIKAKKO.findall(t)
    # 1つ目の表の左の列（データの側の名前）は鍵なので、ツールに書いてよい。鍵の字を除いてから探す
    rest = src
    for k in sorted(d.h1, key=len, reverse=True):
        rest = rest.replace(k, "")
    for w in sorted({w for w in words if len(w) >= NAGASA}):
        if w in rest:
            out.append(f"このツールの中に、表の字「{w}」が書かれている")
    return out


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

# 印が無い行の理由（suji.jiten_kankei が None を返す場合。SCHEMA.md §7.3）。並べる順
RIYU = ("nendo", "hiduke", "shiryo")
# 列の順（docs/design.md 4節）
KANKEI = (sj.KANKEI_ATO, sj.KANKEI_TOCHU, sj.KANKEI_MAE)


def riyu_of(r):
    """印が無い行の理由。jiten_kankei と同じ順で見る。"""
    if not r["nendo"].strip():
        return "nendo"
    if not r["shiryo"].strip():
        return "shiryo"
    return "hiduke"


def hi_str(D, h):
    """YYYY-MM か YYYY-MM-DD → 画面の字（2つ目の表の書式）。"""
    p = [int(x) for x in h.split("-")]
    if len(p) == 2:
        return D.bun("nengetsu", nen=p[0], tsuki=p[1])
    return D.bun("nengappi", nen=p[0], tsuki=p[1], hi=p[2])


def toki_of(D, r, teigi):
    """行の jiten と nendo → (並べる順の鍵, 表に出す字)。印がある行（nendo がある行）に使う。"""
    m = sj.RE_NENGETSU.fullmatch(r["jiten"].strip())
    if m:
        y, mo = sj.GENGO[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2))), int(m.group(3))
        return (y, mo, 0), D.bun("nengetsu", nen=y, tsuki=mo)
    nendo = int(r["nendo"])
    t = teigi.get("nendo_tsuki", "")
    if t in sj.NENDO_TSUKI:
        t = int(t)
        y = nendo if t >= 4 else nendo + 1
        return (y, t, 0), D.bun("nengetsu", nen=y, tsuki=t)
    return (nendo, 4, 1), D.bun("nendo", nendo=nendo)


def hiduke_of(D, shiryo, by):
    """shiryo → (並べる順の鍵, 表に出す字)。発言は発言の日、ほかは文書の表の hiduke。無ければ None。"""
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
    return tuple(int(x) for x in h.split("-")) + (0,) * (3 - len(h.split("-"))), hi_str(D, h)


def para_range(bubun):
    """段落の鍵 → (始め, 終わり)。"""
    _, g = keys.parse(bubun)
    return int(g[1]), int(g[2] or g[1])


def ichi_of(D, r, index):
    """bubun・retsu から親をたどった並び → (HTML, 未確認の印を付けた部分があるか)。bubun が空なら ("", False)。
    印は、torikata が「読んだ」で、chu に確認の記録が無い部分に付ける（判定は tools/suji.py の mikakunin）。"""
    if not r["bubun"]:
        return "", False
    if r["shiryo"].startswith("sp:"):
        a, z = para_range(r["bubun"])
        return (D.bun("danraku", n=a) if a == z else D.bun("danraku-hani", a=a, z=z)), False
    b = sj.bunsho_of(r["shiryo"])
    chain, n = [], r["bubun"]
    while n:
        x = index[(b, n)]
        chain.append(x)
        n = x["oya"]
    chain.reverse()
    if r["retsu"]:
        chain.append(index[(b, r["retsu"])])
    D.dasanai("文書の部分の表 shu が「見出し」")
    head = {sj.MIDASHI: "",
            sj.HYO: D.kotoba("文書の部分の表 shu が「表」"),
            sj.GYO: D.kotoba("文書の部分の表 shu が「行」"),
            sj.RETSU: D.kotoba("文書の部分の表 shu が「列」")}
    yonda = D.kotoba("文書の部分の表 torikata が「読んだ」で、chu に確認の記録が無い")
    D.dasanai("文書の表 chu、文書の部分の表 chu")
    parts = [f"{E(head[x['shu']])}「{S(x['name'])}」" + (E(yonda) if sj.mikakunin(x) else "")
             for x in chain]
    return " ＞ ".join(parts), any(sj.mikakunin(x) for x in chain)


class Entry:
    """数値の表の1行と、ページに出す中身。"""

    def __init__(self, D, r, teigi, inp, by, index):
        self.D = D
        self.r, self.gyo, self.id = r, r["_gyo"], f"g{r['_gyo']}"
        self.kankei = sj.jiten_kankei(r, teigi, by)
        self.riyu = None if self.kankei else riyu_of(r)
        self.toki = toki_of(D, r, teigi) if self.kankei else None
        self.label = self.toki[1] if self.toki else r["jiten"]
        sh = r["shiryo"].strip()
        self.sp = sh.startswith("sp:")
        self.hiduke = hiduke_of(D, sh, by) if sh else None
        self.namae = self.page = self.url = self.konkyo = ""
        self.ichi, self.mikakunin = ichi_of(D, r, index) if sh else ("", False)
        if not sh:
            return
        kind, g = keys.parse(sh)
        if self.sp:
            d = keys.sid_date(g[0])
            sp_name = inp.speaker(g[0])
            self.namae = D.bun("kaigiroku", hi=hi_str(D, d), hito=S(sp_name)) if d and sp_name else ""
        else:
            row = by.get(sj.bunsho_of(sh))
            if row and row["namae"]:
                self.namae = S(row["namae"])
            else:
                n = keys.source_name(inp, sh)
                self.namae = S(n) if n else ""
            if kind in ("pt", "doc"):
                self.page = D.bun("page", n=g[-1])
            if row and row["konkyo"]:
                self.konkyo = f"「{S(row['konkyo'])}」（{D.bun('page', n=sj.page_no(row['konkyo_tokoro']))}）"
        para = para_range(r["bubun"])[0] if self.sp and r["bubun"] else None
        self.url = keys.source_url(inp, sh, para)

    @property
    def atai(self):
        """atai の字（資料の字。印で囲む）。atai が空の行は jotai の字。"""
        return S(self.r["atai"]) if self.r["atai"] else E(self.r["jotai"])

    @property
    def hiduke_ji(self):
        return self.hiduke[1] if self.hiduke else E(self.D.kotoba("文書の表 hiduke が空"))

    def chip(self):
        D = self.D
        ji = (f"<span class=ji>{E(D.kotoba('数値の表 shurui'))}：{S(self.r['shurui'])}</span>"
              if self.r["shurui"] else "")
        if self.r["shiryo"].strip():
            moto = f"<span class=moto>{self.namae}（{self.hiduke_ji}）</span>"
        else:
            moto = f"<span class=moto>{E(self.r['jotai'])}</span>" if self.r["atai"] else ""
        kubun = f"<span class=moto>{E(self.r['kubun'])}</span>" if self.r["kubun"] and not self.toki else ""
        return f"<div class=chip><a href='#{self.id}'><b>{self.atai}</b></a>{ji}{moto}{kubun}</div>"


# ---- ページ ----

STYLE = """body{font-family:sans-serif;line-height:1.7;max-width:60rem;margin:1.5rem auto;padding:0 1rem;color:#222}
h1{font-size:1.4rem} h2{font-size:1.15rem;border-bottom:1px solid #999;margin-top:2rem} h3{font-size:1rem;margin:1rem 0 .3rem}
table{border-collapse:collapse;width:100%} th,td{border:1px solid #bbb;padding:.4rem .6rem;vertical-align:top;text-align:left}
thead th{background:#f0f0f0} tbody th{white-space:nowrap;width:6.5rem} .setsumei{display:block;font-weight:normal;font-size:.8rem}
.chip{margin:.15rem 0} .chip b{font-size:1.1rem} .ji{margin-left:.5rem;border:1px solid #777;padding:0 .3rem;font-size:.8rem}
.moto{margin-left:.5rem;font-size:.85rem;color:#555} .chigau{margin-top:.3rem;font-size:.85rem;border-left:3px solid #555;padding-left:.5rem}
.nai{font-size:.85rem;color:#555} .note{background:#f6f6f6;padding:.6rem .9rem;font-size:.9rem}
section{border:1px solid #ccc;padding:.6rem .9rem;margin:.6rem 0} section h3{margin:0 0 .3rem}
dl{display:grid;grid-template-columns:11rem 1fr;gap:.1rem .8rem;margin:0}
dt{color:#555;font-size:.85rem} dd{margin:0}
@media (max-width:40rem){dl{grid-template-columns:1fr}}"""


class Page:
    def __init__(self, D, teigi, entries, index=None):
        self.D, self.t, self.es = D, teigi, entries
        self.index = index or {}            # (文書の鍵, 番号) → 文書の部分の行。施設の判定に使う
        self.chigau = 0
        D.dasanai("時点の関係 無し")                          # 印が無い行は、表の列に入れない
        self.kotoba = {sj.KANKEI_ATO: D.kotoba("時点の関係 ato"),
                       sj.KANKEI_MAE: D.kotoba("時点の関係 mae"),
                       sj.KANKEI_TOCHU: D.kotoba("時点の関係 tochu")}
        self.setsumei = {sj.KANKEI_ATO: D.retsu_setsumei("時点の関係 ato"),
                         sj.KANKEI_MAE: D.retsu_setsumei("時点の関係 mae")}
        self.riyu = {"nendo": D.kotoba("数値の表 nendo が空"),
                     "hiduke": D.kotoba("文書の表 hiduke が空"),
                     "shiryo": D.kotoba("数値の表 shiryo が空")}

    def head(self):
        D, t = self.D, self.t
        an = E(D.kotoba("定義の表 kettei が「案」")) + "。" if t["kettei"] == "案" else ""
        items = [(D.kotoba("定義の表 nani"), t["nani"])]
        if t["tani"]:
            items.append((D.kotoba("定義の表 tani"), t["tani"]))
        items += [(D.kotoba("定義の表 toki"), t["toki"]), (D.kotoba("定義の表 iikata"), t["iikata"]),
                  (D.kotoba("定義の表 chui"), t["chui"])]
        dl = "".join(f"<dt>{E(k)}</dt><dd>{E(v)}</dd>" for k, v in items)
        return (f"<h1>{D.bun('dai', name=E(t['name']))}</h1>\n"
                f"<p class=note>{E(D.bun('atama'))}{an}</p>\n<h2>{E(D.bun('midashi-teigi'))}</h2>\n<dl>{dl}</dl>\n")

    def cell_mae(self, es):
        """mae の列の中身。数値が一致しなければ（判定は tools/suji.py の ichi_shinai。施設が違う数値は比較しない）、
        一致していないことを書く。"""
        h = "".join(e.chip() for e in es)
        if sj.ichi_shinai([e.r for e in es], self.index):
            self.chigau += 1
            h += f"<div class=chigau>{E(self.D.bun('chigau'))}</div>"
        return h

    def th(self, k):
        s = self.setsumei.get(k)
        return f"<th>{E(self.kotoba[k])}" + (f"<span class=setsumei>{E(s)}</span>" if s else "") + "</th>"

    def nen(self):
        """印がある行の表（kubun ごとに分ける）。"""
        D = self.D
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
            head = "".join(self.th(k) for k in cols)
            out.append((f"<h3>{E(D.kotoba('数値の表 kubun'))}：{E(kb)}</h3>" if kb else "")
                       + f"<table>\n<thead><tr><th>{E(D.bun('hyo-jiki'))}</th>{head}</tr></thead>\n"
                       f"<tbody>{''.join(rows)}</tbody>\n</table>")
        t = self.t["nendo_tsuki"]
        if t in sj.NENDO_TSUKI:
            nendo = D.bun("nendo-tsuki", tsuki=int(t))
        elif any(not sj.RE_NENGETSU.fullmatch(e.r["jiten"].strip()) for e in kes):
            nendo = D.bun("nendo-kikan")
        else:
            nendo = ""
        setsumei = (f"<p>{E(D.bun('retsu-setsumei'))}{E(nendo)}{E(D.bun('yobikata-setsumei'))}"
                    f"{E(D.bun('erabu'))}</p>")
        body = "\n".join(out)
        chigau = f"<p class=note>{E(D.bun('chigau-setsumei'))}</p>" if self.chigau else ""
        return f"<h2>{E(D.bun('midashi-hyo'))}</h2>\n{setsumei}\n{body}\n{chigau}\n{self.nai()}"

    def nai(self):
        """印が無い数値を、理由ごとに並べる。"""
        D = self.D
        es = [e for e in self.es if not e.kankei]
        if not es:
            return ""
        out = [f"<h3>{E(D.bun('midashi-nai'))}</h3>", f"<p>{E(D.bun('nai-setsumei'))}</p>"]
        hani, kakunin = D.kotoba("数値の表 hani"), D.kotoba("数値の表 kakunin")
        for riyu in RIYU:
            xs = [e for e in es if e.riyu == riyu]
            if not xs:
                continue
            li = "".join(f"<li>{E(e.label)}{'（' + E(e.r['kubun']) + '）' if e.r['kubun'] else ''}：{e.chip()}"
                         + (f"<div class=nai>{E(hani)}：{E(e.r['hani'])}"
                            + (f"　{E(kakunin)}：{hi_str(D, e.r['kakunin'])}" if e.r["kakunin"] else "")
                            + "</div>" if e.r["jotai"] != sj.ARU and e.r["hani"] else "")
                         + "</li>" for e in xs)
            out.append(f"<p>{E(D.bun('kensu', riyu=self.riyu[riyu], n=len(xs)))}</p><ul>{li}</ul>")
        return "\n".join(out)

    def hiduke_jun(self):
        """どの行にも印が無い定義：hiduke の古い順に並べた表。hiduke の無い行は終わりに置く（docs/design.md 4節）。"""
        D = self.D
        es = sorted(self.es, key=lambda e: (e.hiduke is None, e.hiduke[0] if e.hiduke else (), e.gyo))
        shurui = any(e.r["shurui"] for e in es)
        rows = "".join(
            f"<tr><td>{e.hiduke_ji}</td>"
            f"<td><a href='#{e.id}'><b>{e.atai}</b></a></td>"
            + (f"<td>{S(e.r['shurui']) if e.r['shurui'] else ''}</td>" if shurui else "")
            + f"<td>{e.namae}{'　' + e.page if e.page else ''}</td></tr>" for e in es)
        heads = [D.kotoba("文書の表 hiduke、発言の日"), D.kotoba("数値の表 atai")]
        heads += [D.kotoba("数値の表 shurui")] if shurui else []
        heads += [D.kotoba("文書の表 namae と、shiryo のページ")]
        return (f"<h2>{E(D.bun('midashi-hiduke'))}</h2>\n"
                f"<p>{E(D.bun('hiduke-setsumei'))}{E(D.bun('erabu'))}</p>\n"
                f"<table>\n<thead><tr>{''.join(f'<th>{E(h)}</th>' for h in heads)}</tr></thead>\n"
                f"<tbody>{rows}</tbody>\n</table>")

    def detail(self, e):
        D, r = self.D, e.r
        items = [(D.kotoba("数値の表 jiten"), E(r["jiten"]))]
        if r["kubun"]:
            items.append((D.kotoba("数値の表 kubun"), E(r["kubun"])))
        if r["shiryo"].strip():
            kubun = D.kotoba("shiryo が発言") if e.sp else D.kotoba("shiryo が計画・町の資料")
            m = RE_KAGIKAKKO.search(kubun)
            items.append((kubun[:m.start()], E(m.group(1))))
            items.append((D.kotoba("文書の表 namae と、shiryo のページ"), e.namae + (f"　{e.page}" if e.page else "")))
            items.append((D.kotoba("文書の表 hiduke、発言の日"), e.hiduke_ji))
            tokoro = D.kotoba("文書の部分（bubun・retsu から親をたどった並び）")
            if e.ichi:
                items.append((tokoro, e.ichi))
            elif e.page:
                items.append((tokoro, E(D.kotoba("bubun が空"))))
            if r["inyo"]:
                items.append((D.kotoba("数値の表 inyo"), f"「{S(r['inyo'])}」"))
        if r["shurui"]:
            items.append((D.kotoba("数値の表 shurui"), S(r["shurui"])))
        if e.konkyo:
            items.append((D.kotoba("文書の表 konkyo"), e.konkyo))
        if r["chu"]:
            items.append((D.kotoba("数値の表 chu"), E(r["chu"])))
        if r["jotai"] != sj.ARU:
            items.append((D.kotoba("数値の表 jotai が「数値がある」でない"), E(r["jotai"])))
            if r["hani"]:
                items.append((D.kotoba("数値の表 hani"), E(r["hani"])))
                if r["kakunin"]:
                    items.append((D.kotoba("数値の表 kakunin"), hi_str(D, r["kakunin"])))
        dl = "".join(f"<dt>{E(k)}</dt><dd>{v}</dd>" for k, v in items)
        if r["shiryo"].strip():
            link = (f"<p><a href='{E(e.url)}'>{E(D.bun('link'))}</a></p>" if e.url
                    else f"<p>{E(D.bun('link-nashi'))}</p>")
        else:
            link = ""
        kb = f"{E(r['kubun'])}　" if r["kubun"] else ""
        return f"<section id='{e.id}'><h3>{kb}{E(e.label)}：{e.atai}</h3><dl>{dl}</dl>{link}</section>"

    def nosete_inai(self):
        """このページで出していないもの。その定義の行に当てはまるものだけ。"""
        D = self.D
        li = []
        if any(e.sp for e in self.es):
            li.append(E(D.bun("nosete-inai-toi")))
        nashi = list(dict.fromkeys(e.namae for e in self.es if e.r["shiryo"].strip() and not e.sp and not e.r["bubun"]))
        if nashi:
            li.append(D.bun("nosete-inai-tokoro", shiryo="、".join(nashi)))
        docs = {sj.bunsho_of(e.r["shiryo"]) or e.r["shiryo"] for e in self.es if e.r["shiryo"].strip()}
        if len(docs) > 1:
            li.append(E(D.bun("nosete-inai-kankei")))
        if not li:
            return ""
        return (f"<h2>{E(D.bun('midashi-nosete-inai'))}</h2>\n<ul>"
                + "".join(f"<li>{x}</li>" for x in li) + "</ul>")

    def render(self, today):
        D = self.D
        if any(e.kankei for e in self.es):
            main = self.nen()
        else:
            main = self.hiduke_jun()
        mikakunin = (f"<p class=note>{E(D.bun('mikakunin-setsumei'))}</p>"
                     if any(e.mikakunin for e in self.es) else "")
        details = "".join(self.detail(e) for e in self.es)
        hi = hi_str(D, today.isoformat())
        note = (f"<p class=note><b>{E(D.bun('midashi-owari'))}</b><br>{E(D.bun('owari'))}"
                f"{E(D.bun('sakusei-bi', hi=hi))}</p>")
        return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{D.bun('dai', name=E(self.t['name']))}</title>
<style>
{STYLE}
</style></head><body>
{self.head()}
{main}
<h2>{E(D.bun('midashi-shosai'))}</h2>
{mikakunin}{details}
{self.nosete_inai()}
{note}
</body></html>
"""


def build(inp, tables, sid, kotoba, today, read_problems=(), design=None):
    """検査を通ればページ（印を消した HTML）と件数を返す。当たれば Stop。

    tables は {"suji", "atai", "bunsho", "bubun"} → 行の並び（tools/suji.py の read_* で読んだ物）。
    design は docs/design.md 3節の表（read_design で読んだ物）。None なら読む。
    """
    D = design or read_design()
    problems = [("(e) デザインシステムとの対応", m) for m in design_problems(D)]
    if problems:
        raise Stop(problems)
    problems += [("(a) 表の検査", mondai_str(m)) for m in read_problems]
    mondai, _, _ = sj.check_all(inp, tables["suji"], tables["atai"], tables["bunsho"], tables["bubun"])
    problems += [("(a) 表の検査", mondai_str(m)) for m in mondai]
    teigi = next((r for r in tables["suji"] if r["id"] == sid), None)
    if teigi is None:
        problems.append(("(c) 定義の id", f"{sid} が {sj.SUJI_NAME} に無い"))
    if problems:
        raise Stop(problems)
    by = {r["bunsho"]: r for r in tables["bunsho"]}
    index = {(r["bunsho"], r["n"]): r for r in tables["bubun"]}
    entries = [Entry(D, r, teigi, inp, by, index) for r in tables["atai"] if r["suji"] == sid]
    for e in entries:
        if e.r["shiryo"].strip() and not e.namae:
            problems.append(("(a) 表の検査", f"{sj.ATAI_NAME} の {e.gyo} 行目：shiryo の名前が作れない（{e.r['shiryo']}）"))
    if problems:
        raise Stop(problems)
    p = Page(D, teigi, entries, index)
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
        page, info = build(inp, tables, sid, bn.read_kotoba(), datetime.date.today(), read_problems,
                           read_design())
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
    print(f"数値の行：{info['gyo']}（ato {k[sj.KANKEI_ATO]}、tochu {k[sj.KANKEI_TOCHU]}、"
          f"mae {k[sj.KANKEI_MAE]}、印が無い {k[None]}）")
    print(f"資料の間で数値が一致していない時期：{info['chigau']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
