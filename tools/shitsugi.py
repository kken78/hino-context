"""議案への質疑の読み取りの結果（taio/yomi-shitsugi/）から、質問と事項の対応の表（taio/shudai.tsv）と、質問が取り上げた
資料と出来事の表（taio/konkyo.tsv）の、議案への質疑の行を作る（SCHEMA.md 7.10。2026-11-28）。行は tools/yomi.py と
tools/konkyo.py が、一般質問の行のあとに置く。このファイルは、行を作る関数と検査と、題の字を出す関数を持つ。

使い方：
  python3 -B tools/shitsugi.py           数と、入れなかった行の内訳を出す（表は書かない。表は tools/yomi.py と tools/konkyo.py が書く）
  python3 -B tools/shitsugi.py --nashi   入れ先の無い候補の名前と、入れなかった基本施策の行の一覧を出す

読むもの（taio/yomi-shitsugi/）：
  taba.json                 束の並び。束ごとに、読んだ質疑の区切りの ID（sq:<台帳の from>）の並び（0から数える）
  <読み手>-<束>-shudai.tsv  列 question、gian、point、hani、mayoi、riyu（point は総合計画の基本施策の名前）
  <読み手>-<束>-konkyo.tsv  列 question、gian、aite、hani
  <読み手>-<束>-kouho.tsv   列 question、gian、bunya、hani、namae、mayoi、riyu（bunya は分野の番号の2桁か空）
候補の名前と入れ先の表 teigi/shitsugi-kouho.tsv：列 bunya、namae、saki、chu。

行を作る決まり（SCHEMA.md 7.10）：
  問いの単位は、質疑の台帳の区切り（question）× 議案（行の n に、議案の番号の字を書く）。
  基本施策の行（point）は、事項の表の、その名前の行（基本施策の行。4つのテーマの中心の分野は、テーマの事項に同じ名前の行が
  あるときだけ）に付ける。行の theme は、その基本施策の分野のテーマ（中心の分野は、そのテーマ）。当たる行が無ければ入れない。
  候補の行は、表の saki が事項の ID なら、その事項に付ける。行の theme は、候補の分野のテーマがその事項の theme の列に
  あればそれ、無ければ（読み手が分野を空にした候補を含む）、その事項の theme の列の最初のテーマ。saki が分野に無い話題の ID か
  空（入れ先なし）の候補は入れない。
  テーマごとに、質問と議案と事項の組で、tools/yomi.py の kumi_gyo と同じ決まりで一致と1回だけの行にする。
  読み手が riyu に「字は議第N号の話」と書いた行（台帳の議案と、段落の字が審議している議案が合わない行）は、chu に、その字と
  読み手を書く（字の議案 RE_JI。画面と応答の文は docs/design.md）。
  資料と出来事の行は、同じ読み手の、同じ質問と議案の、段落が重なる事項の行（候補から入れた行を含む）のテーマの行にする。
  無ければ、もう1人の読み手の行で見る。それでも無ければ入れない。名前は、そのテーマの資料と出来事の名前の表で決める
  （tools/yomi.py の aite_of）。
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402
import yomi as ym  # noqa: E402

DIR = os.path.join(inputs.ROOT, "taio", "yomi-shitsugi")
TABA_PATH = os.path.join(DIR, "taba.json")
KOUHO_PATH = os.path.join(inputs.ROOT, "teigi", "shitsugi-kouho.tsv")
KOUHO_COLS = ["bunya", "namae", "saki", "chu"]
FILE_COLS = {"shudai": ["question", "gian", "point", "hani", "mayoi", "riyu"],
             "konkyo": ["question", "gian", "aite", "hani"],
             "kouho": ["question", "gian", "bunya", "hani", "namae", "mayoi", "riyu"]}
YOMITE = ym.YOMITE
# 4つのテーマの中心の分野（分野の論点は無く、テーマの事項に付ける。SCHEMA.md 7.9）
THEME_OF_BUNYA = {"01": "hoiku", "18": "kaigo", "30": "chiiki", "32": "kokyo"}
RE_JI = re.compile(r"字は((?:議第|報第|決議案第)[0-9]+号)の話")
RE_GIAN = re.compile(r"(議第|報第|決議案第)([0-9]+)号")
GIAN_SONOTA = ("議題外", "不明")      # 台帳の bill の、議案の番号でない字（議案の題は無い）
RE_CHU_JI = re.compile(r"字は((?:議第|報第|決議案第)[0-9]+号)の話：読み手 ([ab](?:、[ab])*)")
WADAI_HEAD = "wadai-"


class ShitsugiError(ValueError):
    """読み取りの結果か表が無いか、形が違う。"""


def read_taba(path=TABA_PATH):
    """束の並び → 束ごとの、質疑の区切りの ID の並び。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def shitsumon(path=TABA_PATH):
    """読んだ質疑の区切りの ID の並び（束の順）。同じ区切りが2回あれば ShitsugiError。"""
    qs = [q for t in read_taba(path) for q in t]
    dup = sorted({q for q in qs if qs.count(q) > 1})
    if dup:
        raise ShitsugiError(f"質疑の区切りが束に2回ある（{'、'.join(dup)}）")
    return qs


