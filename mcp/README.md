# hino-context の MCP サーバー（Cloudflare Workers）

hino-context のデータを、使う人の生成AIから呼べる、読み取り専用の MCP サーバーです（非公式の試作）。日野町および日野町議会の公式のものではありません。

- 応答は、リポジトリの tools/build_mcp.py が先に作った `data/outou.json.gz`（応答の JSON を gzip で圧縮したもの）を、ツールと引数で引いて返すだけです。このフォルダのプログラムは、応答の文を組み立てません。
- `data/outou.json.gz` は、公開と手元での確認のときに `scripts/bunkatsu.mjs` が展開して、目次（`dist/mokuji.json`。プログラムに束ねる）と、応答の文のファイル（`public/o/<番号>.txt`。静的なアセット）に分けます（2026-11-28。応答の文の全部を束ねると、Workers の大きさの上限を超えるため）。`public/` と `dist/` は、リポジトリに入れません。
- ツールは theme、issue、item、facility、document、event、field、review の8つです。ID は、ツールの引数の説明か、theme と field の応答にあります。形と決まりは、リポジトリの docs/mcp.md にあります。
- パスは `/mcp`（Streamable HTTP）。認証はありません。

## 使い方

Claude のカスタムコネクタに、公開の URL（末尾が `/mcp`）を登録します。

## 手元での確認

```
npm ci
npx wrangler dev
node scripts/bunkatsu.mjs
npx tsc --noEmit
```

## 公開

Cloudflare の Workers Builds で、Root directory を `mcp`、Deploy command を `npx wrangler deploy` にします（Build command は空）。`npx wrangler deploy` が、`wrangler.jsonc` の build の command で `scripts/bunkatsu.mjs` を動かしてから、プログラムと静的なアセットを公開します。main へのマージで公開されます。

ライセンスは、プログラムが AGPL-3.0-or-later です。`data/outou.json.gz` に含まれる資料の文の扱いは、リポジトリの LICENSE-DATA.md によります。
