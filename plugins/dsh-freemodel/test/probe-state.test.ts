import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runProbeRound } from "../src/probe.ts";
import { OpenRouterChannel } from "../src/providers/openrouter.ts";
import type { ProbeResult } from "../src/providers/types.ts";
import { addRequests, emptyChannel, emptyState, freshResult, loadState, parseState, requestsToday, saveState } from "../src/state.ts";
import { fakeFetch, json, model, OR_KEY, sse, token } from "./helpers/fake-fetch.ts";

const NOW_S = Date.UTC(2026, 9, 27, 12) / 1000;
const opts = (extra: Partial<Parameters<typeof runProbeRound>[3]> = {}) => ({
  apiKey: OR_KEY,
  maxTests: 5,
  cacheTtlS: 12 * 3600,
  transientTtlS: 1800,
  dailyBudget: null,
  remainingBudget: null,
  reserve: 10,
  timeoutS: 5,
  nowS: () => NOW_S,
  ...extra,
});
const ok = (key: string, testedAt = NOW_S): ProbeResult => ({
  key,
  ok: true,
  ttftMs: 300,
  totalMs: 400,
  error: null,
  statusCode: 200,
  testedAt,
  failureKind: null,
  retryAfterS: null,
  rateLimitRemaining: null,
});

describe("probe round", () => {
  it("reuses fresh results, probes up to maxTests, and counts requests", async () => {
    const fetch = fakeFetch(() => sse([token("hi"), "[DONE]"]));
    const state = emptyChannel();
    state.results["openrouter|m0"] = ok("openrouter|m0");
    const models = ["m0", "m1", "m2", "m3"].map((id) => model(id));
    const round = await runProbeRound(new OpenRouterChannel(fetch), models, state, opts({ maxTests: 2 }));
    expect(round.probes).toBe(2);
    expect([...round.results.keys()]).toEqual(["openrouter|m0", "openrouter|m1", "openrouter|m2"]);
    expect(fetch.calls).toHaveLength(2);
    expect(requestsToday(state, NOW_S * 1000)).toBe(2);
    expect(round.stopReason).toBeNull();
  });

  it("keeps the reserve out of the daily budget", async () => {
    const fetch = fakeFetch(() => sse([token("hi")]));
    const state = emptyChannel();
    addRequests(state, 38, NOW_S * 1000);
    const round = await runProbeRound(new OpenRouterChannel(fetch), [model("a"), model("b"), model("c")], state, opts({ dailyBudget: 50 }));
    expect(round.probes).toBe(2);
    expect(round.stopReason).toBe("daily free-request budget reached (keeping 10 in reserve)");
  });

  it("prefers the remaining count the channel reports", async () => {
    const fetch = fakeFetch(() => sse([token("hi")]));
    const round = await runProbeRound(new OpenRouterChannel(fetch), [model("a"), model("b")], emptyChannel(), opts({ remainingBudget: 10, dailyBudget: 1000 }));
    expect(round.probes).toBe(0);
    expect(fetch.calls).toHaveLength(0);
  });

  it("stops on an account failure without caching it, and blocks until Retry-After", async () => {
    const fetch = fakeFetch(() => json({ error: { message: `bad key ${OR_KEY}` } }, 401, { "retry-after": "120" }));
    const state = emptyChannel();
    const round = await runProbeRound(new OpenRouterChannel(fetch), [model("a"), model("b")], state, opts());
    expect(round.probes).toBe(1);
    expect(round.accountError?.failureKind).toBe("account");
    expect(round.stopReason).toMatch(/^account\/quota error \(401\)/);
    expect(round.stopReason).not.toContain(OR_KEY);
    expect(state.results).toEqual({});
    expect(state.blockedUntil).toBe(NOW_S + 120);
    const again = await runProbeRound(new OpenRouterChannel(fetch), [model("a")], state, opts());
    expect(again.probes).toBe(0);
    expect(again.rateLimited).toBe(true);
  });

  it("stops when the rate limit is nearly exhausted", async () => {
    const fetch = fakeFetch(() => sse([token("hi")], { "x-ratelimit-remaining": "3" }));
    const round = await runProbeRound(new OpenRouterChannel(fetch), [model("a"), model("b")], emptyChannel(), opts());
    expect(round.probes).toBe(1);
    expect(round.stopReason).toContain("X-RateLimit-Remaining=3");
  });

  it("redacts the key from stored errors", async () => {
    const fetch = fakeFetch(() => json({ error: { message: `model gone for ${OR_KEY}` } }, 404));
    const state = emptyChannel();
    await runProbeRound(new OpenRouterChannel(fetch), [model("a")], state, opts());
    expect(state.results["openrouter|a"]?.error).not.toContain(OR_KEY);
    expect(state.results["openrouter|a"]?.error).toBe("model gone for <redacted>");
  });
});

