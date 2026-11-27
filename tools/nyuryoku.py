"""入力の5つのリポジトリの全部を、資料のページの ID か言葉で検索する（CLAUDE.md「入力の全体を確認してから始める」）。

inputs.lock.json に書いた範囲だけでなく、リポジトリの作業ツリーの全部（.git を除く）を調べる。行や項目を足す文案を書く前に、
同じ資料のページや言葉が、入力のどこにすでにあるかを見つけるために使う。見つけるだけで、何も書き換えない。

使い方：
  python3 -B tools/nyuryoku.py pt:youho/honpen/34
  python3 -B tools/nyuryoku.py 再編整備スケジュール 開設を目指
  python3 -B tools/nyuryoku.py --honbun pt:youho/honpen/34     （もとの資料から取り出した文字と OCR の下書きも調べる）

- 資料のページの ID（pt:<計画>/<ファイル>/<ページ>、doc:<資料>/<ページ>）は、頭の「pt:」「doc:」を除いた字でも探す。
- 計画ライブラリは、印刷のページ番号で「honpen p.32」のように書いている。pt: の ID は、計画のデータの pdf_page_offset を
  引いて、その形でも探す（その計画のファイルの中だけを調べる）。
- もとの資料から取り出した文字（data/text、data/text_raw）と OCR の下書き（data/ocr）は、資料そのものなので、
  --honbun を付けたときだけ調べる。
出力は、リポジトリごとに、ファイル、見つかった行の数、はじめの3行。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputs  # noqa: E402

HONBUN = ("data/text/", "data/text_raw/", "data/ocr/")
MIRU = (".tsv", ".json", ".md", ".txt", ".csv", ".yml", ".yaml")
PAGE_ID = re.compile(r"^(pt|doc):(.+)/([0-9]+)$")


def sagasu_ji(term, plans_dir=None):
    """検索する字 → [(字, ファイルの名前に含まれるべき字。無ければ None)]。"""
    out = [(term, None)]
    m = PAGE_ID.match(term)
    if not m:
        return out
    out.append((f"{m.group(2)}/{m.group(3)}", None))
    if m.group(1) == "pt" and "/" in m.group(2):
        plan, file = m.group(2).split("/", 1)
        base = re.sub(r"-[0-9]{6}$", "", file)            # honpen-202503 → honpen（改正前のファイルは、計画のデータに無い）
        path = os.path.join(plans_dir or os.path.join(inputs.repo_dir(inputs.SP), "data", "plans"), f"{plan}.json")
        try:
            with open(path, encoding="utf-8") as f:
                offs = set(re.findall(r'"pdf_page_offset"\s*:\s*(-?[0-9]+)', f.read()))
        except OSError:
            offs = set()
        off = int(offs.pop()) if len(offs) == 1 else None    # 計画のデータに1つだけ書いてあるときに使う
        if off is not None and base == file:
            out.append((f"{base} p.{int(m.group(3)) - off}", f"/{plan}."))
    return out


def sagasu(root, terms, honbun=False):
    """root の下の全部のファイル → [(ファイル, 見つかった行の数, はじめの3行)]。terms は sagasu_ji の出力をつないだもの。"""
    out = []
    for d, ds, fs in os.walk(root):
        ds[:] = sorted(x for x in ds if x not in (".git", "node_modules"))
        for name in sorted(fs):
            path = os.path.join(d, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if not name.endswith(MIRU) or (not honbun and rel.startswith(HONBUN)):
                continue
            use = [ji for ji, naka in terms if naka is None or naka in "/" + rel]
            if not use:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    hits = [line.rstrip("\n") for line in f if any(ji in line for ji in use)]
            except (OSError, UnicodeDecodeError):
                continue
            if hits:
                out.append((rel, len(hits), hits[:3]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ji", nargs="+", help="資料のページの ID か、資料の中の言葉")
    ap.add_argument("--honbun", action="store_true", help="もとの資料から取り出した文字と OCR の下書きも調べる")
    a = ap.parse_args(argv)
    terms = [t for x in a.ji for t in sagasu_ji(x)]
    print("検索した字：" + "、".join(ji + (f"（{naka} を含むファイルだけ）" if naka else "") for ji, naka in terms))
    total = 0
    for repo in inputs.REPOS:
        root = inputs.repo_dir(repo)
        if not os.path.isdir(root):
            print(f"\n## {repo}\n（取得していない：{root}）")
            continue
        hits = sagasu(root, terms, a.honbun)
        print(f"\n## {repo}（ファイル {len(hits)}）")
        for rel, n, lines in hits:
            total += n
            print(f"- {rel}：{n} 行")
            for line in lines:
                print("    " + (line if len(line) <= 160 else line[:160] + "…"))
    print(f"\n見つかった行の合計：{total}" + ("" if a.honbun else "（もとの資料から取り出した文字と OCR の下書きは調べていない）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
