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
  (j) 質問の題と分野の対応の表（taio/bunya.tsv）と、分野に無い話題の名前の表（teigi/bunya-wadai.tsv）の検査
      （tools/bunya.py の check と check_wadai）。台帳の題の start の発言と段落が会議録にあること
  (k) 施策検証結果報告書の記述（SCHEMA.md 7.12）：入力の施策検証シートの表と検収の台帳、総合戦略との結び付け、
      施策検証の取り組みと分野の対応の表（taio/kensho-bunya.tsv）が作り直した行と同じであること（tools/kensho.py の matome）
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

import build_bunya as bb  # noqa: E402
import build_hyo as bh  # noqa: E402
import build_note as bn  # noqa: E402
import bunya as bu  # noqa: E402
import build_suji as bs  # noqa: E402
import build_theme as bt  # noqa: E402
import inputs  # noqa: E402
import jiko  # noqa: E402
import keys  # noqa: E402
import kensho as ks  # noqa: E402
import konkyo  # noqa: E402
import ronten  # noqa: E402
import ronten_kisai as rk  # noqa: E402
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
TSUNAGARI_ICHIRAN = 3                # theme と field のまとまりの見出しに添える、同じ題の数の多いまとまりの数（docs/design.md 4節。2026-11-28。案）
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
         ("event", (("event", "string", True), (TSUZUKI, "integer", False))),
         ("field", (("field", "string", False), (TSUZUKI, "integer", False))),
         ("review", (("review", "string", True), (TSUZUKI, "integer", False))))


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
        self.bu = None                   # 分野と題（tools/bunya.py の matome に、計画 kk を足したもの）。build で入れる
        self.bunya_ronten = {}           # 題の (from, n) → 論点の (名前, ID, テーマ) の並び（tools/bunya.py の ronten_of_dai）。build で入れる
        self.ks = None                   # 施策検証結果報告書の記述（tools/kensho.py の matome）。build で入れる
        self.tsunagari = {}              # まとまりの ID → 同じ題に付いた論点の入る、ほかのまとまりと論点（tsunagari_of）。build で入れる
        self.sk = {}                     # (種類, 資料か出来事の ID) → 構造にしていない記載の行と Page の組の並び（SCHEMA.md 7.14）。build で入れる

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
        intro = [E(D.bun("mcp-hani"))]
        if self.bu:
            intro.append(D.bun("mcp-hani-bunya", keikaku=S(self.bu["kk"]["name"])))
        return Outou(E(D.bun("mcp-midashi-theme")), intro, blocks=[([], items)])

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
        blocks = self.kiroku_block((rk.DEKIGOTO, k), D.bun("mcp-midashi-event-kiroku"), D.bun("mcp-event-short"))
        return self.gikai(self.event_kagi(k), [], blocks, qs, D.bun("mcp-event-short"),
                          lambda q: self.konkyo_pg.get(q["question"]),
                          f"## {E(D.bun('mcp-midashi-event-konkyo', n=len(qs)))}", [], k)

    def kiroku_block(self, k, midashi, short):
        """資料か出来事 k に当たる構造にしていない記載（SCHEMA.md 7.14）→ ブロックの並び（行が無ければ空）。
        midashi は見出しの文。記述の出し方は、論点の記述と同じ（kijutsu）。source_date の新しい順。"""
        D = self.D
        rs = self.sk.get(k, [])
        if not rs:
            return []
        rs = sorted(rs, key=lambda xp: xp[0]["source_date"], reverse=True)
        return [([f"## {E(midashi)}", E(D.bun("mcp-kiroku-setsumei", short=E(short)))],
                 [self.kijutsu(pg, x) for x, pg in rs])]

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
        if keikaku is None:
            return self.ronten_ichiran_matome(matome[0][1], midashi, theme)
        out = []
        for youso, rs0 in matome:
            mi = f"### {S(youso['name'])}" if youso else f"### {E(D.bun('ronten-nashi', keikaku=S(keikaku)))}"
            mae = []        # 論点が無い見出し（章立てに入らない論点が全部まとまりに入っているとき）は、次のブロックの頭に付ける
            for mt, rs in ([("", rs0)] if youso else bn.nashi_wake(rs0)):
                items = [self.ronten_item(r) for r in rs]
                if mt:
                    head = mae + self.matome_head("####", theme, theme, mt)
                else:
                    head = [mi] if out else [midashi, E(D.bun("mcp-ronten-setsumei-jiko", keikaku=S(keikaku))),
                                             E(D.bun("ronten-kazu-setsumei")), mi]
                if not items:
                    mae = head
                    continue
                mae = []
                out.append((head, items))
        return out

    def matome_head(self, level, theme, ue, mt):
        """まとまりの見出しの行（まとまりの名前と ID。引数の名前は issue）と、見出しの下の文（docs/design.md 4節。2026-11-28）。
        ue は、まとまりの ID の頭（見出しの ID）。"""
        D = self.D
        mid = jiko.matome_id(ue, mt)
        bun, url = bn.matome_bun(D, self.inp, self.note[theme][0]["matome"].get(mt))
        out = [f"{level} {self.kagi_ji(E(mt), 'issue', mid)}", bun] + ([self.url_gyo(url)] if url else [])
        # 同じ題に付いた論点の入る、ほかのまとまりを、題の数の多い順に TSUNAGARI_ICHIRAN まで（docs/design.md 4節。2026-11-28。案）
        ue3 = [x for t, x, _ in self.tsunagari.get(mid, []) if t == "matome"][:TSUNAGARI_ICHIRAN]
        if ue3:
            out.append(D.bun("ronten-matome-tsunagari",
                             matome="、".join(self.kagi_ji(E(self.matome[x]["mt"]), "issue", x) for x in ue3)))
        return out

    def kazu(self, r):
        """事項の行 → theme と field の応答で論点に添える、取り上げた質問の数と日付の文（issue の応答の質問と同じ集め方。2026-11-28）。"""
        th = jiko.themes_of(r)[0]
        if th not in self.note:
            return ""
        T, pg = self.note[th]
        if r["id"] not in {s for _, s, _, _ in T["topics"]}:
            return ""
        k = bn.ronten_kazu(self.D, pg.ronten(r["name"])["qs"])
        return f"　{E(k)}" if k else ""

    def ronten_item(self, r):
        """事項の表の1行 → theme の応答の、論点の項目の行。"""
        D = self.D
        shu = f"{E(D.kotoba('事項の表 shurui'))}：{E(self.shurui(r))}"
        if r["aru"]:
            return f"- {self.kagi_ji(E(r['name']), 'issue', r['id'])}　{shu}{self.kazu(r)}"
        return f"- {E(r['name'])}　{shu}　（{E(D.bun('ronten-mada'))}）"

    def ronten_ichiran_matome(self, rows, midashi, theme):
        """章立てが無いテーマ（kokyo と chiiki）の theme の応答の、論点のブロックの並び（docs/design.md 4節。2026-11-28）。まとまり（事項の表の matome）
        ごとに `### ` の見出しにして、ronten-matome-setsumei の文を添える。まとまりの無い論点は、そのあとに ronten-matome-nashi
        の見出しで並べる。matome が jiko.HOKA の論点は、最後に置く。"""
        D = self.D
        out = []
        for mt, rs in bn.nashi_wake(rows, True):
            head = self.matome_head("###", theme, theme, mt) if mt else [f"### {E(D.bun('ronten-matome-nashi'))}"]
            if not out:
                head = [midashi, E(D.bun("mcp-ronten-setsumei-matome")), E(D.bun("ronten-kazu-setsumei"))] + head
            out.append((head, [self.ronten_item(r) for r in rs]))
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
                  "jigyo": D.kotoba("資料の一覧の表 shurui が「jigyo」"), "shingi": D.kotoba("資料の一覧の表 shurui が「shingi」"),
                  "chiiki": D.kotoba("資料の一覧の表 shurui が「chiiki」"),
                  "jinji": D.kotoba("資料の一覧の表 shurui が「jinji」")}
        if b["shurui"] not in shurui:
            self.problems.append(("(e) デザインシステムとの対応",
                                  f"資料の一覧の表の shurui「{b['shurui']}」の行が、docs/design.md 3節に無い（{bkey}）"))
        kk = [r for r in self.t["kankei"] if r["kara"] == bkey]
        ke = [r for r in self.t["kankei"] if r["e"] == bkey]
        ar = [r for r in self.t["atai"] if r["shiryo"].strip() and sj.bunsho_of(r["shiryo"]) == bkey]
        hyo = [p for p in self.t["bubun"] if p["bunsho"] == bkey and p["shu"] == sj.HYO]
        intro = [E(D.bun("mcp-shiryo-hani")),
                 E(D.bun("mcp-shiryo-kazu", hyo=len(hyo), atai=len(ar), teigi=len({r["suji"] for r in ar}),
                         kara=len(kk), e=len(ke), q=len(self.konkyo.get(bkey, [])),
                         kiroku=len(self.sk.get((rk.SHIRYO, bkey), [])))),
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
        blocks += self.kiroku_block((rk.SHIRYO, bkey), D.bun("mcp-midashi-shiryo-kiroku"), D.bun("mcp-konkyo-short"))
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
        lines = [f"- 「{S(x['quote']).replace(chr(10), chr(10) + '  ')}」",
                 "  - " + (D.bun("mcp-issue-jiki-kubun", jiki=jiki, kubun=E(self.kubun_of(x["source"]))) if kubun
                           else D.bun("mcp-issue-jiki", jiki=jiki))]
        if x.get("yomi"):
            # 生成AIが資料を2回読んで付けた記述（SCHEMA.md 7.13）の、読みの言葉
            lines.append("  - " + E(bn.kisai_go(D, x["yomi"])))
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
        # テーマの定義の問いのうち、読んだ質問に入っているもの。読んだ質問の ID は、台帳（data/ippan.tsv）の議員の区切りの最初の
        # 発言なので、定義の問い（2つめの問いなど）は、読んだ質問の台帳の行の turns にあれば、読んだものとする（2026-11-28）
        def turns(q):
            return {t.split(":")[0] for r in self.inp.ippan().get(keys.sid_of(q), []) for t in r["turns"].split(";") if t}
        yturns = {q: turns(q) for q in yomi}
        yomi_toi = {q for q in toi if q in yomi or any(keys.sid_of(q) in ts for ts in yturns.values())}
        tz = [q for q in toi if q in zumi]
        tn = [q for q in toi if q not in zumi and q not in yomi_toi]
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
                               soto=len([q for q in yomi if q not in toi
                                         and not any(keys.sid_of(t) in yturns[q] for t in toi)]), toi=len(toi))))
            nashi = self.yomi_nashi.get(theme, [])     # 読んだが、当たる論点が無かった質問（SKILL.md 4.4 の G5）
            if nashi:
                out.append(E(D.bun("mcp-issue-hani-yomi-nashi", n=len(nashi))))
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
        if jiko.is_bunya(theme):
            # 総合計画の分野の論点（SCHEMA.md 7.9。2026-11-28）。テーマの名前は、分野の番号と名前（入力の字）
            intro = [D.bun("mcp-issue-lead", theme=S(T["theme"]), setsumei=E(setsumei))]
            if slug in T["kihon"]:
                intro.append(D.bun("mcp-issue-kihon", keikaku=S(self.bu["kk"]["name"])))
            hani = self.issue_hani_bunya(theme)
        else:
            intro = [D.bun("mcp-issue-lead", theme=E(T["theme"]), setsumei=E(setsumei))]
            hani = self.issue_hani(theme)
            if any(r["point"] == P and jiko.is_bunya(r["theme"]) for r in pg.m.get("yomi", [])):
                hani = hani + [D.bun("mcp-issue-hani-bunya-hoka", keikaku=S(self.bu["kk"]["name"]))]
        blocks = [([f"## {E(D.bun('mcp-midashi-issue-shiryo'))}"]
                   + ([E(D.bun("kisai-yomi-setsumei", short=E(short)))] if any(x.get("yomi") for x in R["docs"]) else []),
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
                          f"## {E(D.bun('mcp-midashi-issue-gikai', n=len(qs)))}", hani, slug,
                          ato=self.issue_matome(slug, theme))

    def theme_ji(self, th):
        """テーマの名前（HTML）。総合計画の分野のテーマは、分野の番号と名前（入力の字）。"""
        T = self.note[th][0]
        return S(T["theme"]) if jiko.is_bunya(th) else E(T["theme"])

    def ue_ji(self, g):
        """まとまり g（tools/build_bunya.py の midashi_gun の1つ）の、上の見出しの文（HTML）。"""
        D, th, ue = self.D, g["theme"], g["ue"]
        if ue[0] == "nashi":
            return f"{self.theme_ji(th)}　{E(D.bun('ronten-nashi', keikaku=S(ue[1])))}"
        if ue[0] == "kihon":
            return f"{self.theme_ji(th)}　{S(ue[1][0] + ue[1][1])}"
        if ue[0] == "kihon-nashi":
            return f"{self.theme_ji(th)}　{E(D.bun('ronten-kihon-nashi', keikaku=S(self.bu['kk']['name'])))}"
        return self.theme_ji(th)

    def ronten_mei(self, r, theme=None):
        """事項の行 → 論点の名前の項目（issue がある論点は ID を付ける。theme と違うテーマの論点は、テーマの名前を添える）。"""
        D = self.D
        name = self.kagi_ji(E(r["name"]), "issue", r["id"]) if r["id"] in self.issue_ari \
            else f"{E(r['name'])}　（{E(D.bun('ronten-mada'))}）"
        th = jiko.themes_of(r)[0]
        if theme is not None and th != theme and th in self.note:
            name += "　" + D.bun("ronten-theme-mei", theme=self.theme_ji(th))
        return f"- {name}"

    def issue_matome(self, slug, theme):
        """issue の応答の、(a) 同じまとまりのほかの論点と、(b) 同じ質問の同じ題で一緒に取り上げられた論点のブロック（docs/design.md 4節。
        2026-11-28。言葉は案）。"""
        D = self.D
        out = []
        for mid in self.row_matome.get(slug, []):
            g = self.matome[mid]
            hoka = [r for r in g["rows"] if r["id"] != slug]
            if hoka:
                out.append(([f"## {E(D.bun('mcp-midashi-issue-matome'))}",
                             D.bun("mcp-issue-matome", matome=self.kagi_ji(E(g["mt"]), "issue", mid), midashi=self.ue_ji(g))],
                            [self.ronten_mei(r, theme) for r in hoka]))
        issho = self.issho.get(slug, [])
        if issho:
            out.append(([f"## {E(D.bun('mcp-midashi-issue-issho'))}", E(D.bun("mcp-issue-issho-setsumei"))],
                        [f"{self.ronten_mei(self.jiko_by[j], theme)}　{E(D.bun('mcp-issue-issho-kazu', n=n))}"
                         + "".join("　" + self.matome_mei(m) for m in self.row_matome.get(j, [])) for j, n in issho]))
        return out

    def matome_mei(self, mid):
        """まとまりの ID → mcp-matome-mei の文（まとまりの名前と ID）（docs/design.md 4節。2026-11-28。案）。"""
        return self.D.bun("mcp-matome-mei", matome=self.kagi_ji(E(self.matome[mid]["mt"]), "issue", mid))

    def tsunagari_block(self, mid, theme):
        """まとまりの応答の、同じ題に付いた論点の入る、ほかのまとまりと、まとまりに入っていない論点のブロック
        （docs/design.md 4節の issue の11。2026-11-28。案）。無ければ None。"""
        D = self.D
        items = []
        for t, x, n in self.tsunagari.get(mid, []):
            kazu = E(D.bun("mcp-issue-issho-kazu", n=n))
            if t == "matome":
                items.append(f"- {self.matome_mei(x)}　{self.ue_ji(self.matome[x])}　{kazu}")
            else:
                items.append(f"{self.ronten_mei(self.jiko_by[x], theme)}　{kazu}")
        if not items:
            return None
        return ([f"## {E(D.bun('mcp-midashi-matome-tsunagari'))}", E(D.bun("mcp-matome-tsunagari-setsumei"))], items)

    def matome_outou(self, mid):
        """issue にまとまりの ID：まとまりの論点の全部の、名前と ID、種類、取り上げた質問の一覧（docs/design.md 4節。2026-11-28）。"""
        D, inp = self.D, self.inp
        g = self.matome[mid]
        th = g["theme"]
        bun, url = bn.matome_bun(D, inp, self.note[th][0]["matome"].get(g["mt"]))
        intro = [D.bun("mcp-matome-lead", midashi=self.ue_ji(g), n=len(g["rows"])), bun] + ([self.url_gyo(url)] if url else [])
        intro += [E(D.bun("mcp-matome-setsumei")), E(D.bun("ronten-kazu-setsumei"))]
        blocks = []
        ts = self.tsunagari_block(mid, th)
        for r in g["rows"]:
            shu = f"{E(D.kotoba('事項の表 shurui'))}：{E(self.shurui(r))}"
            if r["id"] not in self.issue_ari:
                blocks.append(([f"## {E(r['name'])}　{shu}"], [E(D.bun("ronten-mada"))]))
                continue
            T, pg = self.note[jiko.themes_of(r)[0]]
            qs = pg.ronten(r["name"])["qs"]
            items = []
            for q in qs:
                shu_q = D.bun("mcp-issue-shitsugi") if q["sitsugi"] else D.bun("mcp-issue-ippan")
                items.append(f"- {D.bun('mcp-issue-shitsumon', hi=E(bs.hi_str(D, q['date'])), shu=E(shu_q), dai=bn.S_kagi(q['dai']))}"
                             f"　{E(D.bun('mcp-matome-bubun', n=len(q['paras'])))}\n  - {E(bn.kakunin_go(D, q))}")
            blocks.append(([f"## {self.kagi_ji(E(r['name']), 'issue', r['id'])}　{shu}{self.kazu(r)}"],
                           items or [E(D.bun("mcp-matome-shitsumon-nashi"))]))
        if ts:
            blocks.append(ts)
        return Outou(self.kagi_ji(E(g["mt"]), "issue", mid), intro, blocks)

    def issue_hani_bunya(self, theme):
        """総合計画の分野の論点の、読んだ題の範囲の文（docs/design.md 4節。2026-11-28）。数はデータから数える。"""
        D = self.D
        dai = ym.dai(theme)
        ym_ = sorted(q.split("_")[1][:6] for q, _ in dai)
        a, z = (D.bun("nengetsu", nen=int(x[:4]), tsuki=int(x[4:])) for x in (ym_[0], ym_[-1]))
        out = [D.bun("mcp-issue-hani-bunya", keikaku=S(self.bu["kk"]["name"]), bunya=S(self.note[theme][0]["theme"]),
                     n=len(dai), kikan=E(a if a == z else D.bun("kikan", a=a, z=z)))]
        nashi = ym.nashi_dai(theme, self.yomi_rows)
        if nashi:
            out.append(E(D.bun("mcp-issue-hani-bunya-nashi", n=len(nashi))))
        return out

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

    def gikai(self, title, intro, blocks, qs, short, pg_of, gikai, hani, ji, ato=()):
        """議会での質問と答弁のブロック（issue と document で共通。docs/design.md 4節）。1回めの応答に質問の一覧を出し、
        質問ごとの部分を、続きの応答で返す。pg_of は、質問 → 注（Page.chu_list）を引く build_note.Page（無ければ None）。
        hani は、扱っている質問の範囲の文の並び。ji は、検査の問題に出す字。ato は、質問の一覧のあと、質問ごとの部分の前に置く
        ブロックの並び（issue_matome のブロック。2026-11-28）。"""
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
            return Outou(title, intro, blocks + [([gikai] + setsumei, items)] + list(ato) + tsuzuki)

        # 続きの番号は、分けてみるまで分からないので、仮の番号で分けてから、その番号で作り直す
        o = tsukuru([99] * len(qs))
        o.pages(self.D)
        bango = list(o.hajime)
        o = tsukuru(bango)
        o.pages(self.D)
        if o.hajime != bango:
            self.problems.append(("(h) 論点", f"{ji}：続きの番号が、作り直すと変わる（{bango} → {o.hajime}）"))
        return o

    # field（台帳の題と、総合計画の分野。SCHEMA.md 7.11、docs/design.md 4節）
    def field_kagi(self, no):
        """分野の番号と名前（入力の字のまま続けたもの）と ID。"""
        x = self.bu["bunya"][no]
        return self.kagi_ji(S(x["no"] + x["name"]), "field", no)

    def wadai_kagi(self, name):
        """話題（分野を付けなかった題の、まとめた名前）と ID。"""
        D = self.D
        D.dasanai("分野に無い話題の名前の表 matome")
        D.dasanai("分野に無い話題の名前の表 id")
        return self.kagi_ji(E(name), "field", self.bu["m2id"][name])

    def bunya_hani(self):
        """題の日付の範囲と、入っていないものの文（docs/design.md の bunya-hani）。日付は、台帳の date のいちばん古い日と新しい日。"""
        D, m = self.D, self.bu
        ds = sorted(r["date"] for r in m["dai"].values())
        return D.bun("bunya-hani", a=E(bs.hi_str(D, ds[0])), z=E(bs.hi_str(D, ds[-1])), keikaku=S(m["kk"]["name"]))

    def field_ichiran(self):
        """field（引数なし）：分野（政策の柱ごと）と、話題（分野を付けなかった題）の一覧と、それぞれの題の数。"""
        D, m = self.D, self.bu
        kk = m["kk"]
        D.dasanai("質問の題と分野の対応の表 bunya")
        intro = [D.bun("bunya-setsumei", keikaku=S(kk["name"])), self.bunya_hani(), D.bun("bunya-ichiran-setsumei", keikaku=S(kk["name"])),
                 E(D.bun("mcp-bunya-ichiran"))]
        blocks = []
        for h in kk["hashira"]:
            blocks.append(([f"## {S(h['no'] + ' ' + h['name'])}"],
                           [f"- {self.field_kagi(x['no'])}　{E(D.bun('bunya-kazu', n=len(m['by'].get(x['no'], []))))}"
                            for x in h["bunya"]]))
        blocks.append(([f"## {E(D.kotoba('質問の題と分野の対応の表 wadai'))}", E(D.bun("bunya-wadai-setsumei"))],
                       [f"- {self.wadai_kagi(name)}　{E(D.bun('bunya-kazu', n=len(m['by'].get(i, []))))}"
                        for i, name in m["wadai"]]))
        return Outou(D.bun("mcp-midashi-bunya", keikaku=S(kk["name"])), intro, blocks)

    def field(self, fid):
        """field に分野の番号か話題の ID：分野は基本施策（入力の字のまま）と、題の一覧。話題は題の一覧。"""
        D, m, inp = self.D, self.bu, self.inp
        kk = m["kk"]
        intro = [D.bun("bunya-setsumei", keikaku=S(kk["name"])), self.bunya_hani()]
        blocks = []
        if fid in m["bunya"]:
            x = m["bunya"][fid]
            h = x["hashira"]
            title = self.field_kagi(fid)
            intro.append(f"- {S(h['no'] + ' ' + h['name'])}　{S(x['seisaku'][0] + ' ' + x['seisaku'][1])}")
            t = x["tokoro"]
            pp = sj.page_no(t[0]) if len(t) == 1 else D.bun("kikan", a=sj.page_no(t[0]), z=sj.page_no(t[-1]))
            items = [f"- {S(no + name)}" for no, name in x["shisaku"]]
            items.append(f"{E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{self.bunsho_kagi(kk['id'])}"
                         f"　{E(D.bun('page', n=pp))}　{E(keys.source_url(inp, t[0]))}")
            blocks.append(([f"## {S(x['midashi'])}"], items))
            blocks += self.field_ronten(fid)
            blocks += self.kensho_bunya(fid)
            blocks += self.field_event(fid)
        else:
            name = next(n for i, n in m["wadai"] if i == fid)
            title = self.wadai_kagi(name)
            intro.append(E(D.bun("bunya-wadai-setsumei")))
        dai = m["by"].get(fid, [])
        blocks.append(([f"## {E(D.bun('bunya-midashi-dai', n=len(dai)))}", E(D.bun("bunya-dai-setsumei"))],
                       [self.field_dai(fid, k) for k in dai]))
        return Outou(title, intro, blocks)

    def field_ronten(self, fid):
        """field に分野の番号：論点を基本施策ごとに並べたブロックの並び（docs/design.md 4節の field の8。2026-11-28）。"""
        D = self.D
        kei = S(self.bu["kk"]["name"])
        D.dasanai("事項の表 kihon")
        yonda, secs = bb.ronten_ichiran(self.bu, fid, self.note, self.bunya_ronten)
        midashi = f"## {E(D.bun('mcp-midashi-ronten'))}"
        if not yonda:
            out = []
            for _, t, ps in secs:
                head = [f"### {S(bt.Theme(self.inp, t).namae[0])}"]
                if not out:
                    head = [midashi, E(D.bun("mcp-ronten-bunya-yomanai"))] + head
                out.append((head, ["- " + self.kagi_ji(E(P), "issue", slug) for P, slug in ps]))
            return out
        out = []
        th = jiko.bunya_theme(fid)
        for kind, mi, rs in secs:
            if kind == "kihon":
                jishin, subs = rs[0], rs[1:]
                ue = bb.kihon_midashi_id(th, jishin, mi[0])
                head = [f"### {S(mi[0] + mi[1])}"]
                items = [self.kihon_item(jishin)] if jishin else []
                for mt, xs in subs:
                    if not mt:
                        items += [self.ronten_item(r) for r in xs]
                mae = []
                if items:
                    out.append((head, items))
                else:
                    mae = head      # 基本施策の行も、まとまりの無い論点も無いときは、見出しを次のブロックの頭に付ける
                for mt, xs in subs:
                    if mt and xs:
                        out.append((mae + self.matome_head("####", th, ue, mt), [self.ronten_item(r) for r in xs]))
                        mae = []
            elif kind == "nashi":
                head = [f"### {E(D.bun('ronten-kihon-nashi', keikaku=kei))}"]
                for mt, xs in rs:
                    if mt:
                        out.append((head + self.matome_head("####", th, th, mt),
                                    [self.ronten_item(r) for r in xs]))
                    else:
                        out.append((head + ([f"#### {E(D.bun('ronten-matome-nashi'))}"] if len(rs) > 1 else []),
                                    [self.ronten_item(r) for r in xs]))
                    head = []
            elif kind == "theme":
                out.append(([f"### {E(D.bun('ronten-theme-ronten'))}", E(D.bun("ronten-theme-ronten-setsumei"))],
                            [self.ronten_item(r) + "　" + D.bun("ronten-theme-mei", theme=S(self.theme_namae(r)))
                             for r in rs]))
            else:
                out.append((self.matome_head("###", th, th, mi), [self.ronten_item(r) for r in rs]))
        out[0] = ([midashi, D.bun("mcp-ronten-setsumei-bunya", keikaku=kei), E(D.bun("ronten-kazu-setsumei"))] + out[0][0],
                  out[0][1])
        return out

    def theme_namae(self, r):
        """事項の行の theme の列の、分野でない最初のテーマの名前（テーマの定義の字）。"""
        t = next(t for t in jiko.themes_of(r) if not jiko.is_bunya(t))
        return bt.Theme(self.inp, t).namae[0]

    def kihon_item(self, r):
        """基本施策そのものの事項の行 → field の応答の、論点の項目の行（docs/design.md 4節の field の8）。"""
        D = self.D
        if r["aru"]:
            return f"- {self.kagi_ji(E(r['name']), 'issue', r['id'])}　{E(D.bun('ronten-kihon-jishin'))}{self.kazu(r)}"
        return f"- {E(r['name'])}　（{E(D.bun('ronten-mada'))}）"

    def field_event(self, fid):
        """field に分野の番号：質問が取り上げた出来事のブロック（theme の応答と同じ形。2026-11-28）。"""
        D = self.D
        th = jiko.bunya_theme(fid)
        ev = [(k, r, qs) for k, (r, qs, _) in self.event.items() if r["theme"] == th]
        if not ev:
            return []
        return [([f"## {E(D.kotoba('資料と出来事の名前の表 shu が「出来事」'))}", E(D.bun("mcp-dekigoto-setsumei"))],
                 [f"- {self.event_kagi(k)}　{E(D.bun('mcp-dekigoto-kazu', n=len([q for q in qs if q['theme'] == th])))}"
                  for k, r, qs in ev])]

    def field_dai(self, fid, k):
        """題1つ → 項目。日付と題、その分野（話題）の読み、ほかに付いた分野と話題、論点（tools/bunya.py の ronten_of_dai）、会議録の URL。"""
        D, m = self.D, self.bu
        r, rows = m["dai"][k], m["of"][k]
        D.dasanai("質問の題と分野の対応の表 from、n")
        D.dasanai("質問の題と分野の対応の表 chu")
        mine = next(x for x in rows if (x["bunya"] or m["m2id"][x["wadai"]]) == fid)
        dai = S("「" + r["title"] + "」") if r["title"].strip() else E(D.bun("bunya-dai-nashi"))
        lines = [f"- {E(bs.hi_str(D, r['date']))}　{dai}", "  - " + E(bb.yomi_go(D, mine))]
        hoka = [x for x in rows if x is not mine]
        if hoka:
            lines.append("  - " + D.bun("bunya-hoka", hoka="、".join(
                self.field_kagi(x["bunya"]) if x["bunya"] else self.wadai_kagi(x["wadai"]) for x in hoka)))
        ron = self.bunya_ronten.get(k)
        if ron:
            lines.append("  - " + D.bun("bunya-ronten", ronten="、".join(self.kagi_ji(E(P), "issue", s) for P, s, _ in ron)))
        sid, p = bu.start_of(r)
        lines.append(f"  - {E(D.bun('bunya-link'))}：{E(keys.search_url(sid, p))}")
        return "\n".join(lines)

    # 施策検証結果報告書の記述（SCHEMA.md 7.12、docs/design.md 4節の field の7と review）
    def kensho_namae(self, k):
        """torikumi → kensho-torikumi の文（入力のシートの番号と名前）。"""
        t = self.ks["tori"][k]
        self.D.dasanai("施策検証シートの表 no、name、kihon_no、kihon")
        return self.D.bun("kensho-torikumi", no=S(t["no"]), name=S(t["name"]))

    def kensho_kagi(self, k):
        self.D.dasanai("施策検証の取り組みと分野の対応の表 torikumi")
        return self.kagi_ji(self.kensho_namae(k), "review", k)

    def kensho_shisaku(self, r):
        """施策検証の取り組みと分野の対応の表の行 → 基本施策の番号と名前（入力の字）に、読みの言葉を添えたもの。"""
        D = self.D
        name = dict(self.bu["bunya"][r["bunya"]]["shisaku"])[r["shisaku"]]
        D.dasanai("施策検証の取り組みと分野の対応の表 bunya、shisaku")
        D.dasanai("施策検証の取り組みと分野の対応の表 chu")
        y = {ks.ICCHI: D.kotoba("施策検証の取り組みと分野の対応の表 yomi が「一致」"),
             ks.IKKAI: D.kotoba("施策検証の取り組みと分野の対応の表 yomi が「1回だけ」")}[r["yomi"]]
        return D.bun("kensho-shisaku-yomi", shisaku=S(r["shisaku"] + name), yomi=E(y))

    def kensho_midashi(self, ran):
        """欄の ID → 欄の見出しの字（報告書の字。施策検証の欄の表の最初の候補）。"""
        self.D.dasanai("施策検証の欄の表 midashi")
        return S(ks.kohos(self.ks["ran"][ran])[0])

    def kensho_pages(self, t):
        """入力のシートの行 → シートの2ページ（46〜47 など）。"""
        D = self.D
        p = int(t["page"])
        return E(D.bun("page", n=D.bun("kikan", a=p, z=p + 1)))

    def kensho_sheet(self, t):
        """入力のシートの行 → 報告書の名前と ID、シートの2ページ、URL の行。"""
        D = self.D
        return (f"{E(D.kotoba('資料の一覧の表 namae と、shiryo のページ'))}：{self.bunsho_kagi(ks.SHIRYO)}"
                f"　{self.kensho_pages(t)}　{E(keys.source_url(self.inp, ks.SHIRYO + '/' + t['page']))}")

    def kensho_hito(self, k):
        """人の確認が済んでいない torikumi なら、kensho-hito の文の並び（docs/design.md 3節）。"""
        self.D.dasanai("施策検証シートの検収の台帳 reviewer")
        self.D.dasanai("施策検証シートの検収の台帳 checked が空")
        return [] if self.ks["hito"].get(k) else [E(self.D.bun("kensho-hito"))]

    def kensho_ichi(self, k):
        """担当部署と総合戦略での位置の行の並び。シートの字を出し、総合戦略の本編の字と違うときは、本編の字とそのページを
        添える（SCHEMA.md 7.12）。"""
        D = self.D
        t, x = self.ks["tori"][k], self.ks["sr"][k]
        D.dasanai("施策検証シートの表 tantou")
        D.dasanai("施策検証シートの表 houkou")
        D.dasanai("施策検証シートの表 note、施策検証シートの KPI の表 note、施策検証シートの項目の表 note")
        out = [f"- {D.bun('kensho-tantou', tantou=S(t['tantou']))}"]
        hon = False
        if not ks.onaji(t["tantou"], x["dept"]):
            out.append(f"  - {D.bun('kensho-tantou-honpen', tantou=S(x['dept']))}")
            hon = True
        out.append(f"- {D.bun('kensho-ichi', kihon_no=S(t['kihon_no']), kihon=S(t['kihon']), houkou=S(t['houkou']))}")
        if not ks.onaji(t["houkou"], x["houkou"]):
            out.append(f"  - {D.bun('kensho-houkou-honpen', houkou=S(x['houkou']))}")
            hon = True
        if hon:
            nm, url = self.moto(x["honpen"])
            out.append(f"  - {D.bun('kensho-honpen', shiryo=nm + (('　' + E(url)) if url else ''))}")
        return out

    def kensho_ran(self, t, ran):
        """入力のシートの列（tasseido か kekka）→ 欄の見出しの字とシートの字に、シートのページを添えたもの。"""
        self.D.dasanai("施策検証シートの表 tasseido、kekka")
        return (self.D.bun("hyo-kijutsu-ran", midashi=self.kensho_midashi(ran), atai=S(t[ran]))
                + f"（{self.kensho_pages(t)}）")

    def kensho_bunya(self, fid):
        """field に分野の番号：町の検証のブロックの並び（docs/design.md 4節の field の7）。"""
        D, K = self.D, self.ks
        x = self.bu["bunya"][fid]
        D.dasanai("施策検証の取り組みと分野の対応の表 saisho")
        naka = [k for k in K["tori"] if K["naka"].get(k) == fid]
        hoka = [k for k in K["tori"] if K["naka"].get(k) != fid and any(r["bunya"] == fid for r in K["bunya"].get(k, []))]
        head = [f"## {E(D.bun('kensho-midashi'))}", E(D.bun("kensho-setsumei")), E(D.bun("kensho-mikakunin")),
                E(D.bun("kensho-nendo"))]
        if any(self.kensho_hito(k) for k in naka + hoka):
            head.append(E(D.bun("kensho-hito")))
        aru = {r["shisaku"] for rs in K["bunya"].values() for r in rs if r["bunya"] == fid}
        items = [f"- {D.bun('kensho-nai', shisaku=S(no + name))}" for no, name in x["shisaku"] if no not in aru]
        items += [self.kensho_item(k, fid) for k in naka]
        hh = [f"### {E(D.bun('kensho-hoka'))}", E(D.bun("kensho-hoka-setsumei"))]
        hi = [f"- {self.kensho_kagi(k)}　" + D.bun("kensho-shisaku", shisaku="、".join(
            self.kensho_shisaku(r) for r in K["bunya"][k] if r["bunya"] == fid)) for k in hoka]
        if not items:
            return [(head + hh, hi)]
        return [(head, items)] + ([(hh, hi)] if hi else [])

    def kensho_item(self, k, fid):
        """field の町の検証で、中身を出す torikumi 1つ → 項目。"""
        D, K = self.D, self.ks
        t = K["tori"][k]
        lines = [f"### {self.kensho_kagi(k)}"] + self.kensho_ichi(k)
        lines.append("- " + D.bun("kensho-shisaku", shisaku="、".join(
            self.kensho_shisaku(r) for r in K["bunya"][k] if r["bunya"] == fid)))
        lines.append("- " + self.kensho_ran(t, "kekka"))
        lines.append("- " + self.kensho_ran(t, "tasseido"))
        lines.append("- " + self.kensho_sheet(t))
        return "\n".join(lines)

    def review(self, k):
        """review に torikumi の ID：施策検証シートの記述（docs/design.md 4節の review）。"""
        D, K = self.D, self.ks
        t = K["tori"][k]
        bunya = "、".join(f"{self.field_kagi(r['bunya'])} {self.kensho_shisaku(r)}" for r in K["bunya"][k])
        intro = ([E(D.bun("kensho-review-lead"))] + self.kensho_hito(k) + self.kensho_ichi(k)
                 + ["- " + D.bun("kensho-bunya", bunya=bunya), E(D.bun("kensho-mikakunin")), "- " + self.kensho_sheet(t),
                    E(D.bun("kensho-nendo"))])

        def page(key):
            return E(D.bun("page", n=sj.page_no(key)))
        D.dasanai("施策検証シートの KPI の表 shihyo")
        D.dasanai("施策検証シートの KPI の表 nendo、mokuhyo、jisseki、tasseiritsu")
        D.dasanai("施策検証シートの KPI の表 tani")
        D.dasanai("検証結果の説明の表 inyo、tokoro")
        kara = E(D.kotoba("施策検証シートの KPI の表 mokuhyo、jisseki、tasseiritsu が空"))

        def ran_ji(r, c):
            v = ks.tani_tsuki(r[c], r["tani"]) if c in ("mokuhyo", "jisseki") else r[c]
            return S(v) if v else kara
        items = []
        for kijun, rows in K["kpi"].get(k, []):
            r0 = kijun or rows[0]
            lines = [f"### {D.bun('hyo-kijutsu-ran', midashi=self.kensho_midashi('shihyo'), atai=S(r0['shihyo']))}"
                     f"（{E(D.bun('page', n=int(t['page'])))}）"]
            if kijun:
                lines.append(f"- {D.bun('hyo-kijutsu-ran', midashi=S(kijun['nendo']), atai=S(kijun['jisseki']))}")
            for r in rows:
                lines.append(f"- {S(r['nendo'])}　" + "　".join(
                    D.bun("kensho-kpi-ran", midashi=self.kensho_midashi(c), atai=ran_ji(r, c))
                    for c in ("mokuhyo", "jisseki", "tasseiritsu")))
            items.append("\n".join(lines))

        def setsumei(shu, ran):
            return ([f"  - {D.bun('kensho-setsumei-moto', midashi=self.kensho_midashi(ran))}"]
                    + [f"    - 「{S(r['inyo'])}」（{page(r['tokoro'])}）" for r in K["kekka"] if r["shu"] == shu])
        items.append("\n".join(["- " + self.kensho_ran(t, "tasseido")] + setsumei("tasseido", "tasseido")))
        blocks = [([f"## {self.kensho_midashi('kpi')}", E(D.bun("kensho-kpi-chu"))], items)]
        D.dasanai("施策検証シートの項目の表 line")
        bun = {ran: (mi, rows) for ran, mi, rows in K["bun"].get(k, [])}
        pp = self.kensho_pages(t)
        dare = {"naibu": D.bun("kensho-dare", midashi=self.kensho_midashi("naibu"),
                               dare=E(D.kotoba("施策検証の欄の表 kubun が「naibu」"))),
                "gaibu": D.bun("kensho-dare", midashi=self.kensho_midashi("gaibu"),
                               dare=E(D.kotoba("施策検証の欄の表 kubun が「gaibu」")))}
        top = [f"## {dare['naibu']}"]
        for ran in ks.NAIBU:
            if ran not in bun:
                continue
            mi, rows = bun[ran]
            blocks.append((top + [f"### {S(mi)}（{pp}）"], [f"- 「{S(r['line'])}」" for r in rows]))
            top = []
        blocks.append(([f"## {dare['gaibu']}"],
                       ["\n".join(["- " + self.kensho_ran(t, "kekka")] + setsumei("kekka", "kekka"))]))
        for ran in ks.GAIBU:
            if ran in bun:
                mi, rows = bun[ran]
                blocks.append(([f"### {S(mi)}（{pp}）"], [f"- 「{S(r['line'])}」" for r in rows]))
        blocks.append(([], [E(D.bun("kensho-owari"))]))
        return Outou(self.kensho_kagi(k), intro, blocks)

    # ツールの説明
    def tools(self, themes):
        D = self.D
        ichi = "、".join
        th_erabu = list(themes)
        id_erabu = [x["id"] for x in self.t["suji"]]
        fa_erabu = list(dict.fromkeys(k for th in themes for k in self.shisetsu_ichiran(th, bt.Theme(self.inp, th))))
        b_erabu = list(self.by)
        hyo_erabu = [f"{p['bunsho']} {p['n']}" for p in self.t["bubun"] if p["shu"] == sj.HYO]
        is_namae, is_th = {}, {}
        for th, (T, _) in self.note.items():
            for P, slug, _, _ in T["topics"]:
                is_namae.setdefault(slug, P)
                is_th.setdefault(slug, th)
        is_erabu = list(is_namae) + list(self.matome)
        # 引数の説明に並べるのは、テーマの論点と出来事だけ。総合計画の分野の論点と出来事の ID は、field の応答にある（2026-11-28）
        is_setsumei = [k for k in is_namae if not jiko.is_bunya(is_th[k])]
        ev_setsumei = [k for k in self.event if not jiko.is_bunya(self.event[k][0]["theme"])]
        fi_erabu = list(self.bu["bunya"]) + [i for i, _ in self.bu["wadai"]]
        fi_mei = {i: n for i, n in self.bu["wadai"]}
        rv_erabu = list(self.ks["tori"])
        # torikumi の名前はシートの字なので、使わない言葉の検査では、資料からの文の印を残した文（kensa）を使う
        rv_desc = D.bun("mcp-hikisu-review", erabu="、".join(f"{k}（{self.kensho_namae(k)}）" for k in rv_erabu))

        def fi_namae(k):
            x = self.bu["bunya"].get(k)
            return S(x["no"] + x["name"]) if x else E(fi_mei[k])
        # 分野の名前は入力の字なので、使わない言葉の検査では、資料からの文の印を残した文（kensa）を使う
        fi_desc = D.bun("mcp-hikisu-field", erabu="、".join(f"{k}（{fi_namae(k)}）" for k in fi_erabu))

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
                    "mcp-hikisu-issue", erabu=namae_tsuki(is_setsumei, lambda k: E(is_namae[k]))))))]),
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
                    "mcp-hikisu-event", erabu=namae_tsuki(ev_setsumei, self.event_kagi_namae)))))]),
            "field": (owari(D.bun("mcp-tool-field", keikaku=S(self.bu["kk"]["name"]))), [
                dict(name="field", type="string", required=False, erabu=fi_erabu,
                     description=owari(fi_desc), kensa=fi_desc)]),
            "review": (owari(E(D.bun("mcp-tool-review"))), [
                dict(name="review", type="string", required=True, erabu=rv_erabu, description=owari(rv_desc),
                     kensa=rv_desc)]),
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


