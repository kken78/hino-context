# MCP サーバー（2026-11-27 の試作）

hino-context のデータを、使う人の生成AIから呼べる、読み取り専用の MCP サーバーにする。依頼者が 2026-11-27 に了承した文案（Project の `claude/hino-context-R2/mcp-an-2026-11-27.md`）による。

- 応答の文は、Python のツール（tools/build_mcp.py）が、ページと同じ検査を通ったデータから、先に作る。できた応答は、1つの JSON ファイル（mcp/data/outou.json）にして、リポジトリにコミットする。
- Cloudflare Workers に置くプログラム（mcp/）は、JSON を引いて返すだけにする。応答の文を組み立てる処理、言葉、決まりを、プログラムに書かない。照合、確認の記録、使わない言葉の検査が Python のツールにあり、同じ決まりを2か所に書かないためである。
- 応答の文の型と言葉は docs/design.md（3節の表と、4節の「MCP の応答」）、使う生成AIが守ることは SKILL.md §1 に書く。この文書には、サーバーの形と、置き方を書く。

## 1. ツール（4つ）

| 名前 | 引数（必須は *） | 返すもの |
| --- | --- | --- |
| theme | theme、tsuzuki | theme を省略すると、テーマの一覧。theme にテーマの鍵を付けると、町の説明、これまでの経過、町内の施設、施設の一覧、資料の一覧、数値の定義の一覧 |
| suji | id*、shiryo、tsuzuki | 数値の定義1つと、その数値（資料ごと、資料の日付の古い順）。shiryo に文書の鍵を付けると、その文書の数値だけ |
| shisetsu | key*、tsuzuki | 施設1つの、名前、前の名前、資料が書いている内容、資料の表での記述、施設を指す数値 |
| shiryo | bunsho*、hyo、tsuzuki | 文書1つの、名前、版、日付、種類、根拠、文書どうしの関係（両方向）、数値がある定義、表の一覧。hyo に表の番号を付けると、その表の行と列と欄 |

- 引数の型：hyo と tsuzuki は整数。ほかは文字列。
- 鍵：テーマの鍵は hino-ronten のテーマの定義の theme、定義の鍵は定義の表の id、施設の鍵は施設の参照表の key（`fa:` で始まる）、文書の鍵は文書の表の bunsho、表の番号は文書の部分の表の n（SCHEMA.md §2・§6・§7）。
- 応答の中では、名前のあとの括弧に、引数の名前と鍵を出す（例：「待機児童数（id：taiki）」）。使う人の生成AIは、最初に theme を呼び、応答にある鍵だけを、ほかのツールの引数に使う（SKILL.md §1）。
- 議会の問いと答弁を探すツールは、入れていない。データにまだ無いため（文案6節の4）。

## 2. 応答

- 文（見出しと箇条書き）。HTML は入れない。型は docs/design.md 4節の「MCP の応答」。
- どの数値と引用にも、資料の名前、ページ、もとの資料の URL を付ける。会議録は、日付と、議会での答弁か議会での議員の発言かを出し、発言者の名前は出さない。会議録の全文は入れない（引用は、数値の表の inyo と、hino-ronten の記録の quote だけ）。
- 確認の記録（数値の表の chu の「依頼者が PDF で確認（…）」「2者が画像で確認（…）」、文書の部分の表の shisetsu_kakunin）を付ける。未確認の印は、ページと同じ条件で付ける（tools/suji.py の mikakunin）。
- 数値を計算しない。良し悪しを書かない。

### 2.1 上限と続き

- 1回の応答の上限は、文字数で決める（tools/build_mcp.py の定数 JOGEN。6,000 字）。
- 超える組は、区切りのよい所（資料ごと、表ごと、項目ごと）で分け、最後に続きを取る引数を示す。続きは、同じ引数に tsuzuki=2、3、… を付けて取る。tsuzuki=1 は、tsuzuki を付けない組と同じ応答である。
- tsuzuki は、4つのツールのすべてに付ける（文案2節の表の「どのツールにも」による）。いまのデータで続きがあるのは、theme（幼保）、suji の一部、shisetsu の一部。

### 2.2 該当する組が無いとき

- 引数の組が JSON に無いときは、ツールごとの決まった文（docs/design.md の mcp-nai）を返す。近い鍵を推し量って返さない。存在しない tsuzuki の番号も同じ。
- 必須の引数が無いときと、型が違うとき（hyo に文字列など）は、MCP のライブラリが引数の検査の誤りを返す。

## 3. JSON の形（mcp/data/outou.json）

| 鍵 | 中身 |
| --- | --- |
| name | サーバーの名前（hino-context） |
| version | 版（tools/build_mcp.py の定数。データのもとのコミットと日付は入れない。作るたびに変わると、検査で比較できないため） |
| description | サーバーの説明（mcp-setsumei） |
| instructions | 使う生成AIへの指示。SKILL.md §1 の箇条書きの行をそのまま入れる |
| top | `/` に返す文（mcp-top） |
| tools | ツールの並び。ツールごとに name、description、args。args は引数ごとに name、type（string か integer）、required、description、erabu（選べる値の一覧） |
| nai | ツールの名前 → 該当する組が無いときの文 |
| outou | ツールの名前 → 鍵 → bun の番号 |
| bun | 応答の文の並び |

