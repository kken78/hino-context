# hino-context の MCP サーバー（Cloudflare Workers）

hino-context のデータを、使う人の生成AIから呼べる、読み取り専用の MCP サーバーです（非公式の試作）。日野町および日野町議会の公式のものではありません。

- 応答は、リポジトリの tools/build_mcp.py が先に作った `data/outou.json` を、ツールと引数で引いて返すだけです。このフォルダのプログラムは、応答の文を組み立てません。
- ツールは theme、suji、shisetsu、shiryo の4つです。最初に theme を呼びます。形と決まりは、リポジトリの docs/mcp.md にあります。
- パスは `/mcp`（Streamable HTTP）。認証はありません。

## 使い方

Claude のカスタムコネクタに、公開の URL（末尾が `/mcp`）を登録します。

## 手元での確認

```
npm ci
npx wrangler dev
npx tsc --noEmit
```

## 公開

Cloudflare の Workers Builds で、Root directory を `mcp`、Deploy command を `npx wrangler deploy` にします（Build command は空）。main へのマージで公開されます。

ライセンスは、プログラムが AGPL-3.0-or-later です。`data/outou.json` に含まれる資料の文の扱いは、リポジトリの LICENSE-DATA.md によります。
