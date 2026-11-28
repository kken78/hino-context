// data/outou.json を、応答の文（bun）と、それ以外（目次）に分ける（docs/mcp.md 5節。2026-11-28）。
// 応答の文は、1つずつ静的なアセットのファイル（public/o/<番号>.txt）にし、目次（ツールの一覧、定型文、引数の組 → 応答の文の番号）は
// dist/mokuji.json にして、プログラム（src/index.ts）に束ねる。JSON の中身は変えない。
// 公開のとき（npx wrangler deploy）と手元での確認（npx wrangler dev）のときに、wrangler.jsonc の build の command で動く。
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const moto = new URL("../data/outou.json", import.meta.url);
const pub = new URL("../public/", import.meta.url);
const dist = new URL("../dist/", import.meta.url);
const data = JSON.parse(readFileSync(moto, "utf8"));
if (!Array.isArray(data.bun) || data.bun.length === 0) {
  throw new Error("data/outou.json に、応答の文（bun）が無い");
}
rmSync(pub, { recursive: true, force: true });
rmSync(dist, { recursive: true, force: true });
mkdirSync(new URL("o/", pub), { recursive: true });
mkdirSync(dist, { recursive: true });
data.bun.forEach((t, i) => writeFileSync(new URL(`o/${i}.txt`, pub), t));
const { bun, ...mokuji } = data;
writeFileSync(new URL("mokuji.json", dist), JSON.stringify({ ...mokuji, kazu: bun.length }));
console.log(`応答の文 ${bun.length} を public/o/ に、目次を dist/mokuji.json に書いた`);
