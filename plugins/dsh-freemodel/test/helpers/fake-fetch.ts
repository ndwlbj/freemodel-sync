import type { FetchLike } from "../../src/providers/openai-compat.ts";
import type { CatalogModel } from "../../src/providers/types.ts";

export interface Call {
  url: string;
  init: RequestInit | undefined;
}

export type Route = (url: string, init: RequestInit | undefined) => Response | Promise<Response>;

/** A fetch that answers from `route` and records every call. */
export function fakeFetch(route: Route): FetchLike & { calls: Call[] } {
  const calls: Call[] = [];
  const fn = (async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return route(url, init);
  }) as FetchLike & { calls: Call[] };
  fn.calls = calls;
  return fn;
}

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

/** An SSE body from `data:` payloads (objects are JSON-encoded). */
export const sse = (events: Array<unknown>, headers: Record<string, string> = {}, status = 200): Response =>
  new Response(events.map((e) => `data: ${typeof e === "string" ? e : JSON.stringify(e)}\n\n`).join(""), {
    status,
    headers: { "Content-Type": "text/event-stream", ...headers },
  });

export const token = (content: string, finish: string | null = null) => ({
  choices: [{ delta: { content }, finish_reason: finish }],
});

export function model(id: string, extra: Partial<CatalogModel> = {}): CatalogModel {
  return {
    provider: "openrouter",
    id,
    name: id,
    contextLength: 131072,
    tools: true,
    input: ["text"],
    maxTokens: null,
    expirationDate: null,
    capabilities: { tools: true, vision: null, reasoning: null, source: "catalog" },
    quota: null,
    tier: 1,
    ...extra,
  };
}

export const OR_KEY = `sk-or-v1-${"ab12".repeat(16)}`;
export const GROQ_KEY = `gsk_${"Zy9".repeat(16)}`;
export const SENSENOVA_KEY = `sk-${"A1b2C3d4".repeat(4)}`;
export const DASHSCOPE_KEY = `sk-ws-${"Ab1._-".repeat(18)}`;
