"""入力の場所と lock の確認、入力の読み込み（SCHEMA.md §1）。

入力は読むだけ。lock の SHA の、files に当たるファイルだけを `git show <SHA>:<path>` で読む。
読む前に、5つの入力の作業ツリーの HEAD が lock の SHA と同じかを確認し、違えば止める（InputError）。
"""
import csv
import io
import json
import os
import re
import subprocess
from fnmatch import fnmatchcase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_PATH = os.path.join(ROOT, "inputs.lock.json")
GAIBU_COLUMNS = ["id", "name", "hakkou", "hiduke", "url", "kakunin", "page", "ji"]
HS = "hino-council-search"
SP = "shiga-hino-plans"
TD = "hino-town-docs"
CD = "council-dashboard"
RT = "hino-ronten"
REPOS = (CD, HS, SP, TD, RT)
# hino-ronten の施設の参照表と施設の記録（SCHEMA.md §1・§2）
SHISETSU = "ref/shisetsu.tsv"
SHISETSU_COLUMNS = ["key", "name", "aliases", "district", "source", "reviewer", "date", "note"]
SHISETSU_KIROKU = "records/shisetsu.tsv"
SHISETSU_KIROKU_COLUMNS = ["facility", "aspect", "value", "source", "source_date", "quote", "target", "kind", "prev",
                           "status", "reviewer", "date", "note"]
CONFIRMED = "confirmed"


class InputError(ValueError):
    """入力か lock の誤り。件数と該当を示して止める。"""


def inputs_root():
    return os.environ.get("HINO_CONTEXT_INPUTS", "/tmp/inputs")


def ronten_root():
    return os.environ.get("HINO_CONTEXT_RONTEN", "/home/claude/hino-ronten")


def repo_dir(repo):
    return ronten_root() if repo == RT else os.path.join(inputs_root(), repo)


def load_lock(path=LOCK_PATH):
    """lock を読み、5つの入力・40桁の sha・files の形を確認する。"""
    try:
        with open(path, encoding="utf-8") as f:
            lock = json.load(f)
    except (OSError, ValueError) as e:
        raise InputError(f"{path} を読めない（{e}）")
    if not isinstance(lock, dict) or sorted(lock) != sorted(REPOS):
        raise InputError(f"{path}: 入力が {list(REPOS)} でない")
    for repo in REPOS:
        v = lock[repo]
        if not isinstance(v, dict) or sorted(v) != ["files", "sha"]:
            raise InputError(f"{path}: {repo} の項目が sha・files でない")
        if not isinstance(v["sha"], str) or not re.fullmatch(r"[0-9a-f]{40}", v["sha"]):
            raise InputError(f"{path}: {repo} の sha が40桁の16進数でない（{v['sha']!r}）")
        if not isinstance(v["files"], list) or not all(isinstance(p, str) and p for p in v["files"]):
            raise InputError(f"{path}: {repo} の files が文字列の配列でない")
    return lock


def _git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo_dir(repo), *args], capture_output=True)
    except OSError as e:
        raise InputError(f"{repo}: git を実行できない（{e}）")
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip()
        raise InputError(f"{repo}: git {' '.join(args)} が終了コード {r.returncode}（{msg}）")
    return r.stdout


def check_heads(lock):
    """5つの入力の作業ツリーの HEAD が lock の SHA と同じか。違う入力・HEAD の取れない入力を全部示して止める。"""
    bad = []
    for repo in REPOS:
        if not os.path.isdir(repo_dir(repo)):
            bad.append(f"{repo}：{repo_dir(repo)} が無い")
            continue
        try:
            head = _git(repo, "rev-parse", "HEAD").decode().strip()
        except InputError as e:
            bad.append(f"{repo}：HEAD が取れない（{e}）")
            continue
        if head != lock[repo]["sha"]:
            bad.append(f"{repo}：HEAD {head[:7]} が lock の {lock[repo]['sha'][:7]} と違う")
    if bad:
        raise InputError(f"lock と入力が合わない：{len(bad)} 件\n" + "\n".join(f"  - {b}" for b in bad))


def match_lock(pattern, path):
    """lock の files のパターンにパスが当たるか。「*」は「/」をまたがない。"""
    if "*" not in pattern:
        return path == pattern
    pp, fp = pattern.split("/"), path.split("/")
    return len(pp) == len(fp) and all(fnmatchcase(f, p) for p, f in zip(pp, fp))


