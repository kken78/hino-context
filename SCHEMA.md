# SCHEMA.md — 鍵と照合の決まり

このリポジトリが入力を指す鍵、引用を原典と照らす決まり、出典の url の作り方を書く。いまは、論点ノートの試作（幼保）で使う物だけを書く。もとは hino-ronten の LINK_SCHEMA.md §2・§4・§5・§15.1（hino-ronten 1c34ba0）。

## 1. 入力の固定 `inputs.lock.json`

- 5つの入力（hino-council-search・shiga-hino-plans・hino-town-docs・council-dashboard・hino-ronten）ごとに、コミットの SHA（40桁）と、読むファイルのパターン（files）を書く。`*` は1つの階層の中だけに当たる。
- 道具は、読む前に、5つの入力の作業ツリーの HEAD が lock の SHA と同じかを確かめる。違うとき、git のリポジトリでないとき、HEAD が取れないときは、読まずに止める。
- 読むのは lock の SHA の、files に当たるファイルだけ（`git show <SHA>:<path>`）。入力の場所は、環境変数 `HINO_CONTEXT_INPUTS`（既定 `/tmp/inputs`。その下にリポジトリ名の4つ）と `HINO_CONTEXT_RONTEN`（既定 `/home/claude/hino-ronten`）で受ける。
- hino-ronten から読むのは、題材の定義（ref/themes.tsv）、事柄の記録（records/kotogara.tsv）、過程の記録（records/katei.tsv）、問いと事項の対応（records/taio.tsv）で、status が confirmed の行だけを使う。

## 2. 鍵

| 鍵 | 指す物 | 形 | 例 | 元のデータ |
| --- | --- | --- | --- | --- |
| sp | 会議録の発言 | `sp:<sid>` | `sp:0000008211_20241213_0156` | hino-council-search `public/data/index/<年>.json` の sid |
| sp（段落） | 発言の中の段落 | `sp:<sid>/<段落>`、続いた段落は `sp:<sid>/<始め>-<終わり>`（始め＜終わり） | `sp:0000008116_20240917_0015/5-7` | 同じ発言の text |
| iq | 一般質問の問い | `iq:<sid>` | `iq:0000008397_20250310_0285` | 問いの最初の発言の sid |
| sq | 議案の質疑のまとまり | `sq:<sid>` | `sq:0000008397_20250307_0076` | まとまりの最初の発言の sid |
| doc | 町の資料のページ | `doc:<id>/<ページ>` | `doc:koho-no792-04/1` | hino-town-docs `data/sources.tsv` の id と、PDF のページ（1から） |
| pt | 計画の原典の文字のページ | `pt:<id>/<名前>/<ページ>` | `pt:youho/honpen-202503/4` | shiga-hino-plans `data/sources_index.tsv` の id と file（拡張子を除いた名前）と、ページ（1から） |
| plan | 計画 | `plan:<id>` | `plan:youho` | shiga-hino-plans `data/plans/<id>.json` |
| gi | 議案 | `gi:<会議id>/<議案番号>` | `gi:0000008942/議第115号` | hino-council-search `public/data/gian.json` |
| node | 計画の事業 | `node:<id>/<key>` | `node:jisshi/e008` | shiga-hino-plans `data/plans/<id>.json` の programs の key |

- sid は `<会議id 10桁>_<名前>_<連番4桁>` の形で、`/`・`,`・`:`・空白を含まない。段落の鍵は、最後の `/` で sid と段落に分ける。
- 段落の数え方：lock の版の発言の本文（text）を改行（LF）で分け、空か空白だけの部分を除いて、頭から1、2、…と数える。改行の無い本文は段落1つ。hino-council-search の画面の `&p=<段落>` と同じ数え方。
- sp・iq・sq は発言の位置に依存するので、単独では信頼しない。引用か段落が、その発言の本文にあることで確かめる（§3）。
- gi・node・plan は、この試作では、題材の定義の字の中に出るだけで、道具は読まない。

## 3. 正規化と、引用を原典と照らす決まり

正規化（引用と照らす相手の本文の両方にかける。順に）：

1. NFKC 正規化
2. 改行に続く会議録のページ番号（`\n` の後の「数字-数字」）を除く
3. 前後をハイフンで挟んだページ番号（「-数字-」）を除く
4. 空白（全角・半角・改行・タブなど）をすべて除く

照らす相手：

- sp：lock の版の、その発言の本文
- doc：hino-town-docs の `data/text/<id>.txt` か `data/text_raw/<id>.txt` の、そのページの部分（ページは改ページ `\f` で区切る）
- pt：shiga-hino-plans の `data/text/<id>/<名前>.txt` か `data/text_raw/<id>/<名前>.txt` の、そのページの部分
- 2つの層（text・text_raw）のどちらか一方にあればよい

決まり：

- 正規化した引用が、正規化した相手の本文に含まれれば「合った」とする。
- 合わない引用、相手の本文が無い引用（ファイルやページが無い、鍵の形が違う）は「合わなかった」とする。合わなかった行が1件でもあれば、道具はページを作らずに止まり、件数と行を示す。
- 段落の鍵は、その発言に、その番号の段落があることを確かめる。無ければ同じく止まる。
- 引用の無い記述（資料の鍵が空、名前か url が作れない資料）も、出さずに止まる。

## 4. 出典の名前と url

| 鍵 | 名前 | url |
| --- | --- | --- |
| sp | `会議録 <年>年<月>月<日>日 <発言者>`（日付は sid の8桁、発言者は索引の name） | `https://kken78.github.io/hino-council-search/#sid=<sid>`。引用が1つの段落の中にあれば `&p=<段落>` を付ける |
| sp（段落） | リンクの名前は「会議録」 | `https://kken78.github.io/hino-council-search/#sid=<sid>&p=<段落>` |
| iq・sq | （問いの題は題材の定義の字から） | `https://kken78.github.io/hino-council-search/#sid=<sid>` |
| doc | `「<sources.tsv の title>」 <ページ>ページ` | sources.tsv の url に `#page=<ページ>` |
| pt | `<data/plans/<id>.json の meta.name> <ページ>ページ` | sources_index.tsv の url に `#page=<ページ>` |

- 町のサイトでの掲載が終わった資料：hino-town-docs の sources.tsv の archive_url（依頼者が確かめた保存版）があれば、同じ url の資料（doc・pt とも）の url を archive_url に置き換える。`#page=` はそのまま付ける。

## 5. まだ決めていない物

- `teigi/` の表（事項の種類・関係・数字の定義）と `taio/` の表（問いと事項の対応、事項ごとの記述）の形は、これから決める。
- `teigi/note-hoiku.tsv` は、論点ノートの試作（幼保）のための仮の表。列は kind・key・name・short・setsumei。kind は テーマ（key はテーマの id、setsumei はテーマの説明）、論点（key はページの id、name は hino-ronten の事柄の名前、short は短い名前、setsumei は説明）、準備中（name だけ）、抜き出しの語（name に語。「今後検討・決定するとされていること」に抜き出す記述の語）、単位（key に資料の鍵の頭、name に単位。その資料の、数字だけの値に付ける単位。例 `doc:yosan-` の資料の値は千円）。