def _read(path, cols):
    if not os.path.exists(path):
        raise ShitsugiError(f"ファイルが無い（{os.path.relpath(path, inputs.ROOT)}）")
    with open(path, encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        if rd.fieldnames != cols:
            raise ShitsugiError(f"{os.path.relpath(path, inputs.ROOT)} の列が違う（{rd.fieldnames}）")
        return list(rd)


def read_yomi(d=DIR):
    """読み手の出力 → {種類: [行（yomite、taba を付けたもの）]}。束の外の質問の行があれば ShitsugiError。"""
    out = {k: [] for k in FILE_COLS}
    bad = []
    for n, qs in enumerate(read_taba(os.path.join(d, "taba.json"))):
        qs = set(qs)
        for y in YOMITE:
            for k, cols in FILE_COLS.items():
                for i, r in enumerate(_read(os.path.join(d, f"{y}-{n}-{k}.tsv"), cols), 2):
                    if r["question"] not in qs:
                        bad.append(f"{y}-{n}-{k}.tsv {i} 行目：質問 {r['question']} が束 {n} に無い")
                    out[k].append(dict(r, yomite=y, taba=n))
    if bad:
        raise ShitsugiError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return out


def read_kouho(path=KOUHO_PATH):
    with open(path, encoding="utf-8") as f:
        return inputs.read_tsv(f.read(), os.path.relpath(path, inputs.ROOT), KOUHO_COLS)


def bunya2(no):
    """分野の番号（入力の字。①〜㉞）→ 2桁の字（①は 01）。"""
    return jiko.bunya_theme(no)[1:]


def theme_of_bunya(b):
    """分野の2桁 → 行の theme（中心の分野は、そのテーマ。ほかは分野のテーマ）。"""
    return THEME_OF_BUNYA.get(b) or f"b{b}"


def point_bunya(kihon_names):
    """入力の総合計画の基本施策（字 → 名前）→ 基本施策の名前 → 分野の2桁。同じ名前が2つの分野にあれば ShitsugiError。"""
    out = {}
    for k, name in kihon_names.items():
        b = bunya2(jiko.kihon_bunya(k)[0])
        if name in out and out[name] != b:
            raise ShitsugiError(f"基本施策の名前「{name}」が、2つの分野にある")
        out[name] = b
    return out


def check_kouho(rows, yomi, jiko_ids, wadai_ids):
    """候補の名前と入れ先の表の検査 → 問題の並び。(bunya, namae) が重ならず、saki が空か、事項の表の ID か、分野に無い話題の
    名前の表の ID であること。読み取りの結果の候補の (bunya, namae) の全部に行があり、読み取りの結果に無い行が無いこと。"""
    bad = []
    seen = set()
    for i, r in enumerate(rows, 2):
        k = (r["bunya"], r["namae"])
        if k in seen or not r["namae"]:
            bad.append(f"{i} 行目：bunya と namae の組が重なっているか、namae が空（{r['bunya']} {r['namae']}）")
        seen.add(k)
        if r["bunya"] and not re.fullmatch(r"0[1-9]|[12][0-9]|3[0-4]", r["bunya"]):
            bad.append(f"{i} 行目：bunya が 01〜34 の2桁でない（{r['bunya']}）")
        s = r["saki"]
        if s and s not in jiko_ids and s not in wadai_ids:
            bad.append(f"{i} 行目：saki が事項の表にも、分野に無い話題の名前の表にも無い（{s}）")
    yn = {(r["bunya"], r["namae"]) for r in yomi["kouho"]}
    bad += [f"候補の名前「{n}」（分野 {b or '空'}）が、teigi/shitsugi-kouho.tsv に無い" for b, n in sorted(yn - seen)]
    bad += [f"teigi/shitsugi-kouho.tsv の「{n}」（分野 {b or '空'}）が、読み取りの結果に無い" for b, n in sorted(seen - yn)]
    return bad


def tsukeru(yomi, kouho_rows, jiko_rows, kihon_names):
    """読み手の行 → (事項に付けた読み手の行の並び, 入れなかった行の内訳)。付けた行は、question、n（議案）、theme、point（事項の
    ID）、hani、mayoi、ji（字の議案。無ければ空）、kouho（候補の名前。基本施策の行は空）、yomite、taba。
    内訳は {"kihon_nashi": {(分野, 基本施策の名前): 行の数}, "wadai": {(分野, 名前): 行の数}, "nashi": {(分野, 名前): 行の数}}。"""
    pb = point_bunya(kihon_names)
    by_name = {}
    for r in jiko_rows:
        by_name.setdefault(r["name"], []).append(r)
    jth = {r["id"]: jiko.themes_of(r) for r in jiko_rows}
    saki = {(r["bunya"], r["namae"]): r["saki"] for r in kouho_rows}
    out, nai = [], {"kihon_nashi": {}, "wadai": {}, "nashi": {}}
    bad = []

    def ji_of(r):
        m = RE_JI.search(r.get("riyu", ""))
        return m.group(1) if m else ""

    for r in yomi["shudai"]:
        b = pb.get(r["point"])
        if b is None:
            bad.append(f"{r['yomite']}-{r['taba']}-shudai.tsv：point「{r['point']}」が、総合計画の基本施策の名前に無い")
            continue
        th = theme_of_bunya(b)
        ids = [x["id"] for x in by_name.get(r["point"], []) if th in jiko.themes_of(x)]
        if not ids:
            k = (b, r["point"])
            nai["kihon_nashi"][k] = nai["kihon_nashi"].get(k, 0) + 1
            continue
        out.append(dict(question=r["question"], n=r["gian"], theme=th, point=ids[0], hani=r["hani"],
                        mayoi=r["mayoi"], ji=ji_of(r), kouho="", yomite=r["yomite"], taba=r["taba"]))
    for r in yomi["kouho"]:
        s = saki.get((r["bunya"], r["namae"]))
        k = (r["bunya"], r["namae"])
        if not s:
            nai["nashi"][k] = nai["nashi"].get(k, 0) + 1
            continue
        if s.startswith(WADAI_HEAD):
            nai["wadai"][k] = nai["wadai"].get(k, 0) + 1
            continue
        ths = jth[s]
        th = theme_of_bunya(r["bunya"]) if r["bunya"] and theme_of_bunya(r["bunya"]) in ths else ths[0]
        out.append(dict(question=r["question"], n=r["gian"], theme=th, point=s, hani=r["hani"],
                        mayoi=r["mayoi"], ji=ji_of(r), kouho=r["namae"], yomite=r["yomite"], taba=r["taba"]))
    if bad:
        raise ShitsugiError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in sorted(set(bad))))
    return out, nai


