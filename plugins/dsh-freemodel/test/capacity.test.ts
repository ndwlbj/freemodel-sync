/** capacity: classification, short TTL, separate counter, ranking penalty and downgrade. */
import { describe, expect, it } from "vitest";
import { classifierFor } from "../src/classify.ts";
import { nextUtcMidnight, runProbeRound } from "../src/probe.ts";
import { BailianChannel } from "../src/providers/bailian.ts";
import { type CatalogModel, modelKey, type ProbeResult } from "../src/providers/types.ts";
import { defaultWeights, rank, scoreModel } from "../src/rank.ts";
import { rankingSpec } from "../src/spec.ts";
import { emptyChannel, freshResult, parseState } from "../src/state.ts";
import { fakeFetch, json, model } from "./helpers/fake-fetch.ts";

const NOW_S = Date.UTC(2026, 9, 27, 12) / 1000;
const CACHE_NOW = Math.floor(Date.now() / 1000);
const threshold = (rankingSpec.capacity as { downgradeAfter: number }).downgradeAfter;

const busy = (key = "bailian|busy", streak = 1): ProbeResult => ({
  key,
  ok: false,
  ttftMs: null,
  totalMs: 10,
  error: "queued",
  statusCode: 429,
  testedAt: NOW_S,
  failureKind: "capacity",
  capacityStreak: streak,
  retryAfterS: null,
  rateLimitRemaining: null,
});

const catalog = (id = "busy"): CatalogModel => ({ ...model(id), provider: "bailian" });

describe("capacity classification", () => {
  it("maps queue / no-capacity codes to capacity, leaves bare 429 and 5xx transient", () => {
    const classify = classifierFor("bailian");
    expect(classify(429, { code: "ModelUnavailable" })).toBe("capacity");
    expect(classify(400, { code: "ModelBusy" })).toBe("capacity");
    expect(classify(429, {})).toBe("transient");
    expect(classify(503, { code: "ModelUnavailable" })).toBe("transient");
  });
});

describe("capacity cache and streak", () => {
  it("uses the short TTL and counts capacity separately from transient", async () => {
    const fetch = fakeFetch(() => json({ error: { code: "ModelBusy", message: "queued" } }, 400));
    const channel = new BailianChannel(fetch);
    const state = emptyChannel();
    const m = catalog();
    const opts = {
      apiKey: "sk-test",
      maxTests: 5,
      cacheTtlS: 12 * 3600,
      transientTtlS: 1800,
      dailyBudget: null,
      remainingBudget: null,
      reserve: 10,
      nowS: () => CACHE_NOW,
    };
    const first = await runProbeRound(channel, [m], state, opts);
    expect(first.results.get(modelKey(m))?.capacityStreak).toBe(1);
    const second = await runProbeRound(channel, [m], state, {
      ...opts,
      cacheTtlS: 0,
      transientTtlS: 0,
      nowS: () => CACHE_NOW + 1,
    });
    expect(second.results.get(modelKey(m))?.capacityStreak).toBe(2);

    const transient = busy("bailian|t", 2);
    const { capacityStreak: _ignored, ...transientBase } = transient;
    state.results["bailian|t"] = { ...transientBase, failureKind: "transient", testedAt: CACHE_NOW };
    state.results["bailian|c"] = { ...busy("bailian|c", 2), testedAt: CACHE_NOW };
    expect(freshResult(state, "bailian|t", 7200, 1800, CACHE_NOW + 3600)).toBeNull();
    expect(freshResult(state, "bailian|c", 7200, 1800, CACHE_NOW + 3600)).toBeNull();
    expect(freshResult(state, "bailian|c", 7200, 7200, CACHE_NOW + 3600)).not.toBeNull();
  });

  it("round-trips capacityStreak and drops quota results from the state file", () => {
    const state = emptyChannel();
    state.results["bailian|busy"] = busy();
    state.results["bailian|quota"] = { ...busy("bailian|quota"), failureKind: "quota" };
    const parsed = parseState(
      JSON.stringify({
        schemaVersion: 1,
        plugin: "dsh-freemodel",
        updatedAt: "2026-10-27T12:00:00.000Z",
        channels: { bailian: state },
      }),
    );
    expect(parsed.channels.bailian.results["bailian|busy"]?.capacityStreak).toBe(1);
    expect(parsed.channels.bailian.results["bailian|quota"]).toBeUndefined();
  });
});

describe("capacity ranking", () => {
  it("penalises, then downgrades after N in a row", () => {
    const m = catalog();
    const [score1, reasons1] = scoreModel(m, busy(modelKey(m), 1), defaultWeights(), "2026-10-27", threshold);
    expect(score1).toBeCloseTo(-defaultWeights().capacity_penalty, 6);
    expect(reasons1).toEqual(["no capacity: queued (1/3 in a row, retried later)"]);

    const [scoreN, reasonsN] = scoreModel(m, busy(modelKey(m), threshold), defaultWeights(), "2026-10-27", threshold);
    expect(scoreN).toBe((rankingSpec.score as { failedScore: number }).failedScore);
    expect(reasonsN).toEqual([`no capacity ${threshold} times in a row: queued (downgraded)`]);
  });

  it("ranks below untested but above a hard failure", () => {
    const untested = catalog("a-untested");
    const capacity = catalog("b-busy");
    const dead = catalog("c-dead");
    const deadFailure = busy(modelKey(dead), 1);
    const { capacityStreak: _ignored, ...deadBase } = deadFailure;
    const results: Record<string, ProbeResult> = {
      [modelKey(capacity)]: busy(modelKey(capacity), 1),
      [modelKey(dead)]: { ...deadBase, failureKind: "model" },
    };
    expect(rank([capacity, dead, untested], results).map((r) => r.model.id)).toEqual([
      "a-untested",
      "b-busy",
      "c-dead",
    ]);
  });

  it("has a next UTC midnight helper for a daily quota stop", () => {
    const midnight = nextUtcMidnight(NOW_S);
    expect(new Date(midnight * 1000).toISOString()).toBe("2026-10-28T00:00:00.000Z");
  });
});
