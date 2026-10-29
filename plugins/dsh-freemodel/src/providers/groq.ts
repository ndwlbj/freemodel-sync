/**
 * Groq channel. Groq's catalogue has no prices: models are free only on a
 * Free-plan organization, which the API cannot report, so the plugin lists
 * and probes nothing until the user ticks `freePlanConfirmed` (the caller
 * enforces this). Port of `freemodel_sync.providers.groq`.
 */
import { providerSpec } from "../spec.ts";
import { asInt, type HeaderSource, headerOf, isRecord } from "../util.ts";
import { OpenAICompatChannel } from "./openai-compat.ts";
import { describeError } from "./openrouter.ts";
import { type CatalogModel, ChannelError } from "./types.ts";

interface RateLimitHeaders {
  retryAfter: string;
  reset: string;
  remaining: string;
}

const RL = providerSpec("groq").rateLimitHeaders as RateLimitHeaders;
const UNIT_SECONDS: Record<string, number> = { h: 3600, m: 60, s: 1, ms: 0.001 };
const PLAIN_NUMBER = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

/** Groq reset values such as `"2m59.56s"`, `"7.66s"`, `"120ms"` or plain seconds. */
export function parseDuration(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (text === "") return null;
  if (PLAIN_NUMBER.test(text)) return Math.max(0, Number(text));
  const re = /(\d+(?:\.\d+)?)(ms|h|m|s)/g;
  const parts: Array<[string, string]> = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) parts.push([m[1]!, m[2]!]);
  if (parts.length === 0 || parts.map(([n, u]) => n + u).join("") !== text.replace(/ /g, "")) return null;
  return parts.reduce((sum, [n, u]) => sum + Number(n) * UNIT_SECONDS[u]!, 0);
}

export function groqRateLimitHints(headers: HeaderSource): [number | null, number | null] {
  let retryAfter = parseDuration(headerOf(headers, RL.retryAfter));
  if (retryAfter === null) retryAfter = parseDuration(headerOf(headers, RL.reset));
  return [retryAfter, asInt(headerOf(headers, RL.remaining))];
}

export class GroqChannel extends OpenAICompatChannel {
  readonly id = "groq" as const;

  override rateLimitHints(headers: HeaderSource): [number | null, number | null] {
    return groqRateLimitHints(headers);
  }

  /** Active Groq models; the list needs the key. */
  async discover(apiKey: string | undefined, signal?: AbortSignal): Promise<CatalogModel[]> {
    if (!apiKey) {
      throw new ChannelError(`groq: listing models needs ${providerSpec("groq").apiKeyEnv} (Groq's model list requires a key)`);
    }
    let payload: unknown;
    try {
      payload = await this.getJson(providerSpec("groq").modelsPath, this.authHeaders(apiKey), signal);
    } catch (error) {
      throw new ChannelError(`Groq model list failed: ${describeError(error)}`);
    }
    if (!isRecord(payload) || !Array.isArray(payload.data)) {
      throw new ChannelError("Groq returned an unexpected models payload");
    }
    const models: CatalogModel[] = [];
    for (const raw of payload.data) {
      if (!isRecord(raw)) continue;
      const id = raw.id;
      if (typeof id !== "string" || id === "" || raw.active === false) continue;
      models.push({
        provider: "groq",
        id,
        name: id,
        contextLength: asInt(raw.context_window) ?? 0,
        // Groq's list does not say which models support tools, vision or reasoning.
        tools: null,
        input: ["text"],
        maxTokens: asInt(raw.max_completion_tokens),
        expirationDate: null,
        capabilities: { tools: null, vision: null, reasoning: null, source: "unknown" },
        quota: null,
        tier: 1,
      });
    }
    return models;
  }
}