def dai_jiko(inp, rows):
    """質問と事項の対応の表（taio/shudai.tsv）の行 → 題 → その題に論点に関する部分が付いた事項の ID の集合（SCHEMA.md 7.10。
    2026-11-28）。題は、行の n（総合計画の分野の読み取り）か、範囲の段落が入る、台帳（data/ippan.tsv）の題（build_note の
    dai_gyo。テーマの読み取り）。台帳に無い質問の行は数えない。"""
    dai = {}
    for r in rows:
        q = r["question"]
        if not q.startswith("iq:"):
            continue
        if r["n"]:
            ks = [(keys.sid_of(q), r["n"])]
        else:
            f, rs = inp.ippan_dai(keys.sid_of(q), set(keys.paras_of(r["hani"])))
            ks = [(f, x["n"]) for x in rs]
        for k in ks:
            dai.setdefault(k, set()).add(r["jiko"])
    return dai


def issho_of(inp, rows, jrows, dai=None):
    """質問と事項の対応の表の行 → 事項の ID → 同じ質問の同じ題で一緒に取り上げられた、ほかの事項の (ID, 題の数) の並び
    （題の数の多い順。同じ数は事項の表の順。docs/design.md 4節。2026-11-28）。題の決め方は dai_jiko。"""
    dai = dai_jiko(inp, rows) if dai is None else dai
    jun = {r["id"]: i for i, r in enumerate(jrows)}
    kazu = {}
    for js in dai.values():
        for a in js:
            for b in js:
                if a != b:
                    kazu.setdefault(a, {}).setdefault(b, 0)
                    kazu[a][b] += 1
    return {a: sorted(c.items(), key=lambda x: (-x[1], jun.get(x[0], 0))) for a, c in kazu.items()}