def gian_jun(n):
    """議案の字の並べ方（議第、報第、決議案第の順に番号の順。議題外、不明は最後）。"""
    m = RE_GIAN.fullmatch(n)
    if m:
        return (("議第", "報第", "決議案第").index(m.group(1)), int(m.group(2)), "")
    return (3, 0, n)


def ji_chu(gyo, rows):
    """作った行1つ（question、n、theme、相手、hani）と、その組の読み手の行 → 「字は議第N号の話：読み手 a、b」の字（「。」で
    つなぐ）。行の段落と重なる、字の議案のある読み手の行から。無ければ空。"""
    ps = set(keys.paras_of(gyo))
    d = {}
    for r in rows:
        if r["ji"] and ps & set(keys.paras_of(r["hani"])):
            d.setdefault(r["ji"], set()).add(r["yomite"])
    return "。".join(f"字は{j}の話：読み手 {'、'.join(sorted(ys))}"
                    for j, ys in sorted(d.items(), key=lambda x: gian_jun(x[0])))


def shudai_rows(tsuita, jiko_rows, theme_jun):
    """事項に付けた読み手の行 → taio/shudai.tsv の行（テーマの順、質問、議案、事項の表の順、yomi、chu の順）。"""
    jun = {r["id"]: i for i, r in enumerate(jiko_rows)}
    out = []
    for th in theme_jun:
        rs = [r for r in tsuita if r["theme"] == th]
        if not rs:
            continue
        grp = {}
        for r in rs:
            grp.setdefault((r["question"], r["n"], r["point"]), []).append(r)
        for q, n, a, h, y, w, m, k in ym.kumi_gyo(rs, "point", lambda x, q: x):
            chu = ym.chu_of(w, m, k)
            j = ji_chu(h, grp[(q, n, a)])
            out.append(dict(question=q, n=n, theme=th, jiko=a, hani=h, yomi=y, chu="。".join(x for x in (chu, j) if x)))
    tj = {t: i for i, t in enumerate(theme_jun)}
    out.sort(key=lambda r: (tj[r["theme"]], r["question"], gian_jun(r["n"]), jun[r["jiko"]], ym.YOMI.index(r["yomi"]),
                            r["chu"]))
    return out


