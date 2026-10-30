/**
 * Tier-2 manual registration and opt-in availability probes (plan 6.4).
 *
 * A manual entry only records public facts: a dsh route id, a model id, a
 * label, a hand-written quota note and an expiry date. It never holds a token,
 * PAT, cookie, password or key. Availability is checked only through dsh
 * (`ctx.llm`), so the third-party plugin keeps its own login and state.
 *
 * Probe rules: the global switch AND the entry's `probe` flag must both be on;
 * a model is probed at most once per UTC day (a hard-coded cap, not a setting);
 * an `account` failure stops that platform for the day; a `capacity` failure is
 * recorded but does not stop the platform. Only the six documented fields are
 * ever stored, and error text is redacted and never persisted.
 */
import type { FreemodelConfig, ManualEntryConfig } from "./channels.ts";
import { manualOf, manualProbeOf } from "./channels.ts";
import { redact } from "./redact.ts";
import { isRecord, utcToday } from "./util.ts";

/** Hard-coded ceiling: one request per model per UTC day, never configurable upward. */
export const MANUAL_PROBE_DAILY_LIMIT = 1;
/** Prompt for the single minimal request. */
export const MANUAL_PROBE_PROMPT = "ping";
/** Completion budget for the probe (one token). */
export const MANUAL_PROBE_MAX_TOKENS = 1;

const FORBIDDEN_KEYS = new Set([
  "token",
  "pat",
  "cookie",
  "password",
  "secret",
  "key",
  "apikey",
  "apikeyenv",
  "accesstoken",
  "refreshtoken",
  "clientsecret",
]);

const KEY_LIKE =
  /(?:^|[^A-Za-z0-9])(?:sk-|gsk_|pat_|ghp_|xox[abp]-)[A-Za-z0-9._-]{12,}|bearer\s+[A-Za-z0-9._-]{20,}/i;

const ENTRY_KEYS = new Set(["dshProvider", "model", "label", "quotaNote", "expiresAt", "probe"]);
const PROBE_KEYS = new Set(["enabled"]);

/** One result as stored in `state.manual.probes`; exactly these six fields. */
export interface ManualProbeRecord {
  provider: string;
  model: string;
  ok: boolean;
  failure_kind: "model" | "transient" | "account" | "capacity" | "quota" | null;
  /** Provider/dsh code (e.g. WorkBuddy's 11140); never the error text. */
  error_code: string | null;
  /** Unix seconds. */
  tested_at: number;
}

export interface ManualProbeState {
  probes: Record<string, ManualProbeRecord>;
}

export type ManualProbeRefusal = "disabled" | "probe-off" | "expired" | "platform-stopped" | "daily-limit";

export interface ManualProbeDecision {
  allowed: boolean;
  reason: ManualProbeRefusal | null;
}

/** One row for the settings card / status document. */
export interface ManualEntryView {
  dshProvider: string;
  model: string;
  label: string;
  quotaNote: string;
  expiresAt: string;
  probe: boolean;
  expired: boolean;
  /** null when dsh's provider list is unavailable (the CLI outside dsh). */
  detected: boolean | null;
  lastProbe: ManualProbeRecord | null;
  /** Set when a probe was not run because the route was not registered in dsh. */
  notRunReason?: "route-not-registered" | null;
}

export interface ManualReport {
  enabled: boolean;
  entries: ManualEntryView[];
}

function normaliseKey(name: string): string {
  return name.replace(/[_-]/g, "").toLowerCase();
}

function keyLike(value: string): boolean {
  return KEY_LIKE.test(value);
}

function fail(where: string, message: string): never {
  throw new Error(`dsh-freemodel: ${where}: ${message}`);
}

function checkKeyLikeStrings(value: unknown, where: string): void {
  if (typeof value === "string") {
    if (keyLike(value)) {
      fail(where, "value looks like an API key or token; store it in dsh's credential store, never in manual registration");
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => checkKeyLikeStrings(item, `${where}[${index}]`));
    return;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      if (FORBIDDEN_KEYS.has(normaliseKey(key))) {
        fail(where, `credential-bearing key "${key}" is not allowed; manual entries keep only public facts`);
      }
      checkKeyLikeStrings(item, `${where}.${key}`);
    }
  }
}