def tsunagari_of(dai, matome, kihon, jrows):
    """まとまりごとの、同じ題に付いた論点の入る、ほかのまとまりと、まとまりに入っていない論点（SCHEMA.md 7.10。
    docs/design.md 4節。2026-11-28）。dai は dai_jiko の結果、matome はまとまりの ID → まとまり（rows を持つ。並びは theme と field の並べ方の順）、
    kihon は基本施策そのものの事項の ID の集合（数えない）。
    → まとまりの ID → (種類, ID, 題の数) の並び。種類は "matome"（まとまり）か "ronten"（まとまりに入っていない論点）。
    題の数は、このまとまりの論点のどれかと、相手の論点が、同じ題に付いている題の数。題の数の多い順、同じ数はまとまりを先に、
    まとまりは matome の順、論点は事項の表の順。"""
    row_m = {}
    for mid, g in matome.items():
        for r in g["rows"]:
            row_m.setdefault(r["id"], []).append(mid)
    jun_m = {mid: i for i, mid in enumerate(matome)}
    jun_j = {r["id"]: i for i, r in enumerate(jrows)}
    out = {}
    for mid, g in matome.items():
        A = {r["id"] for r in g["rows"]} - kihon
        kazu = {}
        for k, js in dai.items():
            if not js & A:
                continue
            for b in js - A - kihon:
                for t in ([("matome", m) for m in row_m[b]] if b in row_m else [("ronten", b)]):
                    kazu.setdefault(t, set()).add(k)
        out[mid] = sorted(((t, x, len(ks)) for (t, x), ks in kazu.items()),
                          key=lambda y: (-y[2], y[0] != "matome", jun_m.get(y[1], 0) if y[0] == "matome" else jun_j.get(y[1], 0)))
    return out


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


