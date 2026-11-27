"""hino-ronten の題材の定義と、確定した記録の読み込み（SCHEMA.md §1）。

lock の SHA の hino-ronten から読む。records の表は、status が confirmed の行だけを返す。
"""
THEMES = "ref/themes.tsv"
LINEAGE = "ref/lineage.tsv"
KOTOGARA = "records/kotogara.tsv"
KATEI = "records/katei.tsv"
TAIO = "records/taio.tsv"
CONFIRMED = "confirmed"


def themes(inp, theme):
    """題材の定義の、その題材の行（themes.tsv には status の列が無い。依頼者が決めた行だけが入っている）。"""
    return [r for r in inp.ronten_tsv(THEMES) if r["theme"] == theme]


def lineage_plans(inp, series):
    """系列の表（ref/lineage.tsv）のうち、series が series のどれかの行の plan（空の行は除く）の集まり（SCHEMA.md §1）。"""
    return {r["plan"] for r in inp.ronten_tsv(LINEAGE) if r["series"] in series and r["plan"]}


def _confirmed(inp, path):
    return [r for r in inp.ronten_tsv(path) if r["status"] == CONFIRMED]


def kotogara(inp, points):
    """事柄の記録のうち、point が points のどれかの行。"""
    return [r for r in _confirmed(inp, KOTOGARA) if r["point"] in points]


# 過程の記録のうち、ページと MCP の応答の検査で止まるため、出さない行（SCHEMA.md §1。2026-11-27 の指示）。
# (題材, step) → 理由。理由は、行がその条件に当たることを katei_dasanai で確認する（当たらなくなったら止まる）。
KARA_NASHI = "from が空"
GIAN = "sources に議案の ID（gi:）がある"
KATEI_DASANAI = {("kaigo", "2"): KARA_NASHI, ("kaigo", "4"): KARA_NASHI, ("kaigo", "5"): KARA_NASHI,
                 ("kaigo", "6"): KARA_NASHI, ("kaigo", "8"): GIAN, ("kaigo", "9"): KARA_NASHI,
                 ("kaigo", "12"): KARA_NASHI, ("chiiki", "6"): GIAN, ("chiiki", "8"): KARA_NASHI,
                 ("chiiki", "10"): GIAN}


def _ataru(r, riyu):
    if riyu == KARA_NASHI:
        return not r["from"].strip()
    if riyu == GIAN:
        return any(s.strip().startswith("gi:") for s in r["sources"].split(","))
    return False


def katei_dasanai(inp, theme):
    """出さない過程の記録の行と理由の並び → ([(行, 理由)], 問題の並び)。
    KATEI_DASANAI にある行が無いか、理由の条件に当たらなければ、問題として返す（ページと応答を作らずに止まる）。"""
    rows = {(r["theme"], r["step"]): r for r in _confirmed(inp, KATEI)}
    out, problems = [], []
    for (th, step), riyu in KATEI_DASANAI.items():
        if th != theme:
            continue
        r = rows.get((th, step))
        if r is None or not _ataru(r, riyu):
            problems.append(f"過程の記録 {th} step {step}：出さない行としたが、確定済みの行が無いか、理由（{riyu}）に当たらない")
        else:
            out.append((r, riyu))
    return out, problems


def katei(inp, theme):
    """過程の記録のうち、その題材の行（step の順）。KATEI_DASANAI の行は除く。"""
    return sorted([r for r in _confirmed(inp, KATEI) if r["theme"] == theme
                   and (r["theme"], r["step"]) not in KATEI_DASANAI], key=lambda r: int(r["step"]))


def taio_shitsumon(inp, questions):
    """問いと事項の対応のうち、question が questions のどれかの行がある question の集まり（point は問わない）。"""
    return {r["question"] for r in _confirmed(inp, TAIO) if r["question"] in questions}


def taio_points(inp, questions):
    """問いと事項の対応のうち、question が questions のどれかの行の point の集まり。"""
    return {r["point"] for r in _confirmed(inp, TAIO) if r["question"] in questions}


def taio(inp, points, questions):
    """問いと事項の対応のうち、point が points のどれかで、question が questions のどれかの行。"""
    return [r for r in _confirmed(inp, TAIO) if r["point"] in points and r["question"] in questions]
