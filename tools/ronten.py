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


def katei(inp, theme):
    """過程の記録のうち、その題材の行（step の順）。"""
    return sorted([r for r in _confirmed(inp, KATEI) if r["theme"] == theme], key=lambda r: int(r["step"]))


def taio_shitsumon(inp, questions):
    """問いと事項の対応のうち、question が questions のどれかの行がある question の集まり（point は問わない）。"""
    return {r["question"] for r in _confirmed(inp, TAIO) if r["question"] in questions}


def taio(inp, points, questions):
    """問いと事項の対応のうち、point が points のどれかで、question が questions のどれかの行。"""
    return [r for r in _confirmed(inp, TAIO) if r["point"] in points and r["question"] in questions]