def read_bunya_notes(inp, kk=None):
    """総合計画の分野のテーマ（事項の表に行がある分野。SCHEMA.md 7.9。2026-11-28）の論点の表。論点の仮の表（teigi/note-*.tsv）は
    置かず、事項の表から作る（build_note.jiko_ni_suru）。テーマの名前は、分野の番号と名前（入力の字）。
    → テーマ → 表。並びは分野の番号の順。"""
    kk = bu.keikaku(inp) if kk is None else kk
    B = {jiko.bunya_theme(x["no"]): x for h in kk["hashira"] for x in h["bunya"]}
    rows = jiko.read()
    out = {}
    for th in jiko.theme_jun(rows):
        if jiko.is_bunya(th):
            x = B[th]
            T = dict(theme=x["no"] + x["name"], setsumei=x["name"], topics=[], junbi=[], words=[], units=[], chu=[],
                     bunya=x["no"])
            out[th] = bn.jiko_ni_suru(inp, T, th, rows)
    return out


def theme_jun(inp):
    """hino-ronten のテーマの定義にあるテーマの ID を、定義の順に並べたもの。"""
    return list(dict.fromkeys(r["theme"] for r in inp.ronten_tsv(ronten.THEMES)))


def kiroku_problems(inp, tk, tables, namae=None, jiko_rows=None):
    """構造にしていない記載（確定済み）のうち、資料か出来事に当たる行（tools/ronten_kisai.py）を、tk.sk に入れる。→ 問題の並び。
    引用は、論点の記述と同じく、資料の本文と照合する。出来事は、event の応答がある出来事（tk.event）でなければ止める。
    注と金額の単位を引く Page は、about が hino-ronten のテーマの定義の事柄か記載にある最初のテーマの Page。"""
    namae = ym.read_namae() if namae is None else namae
    jiko_rows = jiko.read() if jiko_rows is None else jiko_rows
    sk = rk.shiryo_kiroku(inp, jiko_rows, tables["bunsho"], namae)
    th_of = {}
    for r in inp.ronten_tsv(ronten.THEMES):
        if r["kind"] in ("事柄", "記載"):
            th_of.setdefault(r["value"], r["theme"])
    problems = []
    rows = [(k, x) for k, xs in sk.items() for x in xs]
    res = shogo.check_quotes(inp, [dict(where=f"構造にしていない記載 {x['point']} / {x['source']}", source=x["source"],
                                        quote=x["quote"]) for _, x in rows])
    problems += [("(a) 引用が資料の本文に無い", f"{m['where']}：{m['reason']}（{m['source']}）「{m['quote']}」")
                 for m in res.mismatched]
    tk.sk = {}
    for k, x in rows:
        if k[0] == rk.DEKIGOTO and k[1] not in tk.event:
            problems.append(("(i) 資料と出来事の名前の表", f"構造にしていない記載 {x['point']}：出来事 {k[1]} の応答が無い"))
            continue
        th = th_of.get(x["point"])
        if th not in tk.note:
            problems.append(("(b) 出典の無い記述", f"構造にしていない記載 {x['point']}：テーマの定義の事柄か記載に無い"))
            continue
        try:
            ok = keys.source_name(inp, x["source"]) and keys.source_url(inp, x["source"]) and x["source_date"]
        except keys.KeyFormError:
            ok = False
        if not ok:
            problems.append(("(b) 出典の無い記述", f"構造にしていない記載 {x['point']}：資料「{x['source']}」の名前か url か日付が作れない"))
            continue
        tk.sk.setdefault(k, []).append((x, tk.note[th][1]))
    return problems


