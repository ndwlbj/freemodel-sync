/**
 * Runs the shared golden cases in spec/conformance/ against the plugin, as
 * tests/test_spec_conformance.py does against the Python tool. Both must
 * agree with every case (spec/README.md).
 */
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { type Classifier, classifierFor, classifyStreamError, classifyWith, defaultErrorMap } from "../src/classify.ts";
import { groqRateLimitHints } from "../src/providers/groq.ts";
import { isFreeModel, openRouterRateLimitHints } from "../src/providers/openrouter.ts";
import type { CatalogModel, ProbeResult } from "../src/providers/types.ts";
import { modelKey } from "../src/providers/types.ts";
import { defaultWeights, isNonChat, rank, scoreModel } from "../src/rank.ts";
import { redact } from "../src/redact.ts";
import { CHANNEL_IDS, providerSpec, SpecError } from "../src/spec.ts";

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
const classifier = (provider: string | null): Classifier => classifierFor(provider as "openrouter" | "groq" | null);

describe("conformance files", () => {
  it("every file has a runner here", () => {
    const areas = readdirSync(dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.slice(0, -5))
      .sort();
    expect(areas).toEqual(["classify", "free_rule", "non_chat", "rate_limit", "score", "stream_classify"]);
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

describe("free_rule", () => {
  type Case = { name: string; provider: string; model: unknown; expected: boolean };
  it.each(load<Case>("free_rule").cases.map((c) => [label(c), c] as const))("%s", (_name, c) => {
    expect(c.provider).toBe("openrouter");
    expect(isFreeModel(c.model)).toBe(c.expected);
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
  type RawTest = { ok: boolean; ttft_ms?: number; failure_kind?: string; error?: string; status_code?: number } | null;
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
