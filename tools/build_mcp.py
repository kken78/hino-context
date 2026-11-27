"""MCP サーバーの応答を、表と入力から作る（docs/mcp.md、docs/design.md 3節・4節）。

実行：python3 -B tools/build_mcp.py [--out <ファイル>] [--hikaku <ファイル>]
  既定の出力は mcp/data/outou.json。Cloudflare に置くプログラム（mcp/src/index.ts）は、この JSON を引いて返すだけで、
  応答の文を組み立てない。
  --hikaku を付けると、作った JSON が、そのファイルと同じかを確認する（tools/kensa.py が使う。違えば終了コード 1）。
中身は teigi/ の表と、lock の版の入力だけから作る。数値を計算しない。良し悪しを書かない。
画面に出す言葉は、docs/design.md 3節の2つの表から読む（tools/build_suji.py の read_design と同じ読み方）。
このファイルには、画面の言葉を書かない。資料の名前、時期、掲載の場所などは、ページを作るツールの関数を使う。

応答は、ツールと引数の組ごとに1つの文（見出しと箇条書き。HTML は入れない）。1回の応答が JOGEN 字を超える組は、
区切りのよい所（資料ごと、表ごと、項目ごと）で分け、続きを引数 page で返す。
論点（issue）の応答は、試作のページ（tools/build_note.py）と同じ集め方（collect と Page.ronten）と検査で作る。

作る前の検査（1つでも当たれば、件数と該当行を示して、何も書かずに止まる。終了コード 1）：
  (a) 表の検査（tools/suji.py の check_all）で問題がある
  (b) 応答の文に、docs/design.md 2節の「使わない」言葉が残っている（資料からの文は除く）
  (c) テーマの定義と施設の参照表が合わない（tools/build_theme.py の build と同じ検査）
  (d) lock と入力が合わない
  (e) docs/design.md 3節の表と、このツールが合わない（tools/build_suji.py の design_problems）
  (f) 過程の記録と施設の記録の quote が、source の資料の本文に無い。資料の名前を作れない（tools/build_theme.py と同じ）
  (g) 施設の割り当てが未確認の行がある（tools/build_theme.py と同じ）
  (h) 論点の仮の表（teigi/note-<テーマ>.tsv）と事項の表（teigi/jiko.tsv）の検査と、試作のページと同じ検査
      （tools/build_note.py の jiko_ni_suru と collect）
  (i) 質問が取り上げた資料と出来事の表（taio/konkyo.tsv）の検査（tools/konkyo.py の check）と、範囲の段落の確認。
      資料と出来事の名前の表（teigi/konkyo-namae.tsv）の検査（tools/yomi.py の check_namae）
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
import konkyo  # noqa: E402
import ronten  # noqa: E402
import shogo  # noqa: E402
import suji as sj  # noqa: E402
import yomi as ym  # noqa: E402

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

NOTE_DIR = os.path.join(inputs.ROOT, "teigi")   # 論点の仮の表 note-<テーマ>.tsv の場所（SCHEMA.md §5）

# ツールと引数（名前、型、必須か）。引数の順は、応答を引く ID の並びの順でもある（docs/mcp.md）。
# 名前は 2026-11-27 に直した（suji → item、shisetsu → facility、shiryo → document。引数 tsuzuki → page など）。
# プログラムの中の関数の名前は、前のままにしている。
TSUZUKI = "page"
TOOLS = (("theme", (("theme", "string", False), (TSUZUKI, "integer", False))),
         ("issue", (("issue", "string", True), (TSUZUKI, "integer", False))),
         ("item", (("item", "string", True), ("document", "string", False), ("breakdown", "integer", False),
                   (TSUZUKI, "integer", False))),
         ("facility", (("facility", "string", True), (TSUZUKI, "integer", False))),
         ("document", (("document", "string", True), ("table", "integer", False), (TSUZUKI, "integer", False))),
         ("event", (("event", "string", True), (TSUZUKI, "integer", False))))


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
    項目は、改行を含んでよい（分けるときは、項目の途中では分けない）。
    ブロックに3つ目の要素 True を付けると、そのブロックは新しい応答から始める（論点の、質問ごとの部分）。
    pages を呼んだあと、hajime に、新しい応答から始めたブロックの、始まりの応答の番号（1から）が入る。"""

    def __init__(self, title, intro=(), blocks=()):
        self.title, self.intro, self.blocks = title, list(intro), [b for b in blocks if b and b[1]]
        self.hajime = []

    def pages(self, D):
        """→ 応答の文（HTML の断片）の並び。1つ目から。"""
        atama = [E(D.bun("mcp-atama")), f"# {self.title}"]
        self.hajime = []
        yobi = len(owari(E(D.bun("mcp-tsuzuki", n=99)))) + len(owari(E(D.bun("mcp-tsuzuki-dai", n=99, m=99)))) + 4

        def nagasa(lines):
            return len(owari("\n".join(lines))) + yobi

        out, cur, aru = [], atama + self.intro, False      # aru：いまの応答に、ブロックの中身が入っているか
        for blk in self.blocks:
            head, items = blk[0], blk[1]
            if len(blk) > 2 and blk[2]:
                if aru:
                    out.append(cur)
                    cur, aru = list(atama), False
                self.hajime.append(len(out) + 1)
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
        self.note = {}                   # テーマ → (論点の仮の表, build_note.Page)。build で入れる
        self.konkyo = {}                 # 資料の ID → 質問が取り上げた資料と出来事の表の質問（Page.ronten の qs と同じ形）。build で入れる
        self.konkyo_pg = {}              # 質問 → 注（Page.chu_list）を引く build_note.Page（その質問があるテーマの Page）
        self.event = {}                  # 出来事の ID → (資料と出来事の名前の表の行, 質問の並び（konkyo と同じ形）, テーマの集まり)

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
        return self.kagi_ji(E(t["name"]), "item", t["id"])

    def bunsho_kagi(self, bkey):
        return self.kagi_ji(self.namae.bunsho(bkey), "document", bkey)

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
        if theme in self.note:
            blocks += self.ronten_ichiran(theme)
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
        items = ["- " + self.kagi_ji(S(self.ref[k]["name"]), "facility", k)
                 for k in self.shisetsu_ichiran(theme, th)]
        blocks.append(([f"## {E(D.bun('mcp-midashi-shisetsu'))}"], items))
        docs = sorted((b for b in self.by if th.has(b)), key=lambda b: (self.by[b]["hiduke"] or "9999", b))
        hb = bs.hiduke_bun(D, False, any(self.namae.hiduke_nashi(b) for b in docs))
        D.kotoba("質問が取り上げた資料と出来事の表 aite")
        blocks.append(([f"## {E(D.bun('mcp-midashi-shiryo'))}", E(D.bun("mcp-shiryo-setsumei")) + E(hb)],
                       ["- " + self.bunsho_kagi(b) + (f"　{E(D.bun('mcp-shiryo-konkyo-ari'))}" if self.konkyo.get(b) else "")
                        for b in docs]))
        ev = [(k, r, qs) for k, (r, qs, ths_) in self.event.items() if theme in ths_]
        if ev:
            blocks.append(([f"## {E(D.kotoba('資料と出来事の名前の表 shu が「出来事」'))}", E(D.bun("mcp-dekigoto-setsumei"))],
                           [f"- {self.event_kagi(k)}　{E(D.bun('mcp-dekigoto-kazu', n=len([q for q in qs if q['theme'] == theme])))}"
                            for k, r, qs in ev]))
        # 項目は、まだテーマと結び付けていない。テーマの表に行があるテーマ（項目を作ったテーマ）にだけ並べ、
        # ほかのテーマに、別のテーマの項目を並べない（docs/design.md 4節）
        teigi = t["suji"] if any(r["theme"] == theme for r in t["theme"]) else []
        if teigi:
            blocks.append(([f"## {E(D.bun('mcp-midashi-teigi'))}", E(D.bun("mcp-teigi-setsumei"))],
                           ["- " + self.teigi_kagi(x) for x in teigi]))
        return Outou(S(name), blocks=blocks)

    def event_kagi(self, k):
        """出来事の名前（namae と、括弧に setsumei）と ID。"""
        D = self.D
        r = self.event[k][0]
        D.dasanai("資料と出来事の名前の表 namae、setsumei")
        D.dasanai("資料と出来事の名前の表 id")
        name = S(r["namae"]) + (f"（{S(r['setsumei'])}）" if r["setsumei"] else "")
        return self.kagi_ji(name, "event", k)

    def event_kagi_namae(self, k):
        return S(self.event[k][0]["namae"])

    def event_outou(self, k):
        """出来事1つ。document の、資料を取り上げている質問と同じ形（gikai）で返す。"""
        D = self.D
        r, qs, _ = self.event[k]
        return self.gikai(self.event_kagi(k), [], [], qs, D.bun("mcp-event-short"),
                          lambda q: self.konkyo_pg.get(q["question"]),
                          f"## {E(D.bun('mcp-midashi-event-konkyo', n=len(qs)))}", [], k)

    def shurui(self, r):
        """事項の表の shurui → 種類の言葉（docs/design.md 3節）。"""
        D = self.D
        return {"kadai": D.kotoba("事項の表 shurui が「kadai」"), "torikumi": D.kotoba("事項の表 shurui が「torikumi」"),
                "atai": D.kotoba("事項の表 shurui が「atai」")}[r["shurui"]]

    def ronten_ichiran(self, theme):
        """テーマの応答の、論点のブロックの並び（docs/design.md 4節）。
        事項の表があるテーマは、計画の章立ての要素ごとにまとめ、種類を出す。記録の無い論点は ID を付けずに、ronten-mada の文を出す。
        事項の表が無いテーマは、論点の仮の表の論点と準備中の行を、表の順に並べる。"""
        D = self.D
        T = self.note[theme][0]
        midashi = f"## {E(D.bun('mcp-midashi-ronten'))}"
        if not T.get("jiko"):
            items = ["- " + self.kagi_ji(E(P), "issue", slug) for P, slug, _, _ in T["topics"]]
            items += ["- " + D.bun("mcp-junbi", name=E(x)) for x in T["junbi"]]
            return [([midashi, E(D.bun("mcp-ronten-setsumei"))], items)]
        keikaku, matome = bn.jiko_matome(self.inp, T)
        D.dasanai("事項の表 taikei")
        D.dasanai("事項の表 taikei が「nashi」")
        D.dasanai("事項の表 matome")
        D.dasanai("候補の名前と扱いの対応の表 atsukai が「ほかのテーマで扱う候補」か「決めていない」")   # 表に行を作らない（tools/yomi.py）
        out = []
        for youso, rs0 in matome:
            mi = f"### {S(youso['name'])}" if youso else f"### {E(D.bun('ronten-nashi', keikaku=S(keikaku)))}"
            for mt, rs in ([("", rs0)] if youso else bn.nashi_wake(rs0)):
                items = []
                for r in rs:
                    shu = f"{E(D.kotoba('事項の表 shurui'))}：{E(self.shurui(r))}"
                    if r["aru"]:
                        items.append(f"- {self.kagi_ji(E(r['name']), 'issue', r['id'])}　{shu}")
                    else:
                        items.append(f"- {E(r['name'])}　{shu}　（{E(D.bun('ronten-mada'))}）")
                if mt:
                    head = [f"#### {E(mt)}", E(D.bun("ronten-matome-setsumei"))]
                else:
                    head = [mi] if out else [midashi, E(D.bun("mcp-ronten-setsumei-jiko", keikaku=S(keikaku))), mi]
                out.append((head, items))
        return out

    def shisetsu_ichiran(self, theme, th):
        """テーマの施設のうち、facility で返す内容（施設の記録、表の行か列、施設を指す数値）があるもの。
        テーマの施設の順（tools/build_theme.py の jun_shisetsu）。内容が無い施設は、theme の応答にも、facility の組にも
        入れない（docs/design.md 4節。2026-11-27）。"""
        hk = self._hk.get(theme)

        def aru(k):
            return (any(r["facility"] == k for r in self.kiroku) or bool(hk and hk.gyo.get(k))
                    or any(r["jotai"] == sj.ARU and k in sj.atai_shisetsu(r, self.index) for r in self.t["atai"]))
        return [k for k in bt.jun_shisetsu(self._hyo.get(theme), th, self.ref) if aru(k)]

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
                gyo = self.kagi_ji(bh.midashi_ji(D, g), "facility", ks[0])
            else:
                gyo = bh.midashi_ji(D, g) + "（" + "、".join(
                    self.kagi_ji(S(self.ref[k]["name"]), "facility", k) for k in ks) + "）"
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
                # 同じページの同じ文が、上の施設の記録に出ている行は除く
                if r["inyo"].strip() and any(q["source"] == r["shiryo"] and sj.shogo.norm(r["inyo"]) in sj.shogo.norm(q["quote"])
                                             for q in rs):
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
        return Outou(self.kagi_ji(S(ref["name"]), "facility", k), intro, blocks)

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
                         kara=len(kk), e=len(ke), q=len(self.konkyo.get(bkey, [])))),
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
                items.append(f"- {bh.midashi_ji(D, p)}（{page}、table："
                             f"{E(p['n'])}）")
        if items and any(sj.mikakunin(p) for p in self.t["bubun"] if p["bunsho"] == bkey and p["shu"] == sj.HYO):
            items.append(E(D.bun("mikakunin-hyo")))
        blocks.append(([f"## {E(D.bun('mcp-midashi-hyo-ichiran'))}"], items or nai))
        qs = self.konkyo.get(bkey, [])
        if not qs:
            return Outou(self.bunsho_kagi(bkey), self.bunsho_intro(bkey), blocks)
        # 質問が取り上げた資料と出来事の表（SCHEMA.md 7.10、docs/design.md 4節）。issue の質問のブロックと同じ形
        D.kotoba("質問が取り上げた資料と出来事の表 hani")
        return self.gikai(self.bunsho_kagi(bkey), self.bunsho_intro(bkey), blocks, qs, D.bun("mcp-konkyo-short"),
                          lambda q: self.konkyo_pg.get(q["question"]),
                          f"## {E(D.bun('mcp-midashi-konkyo', n=len(qs)))}", [], bkey)

    def hyo(self, bkey, n):
        """表1つ（tools/build_hyo.py の Hyo）を、行ごとの箇条書きにする。表の形で出せない表は、定型文を返す。"""
        D = self.D
        h = bh.Hyo(self.inp, self.t, bkey, n)
        hyo = self.index[(bkey, n)]
        title = self.kagi_ji(bh.midashi_ji(D, hyo), "table", n)
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

    # issue
    def kubun_of(self, source):
        """記述の資料の ID → 区分の字。会議録は発言者の役職から決め（Namae.kubun）、ほかは計画と、町が公開した資料の区分（1つ目の表の行）。"""
        if source.startswith("sp:"):
            return self.namae.kubun(keys.sid_of(source)) or ""
        return bs.RE_KAGIKAKKO.search(self.D.kotoba("shiryo が計画・町の資料")).group(1)

    def chu_gyo(self, pg, source, text, sita):
        """試作のページと同じ条件で付ける注（Page.chu_list）→ 項目の行の並び。sita は字下げ。"""
        D, out = self.D, []
        for c in pg.chu_list(source, text):
            nm, url = self.moto(c["moto"])
            out.append(f"{sita}- {D.bun('mcp-issue-chu', chu=E(c['text']))}")
            moto = f"{sita}  - {E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{nm}" + (f"　{E(url)}" if url else "")
            if c["kakunin"]:
                moto += "　" + D.bun("mcp-issue-kakunin-bi", hi=E(bs.hi_str(D, c["kakunin"])))
            out.append(moto)
        return out

    def kijutsu(self, pg, x, kubun=True):
        """論点の記述（hino-ronten の事柄の記録の1行）→ 項目。引用を先に出す。"""
        D = self.D
        nm, url = self.moto(x["source"], x["quote"])
        jiki = E(bs.hi_str(D, x["source_date"]))
        lines = [f"- 「{S(x['quote'])}」",
                 "  - " + (D.bun("mcp-issue-jiki-kubun", jiki=jiki, kubun=E(self.kubun_of(x["source"]))) if kubun
                           else D.bun("mcp-issue-jiki", jiki=jiki))]
        a = pg.atai_shu(x)
        if a and a[0] == "kingaku":
            lines.append("  - " + D.bun("mcp-issue-kingaku", atai=S(a[1])))
        elif a:
            lines.append("  - " + D.bun("mcp-issue-suchi", atai=S(a[1])))
        lines += self.chu_gyo(pg, x["source"], x["quote"], "  ")
        lines.append(f"  - {E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{nm}" + (f"　{E(url)}" if url else ""))
        return "\n".join(lines)

    def issue_hani(self, theme):
        """テーマの質問と質疑のうち、論点との対応を確認してある数と時期の文（docs/design.md 4節）。数はデータから数える。"""
        D = self.D
        trows = ronten.themes(self.inp, theme)
        toi = [r["value"] for r in trows if r["kind"] == "問い"]
        shitsugi = [r["value"] for r in trows if r["kind"] == "質疑"]
        zumi = ronten.taio_shitsumon(self.inp, set(toi + shitsugi))

        def kikan(qs):
            ym = sorted(q.split("_")[1][:6] for q in qs)
            a, z = (D.bun("nengetsu", nen=int(x[:4]), tsuki=int(x[4:])) for x in (ym[0], ym[-1]))
            return a if a == z else D.bun("kikan", a=a, z=z)

        yomi = self.yomi_q.get(theme, [])      # 生成AIの2回の読み取りで読んだ質問（SCHEMA.md 7.10）
        tz = [q for q in toi if q in zumi]
        tn = [q for q in toi if q not in zumi and q not in yomi]
        sz = [q for q in shitsugi if q in zumi]
        if not (tz or sz):
            return []
        # 記録がある問いか質疑が0のテーマでも、文として読める形にする（docs/design.md 4節。2026-11-27）
        if tz and sz:
            out = [E(D.bun("mcp-issue-hani", toi=len(toi), shitsugi=len(shitsugi), toi_zumi=len(tz),
                           kikan=E(kikan(tz)), shitsugi_zumi=len(sz)))]
        elif tz:
            out = [E(D.bun("mcp-issue-hani-toi-dake", toi=len(toi), shitsugi=len(shitsugi), toi_zumi=len(tz),
                           kikan=E(kikan(tz))))]
        else:
            out = [E(D.bun("mcp-issue-hani-shitsugi-dake", toi=len(toi), shitsugi=len(shitsugi),
                           shitsugi_zumi=len(sz)))]
        if yomi:
            out.append(E(D.bun("mcp-issue-hani-yomi", n=len(yomi), kikan=E(kikan(yomi)),
                               soto=len([q for q in yomi if q not in toi]), toi=len(toi))))
        if tn:
            out.append(E(D.bun("mcp-issue-hani-toi", n=len(tn), kikan=E(kikan(tn)))))
        if len(sz) < len(shitsugi):
            out.append(E(D.bun("mcp-issue-hani-shitsugi", n=len(shitsugi) - len(sz))))
        return out

    def issue(self, theme, P, slug, short, setsumei):
        """論点1つ。試作のページの論点のページと同じ集め方（Page.ronten）で、同じ見出しで返す。
        質問ごとに、論点に関する段落を、続きの応答で返す（docs/design.md 4節）。"""
        D, inp = self.D, self.inp
        T, pg = self.note[theme]
        R = pg.ronten(P)
        intro = [D.bun("mcp-issue-lead", theme=E(T["theme"]), setsumei=E(setsumei))]
        blocks = [([f"## {E(D.bun('mcp-midashi-issue-shiryo'))}"],
                   [self.kijutsu(pg, x, False) for x in R["docs"]] or [E(D.bun("mcp-issue-shiryo-nashi"))])]
        items = [self.kijutsu(pg, x) for x in R["ko"]]
        blocks.append(([f"## {E(D.bun('mcp-midashi-issue-setsumei'))}"], items))
        if R["tome"]:
            blocks.append(([f"## {E(D.bun('mcp-midashi-issue-kongo'))}"],
                           [self.kijutsu(pg, x) for x in R["tome"]] + [E(D.bun("mcp-issue-kongo-setsumei"))]))
        if R["mokuteki"]:
            blocks.append(([f"## {E(D.kotoba('つながりの記録 link が「目的と手段」'))}", E(D.bun("mokuteki-setsumei"))],
                           [self.mokuteki(a) for a in R["mokuteki"]]))
        qs = R["qs"]
        return self.gikai(self.kagi_ji(E(P), "issue", slug), intro, blocks, qs, short, lambda q: pg,
                          f"## {E(D.bun('mcp-midashi-issue-gikai', n=len(qs)))}", self.issue_hani(theme), slug)

    def mokuteki(self, a):
        """つながりの記録の相手1つ（Page.ronten の mokuteki の1つ）→ 項目。相手の名前のあとに、issue があれば ID を付ける。"""
        D = self.D
        yaku = D.kotoba("つながりの記録 upper") if a["gawa"] == "upper" else D.kotoba("つながりの記録 lower")
        name = self.kagi_ji(E(a["name"]), "issue", a["slug"]) if a["slug"] else E(a["name"])
        lines = [f"- {E(yaku)}：{name}"]
        for r in a["rows"]:
            nm, url = self.moto(r["source"], r["quote"])
            lines += [f"  - {E(D.kotoba('つながりの記録 quote'))}：「{S(r['quote'])}」",
                      f"    - {E(D.kotoba('つながりの記録 source'))}：{nm}" + (f"　{E(url)}" if url else "")]
        return "\n".join(lines)

    def gikai(self, title, intro, blocks, qs, short, pg_of, gikai, hani, ji):
        """議会での質問と答弁のブロック（issue と document で共通。docs/design.md 4節）。1回めの応答に質問の一覧を出し、
        質問ごとの部分を、続きの応答で返す。pg_of は、質問 → 注（Page.chu_list）を引く build_note.Page（無ければ None）。
        hani は、扱っている質問の範囲の文の並び。ji は、検査の問題に出す字。"""
        D, inp = self.D, self.inp
        zentai = E(D.bun("mcp-issue-zentai"))

        def shitsumon(q):
            if q["sitsugi"]:
                shu = D.bun("mcp-issue-shitsugi")
            else:
                shu = D.bun("mcp-issue-ippan")
            return D.bun("mcp-issue-shitsumon", hi=E(bs.hi_str(D, q["date"])), shu=E(shu), dai=bn.S_kagi(q["dai"]))

        def bubun(q):
            return E(D.bun("mcp-issue-bubun", short=E(short), n=len(q["paras"])))

        def kakunin(q):
            return E(bn.kakunin_go(D, q))

        tsuzuki = []
        for q in qs:
            head = [gikai, f"### {shitsumon(q)}　{bubun(q)}", kakunin(q), f"{zentai}：{E(keys.source_url(inp, q['question']))}"]
            items = []
            pg = pg_of(q)
            for sid, i, para in q["paras"]:
                nm = self.namae.shiryo("sp:" + sid)[0]
                lines = [f"- 「{S(para)}」", f"  - {nm}　{E(D.bun('danraku', n=i))}"]
                if q["mikakunin"]:
                    lines.append(f"  - {E(bn.yomi_go(D, q['yomi'][(sid, i)]))}")
                if pg is not None:
                    lines += self.chu_gyo(pg, "sp:" + sid, para, "  ")
                lines.append(self.url_gyo(keys.search_url(sid, i), "  - "))
                items.append("\n".join(lines))
            tsuzuki.append((head, items, True))

        def tsukuru(bango):
            items = [f"- {shitsumon(q)}\n  - {kakunin(q)}\n  - {self.kagi_ji(bubun(q), TSUZUKI, str(n))}"
                     f"\n  - {zentai}：{E(keys.source_url(inp, q['question']))}" for q, n in zip(qs, bango)]
            setsumei = [E(D.bun("mcp-issue-gikai-setsumei", short=E(short)))]
            if qs:
                setsumei.append(E(D.bun("mcp-issue-gikai-tsuzuki", short=E(short))))
            mi = any(q["mikakunin"] for q in qs)
            if mi:
                setsumei.append(E(D.bun("yomi-setsumei", short=E(short))))
            keisai = D.bun("keisai-yomi", short=E(short)) if mi else D.bun("mcp-issue-keisai", short=E(short))
            items += [E(keisai)] + list(hani) + [E(D.bun("mcp-issue-owari"))]
            return Outou(title, intro, blocks + [([gikai] + setsumei, items)] + tsuzuki)

        # 続きの番号は、分けてみるまで分からないので、仮の番号で分けてから、その番号で作り直す
        o = tsukuru([99] * len(qs))
        o.pages(self.D)
        bango = list(o.hajime)
        o = tsukuru(bango)
        o.pages(self.D)
        if o.hajime != bango:
            self.problems.append(("(h) 論点", f"{ji}：続きの番号が、作り直すと変わる（{bango} → {o.hajime}）"))
        return o

    # ツールの説明
    def tools(self, themes):
        D = self.D
        ichi = "、".join
        th_erabu = list(themes)
        id_erabu = [x["id"] for x in self.t["suji"]]
        fa_erabu = list(dict.fromkeys(k for th in themes for k in self.shisetsu_ichiran(th, bt.Theme(self.inp, th))))
        b_erabu = list(self.by)
        hyo_erabu = [f"{p['bunsho']} {p['n']}" for p in self.t["bubun"] if p["shu"] == sj.HYO]
        is_namae = {slug: P for T, _ in self.note.values() for P, slug, _, _ in T["topics"]}
        is_erabu = list(is_namae)

        def namae_tsuki(ks, f):
            return ichi(f"{k}（{owari(f(k))}）" for k in ks)
        tsuzuki = dict(name=TSUZUKI, type="integer", required=False, description=owari(E(D.bun("mcp-hikisu-tsuzuki"))),
                       erabu=[])
        desc = {
            "theme": (owari(E(D.bun("mcp-tool-theme"))), [
                dict(name="theme", type="string", required=False, erabu=th_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-theme", erabu=namae_tsuki(th_erabu, lambda k: S(bt.Theme(self.inp, k).namae[0]))))))]),
            "issue": (owari(E(D.bun("mcp-tool-issue"))), [
                dict(name="issue", type="string", required=True, erabu=is_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-issue", erabu=namae_tsuki(is_erabu, lambda k: E(is_namae[k]))))))]),
            "item": (owari(E(D.bun("mcp-tool-suji"))), [
                dict(name="item", type="string", required=True, erabu=id_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-id", erabu=namae_tsuki(id_erabu, lambda k: E(self.teigi[k]["name"])))))),
                dict(name="document", type="string", required=False, erabu=b_erabu,
                     description=owari(E(D.bun("mcp-hikisu-shiryo")))),
                dict(name="breakdown", type="integer", required=False, erabu=["1"],
                     description=owari(E(D.bun("mcp-hikisu-uchiwake"))))]),
            "facility": (owari(E(D.bun("mcp-tool-shisetsu"))), [
                dict(name="facility", type="string", required=True, erabu=fa_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-key", erabu=namae_tsuki(fa_erabu, lambda k: S(self.ref[k]["name"]))))))]),
            "event": (owari(E(D.bun("mcp-tool-event"))), [
                dict(name="event", type="string", required=True, erabu=list(self.event), description=owari(E(D.bun(
                    "mcp-hikisu-event", erabu=namae_tsuki(list(self.event), self.event_kagi_namae)))))]),
            "document": (owari(E(D.bun("mcp-tool-shiryo"))), [
                dict(name="document", type="string", required=True, erabu=b_erabu, description=owari(E(D.bun(
                    "mcp-hikisu-bunsho", erabu=namae_tsuki(b_erabu, self.namae.bunsho))))),
                dict(name="table", type="integer", required=False, erabu=hyo_erabu,
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


def read_notes(inp):
    """論点の仮の表（teigi/note-<テーマ>.tsv）の全部。→ テーマ → 表（build_note.read_teigi）。
    並びは、hino-ronten のテーマの定義の順。"""
    out = {}
    for theme in theme_jun(inp):
        path = os.path.join(NOTE_DIR, "note-" + theme + ".tsv")
        if os.path.exists(path):
            out[theme] = bn.jiko_ni_suru(inp, bn.read_teigi(path, theme), theme)
    return out


def ym_jiko():
    import jiko
    return jiko.read()


def theme_jun(inp):
    """hino-ronten のテーマの定義にあるテーマの ID を、定義の順に並べたもの。"""
    return list(dict.fromkeys(r["theme"] for r in inp.ronten_tsv(ronten.THEMES)))


def konkyo_problems(inp, tk, tables, rows, namae=None, yomi_qs=None):
    """質問が取り上げた資料と出来事の表の行を検査し、資料の ID ごとに質問を tk.konkyo に、出来事の ID ごとに質問を
    tk.event に入れる。→ 問題の並び。
    質問は、どれかのテーマの定義の問い・質疑か、生成AIの2回の読み取りで読んだ質問（yomi_qs。質問 → テーマ）。
    質問の題は、その質問があるテーマの定義の行（無ければ hino-council-search の data/ippan.tsv）から取り、注は、そのテーマの Page から引く。
    同じ資料（出来事）と質問の行は、1つの質問にまとめ、段落ごとに yomi を持つ（「入力の確定済み」の行は、人が確認した質問）。
    資料の ID でも出来事の名前でもない aite（計画（案）と、資料と出来事の名前の表に無い名前）の行は、出さない。"""
    namae = ym.read_namae() if namae is None else namae
    yomi_qs = {} if yomi_qs is None else yomi_qs
    hiduke = {r["bunsho"]: r["hiduke"] for r in tables["bunsho"]}
    bunsho = set(hiduke)
    problems = [("(i) 質問が取り上げた資料", m) for m in konkyo.check(rows, bunsho, hiduke, namae)]
    problems += [("(i) 資料と出来事の名前の表", m) for m in ym.check_namae(namae, bunsho, hiduke)]
    qsrc, qtheme, src_of, ippan = {}, {}, {}, set()
    for r in inp.ronten_tsv(ronten.THEMES):
        if r["kind"] in ("問い", "質疑"):
            qsrc.setdefault(r["value"], r["source"])
            qtheme.setdefault(r["value"], r["theme"])
            src_of.setdefault((r["theme"], r["value"]), r["source"])
    # 読んだ質問は、読んだテーマの質問とする（ほかのテーマの定義にもある質問は、題を、読んだテーマの定義か台帳から取る。
    # 試作のページと issue と同じ題にするため）
    for q, th in yomi_qs.items():
        qsrc[q] = src_of.get((th, q)) or bn.ippan_src(inp, q)
        qtheme[q] = th
        if not src_of.get((th, q)):
            ippan.add(q)
    pres = shogo.check_paras(inp, [dict(where=f"質問が取り上げた資料 {r['question']} / {r['aite']}", hani=r["hani"])
                                   for r in rows])
    for m in pres.mismatched:
        problems.append(("(i) 質問が取り上げた資料", f"{m['where']}：{m['reason']}（{m['source']}）"))
    if problems:
        return problems
    ev = {r["namae"]: r for r in namae if r["shu"] == ym.DEKIGOTO}
    kumi = {}
    for r in rows:
        q = r["question"]
        if q not in qsrc or not bn.qhead_parts(qsrc[q])[1]:
            problems.append(("(i) 質問が取り上げた資料", f"{q}：どのテーマの定義の問い・質疑にも、読んだ質問にも無いか、題が無い"))
            continue
        if r["aite"] in bunsho:
            k = ("bunsho", r["aite"])
        elif r["aite"] in ev:
            k = ("event", ev[r["aite"]]["id"])
        else:
            continue
        x = kumi.setdefault(k, {}).setdefault(q, dict(yomi={}, mikakunin=False))
        for p in keys.paras_of(r["hani"]):
            x["yomi"][p] = r["yomi"]
    for (shu, aite), qd in kumi.items():
        out = []
        for q, x in qd.items():
            who = bn.qhead_parts(qsrc[q])[0]
            # 題は、aite に付いた段落の発言を含む問いの題名（SCHEMA.md 7.10。2026-11-28）
            dai = bn.dai_of(inp, q, qsrc, ippan, {sid for sid, _ in x["yomi"]})
            ys = set(x["yomi"].values())
            if konkyo.NYURYOKU in ys and len(ys) > 1:
                problems.append(("(i) 質問が取り上げた資料", f"{q} / {aite}：入力の確定済みの行と、読み取りの行がある"))
                continue
            mi = konkyo.NYURYOKU not in ys
            paras = [(sid, i, inputs.paragraphs(inp.statement_text(sid))[i - 1]) for sid, i in sorted(x["yomi"])]
            out.append(dict(question=q, date=bn.qdate(q), sitsugi=q.startswith("sq:"), who=who, dai=dai, paras=paras,
                            mikakunin=mi, yomi=x["yomi"] if mi else {}, theme=qtheme[q]))
            if qtheme[q] in tk.note:
                tk.konkyo_pg[q] = tk.note[qtheme[q]][1]
        out.sort(key=lambda x: x["date"], reverse=True)
        if shu == "bunsho":
            tk.konkyo[aite] = out
        else:
            r = next(r for r in namae if r["id"] == aite)
            tk.event[aite] = (r, out, {x["theme"] for x in out})
    # 出来事は、名前の表の順に並べる
    tk.event = {r["id"]: tk.event[r["id"]] for r in namae if r["id"] in tk.event}
    return problems


def build(inp, tables, kotoba, read_problems=(), design=None, skill=None, notes=None, konkyo_rows=None):
    """検査を通れば、応答の JSON（辞書）と件数を返す。当たれば Stop。

    tables は tools/build_theme.py の read_tables で読んだもの。notes は read_notes で読んだもの（None なら読む）。
    konkyo_rows は taio/konkyo.tsv の行（None なら読む）。
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
    # テーマは、テーマの表（teigi/theme.tsv）に行があるテーマと、論点の仮の表があるテーマ（docs/design.md 4節。2026-11-27）
    notes = read_notes(inp) if notes is None else notes
    konkyo_rows = konkyo.read() if konkyo_rows is None else konkyo_rows
    themes = list(dict.fromkeys([r["theme"] for r in tables["theme"]] + list(notes)))
    tk._hyo, tk._hk, ths, kiroku, katei_dasanai = {}, {}, {}, [], []
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
        dasanai, more = ronten.katei_dasanai(inp, theme)
        problems += [("(f) 過程の記録", m) for m in more]
        katei_dasanai += [(theme, r["step"], riyu) for r, riyu in dasanai]
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
    # (h) 論点：試作のページと同じ集め方と検査（tools/build_note.py の collect）
    tk.note = {}
    for theme, T in notes.items():
        model, more, _ = bn.collect(inp, T, theme)
        problems += more
        tk.note[theme] = (T, bn.Page(inp, T, model))
    # 生成AIの2回の読み取りで読んだ質問（SCHEMA.md 7.10）。テーマごとの質問の並び（範囲の文に使う）と、質問 → テーマ
    tk.yomi_q = {}
    yomi_qs = {}
    jth = {r["id"]: r["theme"] for r in ym_jiko()}
    yomi_rows = ym.read() if os.path.exists(ym.PATH) else []
    yomi_yonda = ym.shitsumon() if os.path.exists(ym.TABA) else []
    for r in yomi_rows:
        yomi_qs.setdefault(r["question"], jth[r["jiko"]])
    for q in yomi_yonda:
        if q in yomi_qs:
            tk.yomi_q.setdefault(yomi_qs[q], []).append(q)
    # (i) 質問が取り上げた資料と出来事の表
    problems += konkyo_problems(inp, tk, tables, konkyo_rows, yomi_qs=yomi_qs)
    slugs = [slug for T, _ in tk.note.values() for _, slug, _, _ in T["topics"]]
    problems += [("(h) 論点", f"論点の ID {x} が、2つ以上のテーマにある") for x in sorted({x for x in slugs if slugs.count(x) > 1})]
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
    for theme, (T, _) in tk.note.items():
        for P, slug, short, setsumei in T["topics"]:
            ireru("issue", [("issue", slug)], tk.issue(theme, P, slug, short, setsumei))
    for t in tables["suji"]:
        rs = [r for r in tables["atai"] if r["suji"] == t["id"]]
        ireru("item", [("item", t["id"])], tk.suji(t))
        if any(r["kubun"] for r in rs):
            ireru("item", [("item", t["id"]), ("breakdown", "1")], tk.suji(t, uchiwake=True))
        docs = dict.fromkeys(sj.bunsho_of(r["shiryo"]) for r in rs if r["shiryo"].strip())
        for b in docs:
            if b in tk.by:
                ireru("item", [("item", t["id"]), ("document", b)], tk.suji(t, b))
                if any(r["kubun"] and sj.bunsho_of(r["shiryo"]) == b for r in rs if r["shiryo"].strip()):
                    ireru("item", [("item", t["id"]), ("document", b), ("breakdown", "1")], tk.suji(t, b, True))
    seen = set()
    for theme, th in ths.items():
        for k in tk.shisetsu_ichiran(theme, th):
            if k not in seen:
                seen.add(k)
                ireru("facility", [("facility", k)], tk.shisetsu(k, theme, th))
    for k in tk.event:
        ireru("event", [("event", k)], tk.event_outou(k))
    for b in tk.by:
        ireru("document", [("document", b)], tk.shiryo(b))
        for p in tables["bubun"]:
            if p["bunsho"] == b and p["shu"] == sj.HYO:
                o, why = tk.hyo(b, p["n"])
                if why:
                    dasenai.append((f"{b} {p['n']}", why))
                ireru("document", [("document", b), ("table", p["n"])], o)
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
                dasenai=dasenai, kazu={k: len(v) for k, v in outou.items()}, katei_dasanai=katei_dasanai)
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
    for theme, step, riyu in info["katei_dasanai"]:
        print(f"出さない過程の記録 {theme} step {step}：{riyu}")
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
