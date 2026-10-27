/**
 * OpenRouter channel: free (`:free`) models from the public catalogue, the
 * probe with OpenRouter's error and rate-limit rules, and the free-request
 * quota of the key. Port of `freemodel_sync.providers.openrouter`.
 */
import { providerSpec } from "../spec.ts";
import { asFloat, asInt, type HeaderSource, headerOf, isRecord } from "../util.ts";
import { HttpStatusError, MAX_RETRY_AFTER_S, OpenAICompatChannel } from "./openai-compat.ts";
import { type CatalogModel, ChannelError, type QuotaInfo } from "./types.ts";

interface RateLimitHeaders {
  retryAfter: string;
  reset: string;
  remaining: string;
  resetFormat: string;
}

const RL = providerSpec("openrouter").rateLimitHeaders as RateLimitHeaders;

/** `expiration_date` as `YYYY-MM-DD`: a date or an ISO-8601 datetime (date part as written). */
export function parseExpirationDate(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (text === "") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:([T ])(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/.exec(text);
  if (m === null) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return null;
  if (m[4] !== undefined && (Number(m[5]) > 23 || Number(m[6]) > 59 || Number(m[7] ?? 0) > 59)) return null;
  return `${m[1]}-${m[2]}-${m[3]}`;
}

/** `pricing.overrides` entries that cost money (a malformed value counts as priced). */
export function pricedOverrides(pricing: Record<string, unknown>): unknown[] {
  const overrides = pricing.overrides;
  if (overrides === undefined || overrides === null) return [];
  if (!Array.isArray(overrides)) return [{ overrides }];
  const priced: unknown[] = [];
  for (const entry of overrides) {
    if (!isRecord(entry)) {
      priced.push({ override: entry });
      continue;
    }
    for (const k of ["prompt", "completion", "request"]) {
      const value = k in entry ? asFloat(entry[k]) : 0;
      if (value === null || value !== 0) {
        priced.push(entry);
        break;
      }
    }
  }
  return priced;
}

/** Every price exactly 0: prompt and completion present, other fields 0 or absent, no priced override. */
export function isFreePricing(pricing: unknown): boolean {
  if (!isRecord(pricing)) return false;
  if (asFloat(pricing.prompt) !== 0 || asFloat(pricing.completion) !== 0) return false;
  for (const [k, value] of Object.entries(pricing)) {
    if (k === "overrides" || value === null || value === undefined) continue;
    if (asFloat(value) !== 0) return false;
  }
  return pricedOverrides(pricing).length === 0;
}

/** Text in and text out (`input_modalities`/`output_modalities`, or the legacy `modality` string). */
export function supportsText(architecture: unknown): boolean {
  if (!isRecord(architecture)) return false;
  const inputs = architecture.input_modalities;
  const outputs = architecture.output_modalities;
  if (Array.isArray(inputs) && Array.isArray(outputs) && inputs.length > 0 && outputs.length > 0) {
    return inputs.includes("text") && outputs.includes("text");
  }
  const modality = architecture.modality;
  if (typeof modality !== "string" || !modality.includes("->")) return false;
  const at = modality.indexOf("->");
  return modality.slice(0, at).split("+").includes("text") && modality.slice(at + 2).split("+").includes("text");
}

/** OpenRouter's free text model: `:free` suffix, not `openrouter/*`, all prices 0, text in and out. */
export function isFreeModel(model: unknown): boolean {
  if (!isRecord(model)) return false;
  const id = model.id;
  if (typeof id !== "string" || id === "") return false;
  if (id.startsWith("openrouter/")) return false;
  if (!id.endsWith(":free")) return false;
  if (!isFreePricing(model.pricing)) return false;
  return supportsText(model.architecture);
}

function contextLength(model: Record<string, unknown>): number {
  const top = isRecord(model.top_provider) ? model.top_provider.context_length : null;
  const value = model.context_length || top || 0;
  return asInt(value) ?? 0;
}

function imageInput(architecture: unknown): boolean {
  if (!isRecord(architecture)) return false;
  const inputs = architecture.input_modalities;
  if (Array.isArray(inputs)) return inputs.includes("image");
  const modality = architecture.modality;
  return typeof modality === "string" && modality.split("->")[0]!.split("+").includes("image");
}

/** `(retry after seconds, remaining)` from OpenRouter's headers (Retry-After, X-RateLimit-Reset). */
export function openRouterRateLimitHints(headers: HeaderSource, nowS: number = Date.now() / 1000): [number | null, number | null] {
  const rawRetry = headerOf(headers, RL.retryAfter);
  const rawReset = headerOf(headers, RL.reset);
  const rawRemaining = headerOf(headers, RL.remaining);
  let retryAfter: number | null = null;
  let remaining: number | null = null;
  if (rawRetry) {
    const v = asFloat(rawRetry);
    retryAfter = v === null ? null : Math.max(0, v);
  }
  if (retryAfter === null && rawReset) {
    const reset = asFloat(rawReset);
    if (reset !== null) {
      if (reset > 1e11) retryAfter = Math.max(0, reset / 1000 - nowS);
      else if (reset > 1e9) retryAfter = Math.max(0, reset - nowS);
      else if (reset > 3600) retryAfter = reset / 1000;
      else retryAfter = Math.max(0, reset);
    }
  }
  if (rawRemaining) remaining = asInt(rawRemaining);
  if (retryAfter !== null && retryAfter > MAX_RETRY_AFTER_S) retryAfter = MAX_RETRY_AFTER_S;
  return [retryAfter, remaining];
}

export class OpenRouterChannel extends OpenAICompatChannel {
  readonly id = "openrouter" as const;

  override rateLimitHints(headers: HeaderSource): [number | null, number | null] {
    return openRouterRateLimitHints(headers);
  }

  override authHeaders(apiKey: string): Record<string, string> {
    return { Authorization: `Bearer ${apiKey}`, "X-Title": "dsh-freemodel" };
  }

  /** The catalogue is public: no key is sent. */
  async discover(_apiKey: string | undefined, signal?: AbortSignal): Promise<CatalogModel[]> {
    let payload: unknown;
    try {
      payload = await this.getJson(providerSpec("openrouter").modelsPath, {}, signal);
    } catch (error) {
      throw new ChannelError(`OpenRouter model discovery failed: ${describeError(error)}`);
    }
    if (!isRecord(payload) || !Array.isArray(payload.data)) {
      throw new ChannelError("OpenRouter returned an unexpected models payload");
    }
    const models: CatalogModel[] = [];
    for (const raw of payload.data) {
      if (!isFreeModel(raw)) continue;
      const entry = raw as Record<string, unknown>;
      const supported = Array.isArray(entry.supported_parameters) ? entry.supported_parameters : [];
      const top = isRecord(entry.top_provider) ? entry.top_provider : {};
      const id = String(entry.id);
      models.push({
        provider: "openrouter",
        id,
        name: String(entry.name || id),
        contextLength: contextLength(entry),
        tools: supported.includes("tools"),
        input: imageInput(entry.architecture) ? ["text", "image"] : ["text"],
        maxTokens: asInt(top.max_completion_tokens),
        expirationDate: parseExpirationDate(entry.expiration_date),
      });
    }
    return models;
  }

  /** `data.free_model_daily_requests` of `GET /key`; null when unavailable. */
  override async quota(apiKey: string, signal?: AbortSignal): Promise<QuotaInfo | null> {
    if (!apiKey) return null;
    let payload: unknown;
    try {
      payload = await this.getJson("/key", this.authHeaders(apiKey), signal);
    } catch {
      return null;
    }
    const data = isRecord(payload) ? payload.data : null;
    if (!isRecord(data)) return null;
    const free = isRecord(data.free_model_daily_requests) ? data.free_model_daily_requests : {};
    return {
      dailyFreeLimit: asInt(free.limit),
      dailyFreeUsed: asInt(free.used),
      dailyFreeRemaining: asInt(free.remaining),
    };
  }
}

export function describeError(error: unknown): string {
  if (error instanceof HttpStatusError) return `HTTP ${error.status}`;
  const e = error as { name?: string; message?: string } | undefined;
  return e?.name === undefined ? String(error) : `${e.name}${e.message ? `: ${e.message}` : ""}`;
}