def konkyo_problems(inp, tk, tables, rows, namae=None, yomi_qs=None):
    """質問が取り上げた資料と出来事の表の行を検査し、資料の ID ごとに質問を tk.konkyo に、出来事の ID ごとに質問を
    tk.event に入れる。→ 問題の並び。
    質問は、どれかのテーマの定義の問い・質疑か、生成AIの2回の読み取りで読んだ質問（yomi_qs。質問 → 読んだテーマの並び）。
    質問の題は、hino-council-search の data/ippan.tsv にある質問は、その台帳の題（build_note.dai_of。SCHEMA.md 7.10）、
    台帳に無い質問は、その質問があるテーマの定義の行から取り、注は、そのテーマの Page から引く。
    同じ資料（出来事）と質問の行は、1つの質問にまとめ、段落ごとに yomi を持つ（「入力の確定済み」の行は、人が確認した質問）。
    2つのテーマの読み取りの行がある段落の yomi は、tools/yomi.py の yomi_awase で決める（SCHEMA.md 7.10）。
    資料の ID でも出来事の名前でもない aite（計画（案）と、資料と出来事の名前の表に無い名前）の行は、出さない。"""
    namae = ym.read_namae() if namae is None else namae
    yomi_qs = {} if yomi_qs is None else yomi_qs
    hiduke = {r["bunsho"]: r["hiduke"] for r in tables["bunsho"]}
    bunsho = set(hiduke)
    problems = [("(i) 質問が取り上げた資料", m) for m in konkyo.check(rows, bunsho, hiduke, namae)]
    problems += [("(i) 資料と出来事の名前の表", m) for m in ym.check_namae(namae, bunsho, hiduke)]
    qsrc, qtheme, src_of = {}, {}, {}
    for r in inp.ronten_tsv(ronten.THEMES):
        if r["kind"] in ("問い", "質疑"):
            qsrc.setdefault(r["value"], r["source"])
            qtheme.setdefault(r["value"], r["theme"])
            src_of.setdefault((r["theme"], r["value"]), r["source"])
    # 読んだ質問は、読んだテーマの質問とする（ほかのテーマの定義にもある質問は、題を、読んだテーマの定義か台帳から取る。
    # 試作のページと issue と同じ題にするため）
    for q, ths in yomi_qs.items():
        th = ths[0]                   # 2つ以上のテーマで読んだ質問は、テーマの順の最初のテーマ（SCHEMA.md 7.10）
        qsrc[q] = src_of.get((th, q)) or bn.ippan_src(inp, q)
        qtheme[q] = th
    pres = shogo.check_paras(inp, [dict(where=f"質問が取り上げた資料 {r['question']} / {r['aite']}", hani=r["hani"])
                                   for r in rows])
    for m in pres.mismatched:
        problems.append(("(i) 質問が取り上げた資料", f"{m['where']}：{m['reason']}（{m['source']}）"))
    if problems:
        return problems
    ev = {(r["theme"], r["namae"]): r for r in namae if r["shu"] == ym.DEKIGOTO}
    kumi, kumi_th = {}, {}
    for r in rows:
        q = r["question"]
        if q not in qsrc or not bn.qhead_parts(qsrc[q])[1]:
            problems.append(("(i) 質問が取り上げた資料", f"{q}：どのテーマの定義の問い・質疑にも、読んだ質問にも無いか、題が無い"))
            continue
        if r["aite"] in bunsho:
            k = ("bunsho", r["aite"])
        elif (r["theme"], r["aite"]) in ev:
            k = ("event", ev[(r["theme"], r["aite"])]["id"])
        else:
            continue
        x = kumi.setdefault(k, {}).setdefault(q, dict(yomi={}, kakutei={}, mikakunin=False, ys=set()))
        kumi_th.setdefault((k, q), r["theme"])
        x["ys"].add(r["yomi"])
        for p in keys.paras_of(r["hani"]):
            if r["yomi"] == konkyo.NYURYOKU:
                x["kakutei"][p] = r["yomi"]
            else:
                x["yomi"][p] = ym.yomi_awase(x["yomi"].get(p), r["yomi"])
    for (shu, aite), qd in kumi.items():
        out = []
        for q, x in qd.items():
            who = bn.qhead_parts(qsrc[q])[0]
            # 同じ資料（出来事）と質問に、入力の確定済みの行と読み取りの行があるときは、確定済みの行だけを出す
            # （SCHEMA.md 7.10。論点の応答の、確定済みの対応の記録と同じ扱い。案）
            mi = konkyo.NYURYOKU not in x["ys"]
            if not mi:
                x["yomi"] = x["kakutei"]
            # 題は、aite に付いた段落が範囲に入る題の題名（SCHEMA.md 7.10。2026-11-28）
            dai = bn.dai_of(inp, q, qsrc, set(x["yomi"]), tk.D.bun("bunya-dai-nashi"))
            paras = [(sid, i, inputs.paragraphs(inp.statement_text(sid))[i - 1]) for sid, i in sorted(x["yomi"])]
            out.append(dict(question=q, date=bn.qdate(q), sitsugi=q.startswith("sq:"), who=who, dai=dai, paras=paras,
                            mikakunin=mi, yomi=x["yomi"] if mi else {}, theme=kumi_th[((shu, aite), q)]))
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


