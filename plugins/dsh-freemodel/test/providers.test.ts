import { describe, expect, it, vi } from "vitest";
import { GroqChannel, parseDuration } from "../src/providers/groq.ts";
import { pricingIsZero, SenseNovaChannel, senseNovaCapabilities } from "../src/providers/sensenova.ts";
import { OpenRouterChannel, parseExpirationDate } from "../src/providers/openrouter.ts";
import { ChannelError } from "../src/providers/types.ts";
import { fakeFetch, GROQ_KEY, json, model, OR_KEY, SENSENOVA_KEY, sse, token } from "./helpers/fake-fetch.ts";

const freeText = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  name: `Name ${id}`,
  context_length: 131072,
  pricing: { prompt: "0", completion: "0" },
  architecture: { input_modalities: ["text"], output_modalities: ["text"] },
  supported_parameters: ["tools", "max_tokens"],
  top_provider: { max_completion_tokens: 4096 },
  ...extra,
});

describe("OpenRouter catalogue", () => {
  it("keeps free text models, reads tools, max tokens, image input and expiry, and sends no key", async () => {
    const fetch = fakeFetch(() =>
      json({
        data: [
          freeText("a/one:free"),
          freeText("a/paid", { pricing: { prompt: "0.000001", completion: "0" } }),
          freeText("a/vision:free", {
            architecture: { input_modalities: ["text", "image"], output_modalities: ["text"] },
            supported_parameters: [],
            top_provider: {},
            expiration_date: "2026-11-30",
          }),
          "junk",
        ],
      }),
    );
    const models = await new OpenRouterChannel(fetch).discover(OR_KEY);
    expect(models).toEqual([
      {
        provider: "openrouter",
        id: "a/one:free",
        name: "Name a/one:free",
        contextLength: 131072,
        tools: true,
        input: ["text"],
        maxTokens: 4096,
        expirationDate: null,
        capabilities: { tools: true, vision: false, reasoning: false, source: "catalog" },
        quota: null,
        tier: 1,
      },
      {
        provider: "openrouter",
        id: "a/vision:free",
        name: "Name a/vision:free",
        contextLength: 131072,
        tools: false,
        input: ["text", "image"],
        maxTokens: null,
        expirationDate: "2026-11-30",
        capabilities: { tools: false, vision: true, reasoning: false, source: "catalog" },
        quota: null,
        tier: 1,
      },
    ]);
    expect(fetch.calls[0]?.url).toBe("https://openrouter.ai/api/v1/models");
    expect(JSON.stringify(fetch.calls[0]?.init?.headers ?? {})).not.toContain(OR_KEY);
  });

  it("turns HTTP and payload problems into a key-free ChannelError", async () => {
    await expect(new OpenRouterChannel(fakeFetch(() => json({}, 503))).discover(OR_KEY)).rejects.toThrow(
      new ChannelError("OpenRouter model discovery failed: HTTP 503"),
    );
    await expect(new OpenRouterChannel(fakeFetch(() => json({ nope: 1 }))).discover(OR_KEY)).rejects.toThrow(
      /unexpected models payload/,
    );
  });

  it("reads the daily free-request quota from /key, and null when it is unavailable", async () => {
    const fetch = fakeFetch(() => json({ data: { free_model_daily_requests: { limit: 1000, used: 3, remaining: 997 } } }));
    expect(await new OpenRouterChannel(fetch).quota(OR_KEY)).toEqual({
      dailyFreeLimit: 1000,
      dailyFreeUsed: 3,
      dailyFreeRemaining: 997,
    });
    expect(fetch.calls[0]?.url).toBe("https://openrouter.ai/api/v1/key");
    expect(new Headers(fetch.calls[0]?.init?.headers).get("authorization")).toBe(`Bearer ${OR_KEY}`);
    expect(await new OpenRouterChannel(fakeFetch(() => json({}, 401))).quota(OR_KEY)).toBeNull();
    expect(await new OpenRouterChannel(fakeFetch(() => json({ data: {} }))).quota(OR_KEY)).toEqual({
      dailyFreeLimit: null,
      dailyFreeUsed: null,
      dailyFreeRemaining: null,
    });
  });

  it("parses expiration dates like Python", () => {
    expect(parseExpirationDate("2026-11-30")).toBe("2026-11-30");
    expect(parseExpirationDate("2026-11-30T12:00:00Z")).toBe("2026-11-30");
    expect(parseExpirationDate("soon")).toBeNull();
    expect(parseExpirationDate(null)).toBeNull();
  });
});

