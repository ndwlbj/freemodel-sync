import { describe, expect, it } from "vitest";
import { GroqChannel, parseDuration } from "../src/providers/groq.ts";
import { OpenRouterChannel, parseExpirationDate } from "../src/providers/openrouter.ts";
import { ChannelError } from "../src/providers/types.ts";
import { fakeFetch, GROQ_KEY, json, model, OR_KEY, sse, token } from "./helpers/fake-fetch.ts";

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
