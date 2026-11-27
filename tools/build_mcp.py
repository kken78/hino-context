"""MCP サーバーの応答を、表と入力から作る（docs/mcp.md、docs/design.md 3節・4節）。

実行：python3 -B tools/build_mcp.py [--out <ファイル>] [--hikaku <ファイル>]
  既定の出力は mcp/data/outou.json。Cloudflare に置くプログラム（mcp/src/index.ts）は、この JSON を引いて返すだけで、
  応答の文を組み立てない。
  --hikaku を付けると、作った JSON が、そのファイルと同じかを確認する（tools/kensa.py が使う。違えば終了コード 1）。
中身は teigi/ の表と、lock の版の入力だけから作る。数値を計算しない。良し悪しを書かない。
画面に出す言葉は、docs/design.md 3節の2つの表から読む（tools/build_suji.py の read_design と同じ読み方）。
このファイルには、画面の言葉を書かない。資料の名前、時期、掲載の場所などは、ページを作るツールの関数を使う。

応答は、ツールと引数の組ごとに1つの文（見出しと箇条書き。HTML は入れない）。1回の応答が JOGEN 字を超える組は、
区切りのよい所（資料ごと、表ごと、項目ごと）で分け、続きを引数 tsuzuki で返す。

作る前の検査（1つでも当たれば、件数と該当行を示して、何も書かずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all）で問題がある
  (b) 応答の文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文は除く）
  (c) テーマの定義と施設の参照表が合わない（tools/build_theme.py の build と同じ検査）
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems）
  (f) 過程の記録と施設の記録の quote が、source の資料の本文に無い。資料の名前を作れない（tools/build_theme.py と同じ）
  (g) 施設の割り当てが未確認の行がある（tools/build_theme.py と同じ）
"""
import argparse
import datetime
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_hyo as bh  # noqa: E402
import build_note as bn  # noqa: E402
import build_suji as bs  # noqa: E402
import build_theme as bt  # noqa: E402
import inputs  # noqa: E402
import keys  # noqa: E402
import ronten  # noqa: E402
import suji as sj  # noqa: E402

OUT_PATH = os.path.join(inputs.ROOT, "mcp", "data", "outou.json")
SRC_PATH = os.path.abspath(__file__)
SKILL_PATH = os.path.join(inputs.ROOT, "SKILL.md")
SKILL_SETSU = "## 1. "              # SKILL.md の、出すときの規約の節。箇条書きの行を、サーバーの instructions にする
NAME = "hino-context"
VERSION = "0.1.0"                    # データのもとのコミットと日付は入れない（作るたびに変わると、検査で比較できない）
JOGEN = 6000                         # 1回の応答の文字数の上限（目安）
A, B = bn.A, bn.B
E, S = bn.E, bn.S
Stop = bn.Stop

# ツールと引数（名前、型、必須か）。引数の順は、応答を引く ID の並びの順でもある（docs/mcp.md）
TSUZUKI = "tsuzuki"
TOOLS = (("theme", (("theme", "string", False), (TSUZUKI, "integer", False))),
         ("suji", (("id", "string", True), ("shiryo", "string", False), ("uchiwake", "integer", False),
                   (TSUZUKI, "integer", False))),
         ("shisetsu", (("key", "string", True), (TSUZUKI, "integer", False))),
         ("shiryo", (("bunsho", "string", True), ("hyo", "integer", False), (TSUZUKI, "integer", False))))


def design_problems(D, src=None):
    """docs/design.md 3節の表と、このツールが合うか。→ 問題の並び。"""
    return bs.design_problems(D, src, path=SRC_PATH)


def kagi(args):
    """引数の (名前, 値) の並び → 応答を引く ID。値が空の引数は除き、「名前=値」を「&」でつなぐ（docs/mcp.md）。"""
    return "&".join(f"{k}={v}" for k, v in args if v not in (None, ""))


def owari(h):
    """HTML の断片（E と S で作ったもの）→ 応答の文（文字参照を戻し、資料からの文の印を消す）。"""
    return html.unescape(re.sub(r"<[^>]+>", "", h)).replace(A, "").replace(B, "")


def kakunin_kiroku(chu):
    """数値と内容の表の chu → 確認の記録の字（日付の形が合うもの）だけの並び（docs/design.md 3節）。"""
    out = []
    for rx in (sj.RE_KAKUNIN, sj.RE_NISHA):
        out += [m.group(0) for m in rx.finditer(chu or "") if sj.is_ymd(m.group(1))]
    return out


# ---- 応答の分け方 ----

class Outou:
    """1つの組の応答。title は題（HTML の断片）、intro は題の下の行、blocks は (頭の行の並び, 項目の並び) の並び。
    項目は、改行を含んでよい（分けるときは、項目の途中では分けない）。"""

    def __init__(self, title, intro=(), blocks=()):
        self.title, self.intro, self.blocks = title, list(intro), [b for b in blocks if b and b[1]]

    def pages(self, D):
        """→ 応答の文（HTML の断片）の並び。1つ目から。"""
        atama = [E(D.bun("mcp-atama")), f"# {self.title}"]
        yobi = len(owari(E(D.bun("mcp-tsuzuki", n=99)))) + len(owari(E(D.bun("mcp-tsuzuki-dai", n=99, m=99)))) + 4

        def nagasa(lines):
            return len(owari("\n".join(lines))) + yobi

        out, cur, aru = [], atama + self.intro, False      # aru：いまの応答に、ブロックの中身が入っているか
        for head, items in self.blocks:
            cand = cur + [""] + head + items
            if nagasa(cand) <= JOGEN:
                cur, aru = cand, True
                continue
            if aru:
                out.append(cur)
                cur, aru = list(atama), False
                cand = cur + [""] + head + items
                if nagasa(cand) <= JOGEN:
                    cur, aru = cand, True
                    continue
            cur = cur + [""] + head
            n0 = len(cur)
            for it in items:
                if len(cur) > n0 and nagasa(cur + [it]) > JOGEN:
                    out.append(cur)
                    cur = list(atama) + [""] + head
                    n0 = len(cur)
                cur.append(it)
            aru = True
        out.append(cur)
        m = len(out)
        if m > 1:
            for i, p in enumerate(out):
                p.insert(2, E(D.bun("mcp-tsuzuki-dai", n=i + 1, m=m)))
                if i + 1 < m:
                    p += ["", E(D.bun("mcp-tsuzuki", n=i + 2))]
        return ["\n".join(p) for p in out]