describe("state", () => {
  it("round-trips through an owner-only file", () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-state-"));
    const path = join(dir, "freemodel", "state.json");
    const state = emptyState();
    state.channels.openrouter.catalog = { fetchedAt: NOW_S, models: [model("a")], error: null, errorAt: null };
    state.channels.openrouter.results["openrouter|a"] = ok("openrouter|a");
    addRequests(state.channels.openrouter, 3, NOW_S * 1000);
    saveState(path, state);
    if (process.platform !== "win32") {
      expect(statSync(path).mode & 0o777).toBe(0o600);
      expect(statSync(join(dir, "freemodel")).mode & 0o777).toBe(0o700);
    }
    const back = loadState(path);
    expect(back.channels.openrouter).toEqual(state.channels.openrouter);
    expect(JSON.parse(readFileSync(path, "utf8")).plugin).toBe("dsh-freemodel");
  });

  it("reads spec/state.example.json (the schema's sample) without losing anything", () => {
    const example = JSON.parse(readFileSync(new URL("../../../spec/state.example.json", import.meta.url), "utf8"));
    expect(parseState(JSON.stringify(example))).toEqual(example);
  });

  it("writes exactly the fields the schema allows", () => {
    const schema = JSON.parse(readFileSync(new URL("../../../spec/state.schema.json", import.meta.url), "utf8"));
    const state = emptyState();
    state.channels.openrouter.results["openrouter|a"] = ok("openrouter|a");
    state.channels.openrouter.catalog = { fetchedAt: 1, models: [model("a")], error: null, errorAt: null };
    state.channels.openrouter.lastRound = { at: 1, probes: 1, stopReason: null };
    expect(Object.keys(state).sort()).toEqual(Object.keys(schema.properties).sort());
    const channel = schema.$defs.channel;
    expect(Object.keys(state.channels.openrouter).sort()).toEqual(Object.keys(channel.properties).sort());
    expect(Object.keys(state.channels.openrouter.results["openrouter|a"] as object).sort()).toEqual(schema.$defs.result.required.slice().sort());
    expect(Object.keys(model("a")).sort()).toEqual(schema.$defs.model.required.slice().sort());
  });

  it("treats missing, corrupt or foreign files as empty and drops account failures", () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-state-"));
    expect(loadState(join(dir, "none.json"))).toMatchObject({ schemaVersion: 1 });
    writeFileSync(join(dir, "bad.json"), "{nope");
    expect(loadState(join(dir, "bad.json")).channels.groq.results).toEqual({});
    expect(parseState(JSON.stringify({ schemaVersion: 9, channels: {} })).channels.openrouter.catalog).toBeNull();
    const withAccount = emptyState();
    withAccount.channels.openrouter.results["openrouter|x"] = { ...ok("openrouter|x"), ok: false, failureKind: "account" };
    expect(parseState(JSON.stringify(withAccount)).channels.openrouter.results).toEqual({});
  });

  it("expires results like Python's cache: transient sooner, account never trusted", () => {
    const channel = emptyChannel();
    channel.results.a = ok("a", NOW_S - 3600);
    channel.results.t = { ...ok("t", NOW_S - 3600), ok: false, failureKind: "transient" };
    channel.results.c = { ...ok("c", NOW_S), ok: false, failureKind: "account" };
    expect(freshResult(channel, "a", 7200, 1800, NOW_S)).not.toBeNull();
    expect(freshResult(channel, "a", 1800, 1800, NOW_S)).toBeNull();
    expect(freshResult(channel, "t", 7200, 1800, NOW_S)).toBeNull();
    expect(freshResult(channel, "c", 7200, 1800, NOW_S)).toBeNull();
  });

  it("resets the daily counter on a new UTC day", () => {
    const channel = emptyChannel();
    addRequests(channel, 5, NOW_S * 1000);
    expect(requestsToday(channel, NOW_S * 1000)).toBe(5);
    expect(requestsToday(channel, (NOW_S + 86400) * 1000)).toBe(0);
  });
});
