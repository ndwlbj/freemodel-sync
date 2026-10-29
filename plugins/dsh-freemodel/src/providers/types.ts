/** Data shapes shared by the channels, the prober, the ranker and the state file. Never hold a key. */
import type { FailureKind } from "../classify.ts";
import type { ChannelId } from "../spec.ts";
import { isRecord } from "../util.ts";

/** Where a capability value came from; `unknown` means nothing reported it. */
export type CapabilitySource = "catalog" | "config" | "probe" | "manual" | "unknown";

/** What a model can do. `null` means the catalogue does not say; it is never false. */
export interface Capabilities {
  tools: boolean | null;
  vision: boolean | null;
  reasoning: boolean | null;
  source: CapabilitySource;
}

export const UNKNOWN_CAPABILITIES: Capabilities = {
  tools: null,
  vision: null,
  reasoning: null,
  source: "unknown",
};

export type QuotaUnit = "requests" | "tokens" | "credits" | "unknown";
export type QuotaPeriod = "rolling_5h" | "week" | "day" | "total" | "beta" | "unknown";
export type QuotaSource = "api" | "headers" | "manual" | "none";
export type QuotaScope = "account" | "model";

/** A provider or model quota; every number can be missing (unknown). */
export interface Quota {
  unit: QuotaUnit;
  period: QuotaPeriod;
  /** Allowance in one window / in total. */
  limit: number | null;
  used: number | null;
  remaining: number | null;
  /** ISO-8601 timestamp with a timezone, when the provider gives one. */
  resetsAt: string | null;
  /** ISO-8601 timestamp after which the free allowance ends. */
  expiresAt: string | null;
  source: QuotaSource;
  scope: QuotaScope;
  /** Probes sent after the counters were read; never persisted, so optional in old state. */
  probesSinceRead?: number;
}

/** Length of a quota window in seconds, when it has a fixed one. */
export const QUOTA_PERIOD_SECONDS: Record<QuotaPeriod, number | null> = {
  rolling_5h: 5 * 3600,
  week: 7 * 24 * 3600,
  day: 24 * 3600,
  total: null,
  beta: null,
  unknown: null,
};

const QUOTA_PERIOD_ALIASES: Record<string, QuotaPeriod> = {
  "5h": "rolling_5h",
  "5_h": "rolling_5h",
  "5-hour": "rolling_5h",
  "5_hour": "rolling_5h",
  "rolling-5h": "rolling_5h",
  rolling5h: "rolling_5h",
  five_hour: "rolling_5h",
  weekly: "week",
  per_week: "week",
  "7d": "week",
  daily: "day",
  per_day: "day",
  once: "total",
  one_time: "total",
  "one-time": "total",
  public_beta: "beta",
  trial: "beta",
};

const QUOTA_UNIT_ALIASES: Record<string, QuotaUnit> = {
  request: "requests",
  req: "requests",
  token: "tokens",
  credit: "credits",
};

/** Read a capability/boolean flag; unknown strings and missing values give `null`. */
export function optionalBool(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === 0 || value === 1) return value === 1;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (["true", "yes", "1", "supported"].includes(text)) return true;
    if (["false", "no", "0", "unsupported"].includes(text)) return false;
  }
  return null;
}

function choice<T extends string>(value: unknown, choices: readonly T[], aliases: Record<string, T>, fallback: T): T {
  if (typeof value !== "string") return fallback;
  const normalized = aliases[value.trim().toLowerCase()] ?? value.trim().toLowerCase();
  return (choices as readonly string[]).includes(normalized) ? (normalized as T) : fallback;
}

/**
 * Read a capability document. Missing fields are unknown (`null`), never false.
 * @param raw - capabilities object from a catalogue or state file.
 * @param supportsTools - legacy `supports_tools` flag, used only when `tools` is absent.
 */
export function parseCapabilities(raw: unknown, supportsTools?: unknown): Capabilities {
  if (!isRecord(raw)) {
    const tools = optionalBool(supportsTools);
    return tools === null
      ? { ...UNKNOWN_CAPABILITIES }
      : { tools, vision: null, reasoning: null, source: "catalog" };
  }
  const toolsMissing = !("tools" in raw);
  const tools = optionalBool(raw.tools) ?? (toolsMissing ? optionalBool(supportsTools) : null);
  const vision = optionalBool(raw.vision);
  const reasoning = optionalBool(raw.reasoning);
  if (tools === null && vision === null && reasoning === null) return { ...UNKNOWN_CAPABILITIES };
  return {
    tools,
    vision,
    reasoning,
    source:
      raw.source === undefined
        ? "catalog"
        : choice(raw.source, ["catalog", "config", "probe", "manual", "unknown"] as const, {}, "unknown"),
  };
}

function optionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function pick(raw: Record<string, unknown>, ...names: string[]): unknown {
  for (const name of names) if (name in raw) return raw[name];
  return undefined;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * Read a quota document in snake_case (spec/Python), camelCase (plugin state)
 * or a legacy daily `QuotaInfo`. Missing or unrecognised values are unknown.
 * @param raw - quota document; `null`/`undefined` means the model has none.
 */
export function parseQuota(raw: unknown): Quota | null {
  if (raw === null || raw === undefined) return null;
  if (!isRecord(raw)) return null;
  let unit = pick(raw, "unit");
  let period = pick(raw, "period");
  const dailyKeys = ["daily_free_limit", "dailyFreeLimit", "daily_free_used", "dailyFreeUsed", "daily_free_remaining", "dailyFreeRemaining"];
  const legacyDaily = dailyKeys.some((name) => name in raw);
  const legacyValue = dailyKeys.some((name) => pick(raw, name) !== undefined && pick(raw, name) !== null);
  if (period === undefined && legacyDaily) {
    unit = unit ?? "requests";
    period = "day";
  }
  const sourceRaw = pick(raw, "source");
  const source =
    sourceRaw === undefined && period === "day" && legacyValue
      ? "api"
      : choice(sourceRaw, ["api", "headers", "manual", "none"] as const, {}, "none");
  const optProbes = Math.max(0, Math.trunc(optionalNumber(pick(raw, "probes_since_read", "probesSinceRead")) ?? 0));
  return {
    unit: choice(unit, ["requests", "tokens", "credits", "unknown"] as const, QUOTA_UNIT_ALIASES, "unknown"),
    period: choice(period, ["rolling_5h", "week", "day", "total", "beta", "unknown"] as const, QUOTA_PERIOD_ALIASES, "unknown"),
    limit: optionalNumber(pick(raw, "limit", "daily_free_limit", "dailyFreeLimit")),
    used: optionalNumber(pick(raw, "used", "daily_free_used", "dailyFreeUsed")),
    remaining: optionalNumber(pick(raw, "remaining", "daily_free_remaining", "dailyFreeRemaining")),
    resetsAt: stringOrNull(pick(raw, "resets_at", "resetsAt")),
    expiresAt: stringOrNull(pick(raw, "expires_at", "expiresAt")),
    source,
    scope: choice(pick(raw, "scope"), ["account", "model"] as const, {}, "account"),
    ...(optProbes > 0 ? { probesSinceRead: optProbes } : {}),
  };
}

/** Remaining allowance for a fixed window (day/week/rolling); `null` when it cannot be computed. */
export function remainingInWindow(quota: Quota, probesSinceRead = 0): number | null {
  if (!["rolling_5h", "week", "day"].includes(quota.period)) return null;
  const base = quota.remaining ?? (quota.limit === null ? null : Math.max(0, quota.limit - (quota.used ?? 0)));
  if (base === null || quota.source === "manual") return base;
  return Math.max(0, base - Math.max(0, probesSinceRead));
}

/** Remaining daily allowance; `null` for other periods (matches Python's `remaining_today`). */
export function remainingToday(quota: Quota, probesSinceRead = 0): number | null {
  return quota.period === "day" ? remainingInWindow(quota, probesSinceRead) : null;
}

/** Remaining one-off allowance; `null` unless `period` is `total`. */
export function remainingTotal(quota: Quota): number | null {
  if (quota.period !== "total") return null;
  return quota.remaining ?? (quota.limit === null ? null : Math.max(0, quota.limit - (quota.used ?? 0)));
}

/** True only when the quota is known to be used up. */
export function isExhausted(quota: Quota, probesSinceRead = 0): boolean {
  const remaining = remainingInWindow(quota, probesSinceRead) ?? remainingTotal(quota);
  if (remaining !== null) return remaining <= 0;
  return quota.limit !== null && quota.used !== null && quota.used >= quota.limit;
}

/** One free model from a channel's catalogue. */
export interface CatalogModel {
  provider: ChannelId;
  id: string;
  name: string;
  /** Context window in tokens; 0 when the catalogue does not say. */
  contextLength: number;
  /** Tool calling: true/false when the catalogue says, null when it does not (Groq). Kept for old state files. */
  tools: boolean | null;
  /** Accepted inputs as far as the catalogue says (text is always there). */
  input: Array<"text" | "image">;
  /** Largest completion the catalogue reports, if any. */
  maxTokens: number | null;
  /** `YYYY-MM-DD` when the free variant goes away, if announced. */
  expirationDate: string | null;
  /** Capability flags; missing fields in old data are unknown, never false. */
  capabilities: Capabilities;
  /** Model-level quota (e.g. a one-off token allowance); null means not reported. */
  quota: Quota | null;
  /** 1 for an official public API, 2 for a manually registered platform. */
  tier?: number;
}

/** Outcome of one tiny probe request (field meanings as in Python's TestResult). */
export interface ProbeResult {
  /** `"<provider>|<model id>"`, as in the Python cache. */
  key: string;
  ok: boolean;
  ttftMs: number | null;
  totalMs: number | null;
  /** Redacted, at most 200 characters for HTTP errors. */
  error: string | null;
  statusCode: number | null;
  /** Unix seconds. */
  testedAt: number;
  failureKind: FailureKind | null;
  /** Consecutive capacity results; omitted/0 for other outcomes. */
  capacityStreak?: number;
  retryAfterS: number | null;
  rateLimitRemaining: number | null;
}

/** Free-request quota a channel reports for the key (OpenRouter's `/key`). */
export interface QuotaInfo {
  dailyFreeLimit: number | null;
  dailyFreeUsed: number | null;
  dailyFreeRemaining: number | null;
}

export function modelKey(model: Pick<CatalogModel, "provider" | "id">): string {
  return `${model.provider}|${model.id}`;
}

/** Thrown by discovery when the catalogue cannot be read; the message is safe to store. */
export class ChannelError extends Error {
  override name = "ChannelError";
}
