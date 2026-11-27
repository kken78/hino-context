"""ID の読み書きと、出典の名前と url（SCHEMA.md §2・§4）。"""
import re

SID = r"[0-9]{10}_[^\s/,:]+_[0-9]{4}"
RE_SP = re.compile(r"sp:(" + SID + r")")
RE_PARA = re.compile(r"sp:(" + SID + r")/([1-9][0-9]*)(?:-([1-9][0-9]*))?")
RE_IQ = re.compile(r"iq:(" + SID + r")")
RE_SQ = re.compile(r"sq:(" + SID + r")")
RE_DOC_PAGE = re.compile(r"doc:([a-z0-9][a-z0-9-]*)/([1-9][0-9]*)")
RE_PT_PAGE = re.compile(r"pt:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_.-]+)/([1-9][0-9]*)")
RE_PLAN = re.compile(r"plan:([a-z0-9][a-z0-9-]*)")
RE_GI = re.compile(r"gi:([0-9]{10})/([^/,\s]+)")
RE_NODE = re.compile(r"node:([a-z0-9][a-z0-9-]*)/([A-Za-z0-9_-]+)")

SEARCH = "https://kken78.github.io/hino-council-search/#sid={}"


class KeyFormError(ValueError):
    """ID の形が SCHEMA.md §2 に合わない。"""

RE_EXT = re.compile(r"ext:([a-z0-9][a-z0-9-]*)/([0-9]+)")


def parse(key):
    """資料の ID → (種類, 部分の組)。種類は sp・para・iq・sq・doc・pt・plan・gi・node・ext。形が違えば KeyFormError。"""
    key = key or ""
    for kind, rx in (("sp", RE_SP), ("para", RE_PARA), ("iq", RE_IQ), ("sq", RE_SQ), ("doc", RE_DOC_PAGE),
                     ("pt", RE_PT_PAGE), ("plan", RE_PLAN), ("gi", RE_GI), ("node", RE_NODE), ("ext", RE_EXT)):
        m = rx.fullmatch(key)
        if m:
            if kind == "para" and m.group(3) and int(m.group(2)) >= int(m.group(3)):
                raise KeyFormError(f"段落の範囲の始めが終わりより小さくない（{key}）")
            return kind, m.groups()
    raise KeyFormError(f"ID の形が SCHEMA.md §2 に合わない（{key!r}）")


def sp(sid):
    return f"sp:{sid}"


def para(sid, a, b=None):
    """段落の ID。b があり a と違えば範囲（a＜b）。"""
    if b is None or b == a:
        return f"sp:{sid}/{a}"
    if a > b:
        raise KeyFormError(f"段落の範囲の始めが終わりより大きい（{a}-{b}）")
    return f"sp:{sid}/{a}-{b}"


def paras_of(hani):
    """段落の ID を「,」でつないだ字 → (sid, 段落の番号) の並び（書いた順）。"""
    out = []
    for part in (hani or "").split(","):
        kind, g = parse(part)
        if kind != "para":
            raise KeyFormError(f"段落の ID でない（{part!r}）")
        a = int(g[1])
        b = int(g[2]) if g[2] else a
        out += [(g[0], i) for i in range(a, b + 1)]
    return out


def sid_of(key):
    """sp・para・iq・sq の ID → sid。"""
    kind, g = parse(key)
    if kind not in ("sp", "para", "iq", "sq"):
        raise KeyFormError(f"発言の ID でない（{key}）")
    return g[0]


def sid_date(sid):
    """sid の2つめの部分の頭8桁 → YYYY-MM-DD。日付で始まらなければ空。"""
    s = sid.split("_")[1]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if re.fullmatch(r"[0-9]{8}", s[:8]) else ""


def ymd(t):
    """YYYY-MM-DD か YYYY-MM → 「YYYY年M月D日」か「YYYY年M月」。"""
    p = t.split("-")
    return f"{p[0]}年{int(p[1])}月" + (f"{int(p[2])}日" if len(p) > 2 else "")


def search_url(sid, p=None):
    return SEARCH.format(sid) + (f"&p={p}" if p else "")


def archived(inp):
    """町の元の url → 保存版の url（hino-town-docs の sources.tsv の archive_url。SCHEMA.md §4）。"""
    if "archived" not in inp._cache:
        inp._cache["archived"] = {r["url"]: r["archive_url"] for r in inp.docs().values()
                                  if r.get("archive_url") and r.get("url")}
    return inp._cache["archived"]


def _page_url(inp, url, page):
    if not url:
        return ""
    return archived(inp).get(url, url) + f"#page={page}"


def source_name(inp, key):
    """資料の ID → 出典の名前（SCHEMA.md §4）。作れなければ空。"""
    kind, g = parse(key)
    if kind == "sp":
        d = sid_date(g[0])
        return f"会議録 {ymd(d)} {inp.speaker(g[0])}" if d and inp.statement_text(g[0]) is not None else ""
    if kind == "doc":
        title = (inp.docs().get(g[0]) or {}).get("title", "")
        return f"「{title}」 {g[1]}ページ" if title else ""
    if kind == "pt":
        name = ((inp.plan(g[0]) or {}).get("meta") or {}).get("name", "")
        return f"{name} {g[2]}ページ" if name else ""
    if kind == "ext":
        r = next((r for r in inp.gaibu() if r["id"] == g[0] and r["page"] == g[1]), None)
        if not r:
            return ""
        hiduke = f"（{r['hiduke']}）" if r["hiduke"] else ""
        return f"{r['hakkou']}「{r['name']}」{hiduke} {g[1]}ページ"
    return ""


def source_url(inp, key, p=None):
    """資料の ID → 出典の url（SCHEMA.md §4）。p は sp の段落の番号（分かるときだけ）。作れなければ空。"""
    kind, g = parse(key)
    if kind in ("sp", "iq", "sq"):
        return search_url(g[0], p) if inp.statement_text(g[0]) is not None else ""
    if kind == "para":
        return search_url(g[0], g[1])
    if kind == "doc":
        return _page_url(inp, (inp.docs().get(g[0]) or {}).get("url", ""), g[1])
    if kind == "pt":
        row = next((r for r in inp.sources_index() if r["id"] == g[0] and r["file"] == g[1] + ".pdf"), None)
        return _page_url(inp, (row or {}).get("url", ""), g[2])
    if kind == "ext":
        return next((r["url"] for r in inp.gaibu() if r["id"] == g[0] and r["page"] == g[1]), "")
    return ""
