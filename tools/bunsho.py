"""文書と報告の書き方の検査（SKILL.md §3）。

ふつうに使われている言葉を言い換えた書き方（「比較」を「比べ」と書くなど）が、
リポジトリの文書・表・ツールの文に残っていないかを調べる。

使い方：
  python3 -B tools/bunsho.py              リポジトリの文書・表・ツールを調べる
  python3 -B tools/bunsho.py --text FILE  1つのファイル（報告の下書きなど）を調べる
残っていれば、場所・その書き方・使う書き方を出して、終了コード 1 で終わる。
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_PATH = os.path.join(ROOT, "SKILL.md")
HEAD = "| 使わない書き方 | 使う書き方 |"
# 行そのものを調べない表の見出し。SKILL.md §3 のこの表と、docs/design.md 2節の言葉の表（使わない言葉を挙げる表）
SKIP_HEADS = (HEAD, "| 使わない | 使う | 確認する所 |")
TARGETS = ("*.md", "docs/*.md", "teigi/*.tsv", "tools/*.py", "mcp/*.md", "mcp/src/*.ts")
SKIP = ("tools/test_bunsho.py",)   # 検査のテストは、使わない書き方を例として含む


class TableError(ValueError):
    """SKILL.md §3 の表を読めない。"""


def read_table(path=SKILL_PATH):
    """SKILL.md §3 の表 → (正規表現, 表の左の列の字, 使う書き方) の並び。左の列は `…` で囲んだ正規表現。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    try:
        i = lines.index(HEAD)
    except ValueError:
        raise TableError(f"{path}：表の見出しの行（{HEAD}）が無い")
    rows = []
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        m = re.fullmatch(r"`(.+)`", cells[0]) if len(cells) == 2 else None
        if not m or not cells[1]:
            raise TableError(f"{path}：表の行の形が違う（{line}）")
        try:
            rows.append((re.compile(m.group(1)), m.group(1), cells[1]))
        except re.error as e:
            raise TableError(f"{path}：正規表現として読めない（{m.group(1)}：{e}）")
    if not rows:
        raise TableError(f"{path}：表に行が無い")
    return rows


def _mask(line):
    """「」の中（資料の文や、語そのものを挙げた所）と、`…` の中（コード）は調べない。"""
    line = re.sub(r"「[^「」]*」", lambda m: "「" + "＿" * (len(m.group(0)) - 2) + "」", line)
    return re.sub(r"`[^`]*`", lambda m: "＿" * len(m.group(0)), line)


def check_text(text, table, name=""):
    """文 → [(場所, 見つかった書き方, 使う書き方, その行)]。SKILL.md §3 の表と、docs/design.md 2節の言葉の表の、
    行そのものは調べない（SKIP_HEADS）。"""
    out = []
    in_table = False
    for n, line in enumerate(text.splitlines(), 1):
        if line in SKIP_HEADS:
            in_table = True
            continue
        if in_table:
            if line.startswith("|"):
                continue
            in_table = False
        masked = _mask(line)
        for rx, _, use in table:
            for m in rx.finditer(masked):
                out.append((f"{name}:{n}", m.group(0), use, line.strip()[:80]))
    return out


def repo_files():
    files = []
    for pat in TARGETS:
        files += sorted(glob.glob(os.path.join(ROOT, pat)))
    return [f for f in files if os.path.relpath(f, ROOT) not in SKIP]


def check_repo(table):
    out = []
    for f in repo_files():
        with open(f, encoding="utf-8") as fh:
            out += check_text(fh.read(), table, os.path.relpath(f, ROOT))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        table = read_table()
        if argv[:1] == ["--text"] and len(argv) == 2:
            with open(argv[1], encoding="utf-8") as fh:
                hits = check_text(fh.read(), table, os.path.basename(argv[1]))
        elif not argv:
            hits = check_repo(table)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (TableError, OSError) as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    if not hits:
        print(f"使わない書き方は見つからなかった（表 {len(table)} 行）")
        return 0
    print(f"使わない書き方が {len(hits)} 件ある")
    for where, found, use, line in hits:
        print(f"  - {where}：「{found}」→ {use}｜{line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