function optionalString(raw: Record<string, unknown>, key: string, where: string): string {
  const value = raw[key];
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") fail(`${where}.${key}`, "must be a string");
  return value;
}

function validDate(text: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
  const time = Date.parse(`${text}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === text;
}

/**
 * Validate one `manual[]` entry, rejecting unknown/secret keys and key-shaped
 * values. Returns the normalized entry (defaults filled in).
 * @param raw - one entry from the plugin settings.
 * @param where - path for the error message.
 */
export function validateManualEntry(raw: unknown, where = "manual[0]"): ManualEntryConfig {
  if (!isRecord(raw)) fail(where, "must be an object");
  checkKeyLikeStrings(raw, where);
  for (const key of Object.keys(raw)) {
    if (!ENTRY_KEYS.has(key)) fail(`${where}.${key}`, "unknown field (manual entries allow only public registration facts)");
  }
  const dshProvider = raw.dshProvider;
  if (typeof dshProvider !== "string" || dshProvider.trim() === "") fail(`${where}.dshProvider`, "must be a non-empty string");
  const model = raw.model;
  if (typeof model !== "string" || model.trim() === "") fail(`${where}.model`, "must be a non-empty string");
  const expiresAt = optionalString(raw, "expiresAt", where);
  if (expiresAt !== "" && !validDate(expiresAt)) fail(`${where}.expiresAt`, "must be YYYY-MM-DD or empty");
  const probe = raw.probe;
  if (probe !== undefined && probe !== null && typeof probe !== "boolean") fail(`${where}.probe`, "must be a boolean");
  return {
    dshProvider: dshProvider.trim(),
    model: model.trim(),
    label: optionalString(raw, "label", where),
    quotaNote: optionalString(raw, "quotaNote", where),
    expiresAt,
    probe: probe === true,
  };
}

/** Validate the whole `manual[]` array (default `[]`). */
export function validateManualEntries(raw: unknown, where = "manual"): ManualEntryConfig[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) fail(where, "must be a list of manual entries");
  const entries = raw.map((entry, index) => validateManualEntry(entry, `${where}[${index}]`));
  const seen = new Set<string>();
  for (const entry of entries) {
    const key = `${entry.dshProvider}|${entry.model}`;
    if (seen.has(key)) fail(where, `duplicate entry for ${entry.dshProvider}/${entry.model}`);
    seen.add(key);
  }
  return entries;
}

/** Validate `manual` and `manualProbe` in a raw settings object (schema guard). */
export function validateManualConfig(config: unknown): void {
  if (!isRecord(config)) return;
  if (config.manual !== undefined) validateManualEntries(config.manual);
  if (config.manualProbe === undefined) return;
  const probe = config.manualProbe;
  if (!isRecord(probe)) fail("manualProbe", "must be an object");
  for (const key of Object.keys(probe)) {
    if (!PROBE_KEYS.has(key)) fail(`manualProbe.${key}`, "unknown field");
  }
  if (probe.enabled !== undefined && typeof probe.enabled !== "boolean") fail("manualProbe.enabled", "must be a boolean");
}

/** Current validated manual entries from a settings object. */
export function manualEntriesOf(config: FreemodelConfig): ManualEntryConfig[] {
  return validateManualEntries(manualOf(config));
}

/** True when `expiresAt` is before today (UTC); an empty date never expires. */
export function entryExpired(expiresAt: string, today: string = utcToday()): boolean {
  return expiresAt !== "" && expiresAt < today;
}

/** Stable key for a manual probe record. */
export function manualKey(provider: string, model: string): string {
  return `${provider}|${model}`;
}

function recordDay(record: ManualProbeRecord): string {
  return utcToday(record.tested_at * 1000);
}

/**
 * Decide whether a manual entry may be probed now. This mirrors
 * `freemodel_sync.providers.manual.manual_probe_allowed` and the shared
 * conformance cases.
 * @param entry - one manual registration.
 * @param records - current stored manual probe records.
 * @param enabled - the global `manualProbe.enabled` switch.
 * @param now - current time (defaults to `new Date()`).
 */
export function manualProbeDecision(
  entry: Pick<ManualEntryConfig, "dshProvider" | "model" | "probe" | "expiresAt">,
  records: Iterable<ManualProbeRecord>,
  enabled: boolean,
  now: Date = new Date(),
): ManualProbeDecision {
  if (!enabled) return { allowed: false, reason: "disabled" };
  if (!entry.probe) return { allowed: false, reason: "probe-off" };
  const today = utcToday(now.getTime());
  if (entryExpired(entry.expiresAt, today)) return { allowed: false, reason: "expired" };
  for (const record of records) {
    if (record.provider !== entry.dshProvider || recordDay(record) !== today) continue;
    if (record.failure_kind === "account") return { allowed: false, reason: "platform-stopped" };
    if (record.model === entry.model) return { allowed: false, reason: "daily-limit" };
  }
  return { allowed: true, reason: null };
}

/** dsh failure facts from a terminal `finish` chunk or a thrown error. */
export interface LlmFailureLike {
  readonly code?: string;
  readonly status?: number;
  readonly message?: string;
}

export interface LlmStreamChunkLike {
  readonly type: string;
  readonly text?: string;
  readonly reason?: { readonly kind?: string; readonly failure?: LlmFailureLike };
}

export interface ManualLlm {
  stream(options: {
    provider: string;
    model: string;
    messages: Array<{ role: "user"; content: Array<{ type: "text"; text: string }> }>;
    maxTokens: number;
    signal?: AbortSignal;
  }): AsyncIterable<LlmStreamChunkLike>;
}

/** Map a dsh/provider failure to a stable kind and a non-secret error code. */
export function classifyManualFailure(failure: LlmFailureLike | undefined): {
  failureKind: ManualProbeRecord["failure_kind"];
  errorCode: string | null;
} {
  const code = typeof failure?.code === "string" ? failure.code : "";
  const status = typeof failure?.status === "number" ? failure.status : undefined;
  const message = redact(typeof failure?.message === "string" ? failure.message : "", []);
  const blob = `${code} ${message}`.toLowerCase();
  const errorCode = code !== "" ? code : status !== undefined ? String(status) : null;
  if (status === 401 || status === 402 || status === 403) return { failureKind: "account", errorCode };
  if (/11140|account|unauthori[sz]ed|invalid.{0,12}(key|token)|forbidden|quota|credit|balance|billing|login|session/.test(blob)) {
    return { failureKind: "account", errorCode };
  }
  if (status === 429 || status === 503 || status === 529) return { failureKind: "capacity", errorCode };
  if (/capacity|queue|queued|busy|overload|no capacity|model_busy|modelunavailable|serviceunavailable|rate.?limit/.test(blob)) {
    return { failureKind: "capacity", errorCode };
  }
  if (status !== undefined && status >= 500) return { failureKind: "transient", errorCode };
  return { failureKind: "model", errorCode };
}

/** Detect when dsh/llm reports that no adapter is registered for a provider route. */
export function isNoAdapter(failure: LlmFailureLike | undefined, error?: unknown): boolean {
  if (failure?.code === "NO_ADAPTER" || (typeof failure?.code === "string" && failure.code.toUpperCase() === "NO_ADAPTER")) {
    return true;
  }
  if (error !== undefined && error !== null) {
    const err = error as { code?: unknown; name?: unknown; message?: unknown };
    if (err.code === "NO_ADAPTER" || (typeof err.code === "string" && err.code.toUpperCase() === "NO_ADAPTER")) {
      return true;
    }
    if (err.name === "NO_ADAPTER") return true;
    if (typeof err.message === "string" && (err.message.includes("NO_ADAPTER") || err.message.toLowerCase().includes("no adapter registered"))) {
      return true;
    }
  }
  if (typeof failure?.message === "string" && (failure.message.includes("NO_ADAPTER") || failure.message.toLowerCase().includes("no adapter registered"))) {
    return true;
  }
  return false;
}

/**
 * Send the one minimal request for a manual entry through dsh. Only a finish
 * chunk is inspected; no response text, prompt or key is stored.
 * Returns null if the target adapter route is not registered (NO_ADAPTER) so
 * the attempt is treated as not run and does not consume the daily cap.
 * @param llm - host LLM runtime (`ctx.llm`); never a third-party plugin API.
 * @param entry - validated manual entry.
 * @param now - current time (tests inject it).
 */
export async function probeManualEntry(
  llm: ManualLlm,
  entry: ManualEntryConfig,
  now: Date = new Date(),
): Promise<ManualProbeRecord | null> {
  const testedAt = now.getTime() / 1000;
  let failure: LlmFailureLike | undefined;
  let ok = true;
  let thrownError: unknown;
  try {
    let finished = false;
    for await (const chunk of llm.stream({
      provider: entry.dshProvider,
      model: entry.model,
      messages: [{ role: "user", content: [{ type: "text", text: MANUAL_PROBE_PROMPT }] }],
      maxTokens: MANUAL_PROBE_MAX_TOKENS,
    })) {
      if (chunk.type !== "finish") continue;
      finished = true;
      const kind = chunk.reason?.kind;
      if (kind === "error" || kind === "aborted") {
        ok = false;
        failure = chunk.reason?.failure ?? { code: kind, message: kind };
      }
    }
    if (!finished && ok) {
      // Stream ended without a finish: treat it as a transient transport failure.
      ok = false;
      failure = { code: "no-finish", message: "stream ended without a finish chunk" };
    }
  } catch (error) {
    thrownError = error;
    const e = error as { name?: string; message?: string; code?: string };
    ok = false;
    failure = { code: e?.code ?? e?.name ?? "Error", message: e?.message ?? String(error) };
  }
  if (!ok && isNoAdapter(failure, thrownError)) {
    return null;
  }
  const classified = classifyManualFailure(failure);
  return {
    provider: entry.dshProvider,
    model: entry.model,
    ok,
    failure_kind: ok ? null : classified.failureKind,
    error_code: ok ? null : classified.errorCode,
    tested_at: testedAt,
  };
}

/** Whether a dsh provider route is registered; `null` when the host list is unavailable. */
export function routeDetected(entry: ManualEntryConfig, routes: readonly string[] | null): boolean | null {
  return routes === null ? null : routes.includes(entry.dshProvider);
}

/**
 * Build the settings-card/status view of the manual registry.
 * @param config - validated plugin settings.
 * @param records - stored manual probe records.
 * @param routes - dsh provider route ids, or null outside dsh.
 * @param now - current time.
 */
export function manualReport(
  config: FreemodelConfig,
  records: Record<string, ManualProbeRecord>,
  routes: readonly string[] | null,
  now: Date = new Date(),
): ManualReport {
  const enabled = manualEnabled(config);
  const today = utcToday(now.getTime());
  return {
    enabled,
    entries: manualEntriesOf(config).map((entry) => {
      const detected = routeDetected(entry, routes);
      const lastProbe = records[manualKey(entry.dshProvider, entry.model)] ?? null;
      const notRunReason = lastProbe === null && detected === false ? ("route-not-registered" as const) : null;
      return {
        dshProvider: entry.dshProvider,
        model: entry.model,
        label: entry.label,
        quotaNote: entry.quotaNote,
        expiresAt: entry.expiresAt,
        probe: entry.probe,
        expired: entryExpired(entry.expiresAt, today),
        detected,
        lastProbe,
        ...(notRunReason !== null ? { notRunReason } : {}),
      };
    }),
  };
}

function manualEnabled(config: FreemodelConfig): boolean {
  return manualProbeOf(config).enabled === true;
}