def read_tsv(data, name, columns=None):
    """TSV（1行目が列名、引用符を使わない）を辞書の並びで読む。columns があれば列名を確認する。"""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    rows = list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))
    rows = [r for r in rows if r]
    if not rows:
        raise InputError(f"{name}: 列名の行が無い")
    head = rows[0]
    if columns is not None and head != list(columns):
        raise InputError(f"{name}: 列が {list(columns)} でない（{head}）")
    out = []
    for i, r in enumerate(rows[1:], 2):
        if len(r) != len(head):
            raise InputError(f"{name} の {i} 行目：列の数が {len(r)}（{len(head)} のはず）")
        out.append(dict(zip(head, r)))
    return out


class Inputs:
    """lock の版の入力。読んだ物は覚えておく。"""

    def __init__(self, lock=None, check=True):
        self.lock = lock or load_lock()
        if check:
            check_heads(self.lock)
        self._cache = {}
        self._files = {}

    # ---- 共通 ----

    def files(self, repo, pattern):
        """lock のパターンを、その版にあるファイルのパスに展開する（無ければ空）。"""
        if pattern not in self.lock[repo]["files"]:
            raise InputError(f"lock に無いパターン（{repo}: {pattern}）")
        key = (repo, pattern)
        if key not in self._files:
            base = []
            for part in pattern.split("/")[:-1]:
                if "*" in part:
                    break
                base.append(part)
            b = "/".join(base)
            out = _git(repo, "ls-tree", "-r", "--name-only", self.lock[repo]["sha"], "--", (b + "/") if b else ".")
            self._files[key] = {p for p in out.decode("utf-8").splitlines() if match_lock(pattern, p)}
        return self._files[key]

    def read_bytes(self, repo, path):
        if not any(match_lock(p, path) for p in self.lock[repo]["files"]):
            raise InputError(f"lock の files に無いパス（{repo}: {path}）")
        key = (repo, path)
        if key not in self._cache:
            self._cache[key] = _git(repo, "show", f"{self.lock[repo]['sha']}:{path}")
        return self._cache[key]

    def read_text(self, repo, path):
        return self.read_bytes(repo, path).decode("utf-8")

    def read_json(self, repo, path):
        return json.loads(self.read_text(repo, path))

    # ---- 会議録（hino-council-search） ----

    def statements(self):
        """sid → 索引の発言（sid・name・role・text など）。index-manifest.json の shards を全部読む。"""
        if "statements" not in self._cache:
            im = self.read_json(HS, "public/data/index-manifest.json")
            out = {}
            for s in im["shards"]:
                for e in self.read_json(HS, f"public/data/{s['file']}"):
                    out[e["sid"]] = e
            self._cache["statements"] = out
        return self._cache["statements"]

    def statement_text(self, sid):
        e = self.statements().get(sid)
        return None if e is None else (e.get("text") or "")

    def speaker(self, sid):
        return (self.statements().get(sid) or {}).get("name") or ""

    def role(self, sid):
        """発言者の役職（索引の role）。発言が無ければ None。"""
        e = self.statements().get(sid)
        return None if e is None else (e.get("role") or "")

    def ippan(self):
        """一般質問の台帳（data/ippan.tsv）→ 問いの最初の発言の sid（from）→ 行の並び（n の順）。題名（title）を、
        テーマの定義に無い質問の題に使う（SCHEMA.md §1。2026-11-28）。"""
        if "ippan" not in self._cache:
            out = {}
            for r in read_tsv(self.read_bytes(HS, "data/ippan.tsv"), f"{HS} data/ippan.tsv"):
                out.setdefault(r["from"], []).append(r)
            for rs in out.values():
                rs.sort(key=lambda r: int(r["n"]))
            self._cache["ippan"] = out
        return self._cache["ippan"]

    def shitsugi(self):
        """議案への質疑の台帳（data/shitsugi.tsv。1行は、議員の区切り（from）× 議案（bill））→ (from, bill) → 行
        （SCHEMA.md §1・7.10。2026-11-28）。同じ (from, bill) の行が2つあれば InputError。"""
        if "shitsugi" not in self._cache:
            out = {}
            for r in read_tsv(self.read_bytes(HS, "data/shitsugi.tsv"), f"{HS} data/shitsugi.tsv"):
                k = (r["from"], r["bill"])
                if k in out:
                    raise InputError(f"{HS} data/shitsugi.tsv：from と bill の組が2行ある（{k}）")
                out[k] = r
            self._cache["shitsugi"] = out
        return self._cache["shitsugi"]

    def gian_title(self, sid, no):
        """発言の sid と議案の番号（「議第18号」など）→ 議案の一覧（public/data/gian.json）の、その発言の会議の議案の題。
        12月の決算の議案は、番号ごとの題（title。範囲の題 rangeTitle は使わない）。会議か議案が無ければ None。"""
        if "gian" not in self._cache:
            self._cache["gian"] = self.read_json(HS, "public/data/gian.json")
        m = self._cache["gian"].get(sid.split("_")[0])
        if not m:
            return None
        return next((a["title"] for a in m.get("agenda", []) if a["no"] == no), None)

    def ippan_turn(self):
        """発言の sid → その発言を turns に含む台帳の題の (from, n) の並び。"""
        if "ippan_turn" not in self._cache:
            out = {}
            for f, rs in self.ippan().items():
                for r in rs:
                    for t in r["turns"].split(";"):
                        if t:
                            out.setdefault(t.split(":")[0], []).append((f, r["n"]))
            self._cache["ippan_turn"] = out
        return self._cache["ippan_turn"]

    def ippan_dai(self, sid, paras):
        """質問の発言の sid と、出すものに付いた段落の集まり paras → (from, 台帳の題の行の並び)（SCHEMA.md 7.10・7.11）。
        質問の発言を含む議員の区切り（台帳の from。質問の発言が from でなければ、その発言を turns に含む題の区切り）の題の
        うち、paras の段落が範囲に入る題（ippan_ate）。当たる題が無いときは、質問の発言が from なら、その区切りの題の全部、
        from でなければ、質問の発言を turns に含む題。台帳に無い質問は (None, [])。"""
        ip, turn = self.ippan(), self.ippan_turn()
        f = sid if sid in ip else (turn.get(sid) or [(None, None)])[0][0]
        if f is None:
            return None, []
        rs = ip[f]
        ate = self.ippan_ate(rs, paras)
        if not ate:
            ate = rs if sid == f else [r for r in rs if (f, r["n"]) in turn.get(sid, [])]
        return f, ate

    @staticmethod
    def ippan_ate(rs, paras):
        """台帳の1つの区切りの行 rs のうち、paras の段落が、題の範囲に入る行（SCHEMA.md 7.10）。
        paras は、段落（発言の sid と段落の番号の組）の集まり。段落の番号が分からないもの（sid だけの字か、番号が None の組）は、
        その発言の全部の段落として扱う。
        題の範囲は、段落の単位で、その題の start（発言, 段落）から、次の題の start の1つ前の段落まで（最後の題は、区切りの
        終わりまで。start の順で最初の題は、start の発言の最初の段落から）。turns には質問した議員の発言しか無いので、答弁の
        発言は、この範囲で題に結び付ける。turns にある発言も、どれかの題の start の発言は、段落で範囲を見る（1つの発言の途中から
        次の題が始まるため。2026-11-28）。start が空の行は、turns の発言で見る。"""
        def idx(sid):
            return int(sid.rsplit("_", 1)[1])

        def head(sid):
            return sid.rsplit("_", 1)[0]

        items = []
        for x in paras:
            sid, p = (x, None) if isinstance(x, str) else x
            items.append((sid, p))
        st = []
        for r in rs:
            if r.get("start"):
                s, p = r["start"].split(":")
                st.append((r, s, int(p)))
        st.sort(key=lambda x: (idx(x[1]), x[2]))
        start_sids = {s for _, s, _ in st}

        def mae(sid, p, s, q):
            """段落 (sid, p) が、段落 (s, q) より前か。p が None（発言の全部）なら、発言のどれかの段落が前か。"""
            if idx(sid) != idx(s):
                return idx(sid) < idx(s)
            return (1 if p is None else p) < q

        def ato(sid, p, s, q):
            """段落 (sid, p) が、段落 (s, q) と同じか後か。p が None なら、発言のどれかの段落が同じか後か。"""
            if idx(sid) != idx(s):
                return idx(sid) > idx(s)
            return p is None or p >= q

        out = []
        for r in rs:
            turns = {t.split(":")[0] for t in r["turns"].split(";") if t}
            pos = [i for i, (x, _, _) in enumerate(st) if x is r]
            hit = False
            for sid, p in items:
                if pos:
                    i = pos[0]
                    _, a, ap = st[i]
                    ap = 1 if i == 0 else ap
                    if head(sid) == head(a) and ato(sid, p, a, ap) and \
                            (i + 1 == len(st) or mae(sid, p, st[i + 1][1], st[i + 1][2])):
                        hit = True
                    elif sid in turns and sid not in start_sids:
                        hit = True
                elif sid in turns:
                    hit = True
                if hit:
                    break
            if hit:
                out.append(r)
        return out

    # ---- 町の資料（hino-town-docs） ----

    def docs(self):
        """id → data/sources.tsv の行。"""
        if "docs" not in self._cache:
            self._cache["docs"] = {r["id"]: r for r in read_tsv(self.read_bytes(TD, "data/sources.tsv"),
                                                               f"{TD} data/sources.tsv")}
        return self._cache["docs"]

    def doc_text(self, did, layer):
        """町の資料の本文（layer は text か text_raw）。ファイルが無ければ None。"""
        path = f"data/{layer}/{did}.txt"
        return self.read_text(TD, path) if path in self.files(TD, f"data/{layer}/*.txt") else None

    # ---- 計画（shiga-hino-plans） ----

    def plan(self, pid):
        path = f"data/plans/{pid}.json"
        return self.read_json(SP, path) if path in self.files(SP, "data/plans/*.json") else None

    def sources_index(self):
        if "sources_index" not in self._cache:
            self._cache["sources_index"] = read_tsv(self.read_bytes(SP, "data/sources_index.tsv"),
                                                    f"{SP} data/sources_index.tsv")
        return self._cache["sources_index"]

    def pt_text(self, pid, name, layer):
        path = f"data/{layer}/{pid}/{name}.txt"
        return self.read_text(SP, path) if path in self.files(SP, f"data/{layer}/*/*.txt") else None

    # ---- 前の作りの定義と台帳（hino-ronten） ----

    def gaibu(self):
        """外部の公的な資料の表（SCHEMA.md §5）。このリポジトリの teigi/gaibu.tsv。無ければ空。"""
        if not hasattr(self, "_gaibu"):
            path = os.path.join(ROOT, "teigi", "gaibu.tsv")
            rows = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    rows = read_tsv(f.read(), "teigi/gaibu.tsv", GAIBU_COLUMNS)
                errs = []
                for i, r in enumerate(rows, 2):
                    if any(not r[c] for c in ("id", "name", "hakkou", "url", "kakunin", "page", "ji")):
                        errs.append(f"{i} 行目：id・name・hakkou・url・kakunin・page・ji に空がある")
                    elif not r["url"].startswith("https://"):
                        errs.append(f"{i} 行目：url が https で始まらない")
                    elif not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", r["kakunin"]):
                        errs.append(f"{i} 行目：kakunin の形が YYYY-MM-DD でない")
                if errs:
                    raise InputError(f"teigi/gaibu.tsv：{len(errs)} 件\n" + "\n".join(f"  - {e}" for e in errs))
            self._gaibu = rows
        return self._gaibu

    def ronten_tsv(self, path):
        return read_tsv(self.read_bytes(RT, path), f"{RT} {path}")

    def shisetsu(self):
        """施設の参照表（hino-ronten ref/shisetsu.tsv）の行。status の列は無い（SCHEMA.md §1・§2）。"""
        if "shisetsu" not in self._cache:
            self._cache["shisetsu"] = read_tsv(self.read_bytes(RT, SHISETSU), f"{RT} {SHISETSU}", SHISETSU_COLUMNS)
        return self._cache["shisetsu"]

    def shisetsu_kiroku(self):
        """施設の記録（hino-ronten records/shisetsu.tsv）のうち、status が confirmed の行（SCHEMA.md §1）。"""
        if "shisetsu_kiroku" not in self._cache:
            rows = read_tsv(self.read_bytes(RT, SHISETSU_KIROKU), f"{RT} {SHISETSU_KIROKU}", SHISETSU_KIROKU_COLUMNS)
            self._cache["shisetsu_kiroku"] = [r for r in rows if r["status"] == CONFIRMED]
        return self._cache["shisetsu_kiroku"]


_HI = {}


def hatsugen_hi(sid):
    """発言の sid → 発言の日（YYYY-MM-DD）。sid の2つめの部分が日付で始まればその字。始まらない sid（「0000005484_11gijiroku_0010」
    など。議案への質疑の区切りの一部。2026-11-28）は、lock の版の会議録の索引の発言の date。無ければ空。"""
    s = sid.split("_")[1] if "_" in sid else ""
    if re.fullmatch(r"[0-9]{8}", s[:8]):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if "st" not in _HI:
        _HI["st"] = {k: e.get("date") or "" for k, e in Inputs().statements().items()}
    return _HI["st"].get(sid, "")


def paragraphs(text):
    """SCHEMA.md §2 の段落の数え方：本文を改行（LF）で分け、空か空白だけの部分を除いた並び（番号は1から）。"""
    return [p for p in (text or "").split("\n") if p.strip()]
