"""数値の定義の表と数値の表の検査（SCHEMA.md §6）。

使い方：python3 -B tools/suji.py
  teigi/suji.tsv（定義）と teigi/atai.tsv（数値）を読み、SCHEMA.md §6.4 の検査を行う。
  2つの表がどちらも無ければ「表がまだ無い」と出して、終了コード 0 で終わる。
  問題があれば、件数と、表の何行目か・何が問題かを出して、終了コード 1 で終わる。
  inyo の照合は tools/shogo.py の照合（SCHEMA.md §3）をそのまま使う。
"""
import datetime
import os
import re
import sys
import unicodedata
from collections import Counter, namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import keys  # noqa: E402
import shogo  # noqa: E402

TEIGI_DIR = os.path.join(inputs.ROOT, "teigi")
SUJI_NAME = "teigi/suji.tsv"
ATAI_NAME = "teigi/atai.tsv"
SUJI_COLUMNS = ["id", "name", "nani", "tani", "iikata", "toki", "sei", "chui", "kettei"]
ATAI_COLUMNS = ["suji", "kubun", "jiten", "nendo", "atai", "shurui", "jotai", "shiryo", "inyo", "hani", "kakunin",
                "chu"]

ARU = "数値がある"
KARA = "欄が空"
SETSUMEI = "数値を示さない説明がある"
NAI = "調べた範囲に見つからない"
JOTAI = (ARU, KARA, SETSUMEI, NAI)
# 状態ごとに必ず書く列（SCHEMA.md §6.3）。数値がある の行の inyo は別に扱う（書けないときは chu に理由）。
HISSU = {ARU: ("atai", "shiryo"), KARA: ("shiryo",), SETSUMEI: ("shiryo", "inyo"), NAI: ("hani", "kakunin")}
# 定義の表で空にできない列（SCHEMA.md §6.1 で「無ければ空」「決めていなければ空」とされていない列のうち、
# 数値を見分けるのに要る列）。
SUJI_HISSU = ("id", "name", "nani", "kettei")

# atai の中の数字の部分。符号（▲・△・マイナス）は数字の部分に含める。桁区切りの「,」と小数点も含める。
RE_SUJI = re.compile(r"[▲△\-−]?[0-9](?:[0-9,.]*[0-9])?")

# 依頼者が PDF で数値を確認した記録（SCHEMA.md §6.3）。chu にこの字が要る行がある。
RE_KAKUNIN = re.compile(r"依頼者が PDF で確認（([0-9]{4}-[0-9]{2}-[0-9]{2})）")
KOHO = "koho"   # hino-town-docs の sources.tsv の category。広報ひの

Mondai = namedtuple("Mondai", "hyo gyo naiyo")   # 表の名前、行の番号（列名の行は1）、何が問題か