- 鍵は、ツールの引数の順に、値がある引数を「名前=値」にして「&」でつないだ字（例：`id=taiki&shiryo=pt:youho/honpen&tsuzuki=2`）。引数なしは空の字。
- 組の数（2026-11-27）：theme 5、suji 138、shisetsu 26、shiryo 78（続きの分と tsuzuki=1 の分を含む）。応答の文は127。
- 資料の表のページを作れない表（行か列が無い表、欄が数値の表に無い「読んだ」の表）も、組として入れ、決まった文（mcp-hyo-dasenai）を返す。いまは2つ（`doc:shingi-youho-teigen 16`、`doc:jigyo-shinkodomoen-kousou 18`）。

## 4. 応答を作るツール（tools/build_mcp.py）

- `python3 -B tools/build_mcp.py` で mcp/data/outou.json を作る。ページのツールと同じ検査（lock と入力、表の検査、docs/design.md の言葉の検査、引用の照合、使わない言葉）を通し、1つでも当たれば、件数と該当行を示して、何も書かずに終了コード 1。
- 資料の名前、時期、掲載されている所、表の欄は、ページを作るツール（tools/build_suji.py、tools/build_hyo.py、tools/build_theme.py）の関数を使う。
- マージ前の検査（tools/kensa.py）は、`--out build/mcp/outou.json --hikaku mcp/data/outou.json` で作り直し、リポジトリの JSON と同じであることを確認する。違えば止まる。データか docs/design.md の言葉を変えたら、`python3 -B tools/build_mcp.py` で作り直して、同じコミットか、続くデータのコミットに入れる。

## 5. Cloudflare に置くプログラム（mcp/）

- ファイル：package.json、package-lock.json、wrangler.jsonc、tsconfig.json、src/index.ts、data/outou.json。
- Cloudflare の現在の手引き（Agents SDK の createMcpHandler）の形。要求ごとに新しい McpServer を作り、セッションと Durable Objects を使わない。トランスポートは Streamable HTTP。パスは `/mcp`。`/` には mcp-top の文を返す。
- 行うことは3つだけ：ツールの一覧を返す（説明と引数は JSON から）、呼ばれたツールと引数に該当する応答を JSON から引いて返す、該当するものが無いときに JSON の決まった文を返す。引数は、前後の空白を除くだけで、ほかの推定をしない。
- どのツールにも、読むだけの印（annotations の readOnlyHint）を付ける。
- 認証なし。バインディング（KV、D1、Durable Objects など）なし。JSON は import で束ねる。返すのは、公開の資料から作ったデータだけで、書き込みの機能は無い。
- 依存は版を固定する（package.json と package-lock.json）。ライセンスは、プログラムの区分（AGPL-3.0-or-later）。

### 5.1 公開

- Cloudflare の Workers Builds で、このリポジトリをつなぐ。Root directory は `mcp`、Build command は空、Deploy command は `npx wrangler deploy`（既定の値）。依存は、mcp/package-lock.json から、Workers Builds が入れる。リポジトリのいちばん上のファイルは使わない。
- 公開するブランチは main。PR を main にマージするたびに、公開される。
- 公開の URL は `https://hino-context.<アカウントの workers.dev のサブドメイン>/mcp`。Claude のカスタムコネクタに、この URL を登録する。
- アカウントの ID などは、リポジトリに書かない。

### 5.2 手元での確認

`cd mcp && npm ci && npx wrangler dev` で、localhost に立てる。MCP の要求は、`Content-Type: application/json` と `Accept: application/json, text/event-stream` を付けて、`/mcp` に POST する。型の検査は `npx tsc --noEmit`。

## 6. 前の MCP（hino-ronten）の点検で、差が大きいとした点の扱い

2026-11-15 の点検（Project の `claude/hino-ronten-tenken-2026-11-15-mcp.md`）で、MCP の仕様との差が大きいとした点を、次のように扱った。

| 点検で分かった差 | 今回の形 |
| --- | --- |
| 1つのサーバーが1つのテーマの1つの見方だけを扱う | サーバーは1つ。テーマ、定義、施設、文書は、引数で選ぶ |
| 返す量に上限が無い | どのツールにも、1回の上限（6,000 字）と、続きを取る引数 tsuzuki を付けた |
| 引数に説明が無い | 引数ごとに、説明、必須かどうか、型、選べる値を JSON に持ち、ツールの一覧で返す。選べる鍵は、説明の文にも並べる |
| 接続ごとにやりとりを持つ作り | 要求ごとに完結する作り（createMcpHandler）。セッションを持たない |
| 読むだけの印が無い | どのツールにも readOnlyHint を付けた |
