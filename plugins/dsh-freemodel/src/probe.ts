/**
 * One probing round for a channel: reuse fresh results, respect the daily
 * free-request budget and the reserve, stop on account/quota failures and on
 * a nearly exhausted rate limit. Capacity results get their own consecutive
 * counter. Port of `freemodel_sync.tester.run_tests`.
 */
import type { OpenAICompatChannel } from "./providers/openai-compat.ts";
import type { CatalogModel, ProbeResult } from "./providers/types.ts";
import { modelKey } from "./providers/types.ts";
import { redact } from "./redact.ts";
import { addRequests, type ChannelStateData, freshResult, requestsToday } from "./state.ts";

/** Daily free requests assumed when the channel reports none (Python's FALLBACK_DAILY_FREE_LIMIT). */
export const FALLBACK_DAILY_FREE_LIMIT = 50;

export interface ProbeRoundOptions {
  apiKey: string;
  maxTests: number;
  cacheTtlS: number;
  transientTtlS: number;
  /** Free requests per UTC day, checked against the local counter. */
  dailyBudget: number | null;
  /** Free requests left today as reported by the channel (wins over dailyBudget). */
  remainingBudget: number | null;
  reserve: number;
  timeoutS?: number;
  signal?: AbortSignal;
  nowS?: () => number;
}

export interface ProbeRound {
  results: Map<string, ProbeResult>;
  probes: number;
  stopReason: string | null;
  accountError: ProbeResult | null;
  /** A quota failure that stopped this channel for the rest of the UTC day. */
  quotaError: ProbeResult | null;
  rateLimited: boolean;
}

function utcMinute(epochS: number): string {
  return `${new Date(epochS * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** Unix seconds of the next UTC midnight (when a daily quota resets). */
export function nextUtcMidnight(nowS: number = Date.now() / 1000): number {
  const day = new Date(nowS * 1000);
  return Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate() + 1) / 1000;
}

/**
 * Probe `models` in order, updating `state` (results, counter, blockedUntil).
 * Error texts are redacted with the key before they are kept.
 */
export async function runProbeRound(
  channel: OpenAICompatChannel,
  models: readonly CatalogModel[],
  state: ChannelStateData,
  options: ProbeRoundOptions,
): Promise<ProbeRound> {
  const nowS = options.nowS ?? (() => Date.now() / 1000);
  const run: ProbeRound = {
    results: new Map(),
    probes: 0,
    stopReason: null,
    accountError: null,
    quotaError: null,
    rateLimited: false,
  };
  if (options.maxTests < 1) run.stopReason = `max_tests is ${options.maxTests}: no probe allowed`;
  let allowed: number | null = null;
  if (options.remainingBudget !== null) allowed = Math.max(0, options.remainingBudget - options.reserve);
  else if (options.dailyBudget !== null) {
    allowed = Math.max(0, options.dailyBudget - options.reserve - requestsToday(state, nowS() * 1000));
  }
  const blocked = state.blockedUntil !== null && state.blockedUntil > nowS();
  if (blocked) {
    run.rateLimited = true;
    run.stopReason = `rate limited until ${utcMinute(state.blockedUntil!)}`;
  }
  for (const model of models) {
    if (options.signal?.aborted) break;
    const key = modelKey(model);
    const cached = freshResult(state, key, options.cacheTtlS, options.transientTtlS, nowS());
    if (cached !== null) {
      run.results.set(key, cached);
      continue;
    }
    if (run.stopReason !== null) continue;
    if (run.probes >= options.maxTests) continue;
    if (allowed !== null && run.probes >= allowed) {
      run.stopReason = `daily free-request budget reached (keeping ${options.reserve} in reserve)`;
      continue;
    }
    let result: ProbeResult;
    try {
      const probeOptions: Parameters<OpenAICompatChannel["probe"]>[2] = {};
      if (options.timeoutS !== undefined) probeOptions.timeoutS = options.timeoutS;
      if (options.signal !== undefined) probeOptions.signal = options.signal;
      result = await channel.probe(model, options.apiKey, probeOptions);
    } catch (error) {
      const e = error as { name?: string; message?: string };
      result = {
        key,
        ok: false,
        ttftMs: null,
        totalMs: null,
        error: `${e?.name ?? "Error"}: ${e?.message ?? String(error)}`,
        statusCode: null,
        testedAt: nowS(),
        failureKind: "transient",
        retryAfterS: null,
        rateLimitRemaining: null,
      };
    }
    if (result.error !== null) result = { ...result, error: redact(result.error, [options.apiKey]) };
    run.probes += 1;
    addRequests(state, 1, nowS() * 1000);
    if (!result.ok && result.failureKind === "quota") {
      run.quotaError = result;
      run.stopReason = `quota exhausted (${result.statusCode ?? "n/a"}): ${result.error}; stopped until the next UTC day`;
      state.blockedUntil = Math.max(state.blockedUntil ?? 0, nextUtcMidnight(nowS()));
      continue;
    }
    if (!result.ok && result.failureKind === "account") {
      run.accountError = result;
      run.stopReason = `account/quota error (${result.statusCode ?? "n/a"}): ${result.error}`;
      if (result.retryAfterS) state.blockedUntil = nowS() + result.retryAfterS;
      continue;
    }
    if (!result.ok && result.failureKind === "capacity") {
      const previous = state.results[key];
      const prior = previous !== undefined && !previous.ok && previous.failureKind === "capacity" ? (previous.capacityStreak ?? 0) : 0;
      result = { ...result, capacityStreak: prior + 1 };
    }
    state.results[key] = result;
    run.results.set(key, result);
    if (result.rateLimitRemaining !== null && result.rateLimitRemaining <= options.reserve) {
      run.stopReason = `provider rate limit nearly exhausted (X-RateLimit-Remaining=${result.rateLimitRemaining})`;
      if (result.retryAfterS) state.blockedUntil = nowS() + result.retryAfterS;
    }
  }
  if (state.blockedUntil !== null && state.blockedUntil <= nowS()) state.blockedUntil = null;
  return run;
}