describe("Groq catalogue", () => {
  it("needs the key, skips inactive models, and leaves tool support unknown", async () => {
    const fetch = fakeFetch(() =>
      json({
        data: [
          { id: "llama-3.3-70b-versatile", context_window: 131072, max_completion_tokens: 32768, active: true },
          { id: "old", context_window: 8192, active: false },
          { id: "" },
        ],
      }),
    );
    const models = await new GroqChannel(fetch).discover(GROQ_KEY);
    expect(models).toEqual([
      {
        provider: "groq",
        id: "llama-3.3-70b-versatile",
        name: "llama-3.3-70b-versatile",
        contextLength: 131072,
        tools: null,
        input: ["text"],
        maxTokens: 32768,
        expirationDate: null,
        capabilities: { tools: null, vision: null, reasoning: null, source: "unknown" },
        quota: null,
        tier: 1,
      },
    ]);
    expect(fetch.calls[0]?.url).toBe("https://api.groq.com/openai/v1/models");
    await expect(new GroqChannel(fetch).discover(undefined)).rejects.toThrow(/needs GROQ_API_KEY/);
    await expect(new GroqChannel(fakeFetch(() => json({}, 401))).discover(GROQ_KEY)).rejects.toThrow(
      "Groq model list failed: HTTP 401",
    );
  });

  it("parses Groq durations", () => {
    expect(parseDuration("1m30s")).toBe(90);
    expect(parseDuration("250ms")).toBeCloseTo(0.25, 9);
    expect(parseDuration("")).toBeNull();
  });
});

