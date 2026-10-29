/**
 * Alibaba Cloud Bailian / DashScope channel (Beijing, OpenAI-compatible).
 *
 * The API cannot say which calls are free, so the caller lists nothing until
 * `freeQuotaGuardConfirmed` is ticked and a non-empty model allowlist is
 * configured (same as Python's `free_quota_guard: confirmed` + `models`). Per
 * model allowances are hand-entered and marked manual/unverified. Distilled
 * models are marked `tools: false`. Port of
 * `freemodel_sync.providers.bailian`.
 */
import { providerSpec } from "../spec.ts";
import { asInt, isRecord } from "../util.ts";
import { OpenAICompatChannel, type FetchLike } from "./openai-compat.ts";
import { describeError } from "./openrouter.ts";
import { type Capabilities, type CatalogModel, ChannelError, type Quota, UNKNOWN_CAPABILITIES } from "./types.ts";

export interface BailianLogger {
  warn(message: string, ...args: unknown[]): void;
}

const SPEC = providerSpec("bailian");

/** A hand-entered allowance: one-off tokens, manual and unverified. */
export function manualQuota(limit: number | undefined): Quota {
  if (limit === undefined || !Number.isFinite(limit) || limit <= 0) {
    return { unit: "unknown", period: "total", limit: null, used: null, remaining: null, resetsAt: null, expiresAt: null, source: "manual", scope: "model" };
  }
  return { unit: "tokens", period: "total", limit, used: null, remaining: null, resetsAt: null, expiresAt: null, source: "manual", scope: "model" };
}

/** Distilled variants do not call tools; everything else the catalogue does not say. */
export function bailianCapabilities(id: string): Capabilities {
  return id.toLowerCase().includes("distill")
    ? { tools: false, vision: null, reasoning: null, source: "config" }
    : { ...UNKNOWN_CAPABILITIES };
}

function modelOf(raw: Record<string, unknown> | undefined, id: string, quotaTokens?: number): CatalogModel {
  const data = raw ?? {};
  const capabilities = bailianCapabilities(id);
  return {
    provider: "bailian",
    id,
    name: typeof data.name === "string" && data.name !== "" ? data.name : id,
    contextLength: asInt(data.context_length) ?? asInt(data.context_window) ?? 0,
    tools: capabilities.tools,
    input: ["text"],
    maxTokens: asInt(data.max_tokens) ?? asInt(data.max_completion_tokens),
    expirationDate: null,
    capabilities,
    quota: manualQuota(quotaTokens),
    tier: 1,
  };
}

export class BailianChannel extends OpenAICompatChannel {
  readonly id = "bailian" as const;

  constructor(
    fetchImpl?: FetchLike,
    private readonly logger?: BailianLogger,
  ) {
    super(fetchImpl);
  }

  /**
   * Read the catalogue and keep the configured allowlist order. Without a
   * non-empty allowlist nothing is listed, even if the catalogue is readable.
   */
  async discover(
    apiKey: string | undefined,
    signal?: AbortSignal,
    allowlist?: readonly string[],
    modelQuotas?: Readonly<Record<string, number>>,
  ): Promise<CatalogModel[]> {
    if (allowlist === undefined || allowlist.length === 0) {
      this.logger?.warn("dsh-freemodel: Bailian needs a non-empty models allowlist; nothing is listed");
      return [];
    }
    if (!apiKey) {
      throw new ChannelError(`bailian: listing models needs ${SPEC.apiKeyEnv} (the model list requires a key)`);
    }
    let catalog: Map<string, Record<string, unknown>> | null = null;
    try {
      const payload = await this.getJson(SPEC.modelsPath, this.authHeaders(apiKey), signal);
      if (isRecord(payload) && Array.isArray(payload.data)) {
        catalog = new Map();
        for (const raw of payload.data) {
          if (!isRecord(raw)) continue;
          const id = raw.id;
          if (typeof id === "string" && id !== "") catalog.set(id, raw);
        }
      } else {
        this.logger?.warn("dsh-freemodel: Bailian returned an unexpected models payload; using the configured allowlist");
      }
    } catch (error) {
      this.logger?.warn(
        `dsh-freemodel: Bailian model list failed (${describeError(error)}); using the configured allowlist`,
      );
    }

    const ids = catalog === null ? allowlist : allowlist.filter((id) => catalog?.has(id) === true);
    return ids.map((id) => modelOf(catalog?.get(id), id, modelQuotas?.[id]));
  }
}
