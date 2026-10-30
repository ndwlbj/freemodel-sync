import { describe, expect, it, vi } from "vitest";
import {
  AUTO_MODEL_ID,
  AUTO_ROUTE,
  AutoRouteAdapter,
  collectCandidates,
  createAutoRouteAdapter,
  isAutoRoute,
  isTerminalFailure,
  shouldFailover,
  tryNextAfterFailure,
} from "../src/auto-route.ts";
import type { CatalogModel } from "../src/providers/types.ts";
import type { RankedModel } from "../src/rank.ts";
import type { FreemodelService } from "../src/service.ts";
import type { ChannelId } from "../src/spec.ts";

function catalogModel(id: string, extra: Partial<CatalogModel> = {}): CatalogModel {
  return {
    provider: "openrouter",
    id,
    name: id,
    contextLength: 131072,
    tools: true,
    input: ["text"],
    maxTokens: 4096,
    expirationDate: null,
    capabilities: { tools: true, vision: false, reasoning: false, source: "catalog" },
    quota: null,
    tier: 1,
    ...extra,
  };
}

function ranked(id: string, score: number, extra: Partial<CatalogModel> = {}): RankedModel {
  return {
    model: catalogModel(id, extra),
    score,
    test: null,
    reasons: [],
  };
}

describe("auto-route candidates", () => {
  it("isAutoRoute identifies freemodel-auto", () => {
    expect(isAutoRoute(AUTO_ROUTE)).toBe(true);
    expect(isAutoRoute("freemodel-openrouter")).toBe(false);
    expect(isAutoRoute(undefined)).toBe(false);
  });

  it("collectCandidates sorts by score descending and ignores inactive/empty channels", () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter" || id === "groq"),
      listed: vi.fn((id: ChannelId) => {
        if (id === "openrouter") {
          return [ranked("m-mid", 50), ranked("m-high", 90)];
        }
        if (id === "groq") {
          return [ranked("m-top", 100)];
        }
        return [ranked("m-ignored", 999)]; // bailian/sensenova are inactive
      }),
    } as unknown as FreemodelService;

    const candidates = collectCandidates(service);
    expect(candidates.map((c) => [c.channel, c.ranked.model.id, c.ranked.score])).toEqual([
      ["groq", "m-top", 100],
      ["openrouter", "m-high", 90],
      ["openrouter", "m-mid", 50],
    ]);
  });

  it("breaks score ties stably by channel order then model id", () => {
    const service = {
      isActive: vi.fn(() => true),
      listed: vi.fn((id: ChannelId) => {
        if (id === "openrouter") return [ranked("b-model", 80), ranked("a-model", 80)];
        if (id === "groq") return [ranked("z-model", 80)];
        return [];
      }),
    } as unknown as FreemodelService;

    const candidates = collectCandidates(service);
    expect(candidates.map((c) => [c.channel, c.ranked.model.id])).toEqual([
      ["openrouter", "a-model"],
      ["openrouter", "b-model"],
      ["groq", "z-model"],
    ]);
  });

  it("never includes tier-2 manual entries (only service.listed on CHANNEL_IDS)", () => {
    const service = {
      isActive: vi.fn(() => true),
      listed: vi.fn((id: ChannelId) => (id === "openrouter" ? [ranked("or-free", 50)] : [])),
      manual: () => [{ dshProvider: "dsh-zcode", model: "z-manual" }],
    } as unknown as FreemodelService;

    const candidates = collectCandidates(service);
    expect(candidates.length).toBe(1);
    expect(candidates[0]?.route).toBe("freemodel-openrouter");
    expect(candidates[0]?.ranked.model.id).toBe("or-free");
  });
});

describe("failover pure helpers", () => {
  it("detects terminal error chunks and finish reasons", () => {
    expect(isTerminalFailure({ type: "error", error: "boom" })).toBe(true);
    expect(shouldFailover({ type: "error" })).toBe(true);
    expect(isTerminalFailure({ type: "finish", reason: { kind: "error" } })).toBe(true);
    expect(isTerminalFailure({ type: "finish", reason: { kind: "aborted" } })).toBe(true);
    expect(isTerminalFailure(new Error("network error"))).toBe(true);
    expect(isTerminalFailure({ type: "text-delta", text: "hello" })).toBe(false);
    expect(isTerminalFailure({ type: "finish", reason: { kind: "stop" } })).toBe(false);
    expect(isTerminalFailure(null)).toBe(false);
  });

  it("tryNextAfterFailure returns the next candidate or undefined", () => {
    const candidates = ["c0", "c1", "c2"];
    expect(tryNextAfterFailure(1, candidates)).toBe("c1");
    expect(tryNextAfterFailure(2, candidates)).toBe("c2");
    expect(tryNextAfterFailure(3, candidates)).toBeUndefined();
    expect(tryNextAfterFailure("c0", candidates)).toBe("c1");
    expect(tryNextAfterFailure(["c0", "c1"], candidates)).toBe("c2");
    expect(tryNextAfterFailure(["c0", "c1", "c2"], candidates)).toBeUndefined();
  });
});

