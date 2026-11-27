"""引用をもとの資料と照合する（SCHEMA.md §3）。結果は、件数と、合わなかった行の一覧で返す。"""
import re
import unicodedata
from dataclasses import dataclass, field

import keys
from inputs import paragraphs

# JavaScript の \s と同じ空白（hino-ronten の正規化と同じ）
WHITESPACE = "[\t\n\v\f\r    -     　﻿]"


def norm(text):
    """SCHEMA.md §3 の正規化：NFKC → 改行に続くページ番号の除去 → 「-数字-」の除去 → 空白の除去。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\n[0-9]+-[0-9]+", "", text)
    text = re.sub(r"-[0-9]+-", "", text)
    return re.sub(WHITESPACE, "", text)


def page_of(text, page):
    if text is None:
        return None
    parts = text.split("\f")
    return parts[page - 1] if 1 <= page <= len(parts) else None


def source_texts(inp, key):
    """資料の ID → 照合する本文の並び。ID の形が違うか、入力に無ければ None。"""
    try:
        kind, g = keys.parse(key)
    except keys.KeyFormError:
        return None
    if kind == "sp":
        t = inp.statement_text(g[0])
        return None if t is None else [t]
    if kind == "doc":
        if g[0] not in inp.docs():
            return None
        out = [page_of(inp.doc_text(g[0], layer), int(g[1])) for layer in ("text", "text_raw")]
    elif kind == "ext":
        out = [r["ji"] for r in inp.gaibu() if r["id"] == g[0] and r["page"] == g[1]]
    elif kind == "pt":
        out = [page_of(inp.pt_text(g[0], g[1], layer), int(g[2])) for layer in ("text", "text_raw")]
    else:
        return None
    out = [t for t in out if t is not None]
    return out or None


@dataclass
class Result:
    total: int = 0
    matched: int = 0
    mismatched: list = field(default_factory=list)   # {"where", "source", "quote", "reason"}

    def add(self, other):
        self.total += other.total
        self.matched += other.matched
        self.mismatched += other.mismatched


def check_quotes(inp, rows):
    """rows は {"where", "source", "quote"} の並び。引用が資料の本文にあるかを1件ずつ確認する。"""
    res = Result()
    for r in rows:
        res.total += 1
        texts = source_texts(inp, r["source"])
        q = norm(r["quote"])
        if not q:
            reason = "引用が空"
        elif texts is None:
            reason = "資料が入力に無いか、照合できない資料の ID"
        elif not any(q in norm(t) for t in texts):
            reason = "引用が資料の本文に無い"
        else:
            res.matched += 1
            continue
        res.mismatched.append(dict(r, reason=reason))
    return res


def check_paras(inp, rows):
    """rows は {"where", "hani"} の並び。段落の ID が、その発言の段落を指しているかを、段落ごとに確認する。"""
    res = Result()
    for r in rows:
        try:
            ps = keys.paras_of(r["hani"])
        except keys.KeyFormError as e:
            res.total += 1
            res.mismatched.append({"where": r["where"], "source": r["hani"], "quote": "", "reason": str(e)})
            continue
        for sid, n in ps:
            res.total += 1
            t = inp.statement_text(sid)
            if t is not None and 1 <= n <= len(paragraphs(t)):
                res.matched += 1
            else:
                res.mismatched.append({"where": r["where"], "source": keys.para(sid, n), "quote": "",
                                       "reason": "発言が無いか、その番号の段落が無い"})
    return res


def para_of_quote(text, quote):
    """引用が発言のどの段落にあるか。1つの段落の中に1か所だけあれば、その番号。ほかは None。"""
    q = norm(quote)
    hits = [i for i, p in enumerate(paragraphs(text), 1) if q and q in norm(p)]
    return hits[0] if len(hits) == 1 and norm(text).count(q) == 1 else None
