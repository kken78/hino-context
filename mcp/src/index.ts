// hino-context の MCP サーバー（Cloudflare Workers。docs/mcp.md）。
// 行うことは3つだけ：ツールの一覧を返す、呼ばれたツールと引数に該当する応答を data/outou.json から引いて返す、
// 該当するものが無いときに data/outou.json の決まった文を返す。
// 応答の文、言葉、決まりは、tools/build_mcp.py が作った JSON にあり、ここには書かない。
// 要求ごとに新しいサーバーを作る（createMcpHandler）。セッションと Durable Objects は使わない。
import { McpServer } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { z } from "zod";
import json from "../data/outou.json";

type Hikisu = { name: string; type: "string" | "integer"; required: boolean; description: string };
type Tool = { name: string; description: string; args: Hikisu[] };
type Data = {
  name: string;
  version: string;
  description: string;
  instructions: string;
  top: string;
  tools: Tool[];
  nai: Record<string, string>;
  outou: Record<string, Record<string, number>>;
  bun: string[];
};

const data = json as unknown as Data;

function schema(a: Hikisu) {
  const s = (a.type === "integer" ? z.number().int() : z.string()).describe(a.description);
  return a.required ? s : s.optional();
}

// 引数 → 応答を引くための、引数の組の字。ツールの引数の順に「名前=値」を「&」でつなぐ。値は前後の空白を除くだけで、ほかの推定はしない。
function kagi(tool: Tool, args: Record<string, unknown>): string {
  const out: string[] = [];
  for (const a of tool.args) {
    const v = args[a.name];
    if (v === undefined || v === null) continue;
    const s = String(v).trim();
    if (s !== "") out.push(`${a.name}=${s}`);
  }
  return out.join("&");
}

function hiku(tool: Tool, args: Record<string, unknown>): string {
  const i = data.outou[tool.name]?.[kagi(tool, args)];
  return i === undefined ? data.nai[tool.name] : data.bun[i];
}

function createServer() {
  const server = new McpServer(
    { name: data.name, version: data.version, description: data.description },
    { instructions: data.instructions },
  );
  for (const tool of data.tools) {
    const shape = Object.fromEntries(tool.args.map((a) => [a.name, schema(a)]));
    server.registerTool(
      tool.name,
      { description: tool.description, inputSchema: z.object(shape), annotations: { readOnlyHint: true } },
      async (args: Record<string, unknown>) => ({ content: [{ type: "text" as const, text: hiku(tool, args) }] }),
    );
  }
  return server;
}

const mcp = createMcpHandler(createServer, { route: "/mcp" });

export default {
  fetch(request: Request, env: unknown, ctx: ExecutionContext) {
    if (new URL(request.url).pathname === "/") {
      return new Response(data.top, { headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    return mcp(request, env, ctx);
  },
} satisfies ExportedHandler;
