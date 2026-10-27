/**
 * The plugin's state file, `$DSH_HOME/freemodel/state.json` (mode 0600,
 * format: spec/state.schema.json). It caches each channel's catalogue and
 * probe results plus the daily probe counter, so a restart registers models
 * at once and does not spend the free-request budget again. It never holds a
 * key: error texts are redacted before they are stored.
 */
import { chmodSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import type { CatalogModel, ProbeResult } from "./providers/types.ts";
import { CHANNEL_IDS, type ChannelId } from "./spec.ts";
import { isRecord, utcToday } from "./util.ts";

export const STATE_SCHEMA_VERSION = 1;

export interface CatalogState {
  /** Unix seconds of the last successful catalogue read. */
  fetchedAt: number;
  models: CatalogModel[];
  /** Last failed read (redacted); the previous models stay in use. */
  error: string | null;
  errorAt: number | null;
}

export interface RoundState {
  at: number;
  probes: number;
  stopReason: string | null;
}

export interface ChannelStateData {
  catalog: CatalogState | null;
  /** Latest probe result per model key (`"<provider>|<id>"`); account failures are never stored. */
  results: Record<string, ProbeResult>;
  /** Probes sent per UTC day. */
  daily: { date: string; count: number };
  /** Unix seconds until which no probe is sent (after an account-level rate limit). */
  blockedUntil: number | null;
  lastRound: RoundState | null;
}

export interface StateData {
  schemaVersion: number;
  plugin: "dsh-freemodel";
  updatedAt: string;
  channels: Record<ChannelId, ChannelStateData>;
}

export function emptyChannel(): ChannelStateData {
  return { catalog: null, results: {}, daily: { date: utcToday(), count: 0 }, blockedUntil: null, lastRound: null };
}

export function emptyState(): StateData {
  const channels = {} as Record<ChannelId, ChannelStateData>;
  for (const id of CHANNEL_IDS) channels[id] = emptyChannel();
  return { schemaVersion: STATE_SCHEMA_VERSION, plugin: "dsh-freemodel", updatedAt: new Date(0).toISOString(), channels };
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

function readModel(id: ChannelId, raw: unknown): CatalogModel | null {
  if (!isRecord(raw) || typeof raw.id !== "string" || raw.id === "") return null;
  return {
    provider: id,
    id: raw.id,
    name: str(raw.name) ?? raw.id,
    contextLength: num(raw.contextLength) ?? 0,
    tools: typeof raw.tools === "boolean" ? raw.tools : null,
    input: Array.isArray(raw.input) && raw.input.includes("image") ? ["text", "image"] : ["text"],
    maxTokens: num(raw.maxTokens),
    expirationDate: str(raw.expirationDate),
  };
}

const KINDS = new Set(["model", "transient", "account"]);

function readResult(raw: unknown): ProbeResult | null {
  if (!isRecord(raw) || typeof raw.key !== "string" || typeof raw.ok !== "boolean") return null;
  const kind = str(raw.failureKind);
  return {
    key: raw.key,
    ok: raw.ok,
    ttftMs: num(raw.ttftMs),
    totalMs: num(raw.totalMs),
    error: str(raw.error),
    statusCode: num(raw.statusCode),
    testedAt: num(raw.testedAt) ?? 0,
    // Like Python's TestResult.from_dict: a failure without a kind is a model failure.
    failureKind: raw.ok ? null : kind !== null && KINDS.has(kind) ? (kind as ProbeResult["failureKind"]) : "model",
    retryAfterS: num(raw.retryAfterS),
    rateLimitRemaining: num(raw.rateLimitRemaining),
  };
}

function readChannel(id: ChannelId, raw: unknown): ChannelStateData {
  const out = emptyChannel();
  if (!isRecord(raw)) return out;
  if (isRecord(raw.catalog) && Array.isArray(raw.catalog.models)) {
    out.catalog = {
      fetchedAt: num(raw.catalog.fetchedAt) ?? 0,
      models: raw.catalog.models.map((m) => readModel(id, m)).filter((m): m is CatalogModel => m !== null),
      error: str(raw.catalog.error),
      errorAt: num(raw.catalog.errorAt),
    };
  }
  if (isRecord(raw.results)) {
    for (const [key, value] of Object.entries(raw.results)) {
      const result = readResult(value);
      if (result !== null && result.key === key && result.failureKind !== "account") out.results[key] = result;
    }
  }
  if (isRecord(raw.daily) && typeof raw.daily.date === "string") {
    out.daily = { date: raw.daily.date, count: Math.max(0, Math.trunc(num(raw.daily.count) ?? 0)) };
  }
  out.blockedUntil = num(raw.blockedUntil);
  if (isRecord(raw.lastRound)) {
    out.lastRound = {
      at: num(raw.lastRound.at) ?? 0,
      probes: num(raw.lastRound.probes) ?? 0,
      stopReason: str(raw.lastRound.stopReason),
    };
  }
  return out;
}

/** Parse a state document; anything unreadable becomes empty state (never throws). */
export function parseState(text: string): StateData {
  const state = emptyState();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    return state;
  }
  if (!isRecord(payload) || payload.schemaVersion !== STATE_SCHEMA_VERSION || !isRecord(payload.channels)) return state;
  state.updatedAt = str(payload.updatedAt) ?? state.updatedAt;
  for (const id of CHANNEL_IDS) state.channels[id] = readChannel(id, payload.channels[id]);
  return state;
}

/** Read the state file; a missing or corrupt file is empty state. */
export function loadState(path: string): StateData {
  try {
    return parseState(readFileSync(path, "utf8"));
  } catch {
    return emptyState();
  }
}

/** Write the state file atomically with mode 0600 (directory 0700). */
export function saveState(path: string, state: StateData): void {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  state.updatedAt = new Date().toISOString();
  const tmp = `${path}.${process.pid}.${Date.now()}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  try {
    chmodSync(tmp, 0o600);
  } catch {
    // Windows: modes are advisory
  }
  renameSync(tmp, path);
}

/** Probes sent today (UTC). */
export function requestsToday(channel: ChannelStateData, now: number = Date.now()): number {
  return channel.daily.date === utcToday(now) ? channel.daily.count : 0;
}

export function addRequests(channel: ChannelStateData, n: number, now: number = Date.now()): void {
  const today = utcToday(now);
  if (channel.daily.date !== today) channel.daily = { date: today, count: 0 };
  channel.daily.count += Math.max(0, Math.trunc(n));
}

/**
 * A fresh stored result, like Python's `ResultCache.get`: account failures are
 * never trusted; transient failures expire after `transientTtlS`.
 */
export function freshResult(
  channel: ChannelStateData,
  key: string,
  ttlS: number,
  transientTtlS: number | null,
  nowS: number = Date.now() / 1000,
): ProbeResult | null {
  const result = channel.results[key];
  if (result === undefined || (!result.ok && result.failureKind === "account")) return null;
  let ttl = ttlS;
  if (!result.ok && result.failureKind === "transient" && transientTtlS !== null) ttl = Math.min(ttl, transientTtlS);
  return nowS - result.testedAt > ttl ? null : result;
}