describe("streaming probe", () => {
  const m = model("a/one:free");

  it("succeeds on a first token and sends a tiny streaming request", async () => {
    const fetch = fakeFetch(() => sse([token("Hi"), token("", "stop"), "[DONE]"], { "x-ratelimit-remaining": "41" }));
    const result = await new OpenRouterChannel(fetch).probe(m, OR_KEY, { timeoutS: 5 });
    expect(result).toMatchObject({ key: "openrouter|a/one:free", ok: true, error: null, failureKind: null, statusCode: 200 });
    expect(result.rateLimitRemaining).toBe(41);
    expect(result.ttftMs).toBeGreaterThanOrEqual(0);
    const call = fetch.calls[0];
    expect(call?.url).toBe("https://openrouter.ai/api/v1/chat/completions");
    const body = JSON.parse(String(call?.init?.body));
    expect(body).toMatchObject({ model: "a/one:free", stream: true });
    expect(body.max_tokens).toBeGreaterThan(0);
    expect(new Headers(call?.init?.headers).get("x-title")).toBe("dsh-freemodel");
  });

  it("uses max_completion_tokens on Groq", async () => {
    const fetch = fakeFetch(() => sse([token("x"), "[DONE]"]));
    await new GroqChannel(fetch).probe({ ...m, provider: "groq" }, GROQ_KEY);
    const body = JSON.parse(String(fetch.calls[0]?.init?.body));
    expect(body.max_completion_tokens).toBeGreaterThan(0);
    expect(body.max_tokens).toBeUndefined();
  });

  it("counts a clean finish with [DONE] and no text as success, and an empty stream as a model failure", async () => {
    const done = await new OpenRouterChannel(fakeFetch(() => sse([token("", "length"), "[DONE]"]))).probe(m, OR_KEY);
    expect(done.ok).toBe(true);
    const empty = await new OpenRouterChannel(fakeFetch(() => sse([]))).probe(m, OR_KEY);
    expect(empty).toMatchObject({ ok: false, failureKind: "model", error: "empty response" });
  });

  it("classifies HTTP errors with the channel's error map and reads Retry-After", async () => {
    const limited = await new OpenRouterChannel(
      fakeFetch(() => json({ error: { message: "Rate limit exceeded: free-models-per-day" } }, 429, { "retry-after": "60" })),
    ).probe(m, OR_KEY);
    expect(limited).toMatchObject({ ok: false, statusCode: 429, retryAfterS: 60 });
    expect(limited.error).toContain("Rate limit exceeded");
    const auth = await new OpenRouterChannel(fakeFetch(() => json({ error: { message: "No auth" } }, 401))).probe(m, OR_KEY);
    expect(auth).toMatchObject({ ok: false, failureKind: "account", error: "No auth" });
    const gone = await new GroqChannel(fakeFetch(() => new Response("", { status: 404 }))).probe(m, GROQ_KEY);
    expect(gone).toMatchObject({ ok: false, failureKind: "model", error: "HTTP 404" });
  });

  it("classifies a mid-stream error object and finish_reason error", async () => {
    const midStream = await new OpenRouterChannel(
      fakeFetch(() => sse([{ error: { code: 502, message: "Provider returned error" } }])),
    ).probe(m, OR_KEY);
    expect(midStream).toMatchObject({ ok: false, failureKind: "transient", error: "Provider returned error" });
    const finishError = await new OpenRouterChannel(fakeFetch(() => sse([token("", "error")]))).probe(m, OR_KEY);
    expect(finishError).toMatchObject({ ok: false, failureKind: "transient" });
    const filtered = await new OpenRouterChannel(fakeFetch(() => sse([token("", "content_filter")]))).probe(m, OR_KEY);
    expect(filtered).toMatchObject({ ok: false, failureKind: "model" });
  });

  it("treats network errors and a silent upstream as transient", async () => {
    const network = await new OpenRouterChannel(
      fakeFetch(() => {
        throw new TypeError("fetch failed");
      }),
    ).probe(m, OR_KEY);
    expect(network).toMatchObject({ ok: false, failureKind: "transient", error: "TypeError: fetch failed" });

    const silent = await new OpenRouterChannel(
      fakeFetch(
        (_url, init) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    ).probe(m, OR_KEY, { timeoutS: 0.05 });
    expect(silent).toMatchObject({ ok: false, failureKind: "transient" });
    expect(silent.error).toMatch(/ReadTimeout|no token/);
  });

  it("does not call out without a key", async () => {
    const fetch = fakeFetch(() => sse([token("x")]));
    expect(await new OpenRouterChannel(fetch).probe(m, undefined)).toMatchObject({ ok: false, failureKind: "account" });
    expect(fetch.calls).toHaveLength(0);
  });

  it("splits CRLF and bare-CR event streams", async () => {
    const body = `data: ${JSON.stringify(token("a"))}\r\n\r\ndata: [DONE]\r`;
    const result = await new OpenRouterChannel(fakeFetch(() => new Response(body, { status: 200 }))).probe(m, OR_KEY);
    expect(result.ok).toBe(true);
  });
});


describe("SenseNova catalogue", () => {
  const sn = (id: string, extra: Record<string, unknown> = {}) => ({
    id,
    pricing: "0",
    context_length: 262144,
    supported_features: ["text", "image"],
    ...extra,
  });

  it("intersects the allowlist, drops non-zero pricing, and reads capabilities", async () => {
    const warn = vi.fn();
    const fetch = fakeFetch(() =>
      json({
        data: [
          sn("deepseek-v4-flash", { supported_features: ["text", "function_call"] }),
          sn("sensenova-6.8-flash-lite", { businesses: ["vision"] }),
          sn("sensenova-6.8-pro", { pricing: "0.02" }),
          sn("not-in-the-allowlist"),
          "junk",
        ],
      }),
    );
    const models = await new SenseNovaChannel(fetch, { warn }).discover(
      SENSENOVA_KEY,
      undefined,
      ["deepseek-v4-flash", "sensenova-6.8-flash-lite", "sensenova-6.8-pro"],
    );
    expect(models.map((m) => m.id)).toEqual(["deepseek-v4-flash", "sensenova-6.8-flash-lite"]);
    expect(models[0]?.capabilities).toEqual({ tools: true, vision: null, reasoning: null, source: "catalog" });
    expect(models[1]?.capabilities.vision).toBe(true);
    expect(models[1]?.input).toEqual(["text", "image"]);
    expect(models[1]?.contextLength).toBe(262144);
    expect(fetch.calls[0]?.url).toBe("https://token.sensenova.cn/v1/models");
    expect(new Headers(fetch.calls[0]?.init?.headers).get("authorization")).toBe(`Bearer ${SENSENOVA_KEY}`);
    expect(warn.mock.calls.flat().join(" ")).toMatch(/sensenova-6.8-pro.*not the string "0"/);
  });

  it("uses every zero-priced catalogue model when the allowlist is empty", async () => {
    const fetch = fakeFetch(() => json({ data: [sn("a"), sn("b", { pricing: "0.1" }), sn("c", { pricing: 0 })] }));
    expect((await new SenseNovaChannel(fetch).discover(SENSENOVA_KEY, undefined, [])).map((m) => m.id)).toEqual(["a"]);
  });

  it("falls back to a confirmed allowlist when the catalogue is unavailable", async () => {
    const warn = vi.fn();
    const models = await new SenseNovaChannel(fakeFetch(() => json({}, 503)), { warn }).discover(
      SENSENOVA_KEY,
      undefined,
      ["deepseek-v4-flash"],
    );
    expect(models).toHaveLength(1);
    expect(models[0]?.id).toBe("deepseek-v4-flash");
    expect(models[0]?.capabilities.source).toBe("unknown");
    expect(warn).toHaveBeenCalled();
    await expect(new SenseNovaChannel(fakeFetch(() => json({}, 503))).discover(SENSENOVA_KEY, undefined, [])).rejects.toThrow(
      /model list failed: HTTP 503/,
    );
  });

  it("needs the key and reads pricing strictly", async () => {
    await expect(new SenseNovaChannel(fakeFetch(() => json({ data: [] }))).discover(undefined)).rejects.toThrow(/needs SENSENOVA_API_KEY/);
    expect(pricingIsZero("0")).toBe(true);
    expect(pricingIsZero(" 0 ")).toBe(true);
    expect(pricingIsZero(0)).toBe(false);
    expect(pricingIsZero("0.00")).toBe(false);
    expect(senseNovaCapabilities(null)).toEqual({ tools: null, vision: null, reasoning: null, source: "unknown" });
    expect(senseNovaCapabilities({ supported_features: ["reasoning"] }).reasoning).toBe(true);
  });

  it("classifies 403 as a model failure and 401 as an account failure", async () => {
    const m = model("deepseek-v4-flash", { provider: "sensenova" });
    const forbidden = await new SenseNovaChannel(
      fakeFetch(() => json({ error: { message: "model not in plan" } }, 403)),
    ).probe(m, SENSENOVA_KEY);
    expect(forbidden).toMatchObject({ ok: false, statusCode: 403, failureKind: "model" });
    const auth = await new SenseNovaChannel(fakeFetch(() => json({ error: { message: "bad key" } }, 401))).probe(m, SENSENOVA_KEY);
    expect(auth).toMatchObject({ ok: false, statusCode: 401, failureKind: "account" });
  });

  it("probes with max_tokens", async () => {
    const fetch = fakeFetch(() => sse([token("ok"), "[DONE]"]));
    const result = await new SenseNovaChannel(fetch).probe(model("deepseek-v4-flash", { provider: "sensenova" }), SENSENOVA_KEY);
    expect(result.ok).toBe(true);
    const body = JSON.parse(String(fetch.calls[0]?.init?.body));
    expect(body.max_tokens).toBeGreaterThan(0);
    expect(body.max_completion_tokens).toBeUndefined();
  });
});
