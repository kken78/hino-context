"""論点を並べる所（MCP の theme と field の応答、試作のページ）の、いちばん下の見出し（章立ての要素、基本施策、まとまり）ごとに、
論点の数を数え、jiko.MIDASHI_JOGEN を超える見出しの数と名前を出す（SCHEMA.md 7.9。2026-11-28）。止める条件にはしない。

使い方：
  python3 -B tools/midashi.py [--jiko <事項の表のファイル>]
  --jiko は、直しの前の事項の表で数えて比較するためのもの（既定は teigi/jiko.tsv）。
最後の行に、超える見出しの数と名前を出す（tools/kensa.py が、この行を出す）。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_bunya as bb  # noqa: E402
import build_mcp  # noqa: E402
import bunya as bu  # noqa: E402
import inputs  # noqa: E402
import jiko  # noqa: E402

UE = {"nashi": "章立てに入らない論点", "theme": "", "kihon-nashi": "基本施策に入れていない論点",
      "theme-ronten": "テーマごとに読んだ論点", "hoka": ""}


def namae(T, g):
    """見出しの名前（テーマの名前、上の見出し、まとまりの名前を「／」でつないだもの）。"""
    ue = g["ue"]
    if ue[0] == "youso":
        u = ue[1]["name"]
    elif ue[0] == "kihon":
        u = ue[1][0] + ue[1][1]
    else:
        u = UE[ue[0]]
    return "／".join(x for x in (T["theme"], u, g["mt"]) if x)


def kazoeru(inp):
    """→ (見出しの数, [(名前, 論点の数)]。論点の数が jiko.MIDASHI_JOGEN を超える見出し。論点の数の多い順)。"""
    notes = {th: (T, None) for th, T in list(build_mcp.read_notes(inp).items()) + list(build_mcp.read_bunya_notes(inp).items())}
    kk = bu.keikaku(inp)
    m = {"bunya": {x["no"]: x for h in kk["hashira"] for x in h["bunya"]}}
    gun = bb.midashi_gun(inp, notes, m)
    ooi = [(namae(notes[g["theme"]][0], g), len(g["rows"])) for g in gun if len(g["rows"]) > jiko.MIDASHI_JOGEN]
    return len(gun), sorted(ooi, key=lambda x: -x[1])


def main(argv=None):
    p = argparse.ArgumentParser(description="見出しごとの論点の数を数える")
    p.add_argument("--jiko", default=jiko.PATH)
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    jiko.read.__defaults__ = (a.jiko,)     # 事項の表を読む関数の既定のファイルを替える（read_notes などが、引数なしで読むため）
    try:
        inp = inputs.Inputs()
        zen, ooi = kazoeru(inp)
    except (inputs.InputError, bu.BunyaError, OSError, ValueError) as e:
        print(f"止めた：表か入力を読めない\n{e}", file=sys.stderr)
        return 1
    for n, k in ooi:
        print(f"  {n}：{k}")
    print(f"見出し {zen} のうち、論点が {jiko.MIDASHI_JOGEN} を超える見出し {len(ooi)}"
          + (f"（{'、'.join(f'{n} {k}' for n, k in ooi)}）" if ooi else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
