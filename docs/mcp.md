# MCP サーバー（2026-11-27 の試作）

hino-context のデータを、使う人の生成AIから呼べる、読み取り専用の MCP サーバーにする。依頼者が 2026-11-27 に了承した文案（Project の `claude/hino-context-R2/mcp-an-2026-11-27.md`）による。

- 応答の文は、Python のツール（tools/build_mcp.py）が、ページと同じ検査を通ったデータから、先に作る。できた応答は、1つの JSON ファイル（mcp/data/outou.json）にして、リポジトリにコミットする。
- Cloudflare Workers に置くプログラム（mcp/）は、JSON を引いて返すだけにする。応答の文を組み立てる処理、言葉、決まりを、プログラムに書かない。照合、確認の記録、使わない言葉の検査が Python のツールにあり、同じ決まりを2か所に書かないためである。
- 応答の文の型と言葉は docs/design.md（3節の表と、4節の「MCP の応答」）、使う生成AIが守ることは SKILL.md §1 に書く。この文書には、サーバーの形と、置き方を書く。

## 1. ツール（5つ）

| 名前 | 引数（必須は *） | 返すもの |
| --- | --- | --- |
| theme | theme、page | theme を省略すると、テーマの一覧。theme にテーマの ID を付けると、町の説明、論点の一覧、これまでの経過、町内の施設、施設の一覧、資料の一覧、項目の一覧 |
| issue | issue*、page | 論点1つの、町の資料の記述、これまでの説明と答弁（作成者の注を含む）、今後検討・決定するとされていること、目的と手段（事項の表がある論点だけ）、議会での質問と答弁。1回めの応答は質問の一覧までで、質問ごとの、その論点に関する部分は続き（page）で返す |
| item | item*、document、breakdown、page | 項目1つと、その数値（資料ごと、資料の日付の古い順）。document に資料の ID を付けると、その資料の数値だけ。breakdown を省略すると内訳（kubun）の無い数値だけ、breakdown=1 で内訳のある数値だけ |
| facility | facility*、page | 施設1つの、名前、前の名前、資料が書いている内容、資料の表での記述、施設を指す数値 |
| document | document*、table、page | 資料1つの、名前、版、日付、種類、根拠、資料どうしの関係（両方向）、数値がある項目、表の一覧、この資料を取り上げている議会での質問（行がある資料だけ。段落は続きで返す）。table に表の番号を付けると、その表の行と列と欄 |

- ツールと引数の名前は、2026-11-27 に、ローマ字から英語の語に直した（依頼者が了承した文案 `claude/hino-context-R2/ronten-mcp-an-2026-11-27.md` の4節）。前の名前との対応：suji → item、shisetsu → facility、shiryo → document。引数は id → item、key → facility、bunsho と shiryo → document、hyo → table、uchiwake → breakdown、tsuzuki → page。プログラムの中の関数の名前と、docs/design.md 3節の行の ID（mcp-hikisu-tsuzuki など）は、前のままにしている。
- 引数の型：table、breakdown、page は整数。ほかは文字列。
- ID：テーマの ID は hino-ronten のテーマの定義の theme、論点の ID は、事項の表（teigi/jiko.tsv）にそのテーマの行があるテーマ（hoiku）は事項の表の id（2026-11-27）、ほかのテーマは仮の表 teigi/note-<テーマ>.tsv の、kind が「論点」の行の key、項目の ID は項目の表の id、施設の ID は施設の参照表の key（`fa:` で始まる）、資料の ID は資料の一覧の表の bunsho、表の番号は資料の中の場所の表の n（SCHEMA.md §2・§5・§6・§7）。
- 応答の中では、名前のあとの括弧に、引数の名前と ID を出す（例：「待機児童数（item：taiki）」）。使う人の生成AIは、ツールの引数の説明か、応答にある ID だけを、ツールの引数に使う。テーマの全体（町の説明、経過、施設と資料の一覧）を知りたいときは、theme を呼ぶ（SKILL.md §1。2026-11-27 の修正）。
- 議会の質問と答弁は、論点ごとに issue で返す（2026-11-27）。いま返せるのは、4つのテーマ（hoiku、kaigo、kokyo、chiiki）の、確定済みの質問と論点の対応の記録がある質問と、確定済みの事柄の記録だけである（SCHEMA.md §8。2026-11-27 の依頼者の決定で、幼保の論点4つから広げた）。状態が「案」（candidate）の対応の記録（kaigo に28行、chiiki に1行）と、報告（kaigo の委員長の報告など、kind「報告」）との対応の記録は、出していない。語で会議録を探すツールは、入れていない。

