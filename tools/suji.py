"""数値の定義の表と数値の表、文書の表と文書の部分の表の検査（SCHEMA.md §6・§7）。

使い方：python3 -B tools/suji.py
  teigi/suji.tsv（定義）と teigi/atai.tsv（数値）を読み、SCHEMA.md §6.4 の検査を行う。
  teigi/bunsho.tsv（文書）と teigi/bubun.tsv（文書の部分）があれば、SCHEMA.md §7.4 の検査も行う。
  定義と数値の2つの表がどちらも無ければ「表がまだ無い」と出して、終了コード 0 で終わる。
  文書と文書の部分の2つの表は、どちらも無ければ検査しない。片方しか無ければ止まる。
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
SUJI_COLUMNS = ["id", "name", "nani", "tani", "iikata", "toki", "nendo_tsuki", "sei", "chui", "kettei"]
ATAI_COLUMNS = ["suji", "kubun", "jiten", "nendo", "atai", "shurui", "jotai", "shiryo", "inyo", "hani", "kakunin",
                "chu", "bubun", "retsu"]
BUNSHO_NAME = "teigi/bunsho.tsv"
BUBUN_NAME = "teigi/bubun.tsv"
BUNSHO_COLUMNS = ["bunsho", "namae", "shurui", "konkyo", "konkyo_tokoro", "hiduke", "hiduke_moto", "chu"]
BUBUN_COLUMNS = ["bunsho", "n", "oya", "shu", "name", "tokoro", "jun", "torikata", "chu"]

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
KEIKAKU = "keikaku"   # 計画ライブラリの文書（pt・plan の鍵）の shurui（SCHEMA.md §7.1）

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
            out.append(Mondai(name, 1, f"列の順が SCHEMA.md と違う（{'・'.join(columns)} のはず）"))
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


def read_bunsho(text):
    return read_table(text, BUNSHO_NAME, BUNSHO_COLUMNS)


def read_bubun(text):
    return read_table(text, BUBUN_NAME, BUBUN_COLUMNS)


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


NENDO_TSUKI = {str(m) for m in range(1, 13)}
# 時点の関係の印（SCHEMA.md §7.3）。意味は、§7.3 の条件と実物の例で決まる。画面の言葉は、ここに書かない
KANKEI_ATO = "ato"        # 数値の時点が、資料の日付より後
KANKEI_MAE = "mae"        # 数値の時点が、資料の日付と同じか、前
KANKEI_TOCHU = "tochu"    # 数値の時点が年度の期間で、資料の日付が、その期間の中
KANKEI = (KANKEI_ATO, KANKEI_MAE, KANKEI_TOCHU)
RE_NENGETSU = re.compile(r"(令和|平成)(元|[0-9]+)年([0-9]+)月")
GENGO = {"令和": 2018, "平成": 1988}


def shiryo_nengetsu(shiryo, bunsho_by_key):
    """資料の日付 → (年, 月)。発言は発言の日、ほかは文書の表の hiduke。分からなければ None。"""
    try:
        kind, g = keys.parse(shiryo)
    except keys.KeyFormError:
        return None
    if kind == "sp":
        d = keys.sid_date(g[0])            # YYYY-MM-DD
        return (int(d[:4]), int(d[5:7])) if d else None
    h = (bunsho_by_key.get(bunsho_of(shiryo)) or {}).get("hiduke", "")
    return (int(h[:4]), int(h[5:7])) if RE_HIDUKE.fullmatch(h) else None


def jiten_kankei(r, teigi, bunsho_by_key):
    """数値の行 → 時点の関係の印（ato・mae・tochu）。条件に当てはまらない行は None（SCHEMA.md §7.3）。

    r は数値の表の行、teigi はその定義の行、bunsho_by_key は文書の鍵 → 文書の表の行。
    """
    if not r["nendo"].strip() or not r["shiryo"].strip():
        return None
    hi = shiryo_nengetsu(r["shiryo"], bunsho_by_key)
    if hi is None:
        return None
    nendo = int(r["nendo"])
    m = RE_NENGETSU.fullmatch(r["jiten"].strip())
    tsuki = (teigi or {}).get("nendo_tsuki", "")
    if m:                                   # 年月の字。暦の年は元号から出す（1〜3月は、年度と暦の年が違う）
        toki = (GENGO[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2))), int(m.group(3)))
    elif tsuki in NENDO_TSUKI:              # 年度の字で、定義が月を決めている
        t = int(tsuki)
        toki = (nendo if t >= 4 else nendo + 1, t)
    else:                                   # 年度の字で、定義が月を決めていない。年度を期間として扱う
        if hi < (nendo, 4):
            return KANKEI_ATO
        return KANKEI_MAE if hi > (nendo + 1, 3) else KANKEI_TOCHU
    return KANKEI_ATO if toki > hi else KANKEI_MAE


def count_kankei(suji_rows, atai_rows, bunsho_rows):
    """時点の関係ごとの行の数。→ Counter（鍵は3つの関係の字と None）。"""
    teigi = {r["id"]: r for r in suji_rows}
    by = {r["bunsho"]: r for r in bunsho_rows or []}
    return Counter(jiten_kankei(r, teigi.get(r["suji"]), by) for r in atai_rows)


def check_shurui(inp, rows):
    """shurui の字が、shiryo のページ（発言はその発言）の原典の文字にあるか（SCHEMA.md §6.2・§6.4）。

    → (問題の並び, 数えた結果)。原典の文字が入力に無い資料の行と、shiryo が空の行は除いて、数を出す。
    確認するのは、字がページにあることまで。その数値についての字かどうかは、この検査では分からない。
    """
    out, kazoe = [], Counter()
    if inp is None:
        return out, kazoe
    for r in rows:
        sh = r["shurui"].strip()
        if not sh:
            continue
        texts = shogo.source_texts(inp, r["shiryo"]) if r["shiryo"].strip() else None
        if not texts or not any(t for t in texts):
            kazoe["shurui_nozoita"] += 1
            continue
        kazoe["shurui_taisho"] += 1
        if not any(shogo.norm(sh) in shogo.norm(t) for t in texts if t):
            out.append(Mondai(ATAI_NAME, r["_gyo"], f"shurui の字が、shiryo の原典の文字に無い（{sh}）"))
    return out, kazoe


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
        if r["nendo_tsuki"] and r["nendo_tsuki"] not in NENDO_TSUKI:
            out.append(Mondai(SUJI_NAME, n, f"nendo_tsuki の形が違う（空か、1〜12の数のはず：{r['nendo_tsuki']}）"))
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


# ---------------------------------------------------------------- 文書と、文書の部分（SCHEMA.md §7）

MIDASHI, HYO, GYO, RETSU = "見出し", "表", "行", "列"
SHU = (MIDASHI, HYO, GYO, RETSU)
KIKAI, YONDA = "機械", "読んだ"
TORIKATA = (KIKAI, YONDA)
# 部分の種類ごとに、親にできる種類（SCHEMA.md §7.2。見出し → 見出し → 表 → 行・列）。None は親が無いこと。
OYA_SHU = {MIDASHI: (None, MIDASHI), HYO: (None, MIDASHI), GYO: (HYO,), RETSU: (HYO,)}

RE_BUNSHO_PT = re.compile(r"pt:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_.-]+)")
RE_BUNSHO_DOC = re.compile(r"doc:([a-z0-9][a-z0-9-]*)")
RE_HIDUKE = re.compile(r"[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?")
# 表の行の、行の見出しのあとの数値の1つ（▲・△・マイナスの符号、桁区切りの「,」、小数点を含む）。NFKC のあとの字に使う。
RE_KAZU = re.compile(r"[▲△\-−]?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?")


def bunsho_of(key):
    """資料の鍵（§2）→ 文書の鍵（§7.1）。pt と doc はページを除く。plan はそのまま。ほかは None。"""
    try:
        kind, g = keys.parse(key)
    except keys.KeyFormError:
        return None
    if kind == "pt":
        return f"pt:{g[0]}/{g[1]}"
    if kind == "doc":
        return f"doc:{g[0]}"
    if kind == "plan":
        return key
    return None


def page_no(key):
    """pt・doc のページの鍵 → ページの番号。ほかは None。"""
    try:
        kind, g = keys.parse(key)
    except keys.KeyFormError:
        return None
    return int(g[-1]) if kind in ("pt", "doc") else None


def bunsho_aru(inp, bunsho):
    """文書の鍵の形が §7.1 に合い、lock の版の入力にあるか。→ (形が合うか, 入力にあるか)。"""
    m = RE_BUNSHO_PT.fullmatch(bunsho or "")
    if m:
        return True, any(inp.pt_text(m[1], m[2], layer) is not None for layer in ("text", "text_raw"))
    m = RE_BUNSHO_DOC.fullmatch(bunsho or "")
    if m:
        return True, m[1] in inp.docs()
    m = keys.RE_PLAN.fullmatch(bunsho or "")
    if m:
        return True, inp.plan(m[1]) is not None
    return False, False


def page_raw(inp, page_key):
    """pt・doc のページの鍵 → 原典の文字のうち、行の並びを保った物（text_raw）の、そのページ。無ければ None。"""
    try:
        kind, g = keys.parse(page_key)
    except keys.KeyFormError:
        return None
    if kind == "pt":
        return shogo.page_of(inp.pt_text(g[0], g[1], "text_raw"), int(g[2]))
    if kind == "doc":
        return shogo.page_of(inp.doc_text(g[0], "text_raw"), int(g[1]))
    return None


def on_page(inp, text, page_key):
    """text の字が、ページの原典の文字（text か text_raw）にあるか（§3 の正規化）。"""
    texts = shogo.source_texts(inp, page_key)
    q = shogo.norm(text)
    return bool(q) and bool(texts) and any(q in shogo.norm(t) for t in texts)


def check_bunsho(inp, rows):
    """文書の表の検査（SCHEMA.md §7.4）。→ (問題の並び, 文書の鍵の集合)。"""
    out, names = [], set()
    count = Counter(r["bunsho"] for r in rows)
    for r in rows:
        n, b = r["_gyo"], r["bunsho"]
        katachi, aru = bunsho_aru(inp, b)
        if not katachi:
            out.append(Mondai(BUNSHO_NAME, n, f"bunsho の形が §7.1 と違う（pt:<id>/<名前>、doc:<id>、plan:<id> のはず：{b}）"))
        elif not aru:
            out.append(Mondai(BUNSHO_NAME, n, f"bunsho が lock の版の入力に無い（{b}）"))
        if count[b] > 1:
            out.append(Mondai(BUNSHO_NAME, n, f"bunsho が重なっている（{b}）"))
        names.add(b)
        if katachi and aru:
            want = (inp.docs().get(b[4:]) or {}).get("category") if b.startswith("doc:") else KEIKAKU
            if r["shurui"] != want:
                out.append(Mondai(BUNSHO_NAME, n, f"shurui が §7.1 と違う（{want} のはず：{r['shurui']}）"))
        if not r["namae"].strip():
            out.append(Mondai(BUNSHO_NAME, n, "namae が空"))
        elif katachi and aru and not b.startswith("plan:") and not on_page(inp, r["namae"], b + "/1"):
            out.append(Mondai(BUNSHO_NAME, n, f"namae の字が、1ページの原典の文字に無い（{r['namae']}）"))
        if r["konkyo"].strip():
            t = r["konkyo_tokoro"]
            if bunsho_of(t) != b or page_no(t) is None:
                out.append(Mondai(BUNSHO_NAME, n, f"konkyo_tokoro が、この文書のページの鍵でない（{t}）"))
            elif not on_page(inp, r["konkyo"], t):
                out.append(Mondai(BUNSHO_NAME, n, f"konkyo の字が、konkyo_tokoro のページの原典の文字に無い（{t}）"))
        else:
            if r["konkyo_tokoro"].strip():
                out.append(Mondai(BUNSHO_NAME, n, "konkyo が空なのに、konkyo_tokoro がある"))
            if not r["chu"].strip():
                out.append(Mondai(BUNSHO_NAME, n, "konkyo が空なのに、chu に探したページが無い"))
        h, hm = r["hiduke"], r["hiduke_moto"]
        if h:
            if not RE_HIDUKE.fullmatch(h) or not is_ymd(h if len(h) == 10 else h + "-01"):
                out.append(Mondai(BUNSHO_NAME, n, f"hiduke の形が違う（YYYY-MM か YYYY-MM-DD のはず：{h}）"))
            if not hm.strip():
                out.append(Mondai(BUNSHO_NAME, n, "hiduke があるのに、hiduke_moto が空"))
            elif hm.startswith(("pt:", "doc:")):
                if bunsho_of(hm) != b or page_no(hm) is None or shogo.source_texts(inp, hm) is None:
                    out.append(Mondai(BUNSHO_NAME, n, f"hiduke_moto が、この文書のページの鍵でない（{hm}）"))
            elif hm.split(" ")[0] not in inputs.REPOS:
                out.append(Mondai(BUNSHO_NAME, n, f"hiduke_moto が、ページの鍵でも、入力の台帳の名前でもない（{hm}）"))
        elif not r["chu"].strip():
            out.append(Mondai(BUNSHO_NAME, n, "hiduke が空なのに、chu に理由が無い"))
    return out, names


def table_range(inp, bubun_rows, hyo):
    """表の部分 → (原典の文字（text_raw）の、表の範囲の行の並び, 問題の字)。

    範囲は、表の題（name）と同じ字の行のあとから、同じ文書の部分の表にある別の表の題と同じ字の行の前まで。
    別の表の題が無ければ、そのページの終わりまで。題の行が、そのページに1つでなければ、問題の字を返す。
    """
    raw = page_raw(inp, hyo["tokoro"])
    if raw is None:
        return None, f"表の tokoro のページの原典の文字（text_raw）が無い（{hyo['tokoro']}）"
    lines = raw.split("\n")
    title = shogo.norm(hyo["name"])
    at = [i for i, ln in enumerate(lines) if shogo.norm(ln) == title]
    if len(at) != 1:
        return None, f"表の題と同じ字の行が、tokoro のページに {len(at)} 行ある（1行のはず：{hyo['name']}）"
    others = {shogo.norm(x["name"]) for x in bubun_rows
              if x["bunsho"] == hyo["bunsho"] and x["shu"] == HYO and x["n"] != hyo["n"]}
    end = next((i for i in range(at[0] + 1, len(lines)) if shogo.norm(lines[i]) in others), len(lines))
    return lines[at[0] + 1:end], ""


def row_numbers(line, name):
    """原典の文字の1行が、行の見出し name と、それに続く数値だけでできていれば、数値の並び（NFKC のあとの字）。

    行の見出しの字は §3 の正規化で比較する。数値は空白で区切り、1つずつ RE_KAZU に合う物（「▲5」は1つの数値）。
    そうでなければ None。
    """
    q = shogo.norm(name)
    if not q or not shogo.norm(line).startswith(q):
        return None
    k = next(k for k in range(len(line) + 1) if shogo.norm(line[:k]) == q)
    rest = unicodedata.normalize("NFKC", line[k:]).split()
    if not rest or not all(RE_KAZU.fullmatch(x) for x in rest):
        return None
    return rest


def row_in_range(lines, name):
    """表の範囲の行の並びから、行の見出し name の行を探す。→ (数値の並び, 問題の字)。1行だけあるときに数値を返す。"""
    hits = [x for x in (row_numbers(ln, name) for ln in lines) if x is not None]
    if len(hits) != 1:
        return None, f"行の見出しと数値の行が、親の表の範囲に {len(hits)} 行ある（1行のはず：{name}）"
    return hits[0], ""


def check_bubun(inp, rows, bunsho_names):
    """文書の部分の表の検査（SCHEMA.md §7.4）。→ (問題の並び, (文書, 番号) → 行)。"""
    out, index = [], {}
    for r in rows:
        if re.fullmatch(r"[1-9][0-9]*", r["n"]):
            index.setdefault((r["bunsho"], r["n"]), []).append(r)
    for r in rows:
        g, b = r["_gyo"], r["bunsho"]
        if not re.fullmatch(r"[1-9][0-9]*", r["n"]):
            out.append(Mondai(BUBUN_NAME, g, f"n が1からの整数でない（{r['n']}）"))
        elif len(index[(b, r["n"])]) > 1:
            out.append(Mondai(BUBUN_NAME, g, f"bunsho と n の組が重なっている（{b} の {r['n']}）"))
        if b not in bunsho_names:
            out.append(Mondai(BUBUN_NAME, g, f"bunsho が文書の表に無い（{b}）"))
        if r["shu"] not in SHU:
            out.append(Mondai(BUBUN_NAME, g, f"shu が {'・'.join(SHU)} のどれでもない（{r['shu']}）"))
        if r["torikata"] not in TORIKATA:
            out.append(Mondai(BUBUN_NAME, g, f"torikata が {'・'.join(TORIKATA)} のどちらでもない（{r['torikata']}）"))
        oya = None
        if r["oya"]:
            cand = index.get((b, r["oya"])) or []
            if not cand:
                out.append(Mondai(BUBUN_NAME, g, f"oya が、同じ文書の部分の表に無い（{r['oya']}）"))
            elif not (r["n"].isdigit() and int(r["oya"]) < int(r["n"])):
                out.append(Mondai(BUBUN_NAME, g, f"oya が、自分より小さい番号でない（{r['oya']}）"))
            else:
                oya = cand[0]
        if r["shu"] in SHU and not (r["oya"] and oya is None):    # oya の誤りは上で出す
            oshu = oya["shu"] if oya else None
            if oshu not in OYA_SHU[r["shu"]]:
                want = "・".join("無し" if x is None else x for x in OYA_SHU[r["shu"]])
                out.append(Mondai(BUBUN_NAME, g, f"「{r['shu']}」の親の種類が違う（{want} のはず：{oshu or '無し'}）"))
        t = r["tokoro"]
        if bunsho_of(t) != b or page_no(t) is None:
            out.append(Mondai(BUBUN_NAME, g, f"tokoro が、この文書のページの鍵でない（{t}）"))
        elif not r["name"].strip():
            out.append(Mondai(BUBUN_NAME, g, "name が空"))
        elif not on_page(inp, r["name"], t):
            out.append(Mondai(BUBUN_NAME, g, f"name の字が、tokoro のページの原典の文字に無い（{r['name']}）"))
        elif oya and page_no(oya["tokoro"]) is not None and page_no(oya["tokoro"]) > page_no(t):
            out.append(Mondai(BUBUN_NAME, g, f"tokoro のページが、親の tokoro のページより前（{t}）"))
        if r["shu"] == RETSU and not re.fullmatch(r"[1-9][0-9]*", r["jun"]):
            out.append(Mondai(BUBUN_NAME, g, f"列の行で、jun が1からの整数でない（{r['jun']}）"))
        if r["shu"] != RETSU and r["jun"]:
            out.append(Mondai(BUBUN_NAME, g, f"列でない行に jun がある（{r['jun']}）"))
    out += check_tables(inp, rows, index)
    return out, index


def check_tables(inp, rows, index):
    """表の行と列を、原典の文字（text_raw）の、親の表の範囲で確認する（SCHEMA.md §7.4）。torikata が「読んだ」の表は除く。"""
    out = []
    hyos = [r for r in rows if r["shu"] == HYO and r["torikata"] == KIKAI]
    for hyo in hyos:
        ko = [r for r in rows if r["bunsho"] == hyo["bunsho"] and r["oya"] == hyo["n"] and r["shu"] in (GYO, RETSU)]
        if not ko:
            continue
        lines, why = table_range(inp, rows, hyo)
        if lines is None:
            out.append(Mondai(BUBUN_NAME, hyo["_gyo"], why))
            continue
        text = shogo.norm("\n".join(lines))
        juns = Counter(r["jun"] for r in ko if r["shu"] == RETSU)
        for r in ko:
            if r["tokoro"] != hyo["tokoro"]:
                out.append(Mondai(BUBUN_NAME, r["_gyo"], f"行と列の tokoro が、親の表の tokoro と違う（{r['tokoro']}）"))
                continue
            if r["shu"] == GYO and r["torikata"] == KIKAI:
                _, why = row_in_range(lines, r["name"])
                if why:
                    out.append(Mondai(BUBUN_NAME, r["_gyo"], why))
            if r["shu"] == RETSU:
                if shogo.norm(r["name"]) not in text:
                    out.append(Mondai(BUBUN_NAME, r["_gyo"], f"列の見出しの字が、親の表の範囲に無い（{r['name']}）"))
                if r["jun"] and juns[r["jun"]] > 1:
                    out.append(Mondai(BUBUN_NAME, r["_gyo"], f"同じ表に、jun が同じ列がある（{r['jun']}）"))
        # torikata が「機械」の列は、列の見出しが、範囲の中に、jun の順に並んでいることを確認する
        kikai = sorted((r for r in ko if r["shu"] == RETSU and r["torikata"] == KIKAI and r["jun"].isdigit()),
                       key=lambda r: int(r["jun"]))
        pos = 0
        for r in kikai:
            i = text.find(shogo.norm(r["name"]), pos)
            if i < 0:
                if shogo.norm(r["name"]) in text:
                    out.append(Mondai(BUBUN_NAME, r["_gyo"], f"列の見出しが、親の表の範囲で jun の順に並んでいない（{r['name']}）"))
                break
            pos = i + len(shogo.norm(r["name"]))
    return out


def check_atai_bubun(inp, rows, bubun_rows, index, bunsho_names):
    """数値の表の bubun と retsu の検査と、行と列を指す数値の検査（SCHEMA.md §7.4）。→ (問題の並び, 数えた結果)。"""
    out = []
    kazoe = Counter()
    for r in rows:
        n, bu, re_ = r["_gyo"], r["bubun"], r["retsu"]
        if not bu and not re_:
            continue
        if not bu:
            out.append(Mondai(ATAI_NAME, n, "retsu があるのに、bubun が空"))
            continue
        try:
            kind, g = keys.parse(r["shiryo"])
        except keys.KeyFormError:
            out.append(Mondai(ATAI_NAME, n, "bubun があるのに、shiryo の鍵の形が違う"))
            continue
        if kind == "sp":
            out += check_para(inp, r, g[0])
            continue
        b = bunsho_of(r["shiryo"])
        if b is None:
            out.append(Mondai(ATAI_NAME, n, f"bubun を書けない shiryo（{r['shiryo']}）"))
            continue
        if b not in bunsho_names:
            out.append(Mondai(ATAI_NAME, n, f"shiryo の文書が、文書の表に無い（{b}）"))
            continue
        gyo = (index.get((b, bu)) or [None])[0]
        if gyo is None:
            out.append(Mondai(ATAI_NAME, n, f"bubun が、shiryo の文書の部分の表に無い（{b} の {bu}）"))
            continue
        if not re_:
            if gyo["shu"] == GYO:
                out.append(Mondai(ATAI_NAME, n, "bubun が行なのに、retsu が空"))
            elif gyo["shu"] == RETSU:
                out.append(Mondai(ATAI_NAME, n, "bubun が列（行、表、見出しのどれかのはず）"))
            continue
        retsu = (index.get((b, re_)) or [None])[0]
        if retsu is None:
            out.append(Mondai(ATAI_NAME, n, f"retsu が、shiryo の文書の部分の表に無い（{b} の {re_}）"))
            continue
        if retsu["shu"] != RETSU or gyo["shu"] != GYO:
            out.append(Mondai(ATAI_NAME, n, f"bubun が行、retsu が列でない（bubun：{gyo['shu']}、retsu：{retsu['shu']}）"))
            continue
        if gyo["oya"] != retsu["oya"]:
            out.append(Mondai(ATAI_NAME, n, f"bubun の行と retsu の列の親の表が違う（{gyo['oya']} と {retsu['oya']}）"))
            continue
        hyo = (index.get((b, gyo["oya"])) or [None])[0]
        if hyo is None:
            continue    # 親が無いことは、文書の部分の表の検査で出す
        if YONDA in (hyo["torikata"], gyo["torikata"]):
            kazoe["yonda"] += 1
            continue
        kazoe["taisho"] += 1
        if r["shiryo"] != hyo["tokoro"]:
            out.append(Mondai(ATAI_NAME, n, f"shiryo のページが、表の tokoro と違う（{r['shiryo']} と {hyo['tokoro']}）"))
            continue
        lines, why = table_range(inp, bubun_rows, hyo)
        if lines is None:
            out.append(Mondai(ATAI_NAME, n, why))
            continue
        kazu, why = row_in_range(lines, gyo["name"])
        if kazu is None:
            out.append(Mondai(ATAI_NAME, n, why))
            continue
        j = int(retsu["jun"]) if retsu["jun"].isdigit() else 0
        if not 1 <= j <= len(kazu):
            out.append(Mondai(ATAI_NAME, n, f"行の数値は {len(kazu)} 個で、列の jun（{retsu['jun']}）の数値が無い"))
            continue
        if shogo.norm(kazu[j - 1]) != shogo.norm(r["atai"]):
            out.append(Mondai(ATAI_NAME, n, f"行の数値の {j} つ目（{kazu[j - 1]}）が、atai（{r['atai']}）と違う"))
            continue
        kazoe["atta"] += 1
    return out, kazoe


def check_para(inp, r, sid):
    """発言を shiryo にした行の bubun：§2 の段落の鍵の形で、shiryo の発言の段落であり、その段落に inyo の字がある。"""
    n, bu = r["_gyo"], r["bubun"]
    if r["retsu"]:
        return [Mondai(ATAI_NAME, n, "発言を shiryo にした行に、retsu がある")]
    try:
        kind, g = keys.parse(bu)
    except keys.KeyFormError:
        kind, g = None, None
    if kind != "para":
        return [Mondai(ATAI_NAME, n, f"発言を shiryo にした行で、bubun が段落の鍵の形でない（{bu}）")]
    if g[0] != sid:
        return [Mondai(ATAI_NAME, n, f"bubun の発言が、shiryo の発言と違う（{bu}）")]
    text = inp.statement_text(sid)
    ps = inputs.paragraphs(text) if text is not None else []
    a, z = int(g[1]), int(g[2] or g[1])
    if z > len(ps):
        return [Mondai(ATAI_NAME, n, f"bubun の番号の段落が、発言に無い（{bu}）")]
    if not r["inyo"].strip() or shogo.norm(r["inyo"]) not in shogo.norm("\n".join(ps[a - 1:z])):
        return [Mondai(ATAI_NAME, n, f"inyo の字が、bubun の段落に無い（{bu}）")]
    return []


def check(inp, suji_rows, atai_rows, bunsho_rows=None, bubun_rows=None):
    """SCHEMA.md §6.4 と §7.4 の検査。→ (問題の並び, inyo の照合の結果)。"""
    out, res, _ = check_all(inp, suji_rows, atai_rows, bunsho_rows, bubun_rows)
    return out, res


def check_all(inp, suji_rows, atai_rows, bunsho_rows=None, bubun_rows=None):
    """SCHEMA.md §6.4 と §7.4 の検査。→ (問題の並び, inyo の照合の結果, 行と列を指す数値の検査で数えた結果)。

    問題は表と行の番号の順。inp は入力の読み口（inputs.Inputs か、テストの偽の入力）。照合する inyo が無ければ読まない。
    文書の表と文書の部分の表（§7）は、どちらかがあるか、数値の表に bubun か retsu がある行があるときに検査する。
    """
    out = check_suji(suji_rows)
    ids = {r["id"] for r in suji_rows if r["id"]}
    more, quotes = check_atai(atai_rows, ids)
    out += more
    out += check_kakunin(inp, atai_rows)
    out += check_hatsugen(inp, atai_rows)
    more, shurui_kazoe = check_shurui(inp, atai_rows)
    out += more
    res = shogo.check_quotes(inp, quotes) if quotes else shogo.Result()
    for m in res.mismatched:
        out.append(Mondai(ATAI_NAME, m["where"], f"inyo が shiryo の資料の本文に無い（{m['reason']}：{m['source']}）"))
    kazoe = Counter()
    if bunsho_rows is not None or bubun_rows is not None or any(r["bubun"] or r["retsu"] for r in atai_rows):
        more, names = check_bunsho(inp, bunsho_rows or [])
        out += more
        more, index = check_bubun(inp, bubun_rows or [], names)
        out += more
        more, kazoe = check_atai_bubun(inp, atai_rows, bubun_rows or [], index, names)
        out += more
    kazoe = Counter(kazoe)
    kazoe.update(shurui_kazoe)
    order = {SUJI_NAME: 0, ATAI_NAME: 1, BUNSHO_NAME: 2, BUBUN_NAME: 3}
    out.sort(key=lambda m: (order.get(m.hyo, 4), m.gyo))
    return out, res, kazoe


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
    paths7 = {BUNSHO_NAME: os.path.join(d, "bunsho.tsv"), BUBUN_NAME: os.path.join(d, "bubun.tsv")}
    aru = {k: os.path.exists(p) for k, p in paths.items()}
    aru7 = {k: os.path.exists(p) for k, p in paths7.items()}
    if not any(aru.values()) and not any(aru7.values()):
        print(f"表がまだ無い（{SUJI_NAME}・{ATAI_NAME}）")
        return 0
    for a in (aru, aru7):
        if any(a.values()) and not all(a.values()):
            nai = [k for k, v in a.items() if not v]
            print(f"止めた：表が片方しか無い（無い表：{'・'.join(nai)}）", file=sys.stderr)
            return 1
    if not all(aru.values()):
        print(f"止めた：{SUJI_NAME}・{ATAI_NAME} が無いのに、{BUNSHO_NAME}・{BUBUN_NAME} がある", file=sys.stderr)
        return 1
    try:
        suji_rows, p1 = read_suji(_read_file(paths[SUJI_NAME]))
        atai_rows, p2 = read_atai(_read_file(paths[ATAI_NAME]))
        bunsho_rows = bubun_rows = None
        p3 = p4 = []
        if all(aru7.values()):
            bunsho_rows, p3 = read_bunsho(_read_file(paths7[BUNSHO_NAME]))
            bubun_rows, p4 = read_bubun(_read_file(paths7[BUBUN_NAME]))
        need = any(r["inyo"].strip() or r["bubun"] or r["retsu"] or r["shurui"].strip() for r in atai_rows) or bool(bunsho_rows or bubun_rows)
        inp = inputs.Inputs() if need else None
        problems, res, kazoe = check_all(inp, suji_rows, atai_rows, bunsho_rows, bubun_rows)
    except (inputs.InputError, OSError, UnicodeDecodeError) as e:
        print(f"止めた：lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    problems = p1 + p2 + p3 + p4 + problems
    print(f"定義：{len(suji_rows)} 行")
    print(f"数値：{len(atai_rows)} 行")
    c = Counter(r["jotai"] for r in atai_rows)
    for j in JOTAI:
        print(f"  {j}：{c.get(j, 0)} 行")
    hoka = sum(v for k, v in c.items() if k not in JOTAI)
    if hoka:
        print(f"  （4つの状態のどれでもない：{hoka} 行）")
    print(f"inyo の照合：対象 {res.total}、合った {res.matched}、合わなかった {len(res.mismatched)}")
    if bunsho_rows is not None:
        print(f"文書：{len(bunsho_rows)} 行")
        cs, ct = Counter(r["shu"] for r in bubun_rows), Counter(r["torikata"] for r in bubun_rows)
        print(f"文書の部分：{len(bubun_rows)} 行（" + "、".join(f"{x} {cs.get(x, 0)}" for x in SHU) + "。"
              + "、".join(f"{x} {ct.get(x, 0)}" for x in TORIKATA) + "）")
    print(f"数値の表で、bubun がある行：{sum(1 for r in atai_rows if r['bubun'])}、"
          f"retsu がある行：{sum(1 for r in atai_rows if r['retsu'])}")
    print(f"行と列を指す数値の検査：対象 {kazoe['taisho']}、合った {kazoe['atta']}。"
          f"torikata が「読んだ」で検査から外した行 {kazoe['yonda']}")
    kk = count_kankei(suji_rows, atai_rows, bunsho_rows)
    print(f"時点の関係：ato {kk[KANKEI_ATO]}、mae {kk[KANKEI_MAE]}、tochu {kk[KANKEI_TOCHU]}、無し {kk[None]}")
    print(f"shurui の字の検査：対象 {kazoe['shurui_taisho']}。原典の文字が入力に無くて除いた行 {kazoe['shurui_nozoita']}")
    if problems:
        print(f"止めた：問題が {len(problems)} 件", file=sys.stderr)
        for m in problems:
            print(f"  - {m.hyo} の {m.gyo} 行目：{m.naiyo}", file=sys.stderr)
        return 1
    print("問題は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
