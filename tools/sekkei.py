"""設計（docs/hoshin.md 4.2）の物の種類と関係に、当たる表があるかを出す（SCHEMA.md 7.8）。

使い方：
  python3 -B tools/sekkei.py
teigi/sekkei.tsv の name が、docs/hoshin.md 4.2 の表の1列めと合わないか、hyo のファイルが無いと、止まる（終了コード 1）。
「無い」の行は止めずに、数と名前を最後の行に出す。
"""
import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHU = {"mono": "物の種類", "kankei": "物どうしの関係", "toi": "問いと物との関係"}


def hoshin_names(text):
    """docs/hoshin.md の 4.2 の節にある表の、1列めの字の並び（見出しの行と区切りの行を除く）。"""
    sec = text.split("### 4.2", 1)[1].split("\n### ", 1)[0]
    out, head = [], True
    for line in sec.split("\n"):
        if not line.startswith("|"):
            head = True
            continue
        cell = line.strip("|").split("|")[0].strip()
        if head:
            head = False
            continue
        if set(cell) <= set("-: "):
            continue
        out.append(cell)
    return out


def check(rows, names, exists):
    """→ (止める理由の並び, 無い行の並び, 出す行の並び)。exists はパスがあるかを返す関数。"""
    bad, nai, lines = [], [], []
    have = [r["name"] for r in rows]
    for n in names:
        if n not in have:
            bad.append(f"docs/hoshin.md 4.2 の「{n}」が teigi/sekkei.tsv に無い")
    for r in rows:
        if r["shu"] not in SHU:
            bad.append(f"shu が違う（{r['shu']}）：{r['name']}")
        if r["name"] not in names:
            bad.append(f"teigi/sekkei.tsv の「{r['name']}」が docs/hoshin.md 4.2 に無い")
        hyo = r["hyo"]
        if hyo == "無い":
            nai.append(r["name"])
        elif hyo != "持たない":
            for p in hyo.split(";"):
                if not p.startswith("入力:") and not exists(p):
                    bad.append(f"hyo のファイルが無い（{p}）：{r['name']}")
                if not p:
                    bad.append(f"hyo が空：{r['name']}")
        lines.append(f"- {SHU.get(r['shu'], r['shu'])}｜{r['name']}｜{hyo}" + (f"｜{r['chu']}" if r["chu"] else ""))
    return bad, nai, lines


def main():
    with open(os.path.join(REPO, "docs", "hoshin.md"), encoding="utf-8") as fh:
        names = hoshin_names(fh.read())
    with open(os.path.join(REPO, "teigi", "sekkei.tsv"), encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    bad, nai, lines = check(rows, names, lambda p: os.path.exists(os.path.join(REPO, p)))
    print("\n".join(lines))
    if bad:
        print(f"止めた：設計と表の一覧が合わない（{len(bad)} 件）")
        print("\n".join("  - " + b for b in bad))
        return 1
    print(f"設計の物と関係 {len(rows)} のうち、当たる表が無いのは {len(nai)}（{'、'.join(nai)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