## 2. 応答

- 文（見出しと箇条書き）。HTML は入れない。型は docs/design.md 4節の「MCP の応答」。
- どの数値と引用にも、資料の名前、ページ、もとの資料の URL を付ける。会議録は、日付と、議会での答弁か議会での議員の発言かを出し、発言者の名前は出さない。会議録の全文は入れない。引用は、数値と内容の表の inyo、hino-ronten の記録の quote と、issue の続きで返す、論点に関する会議録の段落（hino-ronten の質問と論点の対応の記録の、段落の範囲。幼保の論点4つで96か所。試作のページに出している段落と同じ）と、document の続きで返す、質問が取り上げた資料の表（taio/konkyo.tsv）の段落だけである。hino-ronten の記録の quote には、つながりの記録（目的と手段）の quote を含む（2026-11-27）。
- 確認の記録（数値と内容の表の chu の「人が PDF で確認（…）」「生成AIが画像を2回読んで一致（…）」、資料の中の場所の表の shisetsu_kakunin）を付ける。未確認の印は、ページと同じ条件で付ける（tools/suji.py の mikakunin）。
- 数値を計算しない。良し悪しを書かない。

### 2.1 上限と続き

- 1回の応答の上限は、文字数で決める（tools/build_mcp.py の定数 JOGEN。6,000 字）。
- 超える組は、区切りのよい所（資料ごと、表ごと、項目ごと）で分け、最後に続きを取る引数を示す。続きは、同じ引数に page=2、3、… を付けて取る。page=1 は、page を付けない組と同じ応答である。
- page は、5つのツールのすべてに付ける（文案2節の表の「どのツールにも」による）。いまのデータで続きがあるのは、theme（幼保）、issue、item の一部、facility の一部。
- issue は、上限に収まる場合も、質問ごとの、その論点に関する部分を、1回めの応答に入れず、質問ごとに新しい続きから始める。1回めの応答の質問の一覧に、その質問の部分が始まる続きの番号を出す（docs/design.md 4節）。

### 2.2 該当する組が無いとき

- 引数の組が JSON に無いときは、ツールごとの定型文（docs/design.md の mcp-nai と mcp-hani）を返す。近い ID を推し量って返さない。存在しない tsuzuki の番号も同じ。mcp-hani-nai は、いま入っているのは資料の一部で、無い事柄は、まだ入れていないものであることを示す文で、instructions にも入れる。theme（引数なし）の応答には、同じ内容で、場所に合わせた mcp-hani の文を出す（2026-11-27 の修正）。
- document の応答で、該当する行が無い項目（根拠、この資料について書いている、ほかの資料の文、数値がある項目、表の一覧）は、見出しを出し、mcp-irete-inai の文を出す。根拠が空で、資料の一覧の表の chu の「根拠：」の記述に「見つからない（…）」がある資料は、括弧の中の字（調べた所）を mcp-konkyo-nashi の文で出す（2026-11-27 の修正）。

- document の応答では、名前のすぐあとに、入れているのはその資料の一部であることの文（mcp-shiryo-hani）と、入れているものの数（mcp-shiryo-kazu。資料の表、数値の行と項目、資料どうしの関係の行。表の行を数えただけの数）を出す。資料の種類は、資料の一覧の表の shurui の値ではなく、docs/design.md 3節の言葉で出す（2026-11-27 の2回目の修正）。
- 数値と内容の表の chu に「抽出した文字の並びが崩れている」がある行（SCHEMA.md §6.2）は、資料の該当部分に inyo を出さず、inyo-kuzure の文を出す。数値のページも同じ（2026-11-27 の2回目の修正）。

### 2.3 内訳と、資料の間で一致しない数値（2026-11-27 の修正）

