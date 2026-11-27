"""マージの前の検査を、まとめて行う（CLAUDE.md「進め方」のマージの項目）。

次の順に行い、1つでも失敗したら、そこで止まって終了コード 1 で終わる。全部通れば 0。
  1. 書き方の検査（tools/bunsho.py）
  2. build/ を消して、全部のテスト
  3. 数値と内容の表と、資料の一覧の表・資料の中の場所の表の検査（tools/suji.py）
  3.4 事項の表の検査（tools/jiko.py）
  3.5 設計の物と関係に当たる表の検査（tools/sekkei.py。当たる表が無い物と関係の数と名前を出す）
  4. 試作のページの作成（tools/build_note.py hoiku、kaigo、kokyo、chiiki）
  5. 数値のページの作成（tools/build_suji.py taiki）
  6. 資料の表のページの作成（tools/build_hyo.py pt:youho/honpen 4）
  7. 資料の表のページの作成（tools/build_hyo.py pt:kodomo/honpen 4）
  8. 資料の表のページの作成（tools/build_hyo.py pt:youho/honpen-202503 6）
  9. 資料の表のページの作成（tools/build_hyo.py doc:shingi-youho-teigen 4）
  10. 資料の表のページの作成（tools/build_hyo.py doc:jigyo-shinkodomoen-kousou 4）
  11. 資料の表のページの作成（tools/build_hyo.py pt:kodomo/honpen 37）
  12. テーマのページの作成（tools/build_theme.py hoiku）
  13. MCP の応答の作成と比較（tools/build_mcp.py。build/mcp/outou.json に作り、リポジトリの mcp/data/outou.json と
      同じであることを確認する。リポジトリのファイルは書き換えない）

使い方：
  python3 -B tools/kensa.py
結果は終了コードで判定する。出力を、最後の行だけを見る命令につないで判定しない。
"""
import os
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
PY = [sys.executable, "-B"]

STEPS = [
    ("書き方の検査", PY + [os.path.join(TOOLS, "bunsho.py")]),
    ("全部のテスト", PY + ["-m", "unittest", "discover", "-s", TOOLS, "-p", "test_*.py"]),
    ("表の検査", PY + [os.path.join(TOOLS, "suji.py")]),
    ("事項の表の検査", PY + [os.path.join(TOOLS, "jiko.py")]),
    ("設計の物と関係に当たる表の検査", PY + [os.path.join(TOOLS, "sekkei.py")]),
    ("試作のページの作成（幼保）", PY + [os.path.join(TOOLS, "build_note.py"), "hoiku"]),
    ("試作のページの作成（高齢者福祉・介護）", PY + [os.path.join(TOOLS, "build_note.py"), "kaigo"]),
    ("試作のページの作成（公共施設の再編）", PY + [os.path.join(TOOLS, "build_note.py"), "kokyo"]),
    ("試作のページの作成（地域のあり方・自治会活動）", PY + [os.path.join(TOOLS, "build_note.py"), "chiiki"]),
    ("数値のページの作成", PY + [os.path.join(TOOLS, "build_suji.py"), "taiki"]),
    ("資料の表のページの作成（再編整備計画の表4）", PY + [os.path.join(TOOLS, "build_hyo.py"), "pt:youho/honpen", "4"]),
    ("資料の表のページの作成（子ども・子育て支援事業計画の表4）",
     PY + [os.path.join(TOOLS, "build_hyo.py"), "pt:kodomo/honpen", "4"]),
    ("資料の表のページの作成（再編整備計画 令和7年3月の版の表6）",
     PY + [os.path.join(TOOLS, "build_hyo.py"), "pt:youho/honpen-202503", "6"]),
    ("資料の表のページの作成（懇話会の提言の表4）",
     PY + [os.path.join(TOOLS, "build_hyo.py"), "doc:shingi-youho-teigen", "4"]),
    ("資料の表のページの作成（基本構想の表4）",
     PY + [os.path.join(TOOLS, "build_hyo.py"), "doc:jigyo-shinkodomoen-kousou", "4"]),
    ("資料の表のページの作成（子ども・子育て支援事業計画の表37）",
     PY + [os.path.join(TOOLS, "build_hyo.py"), "pt:kodomo/honpen", "37"]),
    ("テーマのページの作成（幼保）", PY + [os.path.join(TOOLS, "build_theme.py"), "hoiku"]),
    ("MCP の応答の作成と比較", PY + [os.path.join(TOOLS, "build_mcp.py"), "--out",
                                os.path.join(REPO, "build", "mcp", "outou.json"),
                                "--hikaku", os.path.join(REPO, "mcp", "data", "outou.json")]),
]


def run(steps, cwd=REPO, out=sys.stdout):
    """steps（名前と命令の並び）を順に行う。→ 終了コード（失敗した所で止まって 1。全部通れば 0）。"""
    for name, cmd in steps:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines = r.stdout.rstrip("\n").split("\n")
        if r.returncode != 0:
            print(f"止めた：{name} が失敗した（終了コード {r.returncode}）", file=out)
            print("\n".join(lines[-40:]), file=out)
            return 1
        print(f"通った：{name}（{lines[-1]}）", file=out)
    print("検査は全部通った", file=out)
    return 0


def main():
    shutil.rmtree(os.path.join(REPO, "build"), ignore_errors=True)
    return run(STEPS)


if __name__ == "__main__":
    sys.exit(main())