describe("AutoRouteAdapter streaming and metadata", () => {
  it("throws clear error when no candidate models are available", async () => {
    const service = {
      isActive: vi.fn(() => false),
      listed: vi.fn(() => []),
    } as unknown as FreemodelService;
    const delegate = vi.fn(async function* () {});
    const adapter = createAutoRouteAdapter(service, delegate);

    const stream = adapter.stream({ provider: AUTO_ROUTE, model: AUTO_MODEL_ID } as never);
    await expect(async () => {
      for await (const _chunk of stream) {
        // no-op
      }
    }).rejects.toThrow(/no free model available/);
  });

  it("fails over to second candidate when first stream yields error chunk before any text", async () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter"),
      listed: vi.fn(() => [ranked("first-model", 90), ranked("second-model", 80)]),
    } as unknown as FreemodelService;

    const delegateCalls: Array<{ provider: string; model: string }> = [];
    const delegate = vi.fn(async function* (options: { provider: string; model: string }) {
      delegateCalls.push({ provider: options.provider, model: options.model });
      if (options.model === "first-model") {
        yield { type: "block-start", index: 0 };
        yield { type: "error", error: "rate limit" };
      } else {
        yield { type: "text-delta", index: 0, text: "success from second" };
        yield { type: "finish", reason: { kind: "stop" } };
      }
    });

    const adapter = new AutoRouteAdapter(service, delegate);
    const received: unknown[] = [];
    for await (const chunk of adapter.stream({ provider: AUTO_ROUTE, model: AUTO_MODEL_ID } as never)) {
      received.push(chunk);
    }

    expect(delegateCalls).toEqual([
      { provider: "freemodel-openrouter", model: "first-model" },
      { provider: "freemodel-openrouter", model: "second-model" },
    ]);
    expect(received).toEqual([
      { type: "text-delta", index: 0, text: "success from second" },
      { type: "finish", reason: { kind: "stop" } },
    ]);
  });

  it("fails over when first candidate throws an exception before any text", async () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter"),
      listed: vi.fn(() => [ranked("bad-model", 90), ranked("good-model", 80)]),
    } as unknown as FreemodelService;

    const delegate = vi.fn(async function* (options: { provider: string; model: string }) {
      if (options.model === "bad-model") {
        throw new Error("HTTP 503 upstream unavailable");
      }
      yield { type: "text-delta", index: 0, text: "recovered" };
    });

    const adapter = new AutoRouteAdapter(service, delegate);
    const chunks: unknown[] = [];
    for await (const chunk of adapter.stream({ provider: AUTO_ROUTE, model: AUTO_MODEL_ID } as never)) {
      chunks.push(chunk);
    }
    expect(chunks).toEqual([{ type: "text-delta", index: 0, text: "recovered" }]);
  });

  it("does NOT failover mid-stream if text-delta was already emitted", async () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter"),
      listed: vi.fn(() => [ranked("first-model", 90), ranked("second-model", 80)]),
    } as unknown as FreemodelService;

    const delegateCalls: string[] = [];
    const delegate = vi.fn(async function* (options: { provider: string; model: string }) {
      delegateCalls.push(options.model);
      if (options.model === "first-model") {
        yield { type: "text-delta", index: 0, text: "partial output" };
        yield { type: "error", error: "dropped mid stream" };
      } else {
        yield { type: "text-delta", index: 0, text: "should not be called" };
      }
    });

    const adapter = new AutoRouteAdapter(service, delegate);
    const chunks: unknown[] = [];
    for await (const chunk of adapter.stream({ provider: AUTO_ROUTE, model: AUTO_MODEL_ID } as never)) {
      chunks.push(chunk);
    }

    expect(delegateCalls).toEqual(["first-model"]);
    expect(chunks).toEqual([
      { type: "text-delta", index: 0, text: "partial output" },
      { type: "error", error: "dropped mid stream" },
    ]);
  });

  it("surfaces the last failure when all candidates fail", async () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter"),
      listed: vi.fn(() => [ranked("c1", 90), ranked("c2", 80)]),
    } as unknown as FreemodelService;

    const delegate = vi.fn(async function* (options: { provider: string; model: string }) {
      if (options.model === "c1") {
        yield { type: "error", error: "error1" };
      } else {
        yield { type: "error", error: "error2" };
      }
    });

    const adapter = new AutoRouteAdapter(service, delegate);
    const chunks: unknown[] = [];
    for await (const chunk of adapter.stream({ provider: AUTO_ROUTE, model: AUTO_MODEL_ID } as never)) {
      chunks.push(chunk);
    }
    expect(chunks).toEqual([{ type: "error", error: "error2" }]);
  });

  it("listModels and resolveModel describe the current #1 model", async () => {
    const service = {
      isActive: vi.fn((id: ChannelId) => id === "openrouter"),
      listed: vi.fn(() => [ranked("deepseek-free", 95, { contextLength: 65536, maxTokens: 8192 })]),
    } as unknown as FreemodelService;

    const adapter = new AutoRouteAdapter(service, vi.fn());
    const models = await adapter.listModels(AUTO_ROUTE);
    expect(models).toHaveLength(1);
    expect(models[0]?.id).toBe("best");
    expect(models[0]?.name).toBe("Auto · 免费");
    expect(models[0]?.description).toContain("deepseek-free");

    const resolved = await adapter.resolveModel(AUTO_ROUTE, "best");
    expect(resolved.id).toBe("best");
    expect(resolved.context?.contextWindow).toBe(65536);
    expect(resolved.defaultMaxTokens).toBe(8192);

    const prep = await adapter.prepareCall(AUTO_ROUTE, "best");
    expect(prep.model.id).toBe("best");
    expect(typeof prep.stream).toBe("function");
  });
});