def konkyo_wariate(yomi, tsuita):
    """読み手の資料と出来事の行 → (テーマごとの行の並び, 入れなかった行の数)。テーマは、同じ読み手の、同じ質問と議案の、段落が
    重なる事項の行のテーマ（無ければ、もう1人の読み手の行。それでも無ければ入れない）。"""
    idx = {}
    for r in tsuita:
        d = idx.setdefault((r["yomite"], r["question"], r["n"]), {})
        for p in keys.paras_of(r["hani"]):
            d.setdefault(p, set()).add(r["theme"])
    out, nashi = {}, 0
    for r in yomi["konkyo"]:
        ps = keys.paras_of(r["hani"])
        ths = set()
        for y in (r["yomite"], [x for x in YOMITE if x != r["yomite"]][0]):
            d = idx.get((y, r["question"], r["gian"]), {})
            ths = set().union(*[d.get(p, set()) for p in ps])
            if ths:
                break
        if not ths:
            nashi += 1
            continue
        for th in ths:
            out.setdefault(th, []).append(dict(question=r["question"], n=r["gian"], aite=r["aite"], hani=r["hani"],
                                               yomite=r["yomite"], taba=r["taba"]))
    return out, nashi


def konkyo_rows(wariate, namae, hiduke, theme_jun):
    """テーマごとの読み手の資料と出来事の行 → taio/konkyo.tsv の行（テーマの順、質問、議案、aite、yomi、chu の順）。"""
    out = []
    for th in theme_jun:
        rs = wariate.get(th)
        if not rs:
            continue
        for q, n, a, h, y, w, m, k in ym.kumi_gyo(rs, "aite", ym.aite_of(ym.of_theme(namae, th), hiduke)):
            out.append(dict(question=q, n=n, theme=th, aite=a, hani=h, yomi=y, chu=ym.chu_of(w, m, k)))
    tj = {t: i for i, t in enumerate(theme_jun)}
    out.sort(key=lambda r: (tj[r["theme"]], r["question"], gian_jun(r["n"]), r["aite"], ym.YOMI.index(r["yomi"]), r["chu"]))
    return out


def check(inp, shudai, konkyo, qs):
    """質疑の行の検査 → 問題の並び。question が読んだ区切りにあり、(区切り, 議案) が質疑の台帳にあり、議案の番号の字の議案は、
    議案の一覧にその会議の題があること。段落の照合は、tools/yomi.py と tools/konkyo.py の検査が行う。"""
    bad = []
    led = inp.shitsugi()
    qs = set(qs)
    for name, rows in (("taio/shudai.tsv", shudai), ("taio/konkyo.tsv", konkyo)):
        for r in rows:
            q, n = r["question"], r["n"]
            if q not in qs:
                bad.append(f"{name}：question が、読んだ質疑の区切りに無い（{q}）")
            elif (keys.sid_of(q), n) not in led:
                bad.append(f"{name}：区切りと議案の組が、質疑の台帳に無い（{q} {n}）")
            elif n not in GIAN_SONOTA and inp.gian_title(keys.sid_of(q), n) is None:
                bad.append(f"{name}：議案の題が、議案の一覧に無い（{q} {n}）")
    return sorted(set(bad))


