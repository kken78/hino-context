# 経過（CLAUDE.md の「現在の状態」から移した項目）

CLAUDE.md の「現在の状態」は10項目以内に保つ。項目が10を超えたときに、いちばん古い項目を、書いたときの文のまま、この文書の終わりに足す。

- 2026-11-18：hino-ronten での作業を閉じ（hino-ronten 1c34ba0）、このリポジトリで作り直しを始めた。工程は R0〜R4（`docs/hoshin.md` §7）。幼保から通す。R0 のうち、方針と手順書を置いた。次は、R1 の見本に使う事項を決め、見本に要る分だけ鍵と照合のツールを移す
- 2026-11-18（R0）：鍵と、引用をもとの資料と照合する決まりを SCHEMA.md に、出すときの規約と画面に出す言葉の表を SKILL.md に書き、ツール（tools/inputs.py・keys.py・shogo.py・ronten.py・build_note.py）とテスト39件を置いた。`python3 -B tools/build_note.py hoiku` で、テーマ「幼児教育・保育施設の再編」と論点4つ（整備費用と財源・面積・用地・定員）の試作のページ build/note/hoiku.html ができる（中身は hino-ronten の確定済みの記録。引用49件・会議録の部分96か所を照合し、合わないものがあれば作らずに止まる。画面の文に、言葉の表で使わないとした言葉が残っていても止まる）。テーマと論点の名前・抜き出しの語・単位は、仮の表 teigi/note-hoiku.tsv にある（R2 で定義の表に移す）。実装は Opus 5.5、指示と点検は Fable 5.2。確認は `rm -rf build; python3 -B -m unittest discover -s tools -p 'test_*.py'`。次は R1（試作を使う人に見てもらう。依頼者）と、R2 の準備（論点の一覧の案、数字の定義の表の案）