def build(inp, tables, kotoba, read_problems=(), design=None, skill=None, notes=None, konkyo_rows=None, bunya_notes=None):
    """検査を通れば、応答の JSON（辞書）と件数を返す。当たれば Stop。

    tables は tools/build_theme.py の read_tables で読んだもの。notes は read_notes で読んだもの（None なら読む）。
    bunya_notes は read_bunya_notes で読んだもの（None なら読む）。
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
    # 総合計画の分野のテーマ（SCHEMA.md 7.9。2026-11-28）の論点も、同じ集め方と検査で作る。theme の応答には出さない
    bunya_notes = read_bunya_notes(inp) if bunya_notes is None else bunya_notes
    for theme, T in list(notes.items()) + list(bunya_notes.items()):
        model, more, _ = bn.collect(inp, T, theme)
        problems += more
        tk.note[theme] = (T, bn.Page(inp, T, model))
    # 生成AIの2回の読み取りで読んだ質問（SCHEMA.md 7.10）。テーマごとの質問の並び（範囲の文に使う）と、質問 → テーマ
    # 読んだ質問は、テーマの読み取りの結果の保存先（taio/yomi-<テーマ>/）の束の並びの質問の全部（当たる論点が無かった
    # 質問も数える。SKILL.md 4.4 の G5）
    tk.yomi_q, tk.yomi_nashi = {}, {}
    try:
        yomi_qs = ym.shitsumon_theme()
    except ym.YomiError as e:
        raise Stop([("(i) 質問が取り上げた資料", str(e))])
    yomi_rows = ym.read() if os.path.exists(ym.PATH) else []
    tk.yomi_rows = yomi_rows
    for q, qths in yomi_qs.items():
        for th in qths:
            tk.yomi_q.setdefault(th, []).append(q)
    for th in tk.yomi_q:
        tk.yomi_nashi[th] = ym.nashi_shitsumon(th, yomi_rows)
    # (i) 質問が取り上げた資料と出来事の表
    problems += konkyo_problems(inp, tk, tables, konkyo_rows, yomi_qs=yomi_qs)
    # 構造にしていない記載のうち、資料か出来事に当たる行（SCHEMA.md 7.14。2026-11-28）
    problems += kiroku_problems(inp, tk, tables)
    slugs = [slug for T, _ in tk.note.values() for _, slug, _, _ in T["topics"]]
    # ほかのテーマと共通の事項（SCHEMA.md 7.9）は、2つのテーマにあってよい。issue は、theme の列の最初のテーマで作るので、
    # そのテーマの論点にあること
    kyotsu = {r["id"]: jiko.themes_of(r) for r in jiko.read() if len(jiko.themes_of(r)) > 1}
    problems += [("(h) 論点", f"論点の ID {x} が、2つ以上のテーマにある") for x in sorted({x for x in slugs if slugs.count(x) > 1})
                 if x not in kyotsu]
    for x in sorted({x for x in slugs if x in kyotsu}):
        th0 = kyotsu[x][0]
        if th0 not in tk.note or x not in {s for _, s, _, _ in tk.note[th0][0]["topics"]}:
            problems.append(("(h) 論点", f"論点の ID {x} が、事項の表の theme の列の最初のテーマ（{th0}）の論点に無い"))
    # (j) 台帳の題と、総合計画の分野（SCHEMA.md 7.11）
    try:
        tk.bu, more = bb.yomu(inp)
    except (bu.BunyaError, inputs.InputError) as e:
        raise Stop([("(j) 分野", str(e))])
    problems += [("(j) 分野", m) for m in more]
    # (k) 施策検証結果報告書の記述（SCHEMA.md 7.12）
    try:
        tk.ks, more = ks.matome(inp)
    except (ks.KenshoError, bu.BunyaError, inputs.InputError) as e:
        raise Stop([("(k) 施策検証", str(e))])
    problems += [("(k) 施策検証", m) for m in more]
    if problems:
        raise Stop(list(dict.fromkeys(problems)))
    tk.bunya_ronten = bu.ronten_of_dai(inp, tk.note)
    tk.kiroku = kiroku
    # まとまり（SCHEMA.md 7.9、docs/design.md 4節。2026-11-28）と、同じ題で一緒に取り上げられた論点
    jrows = jiko.read()
    jiko_th = {r["id"]: jiko.themes_of(r) for r in jrows}
    tk.jiko_by = {r["id"]: r for r in jrows}
    tk.issue_ari = {slug for theme, (T, _) in tk.note.items() for _, slug, _, _ in T["topics"]
                    if jiko_th.get(slug, [theme])[0] == theme}
    tk.gun = bb.midashi_gun(inp, tk.note, tk.bu)
    tk.matome, tk.row_matome = {}, {}
    for g in tk.gun:
        if g["id"]:
            if g["id"] in tk.matome:
                problems.append(("(h) 論点", f"まとまりの ID {g['id']} が重なっている"))
            tk.matome[g["id"]] = g
            for r in g["rows"]:
                tk.row_matome.setdefault(r["id"], []).append(g["id"])
    dai = dai_jiko(inp, yomi_rows)
    tk.issho = issho_of(inp, yomi_rows, jrows, dai)
    tk.kihon_ids = {x for T, _ in tk.note.values() for x in T.get("kihon", ())}
    tk.tsunagari = tsunagari_of(dai, tk.matome, tk.kihon_ids, jrows)
    if problems:
        raise Stop(list(dict.fromkeys(problems)))

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
    # ほかのテーマと共通の事項（SCHEMA.md 7.9）の issue は、事項の表の theme の列の最初のテーマで1つだけ作る
    jiko_th = {r["id"]: jiko.themes_of(r) for r in jiko.read()}
    for theme, (T, _) in tk.note.items():
        for P, slug, short, setsumei in T["topics"]:
            if jiko_th.get(slug, [theme])[0] == theme:
                ireru("issue", [("issue", slug)], tk.issue(theme, P, slug, short, setsumei))
    for mid in tk.matome:
        ireru("issue", [("issue", mid)], tk.matome_outou(mid))
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
    ireru("field", [], tk.field_ichiran())
    for k in list(tk.bu["bunya"]) + [i for i, _ in tk.bu["wadai"]]:
        ireru("field", [("field", k)], tk.field(k))
    for k in tk.ks["tori"]:
        ireru("review", [("review", k)], tk.review(k))
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
    skill = ((read_skill() if skill is None else skill) + "\n- " + D.bun("mcp-hani-nai")
             + "\n- " + owari(D.bun("mcp-hani-bunya", keikaku=S(tk.bu["kk"]["name"]))))
    # 使わない言葉の検査：応答の文、ツールと引数の説明、定型文
    zenbu = bun + [E(x) for x in list(nai.values()) + [top, setsumei, skill]]
    zenbu += [E(x["description"]) for x in tools] + [a.pop("kensa", None) or E(a["description"]) for x in tools for a in x["args"]]
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
