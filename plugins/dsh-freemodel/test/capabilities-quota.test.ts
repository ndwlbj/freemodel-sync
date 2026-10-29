/** P6: capability/quota parsing and picker badges, including the unknown paths. */
import { describe, expect, it } from "vitest";
import { pickerName, toPiModel } from "../src/adapter.ts";
import { capabilityBadges, compactAmount, modelBadges, quotaBadge } from "../src/badges.ts";
import type { CatalogModel } from "../src/providers/types.ts";
import {
  isExhausted,
  parseCapabilities,
  parseQuota,
  remainingInWindow,
  remainingTotal,
} from "../src/providers/types.ts";
import { parseState } from "../src/state.ts";

const model = (extra: Partial<CatalogModel> = {}): CatalogModel => ({
  provider: "groq",
  id: "llama-x",
  name: "llama-x",
  contextLength: 131072,
  tools: null,
  input: ["text"],
  maxTokens: null,
  expirationDate: null,
  capabilities: { tools: null, vision: null, reasoning: null, source: "unknown" },
  quota: null,
  tier: 1,
  ...extra,
});

describe("capabilities parsing", () => {
  it("treats missing and unknown values as unknown, never false", () => {
    expect(parseCapabilities(undefined)).toEqual({
      tools: null,
      vision: null,
      reasoning: null,
      source: "unknown",
    });
    expect(parseCapabilities({ tools: "?", vision: "n/a", reasoning: "unknown", source: "nowhere" })).toEqual({
      tools: null,
      vision: null,
      reasoning: null,
      source: "unknown",
    });
  });

  it("keeps a known flag next to unknown ones and reads legacy supports_tools", () => {
    expect(parseCapabilities({ tools: null, vision: true, reasoning: "unknown", source: "catalog" })).toEqual({
      tools: null,
      vision: true,
      reasoning: null,
      source: "catalog",
    });
    expect(parseCapabilities(undefined, true).tools).toBe(true);
    expect(parseCapabilities(undefined, false).tools).toBe(false);
  });
});

describe("quota parsing", () => {
  it("reads the five-hour, weekly, total and beta windows", () => {
    const rolling = parseQuota({ unit: "tokens", period: "5h", limit: 120000, remaining: 90000, source: "api" });
    expect(rolling?.period).toBe("rolling_5h");
    expect(rolling === null ? null : remainingInWindow(rolling)).toBe(90000);

    expect(parseQuota({ unit: "tokens", period: "weekly", limit: 1200000 })?.period).toBe("week");
    expect(parseQuota({ unit: "tokens", period: "total", limit: 1000000, used: 250000 })).toMatchObject({
      period: "total",
      remaining: null,
    });
    const total = parseQuota({ unit: "tokens", period: "total", limit: 1000000, used: 250000 });
    expect(total === null ? null : remainingTotal(total)).toBe(750000);
    expect(quotaBadge(parseQuota({ unit: "tokens", period: "beta", source: "none" }))).toBe("公测期");
  });

  it("handles unknown documents and numbers conservatively", () => {
    expect(parseQuota(null)).toBeNull();
    const unknown = parseQuota({ unit: "widgets", period: "fortnight", limit: "many", source: "magic" });
    expect(unknown).toMatchObject({ unit: "unknown", period: "unknown", limit: null, source: "none" });
    expect(unknown === null ? false : isExhausted(unknown)).toBe(false);
  });

  it("subtracts local probes for provider values but not manual ones", () => {
    const api = parseQuota({
      unit: "requests",
      period: "day",
      limit: 50,
      used: 5,
      remaining: 10,
      source: "api",
      probesSinceRead: 3,
    });
    expect(api === null ? null : remainingInWindow(api, api.probesSinceRead ?? 0)).toBe(7);
    const manual = parseQuota({
      unit: "tokens",
      period: "day",
      limit: 100,
      remaining: 100,
      source: "manual",
      probesSinceRead: 5,
    });
    expect(manual === null ? null : remainingInWindow(manual, manual.probesSinceRead ?? 0)).toBe(100);
  });

  it("understands the legacy daily request shape", () => {
    const legacy = parseQuota({ daily_free_limit: 50, daily_free_used: 5, daily_free_remaining: 45 });
    expect(legacy).toMatchObject({ unit: "requests", period: "day", source: "api", limit: 50, remaining: 45 });
    expect(parseQuota({ daily_free_remaining: 7 })).toMatchObject({ period: "day", remaining: 7 });
  });
});

describe("picker badges", () => {
  it("shows explicit unknown badges", () => {
    expect(capabilityBadges(null)).toEqual(["能力未知"]);
    expect(quotaBadge(null)).toBe("额度未知");
    expect(modelBadges(model())).toEqual(["能力未知", "额度未知"]);
    expect(pickerName("llama-x", { model: model(), score: 0, test: null, reasons: [] })).toBe(
      "llama-x · 免费 · 能力未知 · 额度未知",
    );
  });

  it("shows known capability and quota badges and compact amounts", () => {
    const withBadges = model({
      capabilities: { tools: true, vision: true, reasoning: true, source: "catalog" },
      quota: {
        unit: "tokens",
        period: "rolling_5h",
        limit: 120000,
        used: null,
        remaining: 90000,
        resetsAt: null,
        expiresAt: null,
        source: "api",
        scope: "account",
      },
    });
    expect(modelBadges(withBadges)).toEqual(["工具", "视觉", "推理", "余 90k tokens · 5小时"]);
    expect(compactAmount(1_000_000)).toBe("1M");
    expect(compactAmount(120000)).toBe("120k");
  });

  it("maps vision and reasoning into the pi-ai descriptor", () => {
    const descriptor = toPiModel("groq", {
      model: model({
        input: ["text", "image"],
        capabilities: { tools: true, vision: true, reasoning: true, source: "catalog" },
      }),
      score: 0,
      test: null,
      reasons: [],
    });
    expect(descriptor.input).toEqual(["text", "image"]);
    expect(descriptor.reasoning).toBe(true);
  });
});

describe("old state compatibility", () => {
  it("reads a model without capabilities/quota as unknown", () => {
    const state = parseState(
      JSON.stringify({
        schemaVersion: 1,
        plugin: "dsh-freemodel",
        updatedAt: "2026-10-27T12:00:00.000Z",
        channels: {
          openrouter: {
            catalog: {
              fetchedAt: 1,
              models: [
                { provider: "openrouter", id: "old:free", name: "old", contextLength: 4096, tools: true, input: ["text"], maxTokens: null, expirationDate: null },
              ],
              error: null,
              errorAt: null,
            },
            results: {},
            daily: { date: "", count: 0 },
            blockedUntil: null,
            lastRound: null,
          },
          groq: { catalog: null, results: {}, daily: { date: "", count: 0 }, blockedUntil: null, lastRound: null },
        },
      }),
    );
    const old = state.channels.openrouter.catalog?.models[0];
    expect(old?.tools).toBe(true);
    expect(old?.capabilities).toEqual({ tools: true, vision: null, reasoning: null, source: "catalog" });
    expect(old?.quota).toBeNull();
    expect(old?.tier).toBe(1);
  });
});