"""入力の場所と lock の確かめ、入力の読み込み（SCHEMA.md §1）。

入力は読むだけ。lock の SHA の、files に当たるファイルだけを `git show <SHA>:<path>` で読む。
読む前に、5つの入力の作業ツリーの HEAD が lock の SHA と同じかを確かめ、違えば止める（InputError）。
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


class InputError(ValueError):
    """入力か lock の誤り。件数と該当を示して止める。"""


def inputs_root():
    return os.environ.get("HINO_CONTEXT_INPUTS", "/tmp/inputs")


def ronten_root():
    return os.environ.get("HINO_CONTEXT_RONTEN", "/home/claude/hino-ronten")


def repo_dir(repo):
    return ronten_root() if repo == RT else os.path.join(inputs_root(), repo)


def load_lock(path=LOCK_PATH):
    """lock を読み、5つの入力・40桁の sha・files の形を確かめる。"""
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
    """TSV（1行目が列名、引用符を使わない）を辞書の並びで読む。columns があれば列名を確かめる。"""
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


def paragraphs(text):
    """SCHEMA.md §2 の段落の数え方：本文を改行（LF）で分け、空か空白だけの部分を除いた並び（番号は1から）。"""
    return [p for p in (text or "").split("\n") if p.strip()]