# ---- 組ごとの応答を作る ----

class Tsukuru:
    def __init__(self, D, inp, tables):
        self.D, self.inp, self.t = D, inp, tables
        self.by = {r["bunsho"]: r for r in tables["bunsho"]}
        self.index = {(r["bunsho"], r["n"]): r for r in tables["bubun"]}
        self.teigi = {r["id"]: r for r in tables["suji"]}
        self.ref = {r["key"]: r for r in inp.shisetsu()}
        self.namae = bt.Namae(D, inp, self.by)
        self.kaisei = bt.Kaisei(tables)
        self.problems = []

    # 資料の名前と url
    def moto(self, key, quote=""):
        """資料の ID（ページか発言か外部の資料）→ (名前の HTML, url)。"""
        kind, _ = keys.parse(key)
        if kind == "plan":
            return self.namae.bunsho(key), ""
        if kind == "ext":
            name = keys.source_name(self.inp, key)
            if not name:
                self.namae.stop(f"外部の資料の名前を作れない（{key}）")
            return S(name), keys.source_url(self.inp, key)
        return self.namae.shiryo(key, quote)

    def url_gyo(self, url, sita=""):
        D = self.D
        if not url:
            return f"{sita}{E(D.bun('link-nashi'))}"
        return f"{sita}{E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{E(url)}"

    def kagi_ji(self, name, hikisu, key):
        """名前のあとの括弧に、ツールの引数の名前と、その引数に使う ID を付ける。"""
        return self.D.bun("mcp-kagi", name=name, hikisu=E(hikisu), ji=E(key))

    def teigi_kagi(self, t):
        return self.kagi_ji(E(t["name"]), "id", t["id"])

    def bunsho_kagi(self, bkey):
        return self.kagi_ji(self.namae.bunsho(bkey), "bunsho", bkey)

    # theme（引数なし）
    def theme_ichiran(self, themes):
        D = self.D
        items = []
        for th in themes:
            name = bt.Theme(self.inp, th).namae
            items.append("- " + self.kagi_ji(S(name[0]) if name else E(th), "theme", th))
        D.dasanai("テーマの定義 kind が「名前」")
        return Outou(E(D.bun("mcp-midashi-theme")), [E(D.bun("mcp-hani"))], blocks=[([], items)])

    # theme=…
    def theme(self, theme):
        D, inp, t = self.D, self.inp, self.t
        th = bt.Theme(inp, theme)
        name = th.namae[0]
        blocks = []
        rows = sorted((r for r in t["theme"] if r["theme"] == theme and r["shu"] == sj.SETSUMEI_BUN),
                      key=lambda r: int(r["jun"]))
        if rows:
            items, i = [], 0
            while i < len(rows):
                b = sj.bunsho_of(rows[i]["tokoro"])
                k = i
                while k < len(rows) and sj.bunsho_of(rows[k]["tokoro"]) == b:
                    k += 1
                lines = [f"- {self.namae.bunsho(b)}", self.url_gyo(keys.source_url(inp, rows[i]["tokoro"]), "  - ")]
                lines += [f"  - 「{S(r['inyo'])}」（{E(D.bun('page', n=sj.page_no(r['tokoro'])))}）" for r in rows[i:k]]
                items.append("\n".join(lines))
                i = k
            blocks.append(([f"## {E(D.kotoba('テーマの表 shu が「説明の文」'))}"], items))
        katei = sorted(ronten.katei(inp, theme), key=lambda r: (r["from"][:7], int(r["step"])))
        items = []
        for r in katei:
            srcs = list(dict.fromkeys(s.strip() for s in r["sources"].split(",") if s.strip()))
            lines = [f"- {E(bt.kikan(D, r))}：{S(r['name'])}",
                     f"  - {E(D.kotoba('過程の記録 quote'))}：「{S(r['quote'])}」"]
            for s in srcs:
                nm, url = self.namae.shiryo(s, r["quote"])
                b = sj.bunsho_of(s)
                if b in self.by:
                    nm = f"{self.bunsho_kagi(b)}　{E(D.bun('page', n=sj.page_no(s)))}" if sj.page_no(s) \
                        else self.bunsho_kagi(b)
                lines.append(f"  - {E(D.kotoba('過程の記録 sources'))}：{nm}　{E(url)}" if url
                             else f"  - {E(D.kotoba('過程の記録 sources'))}：{nm}")
            for e, x in self.kaisei.of(srcs):
                lines.append(f"  - {E(D.kotoba('資料どうしの関係の表 hyogen が「一部改正」の行の e'))}："
                             f"{self.bunsho_kagi(e)}")
                ks = self.kaisei.items(D, x, self.teigi_kagi)
                if ks:
                    lines.append(f"  - {E(D.kotoba('資料どうしの関係の表 kara、e の資料の、同じ項目の、改正前と改正後の組み合わせで、atai が違うもの'))}"
                                 f"{E(D.bun('mcp-kaisei-hani'))}")
                    lines += [f"    - {k}" for k in ks]
            items.append("\n".join(lines))
        D.kotoba("過程の記録 from、to")
        D.kotoba("過程の記録 name")
        blocks.append(([f"## {E(D.bun('midashi-keika'))}", E(D.bun("keika-setsumei"))], items))
        hyo = self.shisetsu_hyo(theme, th)
        if hyo:
            blocks.append(hyo)
        items = ["- " + self.kagi_ji(S(self.ref[k]["name"]), "key", k)
                 for k in bt.jun_shisetsu(self._hyo.get(theme), th, self.ref)]
        blocks.append(([f"## {E(D.bun('mcp-midashi-shisetsu'))}"], items))
        docs = sorted((b for b in self.by if th.has(b)), key=lambda b: (self.by[b]["hiduke"] or "9999", b))
        hb = bs.hiduke_bun(D, False, any(self.namae.hiduke_nashi(b) for b in docs))
        blocks.append(([f"## {E(D.bun('mcp-midashi-shiryo'))}", E(D.bun("mcp-shiryo-setsumei")) + E(hb)],
                       ["- " + self.bunsho_kagi(b) for b in docs]))
        blocks.append(([f"## {E(D.bun('mcp-midashi-teigi'))}", E(D.bun("mcp-teigi-setsumei"))],
                       ["- " + self.teigi_kagi(x) for x in t["suji"]]))
        return Outou(S(name), blocks=blocks)

    def shisetsu_hyo(self, theme, th):
        """テーマの施設の表（tools/build_theme.py の ShisetsuHyo）を、行ごとの箇条書きにする。"""
        D = self.D
        h = self._hyo.get(theme)
        if h is None:
            return None
        tr = h.trow
        setsumei = [D.bun("theme-hyo", shiryo=self.namae.bunsho(sj.bunsho_of(tr["tokoro"])),
                          page=E(D.bun("page", n=sj.page_no(tr["tokoro"]))), hyo=bh.midashi_ji(D, h.hyo))]
        for x in h.suji:
            moto = {}
            for (sid, _), rs in h.atai.items():
                if sid != x["id"]:
                    continue
                for r in rs:
                    jiten = r["jiten"] if r["nendo"] else ""
                    moto.setdefault((sj.bunsho_of(r["shiryo"]) or r["shiryo"], jiten), set()).add(
                        sj.page_no(r["shiryo"]))
            for (b, jiten), pages in moto.items():
                pp = "、".join(str(p) for p in sorted(p for p in pages if p))
                shiryo = self.namae.bunsho(b) + (f"　{E(D.bun('page', n=pp))}" if pp else "")
                if jiten:
                    setsumei.append(D.bun("theme-suji", name=E(x["name"]), shiryo=shiryo, jiten=S(jiten)))
                else:
                    setsumei.append(D.bun("theme-suji-jiki-nashi", name=E(x["name"]), shiryo=shiryo))
        unei = E(D.kotoba("施設の記録 aspect が「運営」"))
        if any(h.unei.values()):
            setsumei.append(D.bun("theme-unei", unei=unei))
        items = []
        for g, ks in zip(h.gyo, h.keys):
            ran = []
            if g["matome"].strip():
                ran.append(S(g["matome"]))
            if h.unei[ks]:
                ran.append(f"{unei}：{'、'.join(S(v) for v in h.unei[ks])}")
            for x in h.suji:
                vs = h.atai.get((x["id"], ks), [])
                if vs:
                    nm = D.bun("retsu-tani", name=E(x["name"]), tani=E(x["tani"])) if x["tani"] else E(x["name"])
                    ran.append(f"{nm}：{'、'.join(S(r['atai']) for r in vs)}")
            if len(ks) == 1:
                gyo = self.kagi_ji(bh.midashi_ji(D, g), "key", ks[0])
            else:
                gyo = bh.midashi_ji(D, g) + "（" + "、".join(
                    self.kagi_ji(S(self.ref[k]["name"]), "key", k) for k in ks) + "）"
            items.append(f"- {gyo}\n  - " + "　".join(ran))
        url = keys.source_url(self.inp, tr["tokoro"])
        foot = [self.url_gyo(url)]
        used = {k for ks in h.keys for k in ks}
        nai = [k for k in bt.jun_shisetsu(h, th, self.ref) if k not in used]
        if nai:
            foot.append(D.bun("hyo-ni-nai", shisetsu="、".join(S(self.ref[k]["name"]) for k in nai)))
        return ([f"## {E(D.kotoba('テーマの表 shu が「施設の表」'))}"] + ["\n".join(setsumei)], items + foot)

    # suji
    def suji(self, t, bunsho=None, uchiwake=False):
        """項目 t の数値。uchiwake が偽なら kubun の無い行だけ、真なら kubun のある行だけ（docs/mcp.md）。"""
        D = self.D
        zen = [r for r in self.t["atai"] if r["suji"] == t["id"]]
        if bunsho:
            zen = [r for r in zen if r["shiryo"].strip() and sj.bunsho_of(r["shiryo"]) == bunsho]
        rows = [r for r in zen if bool(r["kubun"]) == uchiwake]
        intro = []
        if t["kettei"] == "案":
            intro.append(E(D.kotoba("項目の表 kettei が「案」")))
        for k, c in ((D.kotoba("項目の表 nani"), "nani"), (D.kotoba("項目の表 tani"), "tani"),
                     (bs.toki_go(D, t), "toki"), (D.kotoba("項目の表 iikata"), "iikata"),
                     (D.kotoba("項目の表 chui"), "chui")):
            if t[c]:
                intro.append(f"- {E(k)}：{E(t[c])}")
        if uchiwake:
            intro += ["", E(D.bun("mcp-uchiwake-dake"))]
        kankei = {id(r): sj.jiten_kankei(r, t, self.by) for r in rows}
        kotoba = {sj.KANKEI_ATO: (D.kotoba("時点の関係 ato"), D.retsu_setsumei("時点の関係 ato")),
                  sj.KANKEI_TOCHU: (D.kotoba("時点の関係 tochu"), ""),
                  sj.KANKEI_MAE: (D.kotoba("時点の関係 mae"), D.retsu_setsumei("時点の関係 mae"))}
        D.dasanai("時点の関係 無し")
        tsukau = [k for k in bs.KANKEI if k in kankei.values()]
        if tsukau:
            intro += ["", E(D.bun("mcp-kankei-setsumei"))]
            intro += [f"- {E(kotoba[k][0])}" + (f"：{E(kotoba[k][1])}" if kotoba[k][1] else "") for k in tsukau]
        if any(bs.ichi_of(D, r, self.index)[1] for r in rows if r["shiryo"].strip()):
            intro += ["", E(D.bun("mikakunin-setsumei"))]
        blocks = []
        chigau = self.chigau(t, rows, kankei)
        if chigau:
            blocks.append(([f"## {E(D.bun('chigau'))}"], chigau + [E(D.bun("chigau-setsumei"))]))
        # 資料（ページか発言か外部の資料）ごとにまとめる。shiryo が空の行は最後
        groups = {}
        for r in rows:
            groups.setdefault(r["shiryo"].strip(), []).append(r)

        def jun(k):
            if not k:
                return (3, (), "")
            h = bs.hiduke_of(D, k, self.by)
            if h:
                return (0, h[0], k)
            nendo = self.namae.nendo_dake(sj.bunsho_of(k))
            if nendo:
                return (0, (int(nendo), 4, 0), k)
            return (1, (), k) if k.startswith("ext:") else (2, (), k)      # 外部の資料は、名前に日付を含む
        items_all = []
        for k in sorted(groups, key=jun):
            rs = groups[k]
            if k:
                nm, url = self.moto(k, rs[0]["inyo"])
                head = [f"### {nm}", self.url_gyo(url)]
                b = self.by.get(sj.bunsho_of(k) or "")
                if b and b["konkyo"]:
                    kp = D.bun("page", n=sj.page_no(b["konkyo_tokoro"]))
                    head.append(f"{E(D.kotoba('資料の一覧の表 konkyo'))}：「{S(b['konkyo'])}」（{E(kp)}）")
            else:
                head = [f"### {E(D.kotoba('数値と内容の表 shiryo が空'))}"]
            items = [self.atai_gyo(r, kankei[id(r)], kotoba) for r in rs if not r["kubun"]]
            for kb in dict.fromkeys(r["kubun"] for r in rs if r["kubun"]):
                lines = [f"- {E(D.kotoba('数値と内容の表 kubun'))}：{E(kb)}"]
                lines += ["  " + x.replace("\n", "\n  ") for x in
                          (self.atai_gyo(r, kankei[id(r)], kotoba) for r in rs if r["kubun"] == kb)]
                items.append("\n".join(lines))
            items_all.append((head, items))
        srcs = [k for k in groups if k]
        hb = bs.hiduke_bun(D, any(jun(k)[0] == 0 and not bs.hiduke_of(D, k, self.by) for k in srcs),
                           any(jun(k)[0] == 2 for k in srcs))
        midashi = [f"## {E(D.bun('mcp-midashi-suji', nakami=bs.atai_go(D, t)))}", E(D.bun("hiduke-setsumei")) + E(hb)]
        if items_all:
            # 見出しは、最初の資料のブロックと一緒に出す
            blocks += [(midashi + [""] + items_all[0][0], items_all[0][1])] + items_all[1:]
        sue = []
        if not rows and not uchiwake:
            sue.append(E(D.bun("mcp-uchiwake-nomi")))
        if not uchiwake and any(r["kubun"] for r in zen):
            sue.append(E(D.bun("mcp-uchiwake")))
        if sue:
            blocks.append(([], sue))
        return Outou(self.teigi_kagi(t), intro, blocks)

    def chigau(self, t, rows, kankei):
        """数値のページと同じ判定（mae の数値を、内訳ごと、時期ごとにまとめ、tools/suji.py の ichi_shinai）で、
        資料の間で数値が一致しない時期の行。数値と資料の名前を並べる。どちらが正しいかは書かない。"""
        D = self.D
        kumi = {}
        for r in rows:
            if kankei[id(r)] == sj.KANKEI_MAE:
                key, label = bs.toki_of(D, r, t)
                kumi.setdefault((r["kubun"], key, label), []).append(r)
        out = []
        for (kb, _, label), rs in sorted(kumi.items(), key=lambda x: (x[0][0], x[0][1])):
            if not sj.ichi_shinai(rs, self.index):
                continue
            jiki = E(label) + (f"（{E(D.kotoba('数値と内容の表 kubun'))}：{E(kb)}）" if kb else "")
            atai = "、".join(f"{S(r['atai'])}（{self.moto(r['shiryo'], r['inyo'])[0]}）"
                            for r in rs if r["jotai"] == sj.ARU)
            out.append("- " + D.bun("mcp-chigau-gyo", jiki=jiki, atai=atai))
        return out

    def atai_gyo(self, r, kankei, kotoba):
        """数値と内容の表の1行 → 項目（改行を含む）。"""
        D = self.D
        if r["jotai"] == sj.ARU:
            gyo = f"- {E(r['jiten'])}：{S(r['atai'])}"
        else:
            gyo = f"- {E(r['jiten'])}：{E(D.kotoba('数値と内容の表 jotai が「数値がある」でない'))}「{E(r['jotai'])}」"
        if kankei:
            gyo += f"（{E(kotoba[kankei][0])}）"
        if r["shurui"]:
            gyo += f"　{E(D.kotoba('数値と内容の表 shurui'))}：{S(r['shurui'])}"
        kk = kakunin_kiroku(r["chu"])
        if kk:
            gyo += f"　{E(D.kotoba('数値と内容の表 chu（確認の記録の字）'))}：{E('、'.join(kk))}"
        lines = [gyo]
        sh = r["shiryo"].strip()
        if sh:
            ichi, _ = bs.ichi_of(D, r, self.index)
            if not ichi and not sh.startswith("sp:") and sj.page_no(sh):
                ichi = E(D.kotoba("bubun が空"))
            if ichi:
                lines.append(f"  - {E(D.kotoba('資料の中の場所（bubun・retsu から親をたどった並び）'))}：{ichi}")
            if r["inyo"] and sj.inyo_kuzure(r):
                lines.append(f"  - {E(D.kotoba('数値と内容の表 inyo'))}：{E(D.bun('inyo-kuzure'))}")
            elif r["inyo"]:
                lines.append(f"  - {E(D.kotoba('数値と内容の表 inyo'))}：「{S(r['inyo'])}」")
        if r["jotai"] != sj.ARU and r["hani"]:
            lines.append(f"  - {E(D.kotoba('数値と内容の表 hani'))}：{E(r['hani'])}")
            if r["kakunin"]:
                lines.append(f"  - {E(D.kotoba('数値と内容の表 kakunin'))}：{E(bs.hi_str(D, r['kakunin']))}")
        return "\n".join(lines)

    # shisetsu
    def shisetsu(self, k, theme, th):
        D = self.D
        ref = self.ref[k]
        intro = []
        al = [a.strip() for a in ref["aliases"].split(";") if a.strip()]
        if al:
            intro.append(f"- {E(D.kotoba('施設の参照表 aliases'))}：{S('、'.join(al))}")
        D.dasanai("施設の参照表 name")
        blocks = []
        rs = sorted((r for r in self.kiroku if r["facility"] == k), key=self.namae.kiroku_jun)
        items = []
        for r in rs:
            nm, url = self.namae.shiryo(r["source"], r["quote"])
            v = S(r["value"]) + (f"（{S(r['target'])}）" if r["target"] else "")
            items.append("\n".join([
                f"- {nm}",
                f"  - {E(D.kotoba('施設の記録 aspect'))}：{E(r['aspect'])}　{E(D.kotoba('施設の記録 kind'))}："
                f"{E(r['kind'])}　{E(D.kotoba('施設の記録 value、target'))}：{v}",
                f"  - {E(D.kotoba('施設の記録 quote'))}：「{S(r['quote'])}」",
                self.url_gyo(url, "  - ")]))
        D.kotoba("施設の記録 source")
        srcs = [sj.bunsho_of(r["source"]) for r in rs]
        hb = bs.hiduke_bun(D, any(self.namae.nendo_dake(b) for b in srcs), any(self.namae.hiduke_nashi(b) for b in srcs))
        blocks.append(([f"## {E(D.bun('mcp-midashi-kiroku'))}",
                        E(D.bun("kijutsu-setsumei")) + E(hb) + E(D.bun("kubun-setsumei"))], items))
        hk = self._hk.get(theme)
        items, hyo_parts = [], set()
        for p, hyo, ran in (hk.gyo.get(k, []) if hk else []):
            hyo_parts.add((p["bunsho"], p["oya"]))
            nm, url = self.namae.shiryo(hyo["tokoro"])
            lines = [f"- {nm}",
                     f"  - {E(D.kotoba('資料の中の場所の表 name（shu が「表」）'))}：{bh.midashi_ji(D, hyo)}"
                     f"　{E(D.kotoba('資料の中の場所の表 name（shu が「行」か「列」）'))}：{bh.midashi_ji(D, p)}"]
            if p["shisetsu_kakunin"].strip():
                lines.append(f"  - {E(D.kotoba('資料の中の場所の表 shisetsu_kakunin'))}：{E(p['shisetsu_kakunin'])}")
            lines.append(f"  - {E(D.kotoba('数値と内容の表 atai、retsu'))}：" + "、".join(
                D.bun("hyo-kijutsu-ran", midashi=bh.midashi_ji(D, x), atai=S(r["atai"])) for x, r in ran))
            lines.append(self.url_gyo(url, "  - "))
            items.append("\n".join(lines))
        mi = any(sj.mikakunin(x) for p, hyo, ran in (hk.gyo.get(k, []) if hk else [])
                 for x in [p, hyo] + [x for x, _ in ran])
        hb = bs.hiduke_bun(D, False, any(self.namae.hiduke_nashi(p["bunsho"]) for p, _, _ in
                                         (hk.gyo.get(k, []) if hk else [])))
        head = [f"## {E(D.kotoba('資料の中の場所の表 shisetsu、oya'))}", E(D.bun("hyo-kijutsu-setsumei")) + E(hb)]
        D.kotoba("資料の一覧の表 namae、han、hiduke")
        blocks.append((head, items + ([E(D.bun("mikakunin-hyo"))] if mi and items else [])))
        # 施設を指す数値の行（上の欄に出した表の数値は除く）
        items, mi_suji = [], False
        for x in self.t["suji"]:
            for r in self.t["atai"]:
                if r["suji"] != x["id"] or r["jotai"] != sj.ARU or k not in sj.atai_shisetsu(r, self.index):
                    continue
                b = sj.bunsho_of(r["shiryo"])
                part = self.index.get((b, r["bubun"]))
                if part is not None and (b, part["oya"]) in hyo_parts:
                    continue
                nm, url = self.moto(r["shiryo"], r["inyo"])
                gyo = f"- {self.teigi_kagi(x)}：{S(r['atai'])}"
                gyo += f"　{E(D.kotoba('数値と内容の表 jiten'))}：{E(r['jiten'])}"
                kk = kakunin_kiroku(r["chu"])
                if kk:
                    gyo += f"　{E(D.kotoba('数値と内容の表 chu（確認の記録の字）'))}：{E('、'.join(kk))}"
                lines = [gyo, f"  - {E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{nm}" + (f"　{E(url)}" if url else "")]
                ichi, m = bs.ichi_of(D, r, self.index)
                mi_suji = mi_suji or m
                if ichi:
                    lines.append(f"  - {E(D.kotoba('資料の中の場所（bubun・retsu から親をたどった並び）'))}：{ichi}")
                sk = [self.index[(b, n)]["shisetsu_kakunin"] for n in (r["bubun"], r["retsu"])
                      if n and (b, n) in self.index and self.index[(b, n)]["shisetsu_kakunin"].strip()]
                if sk:
                    lines.append(f"  - {E(D.kotoba('資料の中の場所の表 shisetsu_kakunin'))}：{E('、'.join(sk))}")
                items.append("\n".join(lines))
        if mi_suji:
            items.append(E(D.bun("mikakunin-setsumei")))
        blocks.append(([f"## {E(D.bun('mcp-midashi-shisetsu-suji'))}", E(D.bun("mcp-shisetsu-suji-setsumei"))],
                       items))
        blocks.append(([], [E(D.bun("mcp-shisetsu-teigi", theme=theme))]))
        return Outou(self.kagi_ji(S(ref["name"]), "key", k), intro, blocks)

    # shiryo
    def bunsho_intro(self, bkey):
        D = self.D
        b = self.by[bkey]
        shurui = {"keikaku": D.kotoba("資料の一覧の表 shurui が「keikaku」"), "koho": D.kotoba("資料の一覧の表 shurui が「koho」"),
                  "yosan": D.kotoba("資料の一覧の表 shurui が「yosan」"), "hyoka": D.kotoba("資料の一覧の表 shurui が「hyoka」"),
                  "jigyo": D.kotoba("資料の一覧の表 shurui が「jigyo」"), "shingi": D.kotoba("資料の一覧の表 shurui が「shingi」")}
        if b["shurui"] not in shurui:
            self.problems.append(("(e) デザインシステムとの対応",
                                  f"資料の一覧の表の shurui「{b['shurui']}」の行が、docs/design.md 3節に無い（{bkey}）"))
        kk = [r for r in self.t["kankei"] if r["kara"] == bkey]
        ke = [r for r in self.t["kankei"] if r["e"] == bkey]
        ar = [r for r in self.t["atai"] if r["shiryo"].strip() and sj.bunsho_of(r["shiryo"]) == bkey]
        hyo = [p for p in self.t["bubun"] if p["bunsho"] == bkey and p["shu"] == sj.HYO]
        intro = [E(D.bun("mcp-shiryo-hani")),
                 E(D.bun("mcp-shiryo-kazu", hyo=len(hyo), atai=len(ar), teigi=len({r["suji"] for r in ar}),
                         kara=len(kk), e=len(ke))),
                 f"- {E(D.kotoba('資料の一覧の表 shurui'))}：{E(shurui.get(b['shurui'], b['shurui']))}"]
        if b["konkyo"]:
            kp = D.bun("page", n=sj.page_no(b["konkyo_tokoro"]))
            intro.append(f"- {E(D.kotoba('資料の一覧の表 konkyo'))}：「{S(b['konkyo'])}」（{E(kp)}）")
        else:
            hani = konkyo_hani(b["chu"])
            ji = (D.bun("mcp-konkyo-nashi", hani=E(f"{D.kotoba('資料の一覧の表 chu（「根拠：」の記述の「見つからない（…）」の括弧の中の字）')}：{hani}"))
                  if hani else E(D.bun("mcp-irete-inai")))
            intro.append(f"- {E(D.kotoba('資料の一覧の表 konkyo'))}：{ji}")
        first = f"{bkey}/1" if not keys.RE_PLAN.fullmatch(bkey) else ""
        intro.append(self.url_gyo(keys.source_url(self.inp, first) if first else "", "- "))
        return intro

    def shiryo(self, bkey):
        D = self.D
        blocks = []
        kk = [r for r in self.t["kankei"] if r["kara"] == bkey]
        groups = {}
        for r in kk:
            groups.setdefault((r["inyo"], r["hyogen"]), []).append(r)
        D.dasanai("資料どうしの関係の表 hyogen")
        items = []
        for (inyo, hyogen), rs in groups.items():
            aite = "、".join(dict.fromkeys(self.bunsho_kagi(r["e"]) for r in rs))
            page = E(D.bun("page", n=sj.page_no(rs[0]["tokoro"])))
            items.append(f"- 「{S(inyo)}」（{page}）\n  - {D.bun('aite', hyogen=S(hyogen), aite=aite)}")
        blocks.append(([f"## {E(D.kotoba('資料どうしの関係の表 inyo'))}"],
                       items or [E(D.bun("shiryo-nashi"))]))
        D.kotoba("資料どうしの関係の表 kara、e")
        items = []
        for r in self.t["kankei"]:
            if r["e"] == bkey:
                page = E(D.bun("page", n=sj.page_no(r["tokoro"])))
                items.append(f"- {self.bunsho_kagi(r['kara'])}\n  - 「{S(r['inyo'])}」（{page}）\n"
                             f"  - {D.bun('aite', hyogen=S(r['hyogen']), aite=self.bunsho_kagi(bkey))}")
        nai = [E(D.bun("mcp-irete-inai"))]
        blocks.append(([f"## {E(D.kotoba('資料どうしの関係の表 e'))}"], items or nai))
        ids = {r["suji"] for r in self.t["atai"] if r["shiryo"].strip() and sj.bunsho_of(r["shiryo"]) == bkey}
        blocks.append(([f"## {E(D.bun('mcp-midashi-suji-ari'))}"],
                       ["- " + self.teigi_kagi(x) for x in self.t["suji"] if x["id"] in ids] or nai))
        items = []
        for p in self.t["bubun"]:
            if p["bunsho"] == bkey and p["shu"] == sj.HYO:
                page = E(D.bun("page", n=sj.page_no(p["tokoro"])))
                items.append(f"- {bh.midashi_ji(D, p)}（{page}、hyo："
                             f"{E(p['n'])}）")
        if items and any(sj.mikakunin(p) for p in self.t["bubun"] if p["bunsho"] == bkey and p["shu"] == sj.HYO):
            items.append(E(D.bun("mikakunin-hyo")))
        blocks.append(([f"## {E(D.bun('mcp-midashi-hyo-ichiran'))}"], items or nai))
        return Outou(self.bunsho_kagi(bkey), self.bunsho_intro(bkey), blocks)

    def hyo(self, bkey, n):
        """表1つ（tools/build_hyo.py の Hyo）を、行ごとの箇条書きにする。表の形で出せない表は、定型文を返す。"""
        D = self.D
        h = bh.Hyo(self.inp, self.t, bkey, n)
        hyo = self.index[(bkey, n)]
        title = self.kagi_ji(bh.midashi_ji(D, hyo), "hyo", n)
        page = E(D.bun("page", n=sj.page_no(hyo["tokoro"])))
        intro = [f"- {self.bunsho_kagi(bkey)}　{page}"]
        oya, mi = [], []
        x = hyo["oya"]
        while x:
            oya.insert(0, self.index[(bkey, x)])
            x = oya[0]["oya"]
        if oya:
            intro.append("- " + "　".join(bh.midashi_ji(D, y) for y in oya))
        intro.append(self.url_gyo(keys.source_url(self.inp, hyo["tokoro"]), "- "))
        if h.problems:
            return Outou(title, intro + ["", E(D.bun("mcp-hyo-dasenai"))]), h.problems
        items = []
        for g in h.gyo:
            lines = [f"- {bh.midashi_ji(D, g)}"]
            for c in h.retsu:
                m = f"{S(c['matome'])}　{bh.midashi_ji(D, c)}" if c["matome"] else bh.midashi_ji(D, c)
                lines.append("  - " + D.bun("hyo-kijutsu-ran", midashi=m, atai=S(h.cell[(g["n"], c["n"])])))
            items.append("\n".join(lines))
        if any(sj.mikakunin(y) for y in [hyo] + oya + h.gyo + h.retsu):
            items.append(E(D.bun("mikakunin-hyo")))
        blocks = [([], items)]
        b = self.by[bkey]
        if b["konkyo"]:
            kp = D.bun("page", n=sj.page_no(b["konkyo_tokoro"]))
            intro.append(f"- {E(D.kotoba('資料の一覧の表 konkyo'))}：「{S(b['konkyo'])}」（{E(kp)}）")
        hoka = bh.hoka_bunsho(self.t, h, bkey)
        if hoka:
            li = []
            for k in sorted(hoka, key=lambda k: (self.by[k]["hiduke"] or "9999", k)):
                pp = "、".join(str(p) for p in sorted(hoka[k]))
                li.append(f"- {self.bunsho_kagi(k)}" + (f"　{E(D.bun('page', n=pp))}" if pp else ""))
            blocks.append(([f"## {E(D.bun('midashi-onaji'))}"], li))
        return Outou(title, intro, blocks), []

    # ツールの説明
    def tools(self, themes):
        D = self.D
        ichi = "、".join
        th_erabu = list(themes)
        id_erabu = [x["id"] for x in self.t["suji"]]
        fa_erabu = list(dict.fromkeys(k for th in themes for k in bt.jun_shisetsu(self._hyo.get(th),
                                                                                 bt.Theme(self.inp, th), self.ref)))
        b_erabu = list(self.by)
        hyo_erabu = [f"{p['bunsho']} {p['n']}" for p in self.t["bubun"] if p["shu"] == sj.HYO]

        def namae_tsuki(ks, f):
            return ichi(f"{k}（{owari(f(k))}）" for k in ks)
        tsuzuki = dict(name=TSUZUKI, type="integer", required=False, description=owari(E(D.bun("mcp-hikisu-tsuzuki"))),
                       erabu=[])
        desc = {
            "theme": (owari(E(D.bun("mcp-tool-theme"))), [
                dict(name="theme", type="string", required=False, erabu=th_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-theme", erabu=namae_tsuki(th_erabu, lambda k: S(bt.Theme(self.inp, k).namae[0]))))))]),
            "suji": (owari(E(D.bun("mcp-tool-suji"))), [
                dict(name="id", type="string", required=True, erabu=id_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-id", erabu=namae_tsuki(id_erabu, lambda k: E(self.teigi[k]["name"])))))),
                dict(name="shiryo", type="string", required=False, erabu=b_erabu,
                     description=owari(E(D.bun("mcp-hikisu-shiryo")))),
                dict(name="uchiwake", type="integer", required=False, erabu=["1"],
                     description=owari(E(D.bun("mcp-hikisu-uchiwake"))))]),
            "shisetsu": (owari(E(D.bun("mcp-tool-shisetsu"))), [
                dict(name="key", type="string", required=True, erabu=fa_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-key", erabu=namae_tsuki(fa_erabu, lambda k: S(self.ref[k]["name"]))))))]),
            "shiryo": (owari(E(D.bun("mcp-tool-shiryo"))), [
                dict(name="bunsho", type="string", required=True, erabu=b_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-bunsho", erabu=namae_tsuki(b_erabu, self.namae.bunsho))))),
                dict(name="hyo", type="integer", required=False, erabu=hyo_erabu,
                     description=owari(E(D.bun("mcp-hikisu-hyo"))))]),
        }
        out = []
        for name, args in TOOLS:
            d, a = desc[name]
            a = a + [tsuzuki]
            assert [x["name"] for x in a] == [x for x, _, _ in args]
            out.append(dict(name=name, description=d, args=a))
        return out


def konkyo_hani(chu):
    """資料の一覧の表の chu の「根拠：」の記述に「見つからない（…）」があれば、括弧の中の字。無ければ空。
    括弧の中に括弧があっても、対になる閉じ括弧までを取る。chu のほかの字は使わない（docs/design.md 3節）。"""
    i = (chu or "").find("根拠：")
    if i < 0:
        return ""
    j = chu.find("見つからない（", i)
    if j < 0 or "。" in chu[i:j]:
        return ""
    k, depth = j + len("見つからない（"), 1
    for x in range(k, len(chu)):
        depth += {"（": 1, "）": -1}.get(chu[x], 0)
        if depth == 0:
            return chu[k:x]
    return ""


def read_skill(path=SKILL_PATH):
    """SKILL.md の出すときの規約の節の、箇条書きの行。→ 文。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    s = next((i for i, x in enumerate(lines) if x.startswith(SKILL_SETSU)), None)
    if s is None:
        raise inputs.InputError(f"{path}：出すときの規約の節（{SKILL_SETSU}）が無い")
    e = next((j for j in range(s + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    out = [x for x in lines[s:e] if x.startswith("- ")]
    if not out:
        raise inputs.InputError(f"{path}：出すときの規約の節に、箇条書きの行が無い")
    return "\n".join(out)


def build(inp, tables, kotoba, read_problems=(), design=None, skill=None):
    """検査を通れば、応答の JSON（辞書）と件数を返す。当たれば Stop。

    tables は tools/build_theme.py の read_tables で読んだもの。
    """
    D = design or bs.read_design()
    problems = [("(e) デザインシステムとの対応", m) for m in design_problems(D)]
    if problems:
        raise Stop(problems)
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in read_problems]
    mondai, _, _ = sj.check_all(inp, tables["suji"], tables["atai"], tables["bunsho"], tables["bubun"],
                                tables["kankei"], tables["theme"])
    problems += [("(a) 表の検査", bs.mondai_str(m)) for m in mondai]
    if problems:
        raise Stop(problems)
    tk = Tsukuru(D, inp, tables)
    themes = list(dict.fromkeys(r["theme"] for r in tables["theme"]))
    tk._hyo, tk._hk, ths, kiroku = {}, {}, {}, []
    for theme in themes:
        th = bt.Theme(inp, theme)
        ths[theme] = th
        if len(th.namae) != 1:
            problems.append(("(c) テーマ", f"テーマの定義に、{theme} の kind「{sj.THEME_NAMAE}」の行が {len(th.namae)} 行ある"
                                         "（1行のはず）"))
        bad = [k for k in th.shisetsu if k not in tk.ref]
        if bad:
            problems.append(("(c) テーマ", f"テーマの施設が、施設の参照表に無い（{'・'.join(bad)}）"))
    if problems:
        raise Stop(problems)
    for theme, th in ths.items():
        ki = [r for r in inp.shisetsu_kiroku() if r["facility"] in th.shisetsu]
        kiroku += [r for r in ki if r not in kiroku]
        katei = ronten.katei(inp, theme)
        for r in katei:
            for c in ("from", "to"):
                if r[c] and not (sj.RE_HIDUKE.fullmatch(r[c]) and (len(r[c]) == 7 or sj.is_ymd(r[c]))):
                    problems.append(("(f) 過程の記録", f"step {r['step']} の {c} の形が違う（{r[c]}）"))
            if not r["from"]:
                problems.append(("(f) 過程の記録", f"step {r['step']} の from が空"))
        more, _ = bt.quote_problems(inp, theme, katei, ki)
        problems += more
        trows = [r for r in tables["theme"] if r["theme"] == theme and r["shu"] == sj.SHISETSU_HYO]
        if trows:
            tk._hyo[theme] = bt.ShisetsuHyo(D, tables, trows[0], tk.ref, ki, set(th.shisetsu), th)
            problems += tk._hyo[theme].problems
        tk._hk[theme] = bt.HyoKijutsu(tables, th, trows[0] if trows else None, tk.ref)
        problems += tk._hk[theme].problems
    if problems:
        raise Stop(list(dict.fromkeys(problems)))
    tk.kiroku = kiroku

    outou, bun, dasenai = {name: {} for name, _ in TOOLS}, [], []

    def ireru(tool, args, o):
        """組 args の応答 o を入れる。続きの組も入れる。"""
        pages = o.pages(D)
        for i, p in enumerate(pages, 1):
            bun.append(p)
            outou[tool][kagi(list(args) + [(TSUZUKI, str(i))])] = len(bun) - 1
            if i == 1:
                outou[tool][kagi(args)] = len(bun) - 1

    ireru("theme", [], tk.theme_ichiran(themes))
    for theme, th in ths.items():
        ireru("theme", [("theme", theme)], tk.theme(theme))
    for t in tables["suji"]:
        rs = [r for r in tables["atai"] if r["suji"] == t["id"]]
        ireru("suji", [("id", t["id"])], tk.suji(t))
        if any(r["kubun"] for r in rs):
            ireru("suji", [("id", t["id"]), ("uchiwake", "1")], tk.suji(t, uchiwake=True))
        docs = dict.fromkeys(sj.bunsho_of(r["shiryo"]) for r in rs if r["shiryo"].strip())
        for b in docs:
            if b in tk.by:
                ireru("suji", [("id", t["id"]), ("shiryo", b)], tk.suji(t, b))
                if any(r["kubun"] and sj.bunsho_of(r["shiryo"]) == b for r in rs if r["shiryo"].strip()):
                    ireru("suji", [("id", t["id"]), ("shiryo", b), ("uchiwake", "1")], tk.suji(t, b, True))
    seen = set()
    for theme, th in ths.items():
        for k in bt.jun_shisetsu(tk._hyo.get(theme), th, tk.ref):
            if k not in seen:
                seen.add(k)
                ireru("shisetsu", [("key", k)], tk.shisetsu(k, theme, th))
    for b in tk.by:
        ireru("shiryo", [("bunsho", b)], tk.shiryo(b))
        for p in tables["bubun"]:
            if p["bunsho"] == b and p["shu"] == sj.HYO:
                o, why = tk.hyo(b, p["n"])
                if why:
                    dasenai.append((f"{b} {p['n']}", why))
                ireru("shiryo", [("bunsho", b), ("hyo", p["n"])], o)
    if tk.namae.problems or tk.problems:
        raise Stop(list(dict.fromkeys(tk.namae.problems + tk.problems)))

    tools = tk.tools(themes)
    nai = {name: D.bun("mcp-nai", tool=name) + D.bun("mcp-hani-nai") for name, _ in TOOLS}
    top = D.bun("mcp-top", name=NAME)
    setsumei = D.bun("mcp-setsumei")
    skill = (read_skill() if skill is None else skill) + "\n- " + D.bun("mcp-hani-nai")
    # 使わない言葉の検査：応答の文、ツールと引数の説明、定型文
    zenbu = bun + [E(x) for x in list(nai.values()) + [top, setsumei, skill]]
    zenbu += [E(x["description"]) for x in tools] + [E(a["description"]) for x in tools for a in x["args"]]
    problems = []
    for x in zenbu:
        problems += bn.kotoba_problems(f"<p>{x}</p>", *kotoba)
    if problems:
        raise Stop([("(b) 使わない言葉", m) for _, m in dict.fromkeys(problems)])
    data = dict(name=NAME, version=VERSION, description=setsumei, instructions=skill, top=top, tools=tools,
                nai=nai, outou=outou, bun=[owari(x) for x in bun])
    info = dict(kumi=sum(len(v) for v in outou.values()), bun=len(bun), nagai=max(len(owari(x)) for x in bun),
                kaisei_shinai=tk.kaisei.shinai, kaisei_hoka=tk.kaisei.hoka,
                dasenai=dasenai, kazu={k: len(v) for k, v in outou.items()})
    return data, info


def dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv=None, teigi_dir=None):
    p = argparse.ArgumentParser(description="MCP サーバーの応答の JSON を作る")
    p.add_argument("--out", default=OUT_PATH)
    p.add_argument("--hikaku")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        inp = inputs.Inputs()                                   # (d) lock と入力
        tables, read_problems = bt.read_tables(teigi_dir)
        data, info = build(inp, tables, bn.read_kotoba(), read_problems, bs.read_design())
    except (inputs.InputError, OSError, UnicodeDecodeError) as e:
        print(f"止めた：(d) lock と入力、または表を読めない\n{e}", file=sys.stderr)
        return 1
    except Stop as e:
        print(f"止めた：{len(e.problems)} 件。JSON は作っていない。", file=sys.stderr)
        for kind, msg in e.problems:
            print(f"  - {kind}：{msg}", file=sys.stderr)
        return 1
    s = dumps(data)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"{os.path.relpath(os.path.abspath(a.out), inputs.ROOT)}（{len(s.encode('utf-8'))} バイト）")
    for x, why in info["dasenai"]:
        print(f"表の形で出せない表 {x}：{why[0][1]}")
    print(f"組 {info['kumi']}（{'、'.join(f'{k} {v}' for k, v in info['kazu'].items())}）、応答の文 {info['bun']}、"
          f"いちばん長い応答 {info['nagai']} 字")
    print(f"一部改正の前後の数値で、組み合わせなかった行 {info['kaisei_shinai']}"
          f"（ほかのページの行が組み合わされているので出さない行 {info['kaisei_hoka']}）")
    if a.hikaku:
        moto = None
        if os.path.exists(a.hikaku):
            with open(a.hikaku, encoding="utf-8") as f:
                moto = f.read()
        if moto != s:
            print(f"止めた：作り直した JSON が {os.path.relpath(os.path.abspath(a.hikaku), inputs.ROOT)} と違う。"
                  "データか言葉を変えたのに、MCP の応答を作り直していない。"
                  "python3 -B tools/build_mcp.py で作り直して、コミットする。", file=sys.stderr)
            return 1
        print(f"{os.path.relpath(os.path.abspath(a.hikaku), inputs.ROOT)} と同じ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