def read_table(text, name, columns):
    """TSV の字 → (行の並び, 問題の並び)。行は {"_gyo": 行の番号, 列名: 字}。

    列名の行が columns と違うとき（列が足りない、余分な列がある、順が違う）は、その問題を返し、行は読まない。
    列の数が違う行は、問題として返し、その行は除く。空の行は飛ばす（行の番号は数え続ける）。
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in lines]
    if not lines or not lines[0]:
        return [], [Mondai(name, 1, "列名の行が無い")]
    head = lines[0].split("\t")
    if head != list(columns):
        out = []
        tarinai = [c for c in columns if c not in head]
        yobun = [c for c in head if c not in columns]
        if tarinai:
            out.append(Mondai(name, 1, f"列が足りない（{'・'.join(tarinai)}）"))
        if yobun:
            out.append(Mondai(name, 1, f"余分な列がある（{'・'.join(yobun)}）"))
        if not out:
            out.append(Mondai(name, 1, f"列の順が SCHEMA.md §6 と違う（{'・'.join(columns)} のはず）"))
        return [], out
    rows, out = [], []
    for n, ln in enumerate(lines[1:], 2):
        if not ln.strip():
            continue
        cells = ln.split("\t")
        if len(cells) != len(columns):
            out.append(Mondai(name, n, f"列の数が {len(cells)}（{len(columns)} のはず）"))
            continue
        r = dict(zip(columns, cells))
        r["_gyo"] = n
        rows.append(r)
    return rows, out


def read_suji(text):
    return read_table(text, SUJI_NAME, SUJI_COLUMNS)


def read_atai(text):
    return read_table(text, ATAI_NAME, ATAI_COLUMNS)


def is_ymd(s):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        return False
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def suji_parts(atai):
    """atai の字 → 数字の部分の並び（§3 の正規化をしたあとの字から取り出す）。数字が無ければ空。"""
    return RE_SUJI.findall(shogo.norm(atai))


def atai_in_inyo(atai, inyo):
    """数値がある の行で、atai の数字の部分が、すべて inyo の中に、1つの数として書かれているか。

    数字が1つも無い atai（「なし」など）は、検査の対象にしない（None を返す）。
    """
    parts = suji_parts(atai)
    if not parts:
        return None
    # 数字の境目を見る（40 が 140 の中で合わないように）。空白を消すと境目が分からなくなるので、
    # inyo は NFKC だけを行い、空白は残す。前が数字・「,」・「.」、後ろが数字（「,」「.」に続く数字を含む）なら合わない。
    q = unicodedata.normalize("NFKC", inyo or "")
    return all(re.search(r"(?<![0-9,.])" + re.escape(p) + r"(?![0-9]|[,.][0-9])", q) for p in parts)


def has_kakunin(chu):
    """chu に「依頼者が PDF で確認（YYYY-MM-DD）」があり、日付の形が合っているか。"""
    return any(is_ymd(d) for d in RE_KAKUNIN.findall(chu or ""))


def is_koho(inp, shiryo):
    """shiryo が、広報ひの（sources.tsv の category が koho）の資料か。鍵の形が違う行・doc でない行は False。"""
    try:
        kind, parts = keys.parse(shiryo)
    except keys.KeyFormError:
        return False
    if kind != "doc":
        return False
    return (inp.docs().get(parts[0]) or {}).get("category") == KOHO


def check_kakunin(inp, rows):
    """「数値がある」の行で、広報ひのを出典にした行と、inyo が空の行に、確認の記録があるか（SCHEMA.md §6.4）。"""
    out = []
    for r in rows:
        if r["jotai"] != ARU or has_kakunin(r["chu"]):
            continue
        if not r["inyo"].strip():
            if r["chu"].strip():      # chu が空の行は、check_atai が「理由が無い」として出す
                out.append(Mondai(ATAI_NAME, r["_gyo"],
                                  "「数値がある」の行で、inyo が空なのに、chu に「依頼者が PDF で確認（YYYY-MM-DD）」が無い"))
        elif is_koho(inp, r["shiryo"]):
            out.append(Mondai(ATAI_NAME, r["_gyo"],
                              "広報ひのを出典にした「数値がある」の行で、chu に「依頼者が PDF で確認（YYYY-MM-DD）」が無い"))
    return out


def bun_no_narabi(text):
    """発言の本文 → 文の並び（SCHEMA.md §6.4）。改行と「。」で分ける。「。」は文に含める。"""
    out = []
    for para in (text or "").split("\n"):
        for m in re.finditer(r"[^。]*。|[^。]+$", para):
            if m.group(0).strip():
                out.append(m.group(0).strip())
    return out


def is_bun(inyo, text):
    """inyo が、発言の本文の、文の頭から「。」まで（続いた文をつないだ物を含む）になっているか。"""
    q = shogo.norm(inyo)
    if not q:
        return False
    buns = [shogo.norm(b) for b in bun_no_narabi(text)]
    for i in range(len(buns)):
        acc = ""
        for b in buns[i:]:
            acc += b
            if acc == q:
                return True
            if len(acc) >= len(q):
                break
    return False


def check_hatsugen(inp, rows):
    """発言（sp）を出典にした行の inyo が、文の途中で切られていないか（SCHEMA.md §6.2・§6.4）。"""
    out = []
    for r in rows:
        if not r["inyo"].strip():
            continue
        try:
            kind, parts = keys.parse(r["shiryo"])
        except keys.KeyFormError:
            continue
        if kind != "sp":
            continue
        text = inp.statement_text(parts[0])
        if text is None:        # 発言が入力に無い行は、inyo の照合の側で出す
            continue
        if not is_bun(r["inyo"], text):
            out.append(Mondai(ATAI_NAME, r["_gyo"], "発言を出典にした行で、inyo が、文の頭から「。」までになっていない"))
    return out


def check_suji(rows):
    """定義の表の検査。"""
    out = []
    ids = Counter(r["id"] for r in rows if r["id"])
    for r in rows:
        n = r["_gyo"]
        kara = [c for c in SUJI_HISSU if not r[c].strip()]
        if kara:
            out.append(Mondai(SUJI_NAME, n, f"必ず書く列が空（{'・'.join(kara)}）"))
        if r["id"] and not re.fullmatch(r"[a-z0-9-]+", r["id"]):
            out.append(Mondai(SUJI_NAME, n, f"id の形が違う（英小文字・数字・ハイフンのはず：{r['id']}）"))
        if r["id"] and ids[r["id"]] > 1:
            out.append(Mondai(SUJI_NAME, n, f"定義の id が重なっている（{r['id']}）"))
        if r["kettei"] and r["kettei"] != "案" and not is_ymd(r["kettei"]):
            out.append(Mondai(SUJI_NAME, n, f"kettei の形が違う（YYYY-MM-DD か「案」のはず：{r['kettei']}）"))
    return out


def check_atai(rows, suji_ids):
    """数値の表の検査のうち、資料の本文を読まない物。照合する行の並びも返す。"""
    out, quotes = [], []
    for r in rows:
        n = r["_gyo"]
        j = r["jotai"]
        if r["suji"] not in suji_ids:
            out.append(Mondai(ATAI_NAME, n, f"suji が定義の表に無い（{r['suji']}）"))
        if not r["jiten"].strip():
            out.append(Mondai(ATAI_NAME, n, "jiten（いつの数値か）が空"))
        if j not in JOTAI:
            out.append(Mondai(ATAI_NAME, n, f"jotai が {'・'.join(JOTAI)} のどれでもない（{j}）"))
        else:
            kara = [c for c in HISSU[j] if not r[c].strip()]
            if kara:
                out.append(Mondai(ATAI_NAME, n, f"「{j}」の行で、必ず書く列が空（{'・'.join(kara)}）"))
            if j != ARU and r["atai"].strip():
                out.append(Mondai(ATAI_NAME, n, f"「{j}」の行で、atai に字がある（{r['atai']}）"))
            if j == ARU and not r["inyo"].strip() and not r["chu"].strip():
                out.append(Mondai(ATAI_NAME, n, "「数値がある」の行で、inyo が空で、chu に理由が無い"))
        key_ok = False
        if r["shiryo"]:
            try:
                keys.parse(r["shiryo"])
                key_ok = True
            except keys.KeyFormError as e:
                out.append(Mondai(ATAI_NAME, n, f"shiryo の{e}"))
        if r["inyo"].strip():
            if not r["shiryo"].strip():
                out.append(Mondai(ATAI_NAME, n, "inyo があるが、shiryo が空"))
            elif key_ok:
                quotes.append(dict(where=n, source=r["shiryo"], quote=r["inyo"]))
        if j == ARU and r["atai"].strip() and r["inyo"].strip() and atai_in_inyo(r["atai"], r["inyo"]) is False:
            out.append(Mondai(ATAI_NAME, n, f"atai の数字が inyo の中に無い（atai：{r['atai']}）"))
        if r["kakunin"] and not is_ymd(r["kakunin"]):
            out.append(Mondai(ATAI_NAME, n, f"kakunin の形が違う（YYYY-MM-DD のはず：{r['kakunin']}）"))
        if r["nendo"] and not re.fullmatch(r"[0-9]{4}", r["nendo"]):
            out.append(Mondai(ATAI_NAME, n, f"nendo が西暦4桁でない（{r['nendo']}）"))
    return out, quotes


def check(inp, suji_rows, atai_rows):
    """SCHEMA.md §6.4 の検査。→ (問題の並び, inyo の照合の結果)。問題は表と行の番号の順。

    inp は入力の読み口（inputs.Inputs か、テストの偽の入力）。照合する inyo が無ければ読まない。
    """
    out = check_suji(suji_rows)
    ids = {r["id"] for r in suji_rows if r["id"]}
    more, quotes = check_atai(atai_rows, ids)
    out += more
    out += check_kakunin(inp, atai_rows)
    out += check_hatsugen(inp, atai_rows)
    res = shogo.check_quotes(inp, quotes) if quotes else shogo.Result()
    for m in res.mismatched:
        out.append(Mondai(ATAI_NAME, m["where"], f"inyo が shiryo の資料の本文に無い（{m['reason']}：{m['source']}）"))
    order = {SUJI_NAME: 0, ATAI_NAME: 1}
    out.sort(key=lambda m: (order.get(m.hyo, 2), m.gyo))
    return out, res


def _read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(argv=None, teigi_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    d = teigi_dir or TEIGI_DIR
    paths = {SUJI_NAME: os.path.join(d, "suji.tsv"), ATAI_NAME: os.path.join(d, "atai.tsv")}
    aru = {k: os.path.exists(p) for k, p in paths.items()}
    if not any(aru.values()):
        print(f"表がまだ無い（{SUJI_NAME}・{ATAI_NAME}）")
        return 0
    if not all(aru.values()):
        nai = [k for k, v in aru.items() if not v]
        print(f"止めた：表が片方しか無い（無い表：{'・'.join(nai)}）", file=sys.stderr)
        return 1
    try:
        suji_rows, p1 = read_suji(_read_file(paths[SUJI_NAME]))
        atai_rows, p2 = read_atai(_read_file(paths[ATAI_NAME]))
        inp = inputs.Inputs() if any(r["inyo"].strip() for r in atai_rows) else None
        problems, res = check(inp, suji_rows, atai_rows)
    except (inputs.InputError, OSError, UnicodeDecodeError) as e:
        print(f"止めた：lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    problems = p1 + p2 + problems
    print(f"定義：{len(suji_rows)} 行")
    print(f"数値：{len(atai_rows)} 行")
    c = Counter(r["jotai"] for r in atai_rows)
    for j in JOTAI:
        print(f"  {j}：{c.get(j, 0)} 行")
    hoka = sum(v for k, v in c.items() if k not in JOTAI)
    if hoka:
        print(f"  （4つの状態のどれでもない：{hoka} 行）")
    print(f"inyo の照合：対象 {res.total}、合った {res.matched}、合わなかった {len(res.mismatched)}")
    if problems:
        print(f"止めた：問題が {len(problems)} 件", file=sys.stderr)
        for m in problems:
            print(f"  - {m.hyo} の {m.gyo} 行目：{m.naiyo}", file=sys.stderr)
        return 1
    print("問題は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