def tsukuru(inp, jiko_rows=None, namae=None, hiduke=None):
    """→ dict(shudai：taio/shudai.tsv の質疑の行, konkyo：taio/konkyo.tsv の質疑の行, qs：読んだ区切り, nai：入れなかった
    行の内訳, konkyo_nashi：入れなかった資料と出来事の行の数, kouho：表の行)。合わなければ ShitsugiError。"""
    jiko_rows = jiko.read() if jiko_rows is None else jiko_rows
    namae = ym.read_namae() if namae is None else namae
    if hiduke is None:
        import konkyo
        hiduke = konkyo.bunsho_hiduke()
    import bunya as bu
    qs = shitsumon()
    yomi = read_yomi()
    kr = read_kouho()
    wadai = {r["id"] for r in bu.read_wadai()}
    bad = check_kouho(kr, yomi, {r["id"] for r in jiko_rows}, wadai)
    if bad:
        raise ShitsugiError(f"teigi/shitsugi-kouho.tsv：{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    tsuita, nai = tsukeru(yomi, kr, jiko_rows, jiko.kihon_names_of(inp))
    tj = jiko.theme_jun(jiko_rows)
    sh = shudai_rows(tsuita, jiko_rows, tj)
    wari, kn = konkyo_wariate(yomi, tsuita)
    ko = konkyo_rows(wari, namae, hiduke, tj)
    bad = check(inp, sh, ko, qs)
    if bad:
        raise ShitsugiError(f"{len(bad)} 件\n" + "\n".join("  - " + b for b in bad))
    return dict(shudai=sh, konkyo=ko, qs=qs, nai=nai, konkyo_nashi=kn, kouho=kr)


# ---- 画面と応答の題（docs/design.md 4節） ----

def dai(inp, q, n):
    """質疑の区切りと議案 → 題の字（「議第18号 平成２９年度日野町一般会計予算」。議題外と不明は、その字だけ）。"""
    if n in GIAN_SONOTA:
        return n
    t = inp.gian_title(keys.sid_of(q), n)
    return f"{n} {t}" if t else n


def ji_of_chu(chu):
    """taio/shudai.tsv の chu → 字の議案の並び（「字は議第N号の話」と書いた読み手がいる議案）。"""
    return [m.group(1) for m in RE_CHU_JI.finditer(chu or "")]


def main(argv=None):
    p = argparse.ArgumentParser(description="議案への質疑の読み取りの結果の数を出す")
    p.add_argument("--nashi", action="store_true")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()
        x = tsukuru(inp)
    except (inputs.InputError, ShitsugiError, ym.YomiError, ValueError, OSError) as e:
        print(f"止めた：lock と入力、または読み取りの結果と表を読めない\n{e}", file=sys.stderr)
        return 1
    sh, ko, nai = x["shudai"], x["konkyo"], x["nai"]
    n = {y: sum(r["yomi"] == y for r in sh) for y in ym.YOMI}
    nk = {y: sum(r["yomi"] == y for r in ko) for y in ym.YOMI}
    print(f"読んだ質疑の区切り {len(x['qs'])}。質問と事項の対応の行 {len(sh)}（一致 {n[ym.ICCHI]}、1回だけ {n[ym.IKKAI]}）。"
          f"区切りと議案の組 {len({(r['question'], r['n']) for r in sh})}、事項 {len({r['jiko'] for r in sh})}")
    print(f"資料と出来事の行 {len(ko)}（一致 {nk[ym.ICCHI]}、1回だけ {nk[ym.IKKAI]}）。入れなかった読み手の行 {x['konkyo_nashi']}")
    print(f"字の議案の印がある行 {sum(bool(ji_of_chu(r['chu'])) for r in sh)}")
    for k, why in (("kihon_nashi", "当たる事項が無い基本施策の行"), ("wadai", "分野に無い話題の候補の行"),
                   ("nashi", "入れ先の無い候補の行")):
        d = nai[k]
        print(f"入れなかった読み手の行：{why} {sum(d.values())}（名前 {len(d)}）")
        if a.nashi:
            for (b, nm), c in sorted(d.items()):
                print(f"  分野 {b or '空'} {nm}：{c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
