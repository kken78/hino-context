"""MCP の応答の JSON（mcp/data/outou.json）から、ツールと引数の組の応答の文を出す（docs/mcp.md 3節）。

MCP サーバー（mcp/src/index.ts）と同じ引き方をする：ツールの引数の順に、値がある引数を「名前=値」にして「&」でつないだ字で
引き、無ければ、そのツールの該当する組が無いときの文を出す。直しの前と後で、同じ問いへの答えを比較するために使う。

使い方：
  python3 -B tools/hiku.py [--json <ファイル>] <ツール> [<引数の名前>=<値> …]
  python3 -B tools/hiku.py [--json <ファイル>] <ツール> [<値> …]      （値だけのときは、ツールの引数の順に、その引数の値とする）
例：
  python3 -B tools/hiku.py field ㉝
  python3 -B tools/hiku.py issue b33-07
  python3 -B tools/hiku.py issue "b33-k1:職員の育成と人事評価"
  python3 -B tools/hiku.py --json /home/claude/an/outou-mae.json issue b33-07 page=2
ツールの名前が違うか、引数の名前がツールに無いときは、終了コード 2。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(os.path.dirname(HERE), "mcp", "data", "outou.json")


def kagi(tool, args):
    """ツール（JSON の tools の1つ）と、引数の名前 → 値 → 応答を引く字（mcp/src/index.ts の kagi と同じ）。"""
    out = []
    for a in tool["args"]:
        v = args.get(a["name"])
        if v is None:
            continue
        v = str(v).strip()
        if v != "":
            out.append(f"{a['name']}={v}")
    return "&".join(out)


def hiku(data, name, args):
    """→ 応答の文。ツールが無ければ KeyError。"""
    tool = next(t for t in data["tools"] if t["name"] == name)
    i = data["outou"].get(name, {}).get(kagi(tool, args))
    return data["nai"][name] if i is None else data["bun"][i]


def hikisu(tool, words):
    """コマンドの引数の並び → 引数の名前 → 値。「名前=値」でない字は、ツールの引数の順に、その引数の値とする。名前が無ければ ValueError。"""
    names = [a["name"] for a in tool["args"]]
    out, rest = {}, []
    for w in words:
        n, sep, v = w.partition("=")
        if sep and n in names:
            out[n] = v
        else:
            rest.append(w)
    aki = [x for x in names if x not in out]
    if len(rest) > len(aki):
        raise ValueError("引数が多すぎる")
    out.update(zip(aki, rest))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="MCP の応答の JSON から、応答の文を出す")
    p.add_argument("--json", default=OUT_PATH)
    p.add_argument("tool")
    p.add_argument("args", nargs="*")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    with open(a.json, encoding="utf-8") as f:
        data = json.load(f)
    tool = next((t for t in data["tools"] if t["name"] == a.tool), None)
    if tool is None:
        print(f"ツール {a.tool} が無い（{'、'.join(t['name'] for t in data['tools'])}）", file=sys.stderr)
        return 2
    try:
        args = hikisu(tool, a.args)
    except ValueError as e:
        print(f"{e}（{a.tool} の引数：{'、'.join(x['name'] for x in tool['args'])}）", file=sys.stderr)
        return 2
    print(hiku(data, a.tool, args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
