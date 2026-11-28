"""第6次日野町総合計画の分野ごとの「関連する個別計画」と「指標と目標値」の表（SCHEMA.md 7.15）。

入力の sogo6.json（tab mokuhyo）から毎回読む。表は持たない。計画の名前の別名だけを、計画の名前の別名の表
（teigi/keikaku-betsumei.tsv）に持つ（依頼者が決めた行）。

使い方：
  python3 -B tools/sogo_kanren.py           分野ごとに、計画の名前と結び付いた計画、結び付かない名前の数を出す
  python3 -B tools/sogo_kanren.py --kensa   別名の表を検査する（違えば終了コード 1）

計画の名前の結び付け（推し量らない）：名前の字を NFKC にして空白を除き、入力の計画（data/plans/*.json の meta.name。
総合計画と、名前が「_」で始まるファイル、試しの計画 zcharttest は除く）と比較する。
(1) 別名の表に名前があれば、その計画（2つ以上もある）。
(2) 無ければ、同じ名前の計画。
(3) 無ければ、両方から版の表記（頭の「第<数>期」「第<数>次」、終わりの「(第<数>期)」「(第<数>次)」「(改定)」）を除いて
    比較し、同じ計画が1つだけなら、その計画。2つ以上か、無ければ、結び付けない。
結び付いた計画のうち、資料の一覧の表（teigi/bunsho.tsv）に、その計画の資料（pt:<計画の id>/… か plan:<計画の id>）が
あるものは、その資料の ID を持つ。計画ライブラリに無い資料も、資料の一覧の表の namae と、上と同じ正規化のあとで同じ名前なら、
その資料の ID を持つ（日野町人材育成基本方針など）。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bunya as bu  # noqa: E402
import inputs  # noqa: E402

BETSUMEI_PATH = os.path.join(inputs.ROOT, "teigi", "keikaku-betsumei.tsv")
BETSUMEI_COLS = ["namae", "plan", "riyu"]
KANREN_H = "関連する個別計画"          # 入力の intro の h の字
NOZOKU = {bu.PLAN, "zcharttest"}
HAN = [r"^第[0-9]+[期次]", r"\(第[0-9]+[期次]\)$", r"\(改定\)$"]
ICCHI, HAN_ICCHI, BETSUMEI, NASHI = "一致", "版の表記を除いて一致", "別名の表", "無し"


class KanrenError(Exception):
    pass


def nz(s):
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", s))


def nohan(s):
    for _ in range(2):
        for h in HAN:
            s = re.sub(h, "", s)
    return s


def read_betsumei(path=BETSUMEI_PATH):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), BETSUMEI_COLS)


def keikaku_namae(inp):
    """入力の計画の id → meta.name（総合計画、「_」で始まるファイル、zcharttest を除く）。"""
    out = {}
    for path in inp.files(inputs.SP, "data/plans/*.json"):
        pid = os.path.basename(path)[:-5]
        if pid.startswith("_") or pid in NOZOKU:
            continue
        out[pid] = inp.read_json(inputs.SP, path)["meta"]["name"]
    return out


def check_betsumei(rows, plans):
    """別名の表の検査 → 問題の並び。namae と plan と riyu が空でなく、plan が入力の計画にあり、(namae, plan) が重ならないこと。"""
    bad, seen = [], set()
    for i, r in enumerate(rows, 2):
        if not (r["namae"] and r["plan"] and r["riyu"]):
            bad.append(f"{i} 行目：namae、plan、riyu のどれかが空")
        elif r["plan"] not in plans:
            bad.append(f"{i} 行目：plan「{r['plan']}」が入力の計画に無い")
        elif (r["namae"], r["plan"]) in seen:
            bad.append(f"{i} 行目：namae と plan の組が重なる")
        seen.add((r["namae"], r["plan"]))
    return bad


def musubu(namae, plans, betsumei):
    """総合計画の字の計画の名前 → (結び方, [計画の id])。"""
    bm = [r["plan"] for r in betsumei if r["namae"] == namae]
    if bm:
        return BETSUMEI, bm
    n = nz(namae)
    ex = [k for k, v in plans.items() if nz(v) == n]
    if ex:
        return ICCHI, ex
    nh = [k for k, v in plans.items() if nohan(nz(v)) == nohan(n)]
    if len(nh) == 1:
        return HAN_ICCHI, nh
    return NASHI, []


def bunsho_of_plan(pid, bunsho_ids):
    """計画の id → 資料の一覧の表にある、その計画の資料の ID の並び（表の順）。"""
    return [b for b in bunsho_ids if b == f"plan:{pid}" or b.startswith(f"pt:{pid}/")]


def raw_mokuhyo(inp):
    """sogo6.json の tab mokuhyo の blocks。数値は、入力の字のまま（JSON の数の字）にする。"""
    text = inp.read_text(inputs.SP, f"data/plans/{bu.PLAN}.json")
    p = json.loads(text, parse_float=str, parse_int=str)
    t = next((t for t in p["tabs"] if t["id"] == bu.TAB_BUNYA), None)
    if t is None:
        raise KanrenError(f"{bu.PLAN}.json に tab {bu.TAB_BUNYA} が無い")
    return t["blocks"]


def page_ids(source):
    """「honpen-03 p.5-6」→ ['pt:sogo6/honpen-03/5', 'pt:sogo6/honpen-03/6']。"""
    m = bu.RE_SOURCE.fullmatch(source or "")
    if not m:
        raise KanrenError(f"source の形が違う（{source}）")
    f, a, z = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
    return [f"pt:{bu.PLAN}/{f}/{x}" for x in range(a, z + 1)]


def matome(inp, bunsho, betsumei=None):
    """bunsho は資料の一覧の表の行。
    → 分野の番号 → dict(kanren=dict(h, tokoro, keikaku=[dict(namae, musubi, plans=[(id, 入力の名前, [資料の ID])],
    shiryo=[資料の一覧の表の namae が同じ資料の ID])]) か None,
    shihyo=[dict(tokoro, head, rows, note)])。別名の表の問題か、入力の形が違えば KanrenError。"""
    plans = keikaku_namae(inp)
    bunsho_ids = [r["bunsho"] for r in bunsho]
    betsumei = read_betsumei() if betsumei is None else betsumei
    bad = check_betsumei(betsumei, plans)
    if bad:
        raise KanrenError("計画の名前の別名の表：" + "；".join(bad))
    out = {}
    for b in raw_mokuhyo(inp):
        if b.get("type") == "programs":
            for g in b["groups"]:
                x = out.setdefault(g["no"], dict(name=g["name"], kanren=None, shihyo=[]))
                for sg in g["subgroups"]:
                    for ib in sg.get("intro", []):
                        if ib["h"] != KANREN_H:
                            continue
                        if x["kanren"] is not None:
                            raise KanrenError(f"分野 {g['no']} に「{KANREN_H}」が2つある")
                        kei = []
                        for nm in ib["b"].split("／"):
                            how, ids = musubu(nm, plans, betsumei)
                            kei.append(dict(namae=nm, musubi=how,
                                            plans=[(k, plans[k], bunsho_of_plan(k, bunsho_ids)) for k in ids],
                                            shiryo=[r["bunsho"] for r in bunsho if nz(r["namae"]) == nz(nm)]))
                        x["kanren"] = dict(h=ib["h"], tokoro=page_ids(b["source"]), keikaku=kei)
        elif b.get("type") == "table":
            label = (b.get("fold") or {}).get("label", "")
            hit = [no for no, x in out.items() if label == f"{no} {x['name']}"]
            if len(hit) != 1:
                raise KanrenError(f"指標の表の fold の label「{label}」が、1つの分野に当たらない")
            out[hit[0]]["shihyo"].append(dict(tokoro=page_ids(b["source"]), head=b["head"], rows=b["rows"],
                                              note=b.get("note", "")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kensa", action="store_true")
    a = ap.parse_args(argv)
    inp = inputs.Inputs()
    import build_theme as bt
    tables, _ = bt.read_tables()
    try:
        m = matome(inp, tables["bunsho"])
    except (KanrenError, inputs.InputError) as e:
        print(f"止めた：{e}", file=sys.stderr)
        return 1
    if a.kensa:
        print(f"計画の名前の別名の表：問題なし（{len(read_betsumei())} 行）")
        return 0
    n = {ICCHI: 0, HAN_ICCHI: 0, BETSUMEI: 0, NASHI: 0}
    for no, x in m.items():
        for k in (x["kanren"] or {}).get("keikaku", []):
            n[k["musubi"]] += 1
            ids = "、".join(f"{pid}{'（' + '・'.join(bs) + '）' if bs else ''}" for pid, _, bs in k["plans"])
            print(f"{no}\t{k['namae']}\t{k['musubi']}\t{ids}\t{'・'.join(k['shiryo'])}")
    print(f"名前 {sum(n.values())}：" + "、".join(f"{k} {v}" for k, v in n.items())
          + f"。指標の表 {sum(len(x['shihyo']) for x in m.values())}（表の無い分野 "
          + "、".join(no for no, x in m.items() if not x["shihyo"]) + "）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
