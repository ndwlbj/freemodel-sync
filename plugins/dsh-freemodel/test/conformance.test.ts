/**
 * Runs the shared golden cases in spec/conformance/ against the plugin, as
 * tests/test_spec_conformance.py does against the Python tool. Both must
 * agree with every case (spec/README.md).
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { type Classifier, classifierFor, classifyStreamError, classifyWith, defaultErrorMap } from "../src/classify.ts";
import { entryExpired, manualProbeDecision, type ManualProbeRecord, validateManualEntry } from "../src/manual.ts";
import { groqRateLimitHints } from "../src/providers/groq.ts";
import { isFreeModel, openRouterRateLimitHints } from "../src/providers/openrouter.ts";
import type { CatalogModel, ProbeResult } from "../src/providers/types.ts";
import {
  isExhausted,
  modelKey,
  parseCapabilities,
  parseQuota,
  QUOTA_PERIOD_SECONDS,
  remainingInWindow,
  remainingTotal,
} from "../src/providers/types.ts";
import { defaultWeights, isNonChat, rank, scoreModel } from "../src/rank.ts";
import { redact } from "../src/redact.ts";
import { CHANNEL_IDS, providerSpec, rankingSpec, SpecError } from "../src/spec.ts";
import { isRecord } from "../src/util.ts";

const dir = fileURLToPath(new URL("../../../spec/conformance/", import.meta.url));

interface CaseFile<C> {
  spec_version: number;
  area: string;
  cases: C[];
  today?: string;
  rankOrder?: string[];
}

function load<C>(area: string): CaseFile<C> {
  const data = JSON.parse(readFileSync(`${dir}${area}.json`, "utf8")) as CaseFile<C>;
  expect(data.area).toBe(area);
  return data;
}

const label = (c: { name?: string; id?: string }) => c.name ?? c.id ?? "?";
const classifier = (provider: string | null): Classifier =>
  classifierFor(provider as "openrouter" | "groq" | "sensenova" | null);

describe("conformance files", () => {
  it("every file has a runner here", () => {
    const areas = readdirSync(dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.slice(0, -5))
      .sort();
    expect(areas).toEqual(["capabilities", "capacity", "classify", "free_rule", "manual", "non_chat", "quota", "rate_limit", "score", "stream_classify"]);
  });
});

describe("classify", () => {
  type Case = { name: string; provider: string | null; status: number | null; error: unknown; expected: string };
  it.each(load<Case>("classify").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    const error = typeof c.error === "object" && c.error !== null && !Array.isArray(c.error) ? c.error : {};
    expect(classifier(c.provider)(c.status, error)).toBe(c.expected);
  });

  it("an unknown condition is an error, and no status falls back to the default", () => {
    const map = { preStream: [{ status: [403], when: [{ bogus: "x" }], kind: "model" }], default: "model" };
    expect(() => classifyWith(map as never, 403, {})).toThrow(SpecError);
    expect(() => classifyWith(map as never, 403, {})).toThrow(/unknown condition/);
    expect(classifyWith(defaultErrorMap(), null, {})).toBe("model");
  });
});

describe("stream_classify", () => {
  type Case = { name: string; provider: string | null; code: number | null; error: unknown; expected: string };
  it.each(load<Case>("stream_classify").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    expect(classifyStreamError(c.code, c.error, classifier(c.provider))).toBe(c.expected);
  });
});

function sensenovaFree(c: { plan?: string; model?: unknown }): boolean {
  const plan = String(c.plan ?? "").trim().toLowerCase().replace(/_/g, "-").replace(/ /g, "-");
  if (plan !== (providerSpec("sensenova").freeRule as { value: string }).value) return false;
  if (!isRecord(c.model)) return true;
  return typeof c.model.pricing === "string" && c.model.pricing.trim() === "0";
}

function bailianFree(c: { guard?: string; models?: unknown; model?: unknown }): boolean {
  const guard = String(c.guard ?? "").trim().toLowerCase();
  if (guard !== (providerSpec("bailian").freeRule as { guardValue: string }).guardValue) return false;
  const model = isRecord(c.model) ? c.model : {};
  const id = typeof model.id === "string" ? model.id : null;
  return id !== null && Array.isArray(c.models) && c.models.includes(id);
}

describe("free_rule", () => {
  type Case = { name: string; provider: string; plan?: string; guard?: string; models?: unknown; model?: unknown; expected: boolean };
  it.each(load<Case>("free_rule").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    if (c.provider === "openrouter") expect(isFreeModel(c.model)).toBe(c.expected);
    else if (c.provider === "sensenova") expect(sensenovaFree(c)).toBe(c.expected);
    else if (c.provider === "bailian") expect(bailianFree(c)).toBe(c.expected);
    else throw new Error(`no free-rule runner for ${c.provider}`);
  });
});

describe("rate_limit", () => {
  type Case = {
    name: string;
    provider: "openrouter" | "groq";
    headers: Record<string, string>;
    expected: { retryAfterS: number | null; remaining: number | null };
  };
  it.each(load<Case>("rate_limit").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    const [retryAfter, remaining] =
      c.provider === "openrouter" ? openRouterRateLimitHints(c.headers) : groqRateLimitHints(c.headers);
    if (c.expected.retryAfterS === null) expect(retryAfter).toBeNull();
    else expect(retryAfter).toBeCloseTo(c.expected.retryAfterS, 6);
    expect(remaining).toBe(c.expected.remaining);
  });
});

describe("score", () => {
  type RawModel = { id: string; context_length?: number; supports_tools?: boolean; expiration_date?: string | null };
  type RawTest = { ok: boolean; ttft_ms?: number; failure_kind?: string; capacity_streak?: number; error?: string; status_code?: number } | null;
  type Case = { name: string; model: RawModel; test: RawTest; expected: { score: number; reasons: string[] } };
  const file = load<Case>("score");
  const today = file.today as string;

  const toModel = (raw: RawModel): CatalogModel => ({
    provider: "openrouter",
    id: raw.id,
    name: raw.id,
    contextLength: raw.context_length ?? 0,
    tools: raw.supports_tools ?? false,
    input: ["text"],
    maxTokens: null,
    expirationDate: raw.expiration_date ?? null,
    capabilities: { tools: raw.supports_tools ?? false, vision: null, reasoning: null, source: "catalog" },
    quota: null,
    tier: 1,
  });
  const toTest = (model: CatalogModel, raw: RawTest): ProbeResult | null =>
    raw === null
      ? null
      : {
          key: modelKey(model),
          ok: raw.ok,
          ttftMs: raw.ttft_ms ?? null,
          totalMs: null,
          error: raw.error ?? null,
          statusCode: raw.status_code ?? null,
          testedAt: 0,
          failureKind: (raw.failure_kind ?? null) as ProbeResult["failureKind"],
          ...(raw.capacity_streak === undefined ? {} : { capacityStreak: raw.capacity_streak }),
          retryAfterS: null,
          rateLimitRemaining: null,
        };

  it.each(file.cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    const model = toModel(c.model);
    const [score, reasons] = scoreModel(model, toTest(model, c.test), defaultWeights(), today);
    expect(score).toBeCloseTo(c.expected.score, 6);
    expect(reasons).toEqual(c.expected.reasons);
  });

  it("ranks the cases in rankOrder", () => {
    const models = file.cases.map((c) => toModel(c.model));
    const results: Record<string, ProbeResult> = {};
    file.cases.forEach((c, i) => {
      const result = toTest(models[i] as CatalogModel, c.test);
      if (result !== null) results[result.key] = result;
    });
    expect(rank(models, results, defaultWeights(), today).map((r) => r.model.id)).toEqual(file.rankOrder);
  });
});

describe("capacity", () => {
  type ClassifyCase = {
    name: string;
    kind: "classify";
    provider: string;
    status: number;
    error: unknown;
    expected: string;
  };
  type ScoreCase = {
    name: string;
    kind: "score";
    model: { id: string; context_length?: number; supports_tools?: boolean };
    test: { ok: boolean; failure_kind?: string; capacity_streak?: number; error?: string; status_code?: number };
    expected: { score: number; reasons: string[] };
  };
  type Case = ClassifyCase | ScoreCase;
  const file = load<Case>("capacity");
  const threshold = (rankingSpec.capacity as { downgradeAfter: number }).downgradeAfter;

  const toModel = (raw: ScoreCase["model"]): CatalogModel => ({
    provider: "openrouter",
    id: raw.id,
    name: raw.id,
    contextLength: raw.context_length ?? 0,
    tools: raw.supports_tools ?? false,
    input: ["text"],
    maxTokens: null,
    expirationDate: null,
    capabilities: { tools: raw.supports_tools ?? false, vision: null, reasoning: null, source: "catalog" },
    quota: null,
    tier: 1,
  });

  it.each(file.cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    if (c.kind === "classify") {
      const error = isRecord(c.error) ? c.error : {};
      expect(classifier(c.provider)(c.status, error)).toBe(c.expected);
      return;
    }
    const model = toModel(c.model);
    const test: ProbeResult = {
      key: modelKey(model),
      ok: c.test.ok,
      ttftMs: null,
      totalMs: null,
      error: c.test.error ?? null,
      statusCode: c.test.status_code ?? null,
      testedAt: 0,
      failureKind: (c.test.failure_kind ?? null) as ProbeResult["failureKind"],
      ...(c.test.capacity_streak === undefined ? {} : { capacityStreak: c.test.capacity_streak }),
      retryAfterS: null,
      rateLimitRemaining: null,
    };
    const [score, reasons] = scoreModel(model, test, defaultWeights(), file.today as string, threshold);
    expect(score).toBeCloseTo(c.expected.score, 6);
    expect(reasons).toEqual(c.expected.reasons);
  });
});

describe("capabilities", () => {
  type Case = { name: string; input: unknown; supportsTools?: unknown; expected: ReturnType<typeof parseCapabilities> };
  it.each(load<Case>("capabilities").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    expect(parseCapabilities(c.input, c.supportsTools)).toEqual(c.expected);
  });
});

describe("quota", () => {
  type Case = {
    name: string;
    input: unknown;
    expected: {
      unit: string;
      period: string;
      window_seconds: number | null;
      remaining_window: number | null;
      remaining_today: number | null;
      remaining_total: number | null;
      is_exhausted: boolean;
    };
  };
  it.each(load<Case>("quota").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    const quota = parseQuota(c.input);
    expect({
      unit: quota?.unit ?? "unknown",
      period: quota?.period ?? "unknown",
      window_seconds: quota === null ? null : QUOTA_PERIOD_SECONDS[quota.period],
      remaining_window: quota === null ? null : remainingInWindow(quota, quota.probesSinceRead),
      remaining_today:
        quota === null || quota.period !== "day" ? null : remainingInWindow(quota, quota.probesSinceRead),
      remaining_total: quota === null ? null : remainingTotal(quota),
      is_exhausted: quota === null ? false : isExhausted(quota, quota.probesSinceRead),
    }).toEqual(c.expected);
  });
});

describe("non_chat", () => {
  type Case = { id: string; name: string; expected: boolean };
  it.each(load<Case>("non_chat").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    expect(isNonChat({ id: c.id, name: c.name })).toBe(c.expected);
  });
});

describe("key patterns", () => {
  const samples: Record<string, string> = {
    "sk-or-": `sk-or-v1-${"0123456789abcdef".repeat(4)}`,
    gsk_: `gsk_${"Ab1".repeat(18)}`,
    "sk-": `sk-${"A1b2C3d4".repeat(4)}`,
    "sk-ws-": `sk-ws-${"A1b2C3d4".repeat(14)}`,
  };
  it("every spec key pattern matches its sample and is redacted", () => {
    for (const id of CHANNEL_IDS) {
      for (const pattern of providerSpec(id).keyPatterns as Array<{ prefix: string; regex: string }>) {
        const sample = samples[pattern.prefix] as string;
        expect(new RegExp(pattern.regex).test(sample), `${id} ${pattern.prefix}`).toBe(true);
        const out = redact(`key=${sample} end`);
        expect(out).not.toContain(sample);
        expect(out).toContain(pattern.prefix);
      }
    }
  });
});

describe("manual", () => {
  type Case =
    | { name: string; kind: "entry"; input: Record<string, unknown>; expected: { ok: boolean } }
    | { name: string; kind: "expiry"; expiresAt: string | null; expected: boolean }
    | {
        name: string;
        kind: "probe";
        enabled: boolean;
        entry: Record<string, unknown>;
        now: string;
        probes: ManualProbeRecord[];
        expected: { allowed: boolean; reason: string | null };
      };
  const file = load<Case>("manual");
  const today = file.today as string;

  it.each(file.cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    if (c.kind === "entry") {
      let ok = true;
      try {
        validateManualEntry(c.input);
      } catch {
        ok = false;
      }
      expect(ok).toBe(c.expected.ok);
      return;
    }
    if (c.kind === "expiry") {
      expect(entryExpired(c.expiresAt ?? "", today)).toBe(c.expected);
      return;
    }
    const decision = manualProbeDecision(
      {
        dshProvider: String(c.entry.dshProvider),
        model: String(c.entry.model),
        probe: c.entry.probe === true,
        expiresAt: typeof c.entry.expiresAt === "string" ? c.entry.expiresAt : "",
      },
      c.probes,
      c.enabled,
      new Date(c.now),
    );
    expect(decision).toEqual(c.expected);
  });
});