- item は、引数 breakdown を省略すると、内訳（数値と内容の表の kubun）の無い数値だけを返し、breakdown=1 で、内訳のある数値だけを返す。内訳のある数値がある項目（と資料の組）では、breakdown を付けない応答の終わりに、mcp-uchiwake の文を出す。組は、内訳のある数値がある項目と、内訳のある数値がある資料だけに作る。document と page と組み合わせられる。待機児童数は、内訳の無い数値が2回、内訳のある数値が4回になった（修正の前は5回）。2回目の修正のあとは、内訳の無い数値が3回（資料の該当部分の定型文のため）。
- item の応答の、資料ごとの数値の前に、数値のページと同じ「資料の間で、数値が一致していません」（chigau、chigau-setsumei）を出す。判定は数値のページと同じ（時点の関係が mae の数値を、内訳と時期ごとにまとめ、tools/suji.py の ichi_shinai）。時期ごとに、数値と資料の名前を並べる。どちらが正しいかは書かない。いまは待機児童数の2018年4月（会議録 2019年6月14日の「平成30年度」の「なし」と、提言と再編整備計画の2つの版の表の「1」）が該当する。
- 必須の引数が無いときと、型が違うとき（table に文字列など）は、MCP のライブラリが引数の検査の誤りを返す。

## 3. JSON の形（mcp/data/outou.json）

| 項目 | 中身 |
| --- | --- |
| name | サーバーの名前（hino-context） |
| version | 版（tools/build_mcp.py の定数。データのもとのコミットと日付は入れない。作るたびに変わると、検査で比較できないため） |
| description | サーバーの説明（mcp-setsumei） |
| instructions | 使う生成AIへの指示。SKILL.md §1 の箇条書きの行をそのまま入れ、最後に、扱っている範囲の文（docs/design.md の mcp-hani-nai）を1行足す（2026-11-27 の修正） |
| top | `/` に返す文（mcp-top） |
| tools | ツールの並び。ツールごとに name、description、args。args は引数ごとに name、type（string か integer）、required、description、erabu（選べる値の一覧） |
| nai | ツールの名前 → 該当する組が無いときの文 |
| outou | ツールの名前 → 引数の組の字 → bun の番号 |
| bun | 応答の文の並び |

- 引数の組の字は、ツールの引数の順に、値がある引数を「名前=値」にして「&」でつないだ字（例：`item=taiki&document=pt:youho/honpen&breakdown=1&page=2`）。引数なしは空の字。
- 組の数（2026-11-27 の、幼保の論点を事項の表から作る修正のあと）：theme 12、issue 201、item 183、facility 26、document 80（続きの分と page=1 の分を含む）。応答の文は307。修正の前は、issue 210、document 78、応答の文311（うち theme の7、論点の157）だった。幼保の論点は16から13（記録の無い事項24は、一覧に名前だけを出す）になり、資料の2つ（提言、基本構想）の document に続きが1つずつ増えた。論点の追加の前（2026-11-27）は、theme 6、issue 26、応答の文173（うち論点の22）だった。
- 2026-11-27 の、幼保の論点を事項の表から作る修正では、ツールと引数の名前と型は変えていない。issue の引数の説明の、選べる ID（hoiku07、hoiku09、hoiku12 が無くなった）は変わった。
- ツールの引数（名前、型、必須かどうか）は、なるべく変えない。使う人の Claude は、コネクタを登録したときのツールの一覧を覚えたままで、サーバーの更新に気づかないことがある（2026-11-27 の試行で分かった）。引数を変えるときは、登録し直しが要ることを、依頼者に伝える。2026-11-27 に、issue の追加と名前の修正をまとめて行ったので、マージのあと、登録し直しが1回要る。
- 資料の表のページを作れない表（行か列が無い表、欄が数値と内容の表に無い「読んだ」の表）も、組として入れ、定型文（mcp-hyo-dasenai）を返す。いまは2つ（`doc:shingi-youho-teigen 16`、`doc:jigyo-shinkodomoen-kousou 18`）。
- issue の組は、仮の表 teigi/note-<テーマ>.tsv があるテーマの、論点の行ごとに作る。事項の表にそのテーマの行があるテーマ（hoiku）は、事項の表の行のうち、確定済みの記録がある行ごとに作る（SCHEMA.md 7.9。2026-11-27）。theme の組は、テーマの表（teigi/theme.tsv）に行があるテーマと、仮の表があるテーマに作る（docs/design.md 4節）。

## 4. 応答を作るツール（tools/build_mcp.py）

- `python3 -B tools/build_mcp.py` で mcp/data/outou.json を作る。ページのツールと同じ検査（lock と入力、表の検査、docs/design.md の言葉の検査、引用の照合、使わない言葉。issue は試作のページと同じ検査）を通し、1つでも当たれば、件数と該当行を示して、何も書かずに終了コード 1。
- 資料の名前、時期、掲載されている所、表の欄は、ページを作るツール（tools/build_suji.py、tools/build_hyo.py、tools/build_theme.py）の関数を使う。
- マージ前の検査（tools/kensa.py）は、`--out build/mcp/outou.json --hikaku mcp/data/outou.json` で作り直し、リポジトリの JSON と同じであることを確認する。違えば止まる。データか docs/design.md の言葉を変えたら、`python3 -B tools/build_mcp.py` で作り直して、同じコミットか、続くデータのコミットに入れる。

## 5. Cloudflare に置くプログラム（mcp/）

- ファイル：package.json、package-lock.json、wrangler.jsonc、tsconfig.json、src/index.ts、data/outou.json。
- Cloudflare の現在の手引き（Agents SDK の createMcpHandler）の形。要求ごとに新しい McpServer を作り、セッションと Durable Objects を使わない。トランスポートは Streamable HTTP。パスは `/mcp`。`/` には mcp-top の文を返す。
- 行うことは3つだけ：ツールの一覧を返す（説明と引数は JSON から）、呼ばれたツールと引数に該当する応答を JSON から引いて返す、該当するものが無いときに JSON の定型文を返す。引数は、前後の空白を除くだけで、ほかの推定をしない。
- どのツールにも、読むだけの印（annotations の readOnlyHint）を付ける。
- 認証なし。バインディング（KV、D1、Durable Objects など）なし。JSON は import で束ねる。返すのは、公開の資料から作ったデータだけで、書き込みの機能は無い。
- 依存は版を固定する（package.json と package-lock.json）。ライセンスは、プログラムの区分（AGPL-3.0-or-later）。

### 5.1 公開

- Cloudflare の Workers Builds で、このリポジトリをつなぐ。Root directory は `mcp`、Build command は空、Deploy command は `npx wrangler deploy`（既定の値）。依存は、mcp/package-lock.json から、Workers Builds が入れる。リポジトリのいちばん上のファイルは使わない。
- 公開するブランチは main。PR を main にマージするたびに、公開される。
- main 以外のブランチでは、Cloudflare のビルドを行わない（Cloudflare の設定の「プレビューブランチのビルド」をオフにしている。2026-11-27）。プレビューの URL は使わない（設定ファイル mcp/wrangler.jsonc の `preview_urls` を false にしている）。確認は、手元の wrangler dev で行う。
- 公開の URL は `https://hino-context.<アカウントの workers.dev のサブドメイン>/mcp`。Claude のカスタムコネクタに、この URL を登録する。
- アカウントの ID などは、リポジトリに書かない。

### 5.2 手元での確認

`cd mcp && npm ci && npx wrangler dev` で、localhost に立てる。MCP の要求は、`Content-Type: application/json` と `Accept: application/json, text/event-stream` を付けて、`/mcp` に POST する。型の検査は `npx tsc --noEmit`。

## 6. 前の MCP（hino-ronten）の点検で、差が大きいとした点の扱い

2026-11-15 の点検（Project の `claude/hino-ronten-tenken-2026-11-15-mcp.md`）で、MCP の仕様との差が大きいとした点を、次のように扱った。

| 点検で分かった差 | 今回の形 |
| --- | --- |
| 1つのサーバーが1つのテーマの1つの見方だけを扱う | サーバーは1つ。テーマ、項目、施設、資料は、引数で選ぶ |
| 返す量に上限が無い | どのツールにも、1回の上限（6,000 字）と、続きを取る引数 page（2026-11-27 までは tsuzuki）を付けた。item は、内訳のある数値を引数 breakdown で分けた（2026-11-27 の修正） |
| 引数に説明が無い | 引数ごとに、説明、必須かどうか、型、選べる値を JSON に持ち、ツールの一覧で返す。選べる ID は、説明の文にも並べる |
| 接続ごとにやりとりを持つ作り | 要求ごとに完結する作り（createMcpHandler）。セッションを持たない |
| 読むだけの印が無い | どのツールにも readOnlyHint を付けた |
